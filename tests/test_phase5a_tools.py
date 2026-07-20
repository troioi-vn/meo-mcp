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
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase5a.db'}"
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


def _pet(*, status="active", version="p1", categories=None):
    return {
        "data": {
            "id": 7,
            "name": "Mochi",
            "status": status,
            "pet_type": {"id": 1, "name": "Cat"},
            "categories": categories or [],
            "updated_at": version,
        }
    }


@pytest.mark.asyncio
async def test_pet_categories_status_and_delete_are_verified(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    category = {
        "id": 4,
        "name": "Indoor",
        "slug": "indoor",
        "pet_type_id": 1,
        "approved_at": None,
        "updated_at": "c1",
    }
    with respx.mock:
        respx.get("https://app.example.com/api/categories").mock(
            side_effect=[
                httpx.Response(200, json={"data": [category]}),
                httpx.Response(200, json={"data": [category]}),
            ]
        )
        category_write = respx.post("https://app.example.com/api/categories").mock(
            return_value=httpx.Response(201, json={"data": category})
        )
        respx.get("https://app.example.com/api/pets/7").mock(
            side_effect=[
                httpx.Response(200, json=_pet()),
                httpx.Response(200, json=_pet(status="lost", version="p2")),
                httpx.Response(200, json=_pet(status="lost", version="p2")),
            ]
        )
        status_write = respx.put("https://app.example.com/api/pets/7/status").mock(
            return_value=httpx.Response(200, json=_pet(status="lost", version="p2"))
        )
        delete_write = respx.delete("https://app.example.com/api/pets/7").mock(
            return_value=httpx.Response(204)
        )
        respx.get("https://app.example.com/api/my-pets").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            listed = await _call(client, "list_pet_categories", {"pet_type_id": 1})
            created = await _call(
                client,
                "create_pet_category",
                {"name": "Indoor", "pet_type_id": 1, "idempotency_key": "category-one"},
            )
            changed = await _call(
                client,
                "update_pet_status",
                {
                    "pet_id": 7,
                    "status": "lost",
                    "expected_name": "Mochi",
                    "expected_status": "active",
                    "base_version": "p1",
                    "idempotency_key": "status-one",
                },
            )
            deleted = await _call(
                client,
                "delete_pet",
                {
                    "pet_id": 7,
                    "expected_name": "Mochi",
                    "expected_status": "lost",
                    "base_version": "p2",
                    "idempotency_key": "delete-one",
                },
            )

    assert listed["structuredContent"]["categories"][0]["category_id"] == 4
    assert created["structuredContent"]["verified"] is True
    assert changed["structuredContent"]["pet"]["status"] == "lost"
    assert deleted["structuredContent"] == {"pet_id": 7, "deleted": True, "verified": True}
    assert category_write.calls[0].request.headers["Idempotency-Key"] == "category-one"
    assert b'"expected_name":"Mochi"' in status_write.calls[0].request.content
    assert b'"expected_status":"lost"' in delete_write.calls[0].request.content
    await engine.dispose()


@pytest.mark.asyncio
async def test_category_assignment_city_and_locale_use_narrow_scopes(tmp_path) -> None:
    scopes = [
        "pets:read",
        "pets:write",
        "helpers:read",
        "helpers:write",
        "profile:read",
        "profile:write",
    ]
    app, engine, settings = await _app_with_token(tmp_path, scopes)
    city = {
        "id": 9,
        "name": "Da Lat",
        "country": "VN",
        "approved_at": "2026-07-21T00:00:00Z",
        "updated_at": "ct1",
    }
    profile = {"data": {"id": 42, "name": "A", "locale": "en", "updated_at": "u1"}}
    with respx.mock:
        pet_read = respx.get("https://app.example.com/api/pets/7").mock(
            side_effect=[
                httpx.Response(200, json=_pet()),
                httpx.Response(200, json=_pet(categories=[{"id": 4, "name": "Indoor"}])),
            ]
        )
        pet_write = respx.put("https://app.example.com/api/pets/7").mock(
            return_value=httpx.Response(200, json=_pet())
        )
        city_write = respx.post("https://app.example.com/api/cities").mock(
            return_value=httpx.Response(201, json={"data": city})
        )
        respx.get("https://app.example.com/api/cities").mock(
            return_value=httpx.Response(200, json={"data": [city]})
        )
        profile_read = respx.get("https://app.example.com/api/users/me").mock(
            side_effect=[
                httpx.Response(200, json=profile),
                httpx.Response(
                    200,
                    json={"data": {"id": 42, "name": "A", "locale": "vi", "updated_at": "u2"}},
                ),
            ]
        )
        respx.get("https://app.example.com/api/locale").mock(
            return_value=httpx.Response(
                200, json={"data": {"current": "en", "supported": ["en", "vi"]}}
            )
        )
        locale_write = respx.put("https://app.example.com/api/user/locale").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            assigned = await _call(
                client,
                "update_pet",
                {
                    "pet_id": 7,
                    "base_version": "p1",
                    "idempotency_key": "pet-category",
                    "category_ids": [4],
                },
            )
            created_city = await _call(
                client,
                "create_helper_city_option",
                {"name": "Da Lat", "country": "VN", "idempotency_key": "city-one"},
            )
            changed_locale = await _call(
                client,
                "update_my_locale",
                {"locale": "vi", "base_version": "u1", "idempotency_key": "locale-one"},
            )

    assert assigned["structuredContent"]["pet"]["categories"][0]["category_id"] == 4
    assert created_city["structuredContent"]["city"]["city_id"] == 9
    assert changed_locale["structuredContent"]["profile"]["locale"] == "vi"
    assert b'"category_ids":[4]' in pet_write.calls[0].request.content
    assert city_write.calls[0].request.headers["Idempotency-Key"] == "city-one"
    assert b'"base_version":"u1"' in locale_write.calls[0].request.content
    assert len(pet_read.calls) == 2
    assert len(profile_read.calls) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase_five_tools_require_both_read_and_write_scopes(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:write"])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
        ) as client,
    ):
        result = await _call(
            client,
            "create_pet_category",
            {"name": "Indoor", "pet_type_id": 1, "idempotency_key": "category-one"},
        )
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()
