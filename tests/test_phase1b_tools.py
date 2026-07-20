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


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / ('writes-' + '-'.join(scopes) + '.db')}"
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


def _pet(version: str, name: str = "Miso") -> dict:
    return {
        "data": {
            "id": 9,
            "name": name,
            "pet_type": {"name": "Cat"},
            "country": "VN",
            "updated_at": version,
        }
    }


def _weight(version: str, value: float = 4.2) -> dict:
    return {
        "data": {
            "id": 21,
            "weight_kg": value,
            "record_date": "2026-07-20",
            "updated_at": version,
        }
    }


def _vaccination(version: str, notes: str = "first") -> dict:
    return {
        "data": {
            "id": 31,
            "vaccine_name": "Rabies",
            "administered_at": "2026-07-20",
            "due_at": "2027-07-20",
            "notes": notes,
            "updated_at": version,
        }
    }


def _medical(version: str, description: str = "check") -> dict:
    return {
        "data": {
            "id": 41,
            "record_type": "checkup",
            "record_date": "2026-07-20",
            "description": description,
            "vet_name": "Clinic",
            "updated_at": version,
        }
    }


@pytest.mark.asyncio
async def test_phase1b_writes_cross_asgi_boundary_with_readback(tmp_path) -> None:
    scopes = ["pets:read", "health:read", "pets:write", "health:write"]
    app, engine, settings = await _app_with_token(tmp_path, scopes)
    v1 = "2026-07-20T00:00:00.000000Z"
    v2 = "2026-07-20T00:00:01.000000Z"
    with respx.mock:
        respx.get("https://app.example.com/api/pet-types").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 1, "name": "Cat", "slug": "cat"}]}
            )
        )
        pet_post = respx.post("https://app.example.com/api/pets").mock(
            return_value=httpx.Response(201, json={"data": {"id": 9}})
        )
        respx.get("https://app.example.com/api/pets/9").mock(
            side_effect=[
                httpx.Response(200, json=_pet(v1)),
                httpx.Response(200, json=_pet(v1)),
                httpx.Response(200, json=_pet(v2, "Miso Two")),
            ]
        )
        pet_put = respx.put("https://app.example.com/api/pets/9").mock(
            return_value=httpx.Response(200, json=_pet(v2, "Miso Two"))
        )

        weight_post = respx.post("https://app.example.com/api/pets/9/weights").mock(
            return_value=httpx.Response(201, json={"data": {"id": 21}})
        )
        respx.get("https://app.example.com/api/pets/9/weights/21").mock(
            side_effect=[
                httpx.Response(200, json=_weight(v1)),
                httpx.Response(200, json=_weight(v1)),
                httpx.Response(200, json=_weight(v2, 4.3)),
            ]
        )
        weight_put = respx.put("https://app.example.com/api/pets/9/weights/21").mock(
            return_value=httpx.Response(200, json=_weight(v2, 4.3))
        )

        vaccination_post = respx.post("https://app.example.com/api/pets/9/vaccinations").mock(
            return_value=httpx.Response(201, json={"data": {"id": 31}})
        )
        respx.get("https://app.example.com/api/pets/9/vaccinations/31").mock(
            side_effect=[
                httpx.Response(200, json=_vaccination(v1)),
                httpx.Response(200, json=_vaccination(v1)),
                httpx.Response(200, json=_vaccination(v2, "corrected")),
            ]
        )
        vaccination_put = respx.put("https://app.example.com/api/pets/9/vaccinations/31").mock(
            return_value=httpx.Response(200, json=_vaccination(v2, "corrected"))
        )

        medical_post = respx.post("https://app.example.com/api/pets/9/medical-records").mock(
            return_value=httpx.Response(201, json={"data": {"id": 41}})
        )
        respx.get("https://app.example.com/api/pets/9/medical-records/41").mock(
            side_effect=[
                httpx.Response(200, json=_medical(v1)),
                httpx.Response(200, json=_medical(v1)),
                httpx.Response(200, json=_medical(v2, "corrected")),
            ]
        )
        medical_put = respx.put("https://app.example.com/api/pets/9/medical-records/41").mock(
            return_value=httpx.Response(200, json=_medical(v2, "corrected"))
        )

        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            results = [
                await _call(
                    client,
                    "create_pet",
                    {
                        "name": "Miso",
                        "species": "cat",
                        "country": "vn",
                        "idempotency_key": "pet-create-1",
                    },
                ),
                await _call(
                    client,
                    "update_pet",
                    {
                        "pet_id": 9,
                        "base_version": v1,
                        "idempotency_key": "pet-update-1",
                        "name": "Miso Two",
                    },
                ),
                await _call(
                    client,
                    "add_weight",
                    {
                        "pet_id": 9,
                        "weight_kg": 4.2,
                        "record_date": "2026-07-20",
                        "idempotency_key": "weight-create-1",
                    },
                ),
                await _call(
                    client,
                    "update_weight",
                    {
                        "pet_id": 9,
                        "weight_id": 21,
                        "base_version": v1,
                        "idempotency_key": "weight-update-1",
                        "weight_kg": 4.3,
                    },
                ),
                await _call(
                    client,
                    "add_vaccination",
                    {
                        "pet_id": 9,
                        "vaccine_name": "Rabies",
                        "administered_at": "2026-07-20",
                        "due_at": "2027-07-20",
                        "idempotency_key": "vaccination-create-1",
                    },
                ),
                await _call(
                    client,
                    "update_vaccination",
                    {
                        "pet_id": 9,
                        "vaccination_id": 31,
                        "base_version": v1,
                        "idempotency_key": "vaccination-update-1",
                        "notes": "corrected",
                    },
                ),
                await _call(
                    client,
                    "add_medical_record",
                    {
                        "pet_id": 9,
                        "record_type": "checkup",
                        "record_date": "2026-07-20",
                        "idempotency_key": "medical-create-1",
                        "description": "check",
                    },
                ),
                await _call(
                    client,
                    "update_medical_record",
                    {
                        "pet_id": 9,
                        "record_id": 41,
                        "base_version": v1,
                        "idempotency_key": "medical-update-1",
                        "description": "corrected",
                    },
                ),
            ]

    assert all(result["isError"] is False for result in results)
    assert all(result["structuredContent"]["verified"] is True for result in results)
    for route in (
        pet_post,
        pet_put,
        weight_post,
        weight_put,
        vaccination_post,
        vaccination_put,
        medical_post,
        medical_put,
    ):
        assert route.calls[0].request.headers["Authorization"] == "Bearer delegated"
        assert route.calls[0].request.headers["Idempotency-Key"]
    assert json.loads(pet_post.calls[0].request.content) == {
        "name": "Miso",
        "pet_type_id": 1,
        "country": "VN",
        "allow_duplicate": False,
    }
    assert json.loads(pet_put.calls[0].request.content) == {
        "name": "Miso Two",
        "base_version": v1,
    }
    assert json.loads(weight_put.calls[0].request.content)["base_version"] == v1
    assert json.loads(vaccination_put.calls[0].request.content)["base_version"] == v1
    assert json.loads(medical_put.calls[0].request.content)["base_version"] == v1
    await engine.dispose()


