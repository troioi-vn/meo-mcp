import base64
from datetime import timedelta
from unittest.mock import AsyncMock
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
    database_url = f"sqlite+aiosqlite:///{tmp_path / ('-'.join(scopes) + '.db')}"
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
        headers={"Authorization": "Bearer access", "Accept": "application/json, text/event-stream"},
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
async def test_phase1a_pet_and_health_tools_cross_asgi_boundary(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "health:read"])
    list_envelope = {
        "data": {
            "data": [],
            "meta": {"current_page": 1, "last_page": 1, "per_page": 25, "total": 0},
        }
    }
    with respx.mock:
        respx.get("https://app.example.com/api/my-pets").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 7, "name": "Miso", "pet_type": {"name": "Cat"}}]}
            )
        )
        respx.get("https://app.example.com/api/pets/7").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 7,
                        "name": "Miso",
                        "pet_type": {"name": "Cat"},
                        "private": "omit",
                    }
                },
            )
        )
        respx.get("https://app.example.com/api/pet-types").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 1, "name": "Cat", "slug": "cat", "secret": "omit"}]}
            )
        )
        respx.get("https://app.example.com/api/pets/7/weights").mock(
            return_value=httpx.Response(200, json=list_envelope)
        )
        respx.get("https://app.example.com/api/pets/7/weights/2").mock(
            return_value=httpx.Response(
                200, json={"data": {"id": 2, "weight": 4.5, "date": "2026-01-01", "secret": "omit"}}
            )
        )
        respx.get("https://app.example.com/api/pets/7/vaccinations").mock(
            return_value=httpx.Response(200, json=list_envelope)
        )
        respx.get("https://app.example.com/api/pets/7/vaccinations/3").mock(
            return_value=httpx.Response(
                200, json={"data": {"id": 3, "vaccine_name": "Rabies", "secret": "omit"}}
            )
        )
        respx.get("https://app.example.com/api/pets/7/medical-records").mock(
            return_value=httpx.Response(200, json=list_envelope)
        )
        respx.get("https://app.example.com/api/pets/7/medical-records/4").mock(
            return_value=httpx.Response(
                200, json={"data": {"id": 4, "record_type": "checkup", "secret": "omit"}}
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            results = {
                "find": await _call(client, "find_pets", {"name": "mis"}),
                "pet": await _call(client, "get_pet", {"pet_id": 7}),
                "types": await _call(client, "list_pet_types", {}),
                "weights": await _call(client, "list_weights", {"pet_id": 7}),
                "weight": await _call(client, "get_weight", {"pet_id": 7, "weight_id": 2}),
                "vaccinations": await _call(
                    client, "list_vaccinations", {"pet_id": 7, "status": "all"}
                ),
                "vaccination": await _call(
                    client, "get_vaccination", {"pet_id": 7, "vaccination_id": 3}
                ),
                "medical": await _call(client, "list_medical_records", {"pet_id": 7}),
                "record": await _call(client, "get_medical_record", {"pet_id": 7, "record_id": 4}),
                "overview": await _call(client, "get_pets_overview", {}),
            }
    assert all(not result.get("isError", False) for result in results.values())
    assert results["find"]["structuredContent"]["candidates"][0]["id"] == 7
    assert "private" not in results["pet"]["structuredContent"]["pet"]
    assert "secret" not in results["types"]["structuredContent"]["pet_types"][0]
    assert results["weight"]["structuredContent"]["weight"] == {
        "id": 2,
        "weight_kg": 4.5,
        "record_date": "2026-01-01",
        "version": None,
    }
    assert results["vaccination"]["structuredContent"]["vaccination"]["vaccine_name"] == "Rabies"
    assert results["record"]["structuredContent"]["medical_record"]["record_type"] == "checkup"
    assert results["overview"]["structuredContent"]["pets"][0]["name"] == "Miso"
    await engine.dispose()


@pytest.mark.asyncio
async def test_tool_scope_validation_and_upstream_error_are_structured(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read"])
    with respx.mock:
        respx.get("https://app.example.com/api/pets/7").mock(
            return_value=httpx.Response(422, json={"message": "private upstream validation"})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            missing_scope = await _call(client, "list_weights", {"pet_id": 7})
            invalid = await _call(client, "get_pet", {"pet_id": 0})
            upstream = await _call(client, "get_pet", {"pet_id": 7})
    assert missing_scope["structuredContent"]["error"]["code"] == "scope_required"
    assert invalid["structuredContent"]["error"]["code"] == "validation_error"
    assert upstream["structuredContent"]["error"]["code"] == "upstream_validation_failed"
    assert "private upstream validation" not in str(upstream)
    await engine.dispose()


@pytest.mark.asyncio
async def test_overview_keeps_partial_health_results_and_sorts(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'overview.db'}"
    settings = Settings(
        database_url=database_url,
        token_encryption_key=base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode(),
        meo_connector_hmac_secret="hmac",
        meo_connector_api_key="key",
    )
    _, sessions = make_session_factory(database_url)
    api = MeoApi(sessions, settings)
    api._delegated_token = AsyncMock(return_value="delegated")
    api.list_pets = AsyncMock(
        return_value={"pets": [{"id": 2, "name": "Zed"}, {"id": 1, "name": "Amy"}]}
    )
    api.get_pet = AsyncMock(
        side_effect=lambda pet_id: {"pet": {"id": pet_id, "birthday_month": 12, "birthday_day": 1}}
    )
    api.list_vaccinations = AsyncMock(side_effect=[{"vaccinations": []}, RuntimeError("upstream")])
    api.list_weights = AsyncMock(side_effect=[{"weights": [{"id": 9}]}, {"weights": []}])

    result = await api.get_pets_overview(sort_by="name")

    assert [pet["name"] for pet in result["pets"]] == ["Amy", "Zed"]
    by_id = {pet["id"]: pet for pet in result["pets"]}
    assert by_id[2]["vaccination_data_status"] == "available"
    assert by_id[1]["vaccination_data_status"] == "unavailable"
    assert by_id[2]["recent_weights"] == [{"id": 9}]
