import base64
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import respx

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.security import TokenCipher, digest, now


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase4a.db'}"
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    settings = Settings(
        database_url=database_url,
        token_encryption_key=key,
        meo_connector_hmac_secret="hmac",
        meo_connector_api_key="key",
    )
    engine, sessions = make_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    grant = Grant(
        id=uuid4(),
        client_id="client",
        subject="42",
        scopes=scopes,
        delegated_token_ciphertext=TokenCipher(key).encrypt("delegated"),
        expires_at=now() + timedelta(days=1),
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        session.add(
            AccessTokenRecord(
                token_hash=digest("access"),
                grant_id=grant.id,
                client_id="client",
                scopes=scopes,
                subject="42",
                resource=settings.resource,
                expires_at=now() + timedelta(hours=1),
            )
        )
        await session.commit()
    return create_app(settings), engine, settings


async def _call(client: httpx.AsyncClient, name: str, arguments: dict):
    response = await client.post(
        "/mcp",
        headers={"Authorization": "Bearer access", "Accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


@pytest.mark.asyncio
async def test_group_reads_are_narrowed_and_versioned(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read"])
    with respx.mock:
        respx.get("https://app.example.com/api/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 7,
                            "name": "Care team",
                            "viewer_role": "admin",
                            "member_count": 2,
                            "pet_count": 1,
                            "secret": "omit",
                        }
                    ]
                },
            )
        )
        respx.get("https://app.example.com/api/groups/7").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 7,
                        "name": "Care team",
                        "viewer_role": "admin",
                        "member_count": 1,
                        "pet_count": 1,
                        "updated_at": "v1",
                        "members": [
                            {
                                "user_id": 42,
                                "role": "admin",
                                "start_at": "2026-07-20T00:00:00Z",
                                "user": {"id": 42, "name": "A", "email": "omit@example.test"},
                            }
                        ],
                        "pets": [
                            {
                                "id": 4,
                                "name": "Miso",
                                "photo_url": "https://cdn.example/miso.jpg",
                                "pet_type": {"id": 1, "name": "Cat"},
                            }
                        ],
                    }
                },
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            listed = await _call(client, "list_groups", {})
            detail = await _call(client, "get_group_overview", {"group_id": 7})

    assert listed["structuredContent"]["groups"][0]["group_id"] == 7
    group = detail["structuredContent"]["group"]
    assert group["version"] == "v1"
    assert group["members"][0] == {
        "user_id": 42,
        "user_name": "A",
        "role": "admin",
        "start_at": "2026-07-20T00:00:00Z",
    }
    assert "email" not in str(group)
    assert "secret" not in str(listed["structuredContent"])
    await engine.dispose()


@pytest.mark.asyncio
async def test_finance_overview_and_filtered_transactions_are_narrowed(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read"])
    transaction = {
        "id": 19,
        "ledger_id": 3,
        "account_id": 5,
        "account_name": "Cash",
        "category_id": 6,
        "category_name": "Vet",
        "type": "expense",
        "amount_minor": 1250,
        "amount": "12.50",
        "occurred_on": "2026-07-20",
        "description": "Checkup",
        "created_by": {"id": 42, "name": "A", "email": "omit@example.test"},
        "pets": [{"id": 4, "name": "Miso", "name_snapshot": "Miso"}],
        "has_receipt": True,
        "updated_at": "tv1",
        "secret": "omit",
    }
    with respx.mock:
        respx.get("https://app.example.com/api/ledgers/3").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 3,
                        "title": "Household",
                        "currency_code": "USD",
                        "currency": {
                            "code": "USD",
                            "name": "US dollar",
                            "symbol": "$",
                            "minor_units": 2,
                        },
                        "member_count": 1,
                        "pet_count": 1,
                    }
                },
            )
        )
        respx.get("https://app.example.com/api/ledgers/3/dashboard").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "current_month": {"income": 0, "expense": 1250, "net_activity": -1250},
                        "previous_month": {"income": 0, "expense": 0},
                        "accounts": [],
                        "spending_by_category": [],
                        "income_by_category": [],
                        "spending_by_pet": [],
                        "monthly_trend": [],
                        "recent_transactions": [transaction],
                    }
                },
            )
        )
        for path, data in {
            "accounts": [{"id": 5, "name": "Cash", "income_minor": 0, "expense_minor": 1250}],
            "categories": [{"id": 6, "name": "Vet", "applies_to": "expense"}],
            "members": [{"user_id": 42, "name": "A"}],
            "pets": [{"id": 4, "name": "Miso", "sources": ["manual"]}],
        }.items():
            respx.get(f"https://app.example.com/api/ledgers/3/{path}").mock(
                return_value=httpx.Response(200, json={"data": data})
            )
        transactions = respx.get("https://app.example.com/api/ledgers/3/transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "items": [transaction],
                        "current_page": 1,
                        "last_page": 1,
                        "per_page": 10,
                        "total": 1,
                    }
                },
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            overview = await _call(client, "get_ledger_overview", {"ledger_id": 3})
            listed = await _call(
                client,
                "list_ledger_transactions",
                {
                    "ledger_id": 3,
                    "per_page": 10,
                    "transaction_type": "expense",
                    "pet_id": 4,
                },
            )

    assert overview["structuredContent"]["dashboard"]["current_month"]["expense"] == 1250
    item = listed["structuredContent"]["transactions"][0]
    assert item["transaction_id"] == 19
    assert item["version"] == "tv1"
    assert item["has_receipt"] is True
    assert "email" not in str(item)
    assert "secret" not in str(item)
    assert transactions.calls[0].request.url.params["type"] == "expense"
    assert transactions.calls[0].request.url.params["pet_id"] == "4"
    await engine.dispose()


