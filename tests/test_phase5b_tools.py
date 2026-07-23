import base64
import json
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
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase5b.db'}"
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


def _weight(version="w1"):
    return {
        "data": {
            "id": 21,
            "weight_kg": "4.20",
            "record_date": "2026-07-21T00:00:00.000000Z",
            "updated_at": version,
        }
    }


def _vaccination(
    vaccination_id=31,
    *,
    version="v1",
    name="Core",
    administered="2026-07-01",
    completed=None,
    photo=None,
    is_overdue=False,
):
    return {
        "data": {
            "id": vaccination_id,
            "vaccine_name": name,
            "administered_at": f"{administered}T00:00:00.000000Z",
            "due_at": "2027-07-01T00:00:00.000000Z",
            "notes": None,
            "completed_at": completed,
            "is_overdue": is_overdue,
            "photo_url": photo["url"] if photo else None,
            "photo": photo,
            "updated_at": version,
        }
    }


def _medical(*, version="m1", photos=None):
    return {
        "data": {
            "id": 41,
            "record_type": "checkup",
            "record_date": "2026-07-10T00:00:00.000000Z",
            "description": None,
            "vet_name": None,
            "photos": photos or [],
            "updated_at": version,
        }
    }


@pytest.mark.asyncio
async def test_health_deletes_are_exact_preserve_finance_and_verify_absence(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:read", "health:write"])
    with respx.mock:
        respx.get("https://app.example.com/api/pets/7/weights/21").mock(
            side_effect=[
                httpx.Response(200, json=_weight()),
                httpx.Response(404, json={"message": "Not found"}),
                httpx.Response(404, json={"message": "Not found"}),
                httpx.Response(404, json={"message": "Not found"}),
            ]
        )
        weight_delete = respx.delete("https://app.example.com/api/pets/7/weights/21").mock(
            return_value=httpx.Response(200, json={"data": True})
        )
        respx.get("https://app.example.com/api/pets/7/vaccinations/31").mock(
            side_effect=[
                httpx.Response(200, json=_vaccination()),
                httpx.Response(404, json={"message": "Not found"}),
                httpx.Response(404, json={"message": "Not found"}),
                httpx.Response(404, json={"message": "Not found"}),
            ]
        )
        vaccination_delete = respx.delete(
            "https://app.example.com/api/pets/7/vaccinations/31"
        ).mock(return_value=httpx.Response(200, json={"data": True}))
        respx.get("https://app.example.com/api/pets/7/medical-records/41").mock(
            side_effect=[
                httpx.Response(200, json=_medical()),
                httpx.Response(404, json={"message": "Not found"}),
                httpx.Response(404, json={"message": "Not found"}),
                httpx.Response(404, json={"message": "Not found"}),
            ]
        )
        medical_delete = respx.delete("https://app.example.com/api/pets/7/medical-records/41").mock(
            return_value=httpx.Response(200, json={"data": True})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            weight = await _call(
                client,
                "delete_weight",
                {
                    "pet_id": 7,
                    "weight_id": 21,
                    "expected_weight_kg": 4.2,
                    "expected_record_date": "2026-07-21",
                    "base_version": "w1",
                    "idempotency_key": "weight-delete",
                },
            )
            vaccination = await _call(
                client,
                "delete_vaccination",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "expected_vaccine_name": "Core",
                    "expected_administered_at": "2026-07-01",
                    "base_version": "v1",
                    "idempotency_key": "vaccination-delete",
                },
            )
            medical = await _call(
                client,
                "delete_medical_record",
                {
                    "pet_id": 7,
                    "record_id": 41,
                    "expected_record_type": "checkup",
                    "expected_record_date": "2026-07-10",
                    "base_version": "m1",
                    "idempotency_key": "medical-delete",
                },
            )
            weight_replay = await _call(
                client,
                "delete_weight",
                {
                    "pet_id": 7,
                    "weight_id": 21,
                    "expected_weight_kg": 4.2,
                    "expected_record_date": "2026-07-21",
                    "base_version": "w1",
                    "idempotency_key": "weight-delete",
                },
            )
            vaccination_replay = await _call(
                client,
                "delete_vaccination",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "expected_vaccine_name": "Core",
                    "expected_administered_at": "2026-07-01",
                    "base_version": "v1",
                    "idempotency_key": "vaccination-delete",
                },
            )
            medical_replay = await _call(
                client,
                "delete_medical_record",
                {
                    "pet_id": 7,
                    "record_id": 41,
                    "expected_record_type": "checkup",
                    "expected_record_date": "2026-07-10",
                    "base_version": "m1",
                    "idempotency_key": "medical-delete",
                },
            )

    assert weight["structuredContent"]["verified"] is True
    assert vaccination["structuredContent"]["verified"] is True
    assert medical["structuredContent"]["verified"] is True
    assert weight_replay["structuredContent"] == weight["structuredContent"]
    assert vaccination_replay["structuredContent"] == vaccination["structuredContent"]
    assert medical_replay["structuredContent"] == medical["structuredContent"]
    assert json.loads(weight_delete.calls[0].request.content) == {
        "expected_weight_kg": 4.2,
        "expected_record_date": "2026-07-21",
        "base_version": "w1",
    }
    assert vaccination_delete.calls[0].request.url.params["linked_transaction"] == "keep"
    assert medical_delete.calls[0].request.url.params["linked_transaction"] == "keep"
    await engine.dispose()