@pytest.mark.asyncio
async def test_write_scope_duplicate_and_validation_controls_are_structured(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read"])
    with respx.mock:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            scope_error = await _call(
                client,
                "add_weight",
                {
                    "pet_id": 9,
                    "weight_kg": 4.2,
                    "record_date": "2026-07-20",
                    "idempotency_key": "weight-create-1",
                },
            )
            key_error = await _call(
                client,
                "add_weight",
                {
                    "pet_id": 9,
                    "weight_kg": 4.2,
                    "record_date": "2026-07-20",
                    "idempotency_key": "not valid",
                },
            )
    assert scope_error["structuredContent"]["error"]["code"] == "scope_required"
    assert key_error["structuredContent"]["error"]["code"] == "validation_error"
    await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_pet_and_stale_update_are_rejected_by_meo(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    current_version = "2026-07-20T00:00:02.000000Z"
    with respx.mock:
        respx.get("https://app.example.com/api/pet-types").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 1, "name": "Cat", "slug": "cat"}]}
            )
        )
        blocked_post = respx.post("https://app.example.com/api/pets").mock(
            return_value=httpx.Response(
                409,
                json={
                    "data": {"existing_pet_ids": [9]},
                    "message": "private duplicate details",
                },
            )
        )
        respx.get("https://app.example.com/api/pets/9").mock(
            return_value=httpx.Response(200, json=_pet(current_version))
        )
        blocked_put = respx.put("https://app.example.com/api/pets/9").mock(
            return_value=httpx.Response(
                409,
                json={"data": {"server_version": current_version, "server_value": "private"}},
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
                "create_pet",
                {
                    "name": "miso",
                    "species": "CAT",
                    "country": "VN",
                    "idempotency_key": "pet-create-duplicate",
                },
            )
            stale = await _call(
                client,
                "update_pet",
                {
                    "pet_id": 9,
                    "base_version": "stale-version",
                    "idempotency_key": "pet-update-stale",
                    "name": "Other",
                },
            )
    assert duplicate["structuredContent"]["error"]["code"] == "duplicate_candidate"
    assert duplicate["structuredContent"]["error"]["existing_pet_ids"] == [9]
    assert stale["structuredContent"]["error"]["code"] == "concurrency_conflict"
    assert "private duplicate details" not in str(duplicate)
    assert "server_value" not in str(stale)
    assert blocked_post.called
    assert blocked_put.called
    await engine.dispose()


@pytest.mark.asyncio
async def test_exact_update_retry_reaches_meo_idempotency_before_version_check(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:read", "health:write"])
    old_version = "2026-07-20T00:00:00.000000Z"
    current_version = "2026-07-20T00:00:01.000000Z"
    with respx.mock:
        respx.get("https://app.example.com/api/pets/9/weights/21").mock(
            side_effect=[
                httpx.Response(200, json=_weight(current_version, 4.3)),
                httpx.Response(200, json=_weight(current_version, 4.3)),
            ]
        )
        replay = respx.put("https://app.example.com/api/pets/9/weights/21").mock(
            return_value=httpx.Response(200, json=_weight(current_version, 4.3))
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "update_weight",
                {
                    "pet_id": 9,
                    "weight_id": 21,
                    "base_version": old_version,
                    "idempotency_key": "weight-update-retry",
                    "weight_kg": 4.3,
                },
            )
    assert result["isError"] is False
    assert result["structuredContent"]["verified"] is True
    assert replay.called
    assert json.loads(replay.calls[0].request.content)["base_version"] == old_version
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "payload", "expected_code", "retryable"),
    [
        (422, {"message": "private details"}, "upstream_validation_failed", False),
        (409, {"data": {"server_version": "new"}}, "concurrency_conflict", False),
        (409, {"message": "conflict"}, "idempotency_conflict", False),
        (425, {"message": "pending"}, "idempotency_in_progress", True),
        (503, {"message": "private outage"}, "upstream_server_error", True),
    ],
)
async def test_upstream_write_conflicts_are_stable_and_redacted(
    tmp_path, status, payload, expected_code, retryable
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:read", "health:write"])
    with respx.mock:
        respx.post("https://app.example.com/api/pets/9/weights").mock(
            return_value=httpx.Response(status, json=payload)
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "add_weight",
                {
                    "pet_id": 9,
                    "weight_kg": 4.2,
                    "record_date": "2026-07-20",
                    "idempotency_key": "weight-conflict-1",
                },
            )
    error = result["structuredContent"]["error"]
    assert error["code"] == expected_code
    assert error["retryable"] is retryable
    assert "server_version" not in str(result)
    assert "private details" not in str(result)
    assert "private outage" not in str(result)
    await engine.dispose()


@pytest.mark.asyncio
async def test_successful_write_with_failed_readback_has_uncertain_outcome(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:read", "health:write"])
    with respx.mock:
        respx.post("https://app.example.com/api/pets/9/weights").mock(
            return_value=httpx.Response(201, json={"data": {"id": 21}})
        )
        respx.get("https://app.example.com/api/pets/9/weights/21").mock(
            return_value=httpx.Response(503, json={"message": "private outage"})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "add_weight",
                {
                    "pet_id": 9,
                    "weight_kg": 4.2,
                    "record_date": "2026-07-20",
                    "idempotency_key": "weight-uncertain-1",
                },
            )
    error = result["structuredContent"]["error"]
    assert error["code"] == "post_write_verification_failed"
    assert error["retryable"] is True
    assert "private outage" not in str(result)
    await engine.dispose()
