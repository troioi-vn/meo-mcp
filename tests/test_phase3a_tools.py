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
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase3a.db'}"
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
async def test_placement_reads_filter_and_narrow_without_cross_domain_scope(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["placement:read"])
    with respx.mock:
        upstream = respx.get("https://app.example.com/api/pets/placement-requests").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 9,
                            "name": "Miso",
                            "pet_type": {"id": 2, "name": "Cat", "internal": "omit"},
                            "country": "VN",
                            "city": {"name": "Hanoi", "postal": "omit"},
                            "owner_email": "omit@example.test",
                            "placement_requests": [
                                {
                                    "id": 4,
                                    "pet_id": 9,
                                    "request_type": "foster_free",
                                    "status": "open",
                                    "notes": "Needs care",
                                    "secret": "omit",
                                },
                                {"id": 5, "request_type": "permanent", "status": "closed"},
                            ],
                        }
                    ]
                },
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "list_placement_opportunities",
                {"request_type": "foster_free", "country": "vn", "city": "han"},
            )
            denied = await _call(client, "search_helper_profiles", {})

    assert upstream.called
    assert result["structuredContent"] == {
        "opportunities": [
            {
                "pet_id": 9,
                "pet_name": "Miso",
                "pet_type_id": 2,
                "species": "Cat",
                "photo_url": None,
                "country": "VN",
                "state": None,
                "city": "Hanoi",
                "requests": [
                    {
                        "placement_request_id": 4,
                        "pet_id": 9,
                        "request_type": "foster_free",
                        "status": "open",
                        "notes": "Needs care",
                        "notes_locale": None,
                        "expires_at": None,
                        "start_date": None,
                        "end_date": None,
                        "response_count": None,
                        "notes_translation": None,
                        "pet": None,
                        "owner": None,
                        "version": None,
                    }
                ],
            }
        ]
    }
    assert denied["isError"] is True
    assert denied["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()


@pytest.mark.asyncio
async def test_helper_public_and_private_profiles_have_distinct_privacy_shapes(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["helpers:read"])
    raw = {
        "id": 7,
        "user_id": 42,
        "user": {"id": 42, "name": "Helper", "email": "omit@example.test"},
        "country": "VN",
        "address": "Private street",
        "zip_code": "10000",
        "phone_number": "+84000",
        "contact_details": [{"type": "telegram", "value": "private"}],
        "experience": "Cats",
        "request_types": ["foster_free"],
        "approval_status": "approved",
        "updated_at": "v1",
    }
    with respx.mock:
        respx.get("https://app.example.com/api/helpers").mock(
            return_value=httpx.Response(200, json={"data": [raw]})
        )
        respx.get("https://app.example.com/api/helper-profiles/7").mock(
            return_value=httpx.Response(200, json={"data": raw})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            public = await _call(client, "search_helper_profiles", {})
            private = await _call(client, "get_helper_profile", {"helper_profile_id": 7})

    public_profile = public["structuredContent"]["helper_profiles"][0]
    assert "address" not in public_profile
    assert "phone_number" not in public_profile
    assert "contact_details" not in public_profile
    assert "email" not in str(public_profile)
    private_profile = private["structuredContent"]["helper_profile"]
    assert private_profile["address"] == "Private street"
    assert private_profile["contact_details"] == [{"type": "telegram", "value": "private"}]
    assert "email" not in str(private_profile)
    await engine.dispose()


@pytest.mark.asyncio
async def test_message_reads_are_narrow_paginated_and_do_not_mark_read(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["messages:read"])
    with respx.mock:
        messages = respx.get("https://app.example.com/api/msg/chats/3/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "data": [
                            {
                                "id": 11,
                                "chat_id": 3,
                                "sender": {
                                    "id": 8,
                                    "name": "Friend",
                                    "email": "omit@example.test",
                                },
                                "type": "text",
                                "content": "Hello",
                                "is_mine": False,
                                "created_at": "2026-07-20T00:00:00Z",
                                "internal": "omit",
                            }
                        ],
                        "meta": {
                            "has_more": True,
                            "next_cursor": "next",
                            "counterparty_read_at": None,
                        },
                    }
                },
            )
        )
        unread = respx.get("https://app.example.com/api/msg/unread-count").mock(
            return_value=httpx.Response(200, json={"data": {"unread_message_count": 2}})
        )
        mark_read = respx.post("https://app.example.com/api/msg/chats/3/read").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client, "list_chat_messages", {"chat_id": 3, "cursor": "cursor", "limit": 20}
            )
            count = await _call(client, "get_unread_message_count", {})

    assert dict(messages.calls[0].request.url.params) == {"limit": "20", "cursor": "cursor"}
    assert result["structuredContent"] == {
        "messages": [
            {
                "message_id": 11,
                "chat_id": 3,
                "sender": {"user_id": 8, "user_name": "Friend", "avatar_url": None},
                "type": "text",
                "content": "Hello",
                "is_mine": False,
                "created_at": "2026-07-20T00:00:00Z",
                "version": None,
            }
        ],
        "pagination": {"has_more": True, "next_cursor": "next"},
        "counterparty_read_at": None,
    }
    assert count["structuredContent"] == {"unread_message_count": 2}
    assert unread.called
    assert not mark_read.called
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase3a_validation_and_malformed_unread_are_structured(tmp_path) -> None:
    app, engine, settings = await _app_with_token(
        tmp_path, ["placement:read", "helpers:read", "messages:read"]
    )
    with respx.mock:
        respx.get("https://app.example.com/api/msg/unread-count").mock(
            return_value=httpx.Response(200, json={"data": {"unread_message_count": -1}})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            invalid_country = await _call(
                client, "list_placement_opportunities", {"country": "USA"}
            )
            invalid_location = await _call(
                client, "list_helper_location_options", {"search": "Han"}
            )
            malformed = await _call(client, "get_unread_message_count", {})

    assert invalid_country["structuredContent"]["error"]["code"] == "validation_error"
    assert invalid_location["structuredContent"]["error"]["code"] == "validation_error"
    assert malformed["structuredContent"]["error"] == {
        "code": "upstream_malformed",
        "message": "Meo returned a malformed unread count.",
        "retryable": True,
    }
    await engine.dispose()
