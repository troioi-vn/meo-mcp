import base64
from datetime import timedelta
from ipaddress import ip_address
from uuid import uuid4

import httpx
import pytest
import respx

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.meo_api import MeoApi
from meo_mcp.security import TokenCipher, digest, now


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase3b.db'}"
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
async def test_create_placement_request_is_replay_keyed_and_verified(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["placement:read", "placement:write"])
    request = {
        "id": 7,
        "pet_id": 4,
        "request_type": "foster_free",
        "status": "open",
        "start_date": "2026-07-21",
        "updated_at": "v1",
        "pet": {"id": 4, "name": "Miso"},
    }
    with respx.mock:
        created = respx.post("https://app.example.com/api/placement-requests").mock(
            return_value=httpx.Response(201, json={"data": {**request, "pet": None}})
        )
        respx.get("https://app.example.com/api/placement-requests/7").mock(
            return_value=httpx.Response(200, json={"data": request})
        )
        respx.get("https://app.example.com/api/placement-requests/7/me").mock(
            return_value=httpx.Response(
                200, json={"data": {"viewer_role": "owner", "available_actions": {}}}
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
                "create_placement_request",
                {
                    "pet_id": 4,
                    "expected_pet_name": "Miso",
                    "request_type": "foster_free",
                    "start_date": "2026-07-21",
                    "idempotency_key": "placement-create-1",
                },
            )
    assert result["structuredContent"]["placement_request"]["placement_request_id"] == 7
    assert result["structuredContent"]["verified"] is True
    assert created.calls[0].request.headers["Idempotency-Key"] == "placement-create-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_helper_profile_requires_independent_read_and_write_scopes(tmp_path) -> None:
    scopes = ["helpers:read", "helpers:write"]
    app, engine, settings = await _app_with_token(tmp_path, scopes)
    profile = {
        "id": 9,
        "user_id": 42,
        "user": {"id": 42, "name": "Helper"},
        "country": "VN",
        "cities": [{"id": 2, "name": "Hanoi", "country": "VN"}],
        "experience": "Cats",
        "has_pets": False,
        "has_children": False,
        "request_types": ["foster_free"],
        "status": "private",
        "updated_at": "v1",
    }
    with respx.mock:
        respx.post("https://app.example.com/api/helper-profiles").mock(
            return_value=httpx.Response(201, json={"data": profile})
        )
        respx.get("https://app.example.com/api/helper-profiles/9").mock(
            return_value=httpx.Response(200, json={"data": profile})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "create_helper_profile",
                {
                    "country": "VN",
                    "city_ids": [2],
                    "phone_number": "+84 1",
                    "experience": "Cats",
                    "has_pets": False,
                    "has_children": False,
                    "request_types": ["foster_free"],
                    "idempotency_key": "helper-create-1",
                },
            )
    assert result["structuredContent"]["helper_profile"]["helper_profile_id"] == 9
    assert result["structuredContent"]["verified"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_helper_profile_exact_retry_verifies_existing_postcondition(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["helpers:read", "helpers:write"])

    def profile(version: str, offer: str) -> dict:
        return {
            "id": 9,
            "user_id": 42,
            "user": {"id": 42, "name": "Helper"},
            "country": "VN",
            "cities": [{"id": 2, "name": "Hanoi", "country": "VN"}],
            "experience": "Cats",
            "offer": offer,
            "has_pets": False,
            "has_children": False,
            "request_types": ["foster_free"],
            "status": "private",
            "updated_at": version,
        }

    with respx.mock:
        respx.get("https://app.example.com/api/helper-profiles/9").mock(
            side_effect=[
                httpx.Response(200, json={"data": profile("v1", "Old")}),
                httpx.Response(200, json={"data": profile("v2", "New")}),
                httpx.Response(200, json={"data": profile("v2", "New")}),
                httpx.Response(200, json={"data": profile("v2", "New")}),
            ]
        )
        updated = respx.put("https://app.example.com/api/helper-profiles/9").mock(
            return_value=httpx.Response(200, json={"data": profile("v2", "New")})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            arguments = {
                "helper_profile_id": 9,
                "base_version": "v1",
                "idempotency_key": "helper-update-1",
                "offer": "New",
            }
            first = await _call(client, "update_helper_profile", arguments)
            replay = await _call(client, "update_helper_profile", arguments)
    assert first["structuredContent"]["verified"] is True
    assert replay["structuredContent"]["verified"] is True
    assert len(updated.calls) == 2
    assert all(
        call.request.headers["Idempotency-Key"] == "helper-update-1" for call in updated.calls
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_helper_photo_upload_exact_retry_uses_authority_photo_id(
    tmp_path, monkeypatch
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["helpers:read", "helpers:write"])
    photo = {
        "id": 81,
        "url": "https://cdn.example/photo.jpg",
        "thumb_url": None,
        "medium_url": None,
        "is_primary": True,
    }

    def profile(version: str, photos: list[dict]) -> dict:
        return {
            "id": 9,
            "user_id": 42,
            "user": {"id": 42, "name": "Helper"},
            "country": "VN",
            "cities": [{"id": 2, "name": "Hanoi", "country": "VN"}],
            "experience": "Cats",
            "has_pets": False,
            "has_children": False,
            "request_types": ["foster_free"],
            "photos": photos,
            "status": "private",
            "updated_at": version,
        }

    async def public_addresses(_: str):
        return {ip_address("93.184.216.34")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(public_addresses))
    with respx.mock:
        respx.get("https://93.184.216.34/image").mock(
            return_value=httpx.Response(
                200, content=b"safe-image", headers={"Content-Type": "image/jpeg"}
            )
        )
        respx.get("https://app.example.com/api/helper-profiles/9").mock(
            side_effect=[
                httpx.Response(200, json={"data": profile("v1", [])}),
                httpx.Response(200, json={"data": profile("v2", [photo])}),
                httpx.Response(200, json={"data": profile("v2", [photo])}),
                httpx.Response(200, json={"data": profile("v2", [photo])}),
            ]
        )
        upload = respx.post("https://app.example.com/api/helper-profiles/9").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        **profile("v2", [photo]),
                        "uploaded_photo_ids": [81],
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
            arguments = {
                "helper_profile_id": 9,
                "base_version": "v1",
                "source_url": "https://images.example/image",
                "idempotency_key": "helper-photo-1",
            }
            first = await _call(client, "upload_helper_profile_photo_from_url", arguments)
            replay = await _call(client, "upload_helper_profile_photo_from_url", arguments)
    assert first["structuredContent"]["photo"]["id"] == 81
    assert replay["structuredContent"]["photo"]["id"] == 81
    assert len(upload.calls) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_send_message_previews_exact_recipient_and_returns_narrow_message(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["messages:read", "messages:write"])
    chat = {
        "id": 3,
        "type": "direct",
        "participants": [{"id": 8, "name": "Friend"}],
        "updated_at": "v1",
    }
    with respx.mock:
        respx.get("https://app.example.com/api/msg/chats/3").mock(
            return_value=httpx.Response(200, json={"data": chat})
        )
        sent = respx.post("https://app.example.com/api/msg/chats/3/messages").mock(
            return_value=httpx.Response(
                201,
                json={
                    "data": {
                        "id": 11,
                        "chat_id": 3,
                        "sender": {"id": 42, "name": "Me"},
                        "type": "text",
                        "content": "Hello",
                        "is_mine": True,
                        "created_at": "now",
                    }
                },
            )
        )
        respx.get("https://app.example.com/api/msg/chats/3/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "data": [
                            {
                                "id": 11,
                                "chat_id": 3,
                                "sender": {"id": 42, "name": "Me"},
                                "type": "text",
                                "content": "Hello",
                                "is_mine": True,
                                "created_at": "now",
                                "updated_at": "v1",
                            }
                        ],
                        "meta": {"has_more": False, "next_cursor": None},
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
            result = await _call(
                client,
                "send_chat_message",
                {
                    "chat_id": 3,
                    "expected_recipient_user_id": 8,
                    "content": "Hello",
                    "idempotency_key": "message-send-1",
                },
            )
    assert result["structuredContent"]["message"]["message_id"] == 11
    assert result["structuredContent"]["message"]["is_mine"] is True
    assert sent.calls[0].request.headers["Idempotency-Key"] == "message-send-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_send_message_fails_when_post_write_read_cannot_find_it(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["messages:read", "messages:write"])
    chat = {
        "id": 3,
        "type": "direct",
        "participants": [{"id": 8, "name": "Friend"}],
        "updated_at": "v1",
    }
    with respx.mock:
        respx.get("https://app.example.com/api/msg/chats/3").mock(
            return_value=httpx.Response(200, json={"data": chat})
        )
        respx.post("https://app.example.com/api/msg/chats/3/messages").mock(
            return_value=httpx.Response(
                201,
                json={
                    "data": {
                        "id": 11,
                        "chat_id": 3,
                        "sender": {"id": 42, "name": "Me"},
                        "type": "text",
                        "content": "Hello",
                        "is_mine": True,
                        "created_at": "now",
                    }
                },
            )
        )
        respx.get("https://app.example.com/api/msg/chats/3/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "data": [],
                        "meta": {"has_more": False, "next_cursor": None},
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
            result = await _call(
                client,
                "send_chat_message",
                {
                    "chat_id": 3,
                    "expected_recipient_user_id": 8,
                    "content": "Hello",
                    "idempotency_key": "message-send-unverified",
                },
            )
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "post_write_verification_failed"
    await engine.dispose()
