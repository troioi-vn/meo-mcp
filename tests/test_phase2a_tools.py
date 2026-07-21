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
from meo_mcp.meo_api import MeoApi, MeoApiError
from meo_mcp.security import TokenCipher, digest, now


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / ('phase2a-' + '-'.join(scopes) + '.db')}"
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


def _habit(version: str, *, archived: bool = False) -> dict:
    return {
        "data": {
            "id": 51,
            "name": "Morning medicine",
            "timezone": "Asia/Ho_Chi_Minh",
            "value_type": "yes_no",
            "scale_min": None,
            "scale_max": None,
            "day_summary_mode": "average_scored_pets",
            "share_with_coowners": False,
            "reminder_enabled": False,
            "reminder_time": None,
            "reminder_weekdays": None,
            "archived_at": "2026-07-20T00:00:00Z" if archived else None,
            "pet_count": 1,
            "pets": [{"id": 9, "name": "Miso", "photo_url": None, "private": "omit"}],
            "capabilities": {
                "can_edit": True,
                "can_delete": True,
                "can_archive": True,
                "can_share": True,
                "private": True,
            },
            "created_by": 42,
            "updated_at": version,
        }
    }


def _pet(version: str, photos: list[dict] | None = None) -> dict:
    return {
        "data": {
            "id": 9,
            "name": "Miso",
            "updated_at": version,
            "photos": photos or [],
            "relationships": [{"private": True}],
        }
    }


def _microchip(version: str) -> dict:
    return {
        "data": {
            "id": 61,
            "pet_id": 9,
            "chip_number": "982000123456789",
            "issuer": "Test Registry",
            "implanted_at": "2026-07-20",
            "updated_at": version,
            "health_finance_link_exists": True,
            "finance_transaction_id": 999,
        }
    }


@pytest.mark.asyncio
async def test_habit_create_entries_lifecycle_and_delete_retry_cross_boundary(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["habits:read", "habits:write"])
    v1, v2 = "2026-07-20T00:00:00Z", "2026-07-20T00:00:01Z"
    day = {
        "data": {
            "habit": _habit(v1)["data"],
            "date": "2026-07-20",
            "entries": [
                {
                    "entry_id": 71,
                    "pet_id": 9,
                    "pet_name": "Miso",
                    "pet_photo_url": None,
                    "value_int": 1,
                    "is_current_pet": True,
                    "has_entry": True,
                    "private": "omit",
                }
            ],
        }
    }
    with respx.mock:
        create = respx.post("https://app.example.com/api/habits").mock(
            return_value=httpx.Response(201, json={"data": {"id": 51}})
        )
        detail = respx.get("https://app.example.com/api/habits/51").mock(
            side_effect=[
                httpx.Response(200, json=_habit(v1)),
                httpx.Response(200, json=_habit(v1)),
                httpx.Response(200, json=_habit(v2, archived=True)),
                httpx.Response(200, json=_habit(v2, archived=True)),
                httpx.Response(404),
                httpx.Response(404),
                httpx.Response(404),
            ]
        )
        respx.get("https://app.example.com/api/habits/51/entries/2026-07-20").mock(
            return_value=httpx.Response(200, json=day)
        )
        day_put = respx.put("https://app.example.com/api/habits/51/entries/2026-07-20").mock(
            return_value=httpx.Response(200, json=day)
        )
        archive = respx.post("https://app.example.com/api/habits/51/archive").mock(
            return_value=httpx.Response(200, json=_habit(v2, archived=True))
        )
        delete = respx.delete("https://app.example.com/api/habits/51").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            created = await _call(
                client,
                "create_habit",
                {
                    "name": "Morning medicine",
                    "value_type": "yes_no",
                    "pet_ids": [9],
                    "timezone": "Asia/Ho_Chi_Minh",
                    "idempotency_key": "habit-create",
                },
            )
            saved = await _call(
                client,
                "save_habit_day_entries",
                {
                    "habit_id": 51,
                    "entry_date": "2026-07-20",
                    "entries": [{"pet_id": 9, "value_int": 1}],
                    "idempotency_key": "habit-day",
                },
            )
            archived = await _call(
                client,
                "archive_habit",
                {"habit_id": 51, "base_version": v1, "idempotency_key": "habit-archive"},
            )
            deleted = await _call(
                client,
                "delete_habit",
                {"habit_id": 51, "base_version": v2, "idempotency_key": "habit-delete"},
            )
            replayed = await _call(
                client,
                "delete_habit",
                {"habit_id": 51, "base_version": v2, "idempotency_key": "habit-delete"},
            )

    assert created["structuredContent"]["habit"]["version"] == v1
    assert "created_by" not in created["structuredContent"]["habit"]
    assert saved["structuredContent"]["entries"][0]["value_int"] == 1
    assert archived["structuredContent"]["habit"]["archived_at"] is not None
    assert deleted["structuredContent"] == replayed["structuredContent"]
    assert create.calls[0].request.headers["Idempotency-Key"] == "habit-create"
    assert json.loads(day_put.calls[0].request.content) == {
        "entries": [{"pet_id": 9, "value_int": 1}]
    }
    assert json.loads(archive.calls[0].request.content)["base_version"] == v1
    assert len(delete.calls) == 2
    assert len(detail.calls) == 7
    await engine.dispose()