@pytest.mark.asyncio
async def test_vaccination_renewal_completes_old_and_verifies_successor(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:read", "health:write"])
    old_completed = _vaccination(completed="2026-07-21T00:00:00Z", version="v2")
    successor = _vaccination(32, version="v3", name="Core Plus", administered="2026-07-21")
    old_calls = 0

    def detail_response(request: httpx.Request) -> httpx.Response:
        nonlocal old_calls
        if request.url.path.endswith("/31"):
            old_calls += 1
            return httpx.Response(200, json=_vaccination() if old_calls == 1 else old_completed)
        return httpx.Response(200, json=successor)

    with respx.mock:
        detail = respx.get(
            url__regex=r"https://app\.example\.com/api/pets/7/vaccinations/\d+"
        ).mock(side_effect=detail_response)
        renew = respx.post("https://app.example.com/api/pets/7/vaccinations/31/renew").mock(
            return_value=httpx.Response(201, json=successor)
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "renew_vaccination",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "expected_vaccine_name": "Core",
                    "expected_administered_at": "2026-07-01",
                    "vaccine_name": "Core Plus",
                    "administered_at": "2026-07-21",
                    "base_version": "v1",
                    "idempotency_key": "vaccination-renew",
                },
            )
            replay = await _call(
                client,
                "renew_vaccination",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "expected_vaccine_name": "Core",
                    "expected_administered_at": "2026-07-01",
                    "vaccine_name": "Core Plus",
                    "administered_at": "2026-07-21",
                    "base_version": "v1",
                    "idempotency_key": "vaccination-renew",
                },
            )

    content = result["structuredContent"]
    assert content["completed_vaccination"]["completed_at"] is not None
    assert content["renewed_vaccination"]["id"] == 32
    assert replay["structuredContent"] == content
    assert json.loads(renew.calls[0].request.content)["base_version"] == "v1"
    assert len(detail.calls) == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_photo_import_and_delete_are_guarded_and_verified(
    tmp_path, monkeypatch
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:read", "health:write"])
    vaccination_photo = {
        "id": 51,
        "url": "https://cdn.example/vaccination.jpg",
        "thumb_url": None,
        "medium_url": None,
    }
    medical_photo = {
        "id": 61,
        "url": "https://cdn.example/medical.jpg",
        "thumb_url": None,
        "medium_url": None,
    }

    async def public_addresses(_: str):
        return {ip_address("93.184.216.34")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(public_addresses))
    with respx.mock:
        source = respx.get("https://93.184.216.34/image").mock(
            return_value=httpx.Response(
                200, content=b"safe-image", headers={"Content-Type": "image/jpeg"}
            )
        )
        respx.get("https://app.example.com/api/pets/7/vaccinations/31").mock(
            side_effect=[
                httpx.Response(200, json=_vaccination()),
                httpx.Response(200, json=_vaccination(version="v2", photo=vaccination_photo)),
                httpx.Response(200, json=_vaccination(version="v2", photo=vaccination_photo)),
                httpx.Response(200, json=_vaccination(version="v2", photo=vaccination_photo)),
                httpx.Response(200, json=_vaccination(version="v2", photo=vaccination_photo)),
                httpx.Response(200, json=_vaccination(version="v3")),
                httpx.Response(200, json=_vaccination(version="v3")),
                httpx.Response(200, json=_vaccination(version="v3")),
            ]
        )
        vaccination_upload = respx.post(
            "https://app.example.com/api/pets/7/vaccinations/31/photo"
        ).mock(
            return_value=httpx.Response(
                200, json=_vaccination(version="v2", photo=vaccination_photo)
            )
        )
        vaccination_delete = respx.delete(
            "https://app.example.com/api/pets/7/vaccinations/31/photo"
        ).mock(return_value=httpx.Response(204))
        respx.get("https://app.example.com/api/pets/7/medical-records/41").mock(
            side_effect=[
                httpx.Response(200, json=_medical()),
                httpx.Response(200, json=_medical(version="m2", photos=[medical_photo])),
                httpx.Response(200, json=_medical(version="m2", photos=[medical_photo])),
                httpx.Response(200, json=_medical(version="m2", photos=[medical_photo])),
                httpx.Response(200, json=_medical(version="m2", photos=[medical_photo])),
                httpx.Response(200, json=_medical(version="m3")),
                httpx.Response(200, json=_medical(version="m3")),
                httpx.Response(200, json=_medical(version="m3")),
            ]
        )
        medical_upload = respx.post(
            "https://app.example.com/api/pets/7/medical-records/41/photos"
        ).mock(
            return_value=httpx.Response(200, json=_medical(version="m2", photos=[medical_photo]))
        )
        medical_delete = respx.delete(
            "https://app.example.com/api/pets/7/medical-records/41/photos/61"
        ).mock(return_value=httpx.Response(204))
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            vaccination_added = await _call(
                client,
                "upload_vaccination_photo_from_url",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "expected_photo_id": None,
                    "base_version": "v1",
                    "source_url": "https://images.example/image",
                    "idempotency_key": "vaccination-photo",
                },
            )
            vaccination_added_replay = await _call(
                client,
                "upload_vaccination_photo_from_url",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "expected_photo_id": None,
                    "base_version": "v1",
                    "source_url": "https://images.example/image",
                    "idempotency_key": "vaccination-photo",
                },
            )
            vaccination_removed = await _call(
                client,
                "delete_vaccination_photo",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "photo_id": 51,
                    "base_version": "v2",
                    "idempotency_key": "vaccination-photo-delete",
                },
            )
            vaccination_removed_replay = await _call(
                client,
                "delete_vaccination_photo",
                {
                    "pet_id": 7,
                    "vaccination_id": 31,
                    "photo_id": 51,
                    "base_version": "v2",
                    "idempotency_key": "vaccination-photo-delete",
                },
            )
            medical_added = await _call(
                client,
                "upload_medical_record_photo_from_url",
                {
                    "pet_id": 7,
                    "record_id": 41,
                    "base_version": "m1",
                    "source_url": "https://images.example/image",
                    "idempotency_key": "medical-photo",
                },
            )
            medical_added_replay = await _call(
                client,
                "upload_medical_record_photo_from_url",
                {
                    "pet_id": 7,
                    "record_id": 41,
                    "base_version": "m1",
                    "source_url": "https://images.example/image",
                    "idempotency_key": "medical-photo",
                },
            )
            medical_removed = await _call(
                client,
                "delete_medical_record_photo",
                {
                    "pet_id": 7,
                    "record_id": 41,
                    "photo_id": 61,
                    "base_version": "m2",
                    "idempotency_key": "medical-photo-delete",
                },
            )
            medical_removed_replay = await _call(
                client,
                "delete_medical_record_photo",
                {
                    "pet_id": 7,
                    "record_id": 41,
                    "photo_id": 61,
                    "base_version": "m2",
                    "idempotency_key": "medical-photo-delete",
                },
            )

    assert vaccination_added["structuredContent"]["photo"]["id"] == 51
    assert vaccination_added_replay["structuredContent"] == vaccination_added["structuredContent"]
    assert vaccination_removed["structuredContent"]["vaccination"]["photo"] is None
    assert (
        vaccination_removed_replay["structuredContent"] == vaccination_removed["structuredContent"]
    )
    assert medical_added["structuredContent"]["photo"]["id"] == 61
    assert medical_added_replay["structuredContent"] == medical_added["structuredContent"]
    assert medical_removed["structuredContent"]["medical_record"]["photos"] == []
    assert medical_removed_replay["structuredContent"] == medical_removed["structuredContent"]
    assert source.call_count == 4
    assert source.calls[0].request.headers["host"] == "images.example"
    assert b'name="expected_photo_id"' in vaccination_upload.calls[0].request.content
    assert b'name="photo"; filename="photo.jpg"' in vaccination_upload.calls[0].request.content
    assert b'name="base_version"' in medical_upload.calls[0].request.content
    assert json.loads(vaccination_delete.calls[0].request.content)["expected_photo_id"] == 51
    assert json.loads(medical_delete.calls[0].request.content) == {"base_version": "m2"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase5b_tools_require_health_read_and_write_scopes(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["health:write"])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
        ) as client,
    ):
        result = await _call(
            client,
            "delete_weight",
            {
                "pet_id": 7,
                "weight_id": 21,
                "expected_weight_kg": 4.2,
                "expected_record_date": "2026-07-21",
                "base_version": "w1",
                "idempotency_key": "weight-delete",
            },
        )
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()
