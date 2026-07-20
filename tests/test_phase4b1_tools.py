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
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase4b1.db'}"
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


def _group(*, members=None, pets=None, name="Care team", version="g1"):
    return {
        "data": {
            "id": 7,
            "name": name,
            "viewer_role": "admin",
            "member_count": len(members or []),
            "pet_count": len(pets or []),
            "members": members or [],
            "pets": pets or [],
            "updated_at": version,
        }
    }


@pytest.mark.asyncio
async def test_create_group_is_idempotent_and_post_write_verified(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read", "groups:write"])
    with respx.mock:
        created = respx.post("https://app.example.com/api/groups").mock(
            return_value=httpx.Response(201, json={"data": {"id": 7}})
        )
        respx.get("https://app.example.com/api/groups/7").mock(
            return_value=httpx.Response(200, json=_group())
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "create_group",
                {
                    "name": "Care team",
                    "pet_ids": [],
                    "idempotency_key": "phase4b1-create",
                },
            )
            replay = await _call(
                client,
                "create_group",
                {
                    "name": "Care team",
                    "pet_ids": [],
                    "idempotency_key": "phase4b1-create",
                },
            )

    assert result["structuredContent"]["group"]["group_id"] == 7
    assert result["structuredContent"]["verified"] is True
    assert replay["structuredContent"]["group"]["group_id"] == 7
    assert created.calls[0].request.headers["Idempotency-Key"] == "phase4b1-create"
    assert created.calls[1].request.headers["Idempotency-Key"] == "phase4b1-create"
    assert created.calls[0].request.content == created.calls[1].request.content
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_group_translates_authoritative_duplicate_candidates(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read", "groups:write"])
    with respx.mock:
        respx.post("https://app.example.com/api/groups").mock(
            return_value=httpx.Response(
                409,
                json={
                    "data": {
                        "code": "duplicate_candidate",
                        "existing_group_ids": [7],
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
                "create_group",
                {
                    "name": "Care team",
                    "pet_ids": [],
                    "idempotency_key": "phase4b1-distinct-create",
                },
            )

    assert duplicate["isError"] is True
    assert duplicate["structuredContent"]["error"]["code"] == "duplicate_candidate"
    assert duplicate["structuredContent"]["error"]["existing_group_ids"] == [7]
    await engine.dispose()


@pytest.mark.asyncio
async def test_group_member_add_requires_fresh_suggestion_and_verifies_role(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read", "groups:write"])
    member = {"user_id": 9, "role": "member", "user": {"id": 9, "name": "B"}}
    with respx.mock:
        detail = respx.get("https://app.example.com/api/groups/7").mock(
            side_effect=[
                httpx.Response(200, json=_group()),
                httpx.Response(200, json=_group(members=[member], version="g2")),
            ]
        )
        respx.get("https://app.example.com/api/groups/7/member-suggestions").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 9, "name": "B"}]})
        )
        added = respx.post("https://app.example.com/api/groups/7/members").mock(
            return_value=httpx.Response(201, json={"data": member})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "add_group_member",
                {
                    "group_id": 7,
                    "user_id": 9,
                    "role": "member",
                    "base_version": "g1",
                    "idempotency_key": "phase4b1-member",
                },
            )

    assert detail.call_count == 2
    assert added.calls[0].request.content
    assert result["structuredContent"]["member"]["role"] == "member"
    await engine.dispose()


@pytest.mark.asyncio
async def test_group_pet_removal_matches_name_and_verifies_absence(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read", "groups:write"])
    pet = {"id": 4, "name": "Miso", "pet_type": {"id": 1, "name": "Cat"}}
    with respx.mock:
        respx.get("https://app.example.com/api/groups/7").mock(
            side_effect=[
                httpx.Response(200, json=_group(pets=[pet])),
                httpx.Response(200, json=_group(version="g2")),
            ]
        )
        removed = respx.delete("https://app.example.com/api/groups/7/pets/4").mock(
            return_value=httpx.Response(204)
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "remove_group_pet",
                {
                    "group_id": 7,
                    "pet_id": 4,
                    "expected_pet_name": "Miso",
                    "base_version": "g1",
                    "idempotency_key": "phase4b1-pet",
                },
            )

    assert b'"base_version":"g1"' in removed.calls[0].request.content
    assert result["structuredContent"]["removed"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_group_invitation_accept_uses_body_token_and_verifies_access(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read", "groups:write"])
    token = "A" * 64
    preview = {
        "data": {
            "status": "pending",
            "is_valid": True,
            "is_authenticated": True,
            "is_self_invitation": False,
            "updated_at": "iv1",
            "inviter": {"name": "A"},
            "target": {"group_id": 7, "name": "Care team", "role": "member"},
        }
    }
    with respx.mock:
        previewed = respx.post("https://app.example.com/api/mcp/group-invitations/preview").mock(
            return_value=httpx.Response(200, json=preview)
        )
        accepted = respx.post("https://app.example.com/api/mcp/group-invitations/accept").mock(
            return_value=httpx.Response(200, json={"data": {"group_id": 7, "role": "member"}})
        )
        respx.get("https://app.example.com/api/groups/7").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        **_group()["data"],
                        "viewer_role": "member",
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
                "accept_group_invitation",
                {
                    "invitation": token,
                    "expected_group_name": "Care team",
                    "expected_role": "member",
                    "invitation_base_version": "iv1",
                    "idempotency_key": "phase4b1-accept",
                },
            )

    assert token not in str(previewed.calls[0].request.url)
    assert token not in str(accepted.calls[0].request.url)
    assert token.encode() in previewed.calls[0].request.content
    assert result["structuredContent"]["accepted"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_groups_write_scope_is_independent(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["groups:read"])
    with respx.mock:
        respx.get("https://app.example.com/api/groups").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "create_group",
                {"name": "Care team", "pet_ids": [], "idempotency_key": "scope"},
            )

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()