@pytest.mark.asyncio
async def test_photo_upload_pins_public_host_forwards_multipart_and_verifies(
    tmp_path, monkeypatch
) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    v1, v2 = "2026-07-20T00:00:00Z", "2026-07-20T00:00:01Z"
    photo = {
        "id": 81,
        "url": "https://cdn.example/photo.jpg",
        "thumb_url": None,
        "medium_url": None,
        "width": 2,
        "height": 2,
        "is_primary": True,
        "processing": False,
        "private": "omit",
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
        pet_get = respx.get("https://app.example.com/api/pets/9").mock(
            side_effect=[
                httpx.Response(200, json=_pet(v1)),
                httpx.Response(200, json=_pet(v2, [photo])),
            ]
        )
        upload = respx.post("https://app.example.com/api/pets/9/photos").mock(
            return_value=httpx.Response(200, json=_pet(v2, [photo]))
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "upload_pet_photo_from_url",
                {
                    "pet_id": 9,
                    "base_version": v1,
                    "source_url": "https://images.example/image",
                    "idempotency_key": "photo-upload",
                },
            )

    assert result["structuredContent"]["photo"]["id"] == 81
    assert "private" not in result["structuredContent"]["photo"]
    assert source.calls[0].request.headers["host"] == "images.example"
    assert b'name="base_version"' in upload.calls[0].request.content
    assert b'name="photo"; filename="photo.jpg"' in upload.calls[0].request.content
    assert b"safe-image" in upload.calls[0].request.content
    assert len(pet_get.calls) == 2
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_url",
    [
        "http://images.example/photo.jpg",
        "https://user:secret@images.example/photo.jpg",
        "https://images.example:8443/photo.jpg",
        "https://images.example/photo.jpg#fragment",
        "https://127.0.0.1/photo.jpg",
    ],
)
async def test_photo_source_rejects_non_public_destinations(tmp_path, source_url) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["pets:read", "pets:write"])
    with respx.mock:
        respx.get("https://app.example.com/api/pets/9").mock(
            return_value=httpx.Response(200, json=_pet("v1"))
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            result = await _call(
                client,
                "upload_pet_photo_from_url",
                {
                    "pet_id": 9,
                    "base_version": "v1",
                    "source_url": source_url,
                    "idempotency_key": "unsafe-photo",
                },
            )
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "source_url_rejected"
    await engine.dispose()


@pytest.mark.asyncio
async def test_photo_source_rejects_mixed_dns_and_revalidates_redirects(monkeypatch) -> None:
    api = object.__new__(MeoApi)
    original_public_addresses = MeoApi._public_addresses

    async def mixed_addresses(_: str):
        return {ip_address("8.8.8.8"), ip_address("127.0.0.1")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(mixed_addresses))
    with pytest.raises(MeoApiError) as mixed:
        await api._pinned_public_url("https://images.example/photo.jpg")
    assert mixed.value.payload["code"] == "source_url_rejected"

    async def public_addresses(hostname: str):
        if hostname == "127.0.0.1":
            return await original_public_addresses(hostname)
        return {ip_address("8.8.8.8")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(public_addresses))
    with respx.mock:
        respx.get("https://8.8.8.8/photo.jpg").mock(
            return_value=httpx.Response(302, headers={"Location": "https://127.0.0.1/private"})
        )
        with pytest.raises(MeoApiError) as redirect:
            await api._fetch_public_image("https://images.example/photo.jpg")
    assert redirect.value.payload["code"] == "source_url_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "content", "code"),
    [
        ({"Content-Type": "text/html"}, b"not-an-image", "source_image_invalid"),
        (
            {"Content-Type": "image/png", "Content-Length": str(10 * 1024 * 1024 + 1)},
            b"x",
            "source_image_too_large",
        ),
        ({"Content-Type": "image/png"}, b"", "source_image_invalid"),
    ],
)
async def test_photo_source_enforces_mime_and_size(monkeypatch, headers, content, code) -> None:
    api = object.__new__(MeoApi)

    async def public_addresses(_: str):
        return {ip_address("8.8.8.8")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(public_addresses))
    with respx.mock:
        respx.get("https://8.8.8.8/photo").mock(
            return_value=httpx.Response(200, headers=headers, content=content)
        )
        with pytest.raises(MeoApiError) as failure:
            await api._fetch_public_image("https://images.example/photo")
    assert failure.value.payload["code"] == code


