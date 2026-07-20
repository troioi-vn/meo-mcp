import base64
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import respx

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.oauth import ALLOWED_SCOPES
from meo_mcp.security import TokenCipher, digest, now


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase4b2.db'}"
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


def _ledger(*, title="MCP ledger", version="l1", archived_at=None, can_delete=True):
    return {
        "data": {
            "id": 11,
            "title": title,
            "currency_code": "VND",
            "archived_at": archived_at,
            "can_delete": can_delete,
            "updated_at": version,
            "member_count": 1,
            "pet_count": 0,
        }
    }


@pytest.mark.asyncio
async def test_create_ledger_is_idempotent_and_post_write_verified(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read", "finance:write"])
    with respx.mock:
        created = respx.post("https://app.example.com/api/ledgers").mock(
            return_value=httpx.Response(201, json={"data": {"id": 11}})
        )
        for path in (
            "/api/ledgers/11",
            "/api/ledgers/11/dashboard",
            "/api/ledgers/11/accounts",
            "/api/ledgers/11/categories",
            "/api/ledgers/11/members",
            "/api/ledgers/11/pets",
        ):
            if path.endswith("/dashboard"):
                respx.get(f"https://app.example.com{path}").mock(
                    return_value=httpx.Response(200, json={"data": {}})
                )
            elif path.endswith(("/accounts", "/categories", "/members", "/pets")):
                respx.get(f"https://app.example.com{path}").mock(
                    return_value=httpx.Response(200, json={"data": []})
                )
            else:
                respx.get(f"https://app.example.com{path}").mock(
                    return_value=httpx.Response(200, json=_ledger())
                )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "create_ledger",
                {
                    "title": "MCP ledger",
                    "currency_code": "VND",
                    "idempotency_key": "phase4b2-create",
                },
            )
            replay = await _call(
                client,
                "create_ledger",
                {
                    "title": "MCP ledger",
                    "currency_code": "VND",
                    "idempotency_key": "phase4b2-create",
                },
            )

    assert result["structuredContent"]["ledger"]["ledger_id"] == 11
    assert result["structuredContent"]["verified"] is True
    assert replay["structuredContent"]["ledger"]["ledger_id"] == 11
    assert created.calls[0].request.headers["Idempotency-Key"] == "phase4b2-create"
    assert created.calls[1].request.headers["Idempotency-Key"] == "phase4b2-create"
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_ledger_translates_authoritative_duplicate_candidates(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read", "finance:write"])
    with respx.mock:
        respx.post("https://app.example.com/api/ledgers").mock(
            return_value=httpx.Response(
                409,
                json={
                    "data": {
                        "code": "duplicate_candidate",
                        "existing_ledger_ids": [11],
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
            duplicate = await _call(
                client,
                "create_ledger",
                {
                    "title": "MCP ledger",
                    "currency_code": "VND",
                    "idempotency_key": "phase4b2-distinct-create",
                },
            )

    assert duplicate["isError"] is True
    assert duplicate["structuredContent"]["error"]["code"] == "duplicate_candidate"
    assert duplicate["structuredContent"]["error"]["existing_ledger_ids"] == [11]
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_ledger_rejects_stale_version_conflict(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read", "finance:write"])
    with respx.mock:
        for path in (
            "/api/ledgers/11",
            "/api/ledgers/11/dashboard",
            "/api/ledgers/11/accounts",
            "/api/ledgers/11/categories",
            "/api/ledgers/11/members",
            "/api/ledgers/11/pets",
        ):
            if path.endswith("/dashboard"):
                respx.get(f"https://app.example.com{path}").mock(
                    return_value=httpx.Response(200, json={"data": {}})
                )
            elif path.endswith(("/accounts", "/categories", "/members", "/pets")):
                respx.get(f"https://app.example.com{path}").mock(
                    return_value=httpx.Response(200, json={"data": []})
                )
            else:
                respx.get(f"https://app.example.com{path}").mock(
                    return_value=httpx.Response(200, json=_ledger())
                )
        respx.put("https://app.example.com/api/ledgers/11").mock(
            return_value=httpx.Response(
                409,
                json={
                    "data": {
                        "server_version": "l2",
                        "client_base_version": "l1",
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
            stale = await _call(
                client,
                "update_ledger",
                {
                    "ledger_id": 11,
                    "base_version": "l1",
                    "title": "Renamed",
                    "idempotency_key": "phase4b2-stale",
                },
            )

    assert stale["isError"] is True
    assert stale["structuredContent"]["error"]["code"] == "concurrency_conflict"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ledger_invitation_preview_keeps_token_in_body(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read"])
    token = "A" * 64
    with respx.mock:
        preview = respx.post("https://app.example.com/api/mcp/ledger-invitations/preview").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "is_valid": True,
                        "updated_at": "inv1",
                        "target": {
                            "ledger_id": 11,
                            "name": "MCP ledger",
                            "role": "member",
                            "currency_code": "VND",
                        },
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
            result = await _call(client, "preview_ledger_invitation", {"invitation": token})

    assert result["structuredContent"]["invitation"]["ledger_id"] == 11
    assert result["structuredContent"]["invitation"]["ledger_title"] == "MCP ledger"
    assert preview.calls[0].request.url.path.endswith("/api/mcp/ledger-invitations/preview")
    assert token.encode() in preview.calls[0].request.content
    assert token not in str(preview.calls[0].request.url)
    await engine.dispose()


@pytest.mark.asyncio
async def test_finance_write_scope_is_required(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["finance:read"])
    with respx.mock:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            denied = await _call(
                client,
                "create_ledger",
                {
                    "title": "MCP ledger",
                    "currency_code": "VND",
                    "idempotency_key": "phase4b2-denied",
                },
            )

    assert denied["isError"] is True
    assert denied["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()


def test_finance_write_scope_is_advertised() -> None:
    assert "finance:write" in ALLOWED_SCOPES
    assert ALLOWED_SCOPES.index("finance:write") == ALLOWED_SCOPES.index("finance:read") + 1
