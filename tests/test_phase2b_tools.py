import base64
import json
import logging
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
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase2b.db'}"
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


def _sharing(version: str, role: str = "owner", user_id: int = 42) -> dict:
    return {
        "data": {
            "pet_id": 9,
            "pet_name": "Miso",
            "version": version,
            "viewer_permissions": {
                "can_manage_people": role == "owner",
                "is_owner": role == "owner",
                "has_active_relationship": True,
                "private": "omit",
            },
            "relationship_types": [role],
            "relationships": [
                {
                    "relationship_id": 1,
                    "user_id": user_id,
                    "user_name": "Athanasius",
                    "relationship_type": role,
                    "version": version,
                    "email": "never-return@example.test",
                }
            ],
            "created_by": 42,
        }
    }


def _preview(token_version: str, *, valid: bool = True) -> dict:
    return {
        "data": {
            "type": "pet",
            "status": "pending" if valid else "declined",
            "expires_at": "2026-07-21T00:00:00Z",
            "updated_at": token_version,
            "is_valid": valid,
            "is_authenticated": True,
            "is_self_invitation": False,
            "inviter": {"name": "Inviter", "email": "omit@example.test"},
            "target": {"name": "Miso", "role": "viewer", "thumbnail": "omit"},
        }
    }


@pytest.mark.asyncio
async def test_sharing_reads_are_narrow_and_require_sharing_scope(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["sharing:read"])
    token = "A" * 64
    with respx.mock:
        respx.get("https://app.example.com/api/pets/9/sharing").mock(
            return_value=httpx.Response(200, json=_sharing("v1"))
        )
        respx.get("https://app.example.com/api/pets/9/relationship-suggestions").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 7, "name": "Friend", "email": "omit"}]}
            )
        )
        respx.get("https://app.example.com/api/pets/9/invitations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 5,
                            "relationship_type": "viewer",
                            "status": "pending",
                            "expires_at": "2026-07-21T00:00:00Z",
                            "updated_at": "iv1",
                            "invitation_url": f"https://app.example.com/invite/{token}",
                            "token": token,
                        }
                    ]
                },
            )
        )
        respx.post("https://app.example.com/api/mcp/resource-invitations/preview").mock(
            return_value=httpx.Response(200, json=_preview("iv1"))
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=str(settings.public_base_url),
            ) as client,
        ):
            sharing = await _call(client, "get_pet_sharing", {"pet_id": 9})
            suggestions = await _call(client, "list_pet_relationship_suggestions", {"pet_id": 9})
            invitations = await _call(client, "list_pet_invitations", {"pet_id": 9})
            preview = await _call(client, "preview_pet_invitation", {"invitation": token})
            denied = await _call(client, "list_pets", {})

    assert sharing["structuredContent"]["sharing"]["relationships"][0] == {
        "relationship_id": 1,
        "user_id": 42,
        "user_name": "Athanasius",
        "relationship_type": "owner",
        "version": "v1",
    }
    assert suggestions["structuredContent"] == {
        "suggestions": [{"user_id": 7, "user_name": "Friend"}]
    }
    assert invitations["structuredContent"]["invitations"][0]["share_url"].endswith(token)
    assert "token" not in preview["structuredContent"]["invitation"]
    assert denied["isError"] is True
    assert denied["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()


@pytest.mark.asyncio
async def test_add_collaborator_enforces_suggestion_and_verifies_role(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["sharing:read", "sharing:write"])
    with respx.mock:
        sharing_route = respx.get("https://app.example.com/api/pets/9/sharing").mock(
            side_effect=[
                httpx.Response(200, json=_sharing("v1")),
                httpx.Response(200, json=_sharing("v2", "viewer", 7)),
            ]
        )
        respx.get("https://app.example.com/api/pets/9/relationship-suggestions").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 7, "name": "Friend"}]})
        )
        write = respx.post("https://app.example.com/api/pets/9/users").mock(
            return_value=httpx.Response(201, json={"data": {"id": 2}})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=str(settings.public_base_url),
            ) as client,
        ):
            result = await _call(
                client,
                "add_pet_collaborator",
                {
                    "pet_id": 9,
                    "user_id": 7,
                    "relationship_type": "viewer",
                    "sharing_base_version": "v1",
                    "idempotency_key": "share-add-7",
                },
            )

    assert result["structuredContent"]["verified"] is True
    assert result["structuredContent"]["relationship"]["user_id"] == 7
    assert write.calls[0].request.headers["Idempotency-Key"] == "share-add-7"
    assert json.loads(write.calls[0].request.content)["base_version"] == "v1"
    assert sharing_route.call_count == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_invitation_accept_rejects_preview_mismatch_without_writing(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["sharing:read", "sharing:write"])
    token = "B" * 64
    with respx.mock:
        respx.post("https://app.example.com/api/mcp/resource-invitations/preview").mock(
            return_value=httpx.Response(200, json=_preview("iv1"))
        )
        write = respx.post("https://app.example.com/api/mcp/resource-invitations/accept").mock(
            return_value=httpx.Response(200, json={"data": {"pet_id": 9}})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=str(settings.public_base_url),
            ) as client,
        ):
            result = await _call(
                client,
                "accept_pet_invitation",
                {
                    "invitation": token,
                    "expected_pet_name": "Wrong pet",
                    "expected_relationship_type": "viewer",
                    "invitation_base_version": "iv1",
                    "idempotency_key": "invite-accept",
                },
            )

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "invitation_mismatch"
    assert write.call_count == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_invitation_accept_exact_retry_reaches_upstream_idempotency(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["sharing:read", "sharing:write"])
    token = "C" * 64
    with respx.mock:
        preview = respx.post("https://app.example.com/api/mcp/resource-invitations/preview").mock(
            side_effect=[
                httpx.Response(200, json=_preview("iv1")),
                httpx.Response(200, json=_preview("iv2", valid=False)),
            ]
        )
        write = respx.post("https://app.example.com/api/mcp/resource-invitations/accept").mock(
            return_value=httpx.Response(200, json={"data": {"pet_id": 9}})
        )
        respx.get("https://app.example.com/api/pets/9/sharing").mock(
            return_value=httpx.Response(200, json=_sharing("v2", "viewer"))
        )
        arguments = {
            "invitation": token,
            "expected_pet_name": "Miso",
            "expected_relationship_type": "viewer",
            "invitation_base_version": "iv1",
            "idempotency_key": "invite-accept-replay",
        }
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=str(settings.public_base_url),
            ) as client,
        ):
            first = await _call(client, "accept_pet_invitation", arguments)
            replay = await _call(client, "accept_pet_invitation", arguments)

    assert first["structuredContent"]["accepted"] is True
    assert replay["structuredContent"]["accepted"] is True
    assert preview.call_count == 2
    assert write.call_count == 2
    assert all(
        call.request.headers["Idempotency-Key"] == "invite-accept-replay" for call in write.calls
    )
    for call in [*preview.calls, *write.calls]:
        assert token not in str(call.request.url)
        assert json.loads(call.request.content)["token"] == token
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "payload", "expected_code"),
    [
        (409, {"data": {"code": "last_owner_conflict"}}, "last_owner_conflict"),
        (410, {"message": "private invitation state"}, "invitation_inactive"),
    ],
)
async def test_sharing_conflicts_have_stable_codes(
    tmp_path, status: int, payload: dict, expected_code: str
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["sharing:read", "sharing:write"])
    with respx.mock:
        respx.get("https://app.example.com/api/pets/9/sharing").mock(
            return_value=httpx.Response(200, json=_sharing("v1"))
        )
        respx.post("https://app.example.com/api/pets/9/leave").mock(
            return_value=httpx.Response(status, json=payload)
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=str(settings.public_base_url),
            ) as client,
        ):
            result = await _call(
                client,
                "leave_shared_pet",
                {
                    "pet_id": 9,
                    "sharing_base_version": "v1",
                    "expected_relationship_types": ["owner"],
                    "idempotency_key": f"leave-{status}",
                },
            )

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == expected_code
    await engine.dispose()


def test_http_transport_loggers_do_not_emit_invitation_urls() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        token_encryption_key=base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode(),
        meo_connector_hmac_secret="hmac",
        meo_connector_api_key="key",
    )
    create_app(settings)
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


def test_phase2b_scopes_are_advertised_last() -> None:
    assert ALLOWED_SCOPES[8:10] == ["sharing:read", "sharing:write"]