@pytest.mark.asyncio
async def test_microchip_create_and_delete_preserve_finance_boundary(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["microchips:read", "microchips:write"])
    version = "2026-07-20T00:00:00Z"
    with respx.mock:
        create = respx.post("https://app.example.com/api/pets/9/microchips").mock(
            return_value=httpx.Response(201, json={"data": {"id": 61}})
        )
        detail = respx.get("https://app.example.com/api/pets/9/microchips/61").mock(
            side_effect=[
                httpx.Response(200, json=_microchip(version)),
                httpx.Response(200, json=_microchip(version)),
                httpx.Response(404),
            ]
        )
        delete = respx.delete("https://app.example.com/api/pets/9/microchips/61").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            created = await _call(
                client,
                "add_microchip",
                {
                    "pet_id": 9,
                    "chip_number": "982000123456789",
                    "issuer": "Test Registry",
                    "idempotency_key": "chip-create",
                },
            )
            deleted = await _call(
                client,
                "delete_microchip",
                {
                    "pet_id": 9,
                    "microchip_id": 61,
                    "base_version": version,
                    "idempotency_key": "chip-delete",
                },
            )

    chip = created["structuredContent"]["microchip"]
    assert chip["has_linked_transaction"] is True
    assert "finance_transaction_id" not in chip
    assert deleted["structuredContent"]["verified"] is True
    assert json.loads(create.calls[0].request.content).get("finance_expense") is None
    assert delete.calls[0].request.url.params["linked_transaction"] == "keep"
    assert detail.call_count == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase2a_scope_and_local_validation_errors_are_structured(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["habits:read"])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
        ) as client,
    ):
        missing_scope = await _call(
            client,
            "create_habit",
            {
                "name": "Medicine",
                "value_type": "yes_no",
                "pet_ids": [9],
                "idempotency_key": "habit-create",
            },
        )
        duplicate_pets = await _call(
            client,
            "create_habit",
            {
                "name": "Medicine",
                "value_type": "yes_no",
                "pet_ids": [9, 9],
                "idempotency_key": "habit-create-2",
            },
        )
    assert missing_scope["structuredContent"]["error"]["code"] == "scope_required"
    assert duplicate_pets["structuredContent"]["error"]["code"] == "validation_error"
    await engine.dispose()


def test_phase2a_normalizers_and_validators_narrow_and_reject() -> None:
    habit = MeoApi._habit(_habit("v1")["data"])
    chip = MeoApi._microchip(_microchip("v1")["data"])
    assert "created_by" not in habit
    assert habit["pets"] == [{"id": 9, "name": "Miso", "photo_url": None}]
    assert "finance_transaction_id" not in chip
    assert MeoApi._chip_number(" 982000123456789 ") == "982000123456789"
    with pytest.raises(MeoApiError, match="pet_ids must be unique"):
        MeoApi._habit_configuration(
            name="Habit",
            value_type="yes_no",
            pet_ids=[9, 9],
            creating=True,
        )
    with pytest.raises(MeoApiError, match="pet_ids must be unique"):
        MeoApi._habit_entries([{"pet_id": 9, "value_int": 1}, {"pet_id": 9, "value_int": None}])
