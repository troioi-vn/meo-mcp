import base64
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import respx

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.security import TokenCipher, digest, now

BASE = "https://app.example.com/api"


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'litters.db'}"
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


def _litter(members: list[dict] | None = None, name: str = "Spring 2026") -> dict:
    return {
        "data": {
            "id": 3,
            "name": name,
            "updated_at": "v1",
            "pet_type": {"name": "Cat"},
            "pets": members
            if members is not None
            else [
                {"id": 7, "name": "Miso", "pet_type": {"name": "Cat"}},
                {"id": 8, "name": "Pepper", "pet_type": {"name": "Cat"}},
            ],
        }
    }


async def _client(app, settings):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
    )


@pytest.mark.asyncio
async def test_create_litter_sends_members_and_verifies_by_reading_back(tmp_path) -> None:
    """One call creates the litter and every member pet, so the read-back is
    the only thing that proves what was actually created."""
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    with respx.mock:
        created = respx.post(f"{BASE}/litters").mock(
            return_value=httpx.Response(201, json=_litter())
        )
        respx.get(f"{BASE}/litters/3").mock(return_value=httpx.Response(200, json=_litter()))
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "create_litter",
                {
                    "pet_type_id": 1,
                    "country": "VN",
                    "members": [{"name": "Miso", "sex": "female"}, {"sex": "male"}],
                    "idempotency_key": str(uuid4()),
                    "name": "Spring 2026",
                },
            )

    assert result["isError"] is False, result
    body = json.loads(created.calls[0].request.content)
    assert body["members"] == [{"name": "Miso", "sex": "female"}, {"sex": "male"}]
    assert body["country"] == "VN"
    litter = result["structuredContent"]["litter"]
    assert litter["litter_id"] == 3
    assert litter["member_count"] == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_separating_the_second_to_last_member_reports_the_litter_dissolved(
    tmp_path,
) -> None:
    """Meo dissolves a litter that drops below two members, so the follow-up
    read is a 404 on the happy path rather than a failure."""
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    with respx.mock:
        detail = respx.get(f"{BASE}/litters/3")
        detail.side_effect = [
            httpx.Response(200, json=_litter()),
            httpx.Response(404, json={"message": "Not found."}),
        ]
        respx.delete(f"{BASE}/litters/3/members/8").mock(return_value=httpx.Response(204))
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "separate_pet_from_litter",
                {
                    "litter_id": 3,
                    "pet_id": 8,
                    "expected_litter_name": "Spring 2026",
                    "base_version": "v1",
                    "idempotency_key": str(uuid4()),
                },
            )

    assert result["isError"] is False, result
    assert result["structuredContent"] == {
        "litter": None,
        "litter_dissolved": True,
        "verified": True,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_split_up_sends_no_base_version_and_verifies_absence(tmp_path) -> None:
    """Upstream runs no version check on this route; inventing one here would
    reject writes Meo accepts."""
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    with respx.mock:
        detail = respx.get(f"{BASE}/litters/3")
        detail.side_effect = [
            httpx.Response(200, json=_litter()),
            httpx.Response(404, json={"message": "Not found."}),
        ]
        split = respx.post(f"{BASE}/litters/3/split-up").mock(return_value=httpx.Response(204))
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "split_up_litter",
                {
                    "litter_id": 3,
                    "expected_litter_name": "Spring 2026",
                    "idempotency_key": str(uuid4()),
                },
            )

    assert result["isError"] is False, result
    assert not split.calls[0].request.content
    assert result["structuredContent"]["split_up"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_wrong_expected_name_refuses_before_any_write(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    with respx.mock:
        respx.get(f"{BASE}/litters/3").mock(return_value=httpx.Response(200, json=_litter()))
        renamed = respx.put(f"{BASE}/litters/3").mock(return_value=httpx.Response(200))
        async with app.router.lifespan_context(app), await _client(app, settings) as client:
            result = await _call(
                client,
                "rename_litter",
                {
                    "litter_id": 3,
                    "name": "Autumn 2026",
                    "expected_current_name": "Not The Litter",
                    "base_version": "v1",
                    "idempotency_key": str(uuid4()),
                },
            )

    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["code"] == "target_mismatch"
    assert not renamed.called
    await engine.dispose()