@pytest.mark.asyncio
async def test_notification_and_profile_reads_drop_unsafe_or_internal_fields(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["notifications:read", "profile:read"])
    with respx.mock:
        respx.get("https://app.example.com/api/notifications/unified").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "bell_notifications": [
                            {
                                "id": "n1",
                                "level": "info",
                                "title": "Update",
                                "body": "Ready",
                                "url": "https://evil.example/path",
                                "actions": [{"key": "view", "label": "View", "handler": "omit"}],
                                "created_at": "2026-07-20T00:00:00Z",
                                "read_at": None,
                            }
                        ],
                        "unread_bell_count": 1,
                        "unread_message_count": 2,
                    }
                },
            )
        )
        respx.get("https://app.example.com/api/users/me").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 42,
                        "name": "A",
                        "email": "a@example.test",
                        "locale": "en",
                        "avatar_url": "https://cdn.example/a.jpg",
                        "has_password": True,
                        "roles": ["admin"],
                        "can_access_admin": True,
                        "remember_token": "omit",
                        "updated_at": "pv1",
                    }
                },
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            inbox = await _call(client, "get_notification_inbox", {})
            profile = await _call(client, "get_my_profile", {})

    notification = inbox["structuredContent"]["notifications"][0]
    assert notification["url"] is None
    assert notification["actions"] == [{"key": "view", "label": "View", "style": None}]
    narrowed = profile["structuredContent"]["profile"]
    assert narrowed["version"] == "pv1"
    assert "roles" not in narrowed
    assert "admin" not in str(narrowed)
    assert "remember_token" not in str(narrowed)
    await engine.dispose()


@pytest.mark.asyncio
async def test_owner_weight_and_account_invitation_reads_are_bounded(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["profile:read", "invitations:read"])
    with respx.mock:
        respx.get("https://app.example.com/api/users/me/owner-weights").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "data": [
                            {
                                "id": 8,
                                "weight_kg": "70.5",
                                "record_date": "2026-07-20",
                                "notes": "Morning",
                                "updated_at": "wv1",
                            }
                        ],
                        "meta": {
                            "current_page": 1,
                            "last_page": 1,
                            "per_page": 25,
                            "total": 1,
                        },
                    }
                },
            )
        )
        respx.get("https://app.example.com/api/invitations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 9,
                            "code": "BEARER",
                            "status": "pending",
                            "invitation_url": "https://app.example.test/invite/BEARER",
                            "recipient": {
                                "id": 5,
                                "name": "B",
                                "email": "b@example.test",
                                "secret": "omit",
                            },
                        }
                    ]
                },
            )
        )
        respx.get("https://app.example.com/api/invitations/stats").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "total": 1,
                        "pending": 1,
                        "accepted": 0,
                        "expired": 0,
                        "revoked": 0,
                    }
                },
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            weights = await _call(client, "list_owner_weights", {"page": 1})
            invitations = await _call(client, "get_account_invitation_summary", {})

    assert weights["structuredContent"]["weights"][0]["version"] == "wv1"
    assert weights["structuredContent"]["pagination"]["total"] == 1
    assert invitations["structuredContent"]["counts"]["pending"] == 1
    assert "secret" not in str(invitations["structuredContent"])
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase4a_read_scopes_are_independent(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read"])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
        ) as client,
    ):
        result = await _call(client, "list_currencies", {})

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()
