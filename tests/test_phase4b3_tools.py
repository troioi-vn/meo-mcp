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
from meo_mcp.oauth import ALLOWED_SCOPES
from meo_mcp.security import TokenCipher, digest, now


async def _app_with_token(tmp_path, scopes: list[str]):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase4b3.db'}"
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


def _profile(*, name="Athanasius", avatar_url=None, version="p1"):
    return {
        "data": {
            "id": 42,
            "name": name,
            "email": "owner@example.test",
            "avatar_url": avatar_url,
            "updated_at": version,
        }
    }


def _inbox(count: int, *, read_at=None):
    return {
        "data": {
            "bell_notifications": [
                {
                    "id": 7,
                    "title": "Update",
                    "read_at": read_at,
                    "actions": [{"key": "unapprove", "label": "Admin only"}],
                }
            ],
            "unread_bell_count": count,
            "unread_message_count": 0,
        }
    }


def _preferences(*, email=True, in_app=True, telegram=False):
    return {
        "data": [
            {
                "type": "system_announcement",
                "label": "System announcement",
                "group": "account",
                "email_enabled": email,
                "in_app_enabled": in_app,
                "telegram_enabled": telegram,
                "updated_at": "np1",
            }
        ]
    }


def _invitation(*, invitation_id=31, status="pending", email=None, version="i1"):
    return {
        "id": invitation_id,
        "code": "BEARER-CODE",
        "email": email,
        "status": status,
        "invitation_url": "https://app.example.com/register?invitation_code=BEARER-CODE",
        "updated_at": version,
        "recipient": None,
    }


@pytest.mark.asyncio
async def test_notification_receipts_and_preferences_enforce_expected_state(tmp_path) -> None:
    app, engine, settings = await _app_with_token(
        tmp_path, ["notifications:read", "notifications:write"]
    )
    with respx.mock:
        inbox = respx.get("https://app.example.com/api/notifications/unified").mock(
            side_effect=[
                httpx.Response(200, json=_inbox(1)),
                httpx.Response(200, json=_inbox(0, read_at="2026-07-21T00:00:00Z")),
                httpx.Response(200, json=_inbox(2)),
                httpx.Response(200, json=_inbox(0, read_at="2026-07-21T00:00:00Z")),
            ]
        )
        single = respx.patch("https://app.example.com/api/notifications/7/read").mock(
            return_value=httpx.Response(204)
        )
        bulk = respx.post("https://app.example.com/api/notifications/mark-all-read").mock(
            return_value=httpx.Response(204)
        )
        preferences = respx.get("https://app.example.com/api/notification-preferences").mock(
            side_effect=[
                httpx.Response(200, json=_preferences()),
                httpx.Response(200, json=_preferences(email=False)),
            ]
        )
        update = respx.put("https://app.example.com/api/notification-preferences").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            marked = await _call(
                client,
                "mark_notification_read",
                {"notification_id": 7, "idempotency_key": "notification-one"},
            )
            marked_all = await _call(
                client,
                "mark_all_notifications_read",
                {"expected_unread_count": 2, "idempotency_key": "notification-all"},
            )
            changed = await _call(
                client,
                "update_notification_preference",
                {
                    "notification_type": "system_announcement",
                    "expected_email_enabled": True,
                    "expected_in_app_enabled": True,
                    "expected_telegram_enabled": False,
                    "email_enabled": False,
                    "in_app_enabled": True,
                    "telegram_enabled": False,
                    "idempotency_key": "notification-preference",
                },
            )

    assert marked["structuredContent"]["verified"] is True
    assert marked_all["structuredContent"]["marked_read_count"] == 2
    assert changed["structuredContent"]["preference"]["email_enabled"] is False
    assert single.calls[0].request.headers["Idempotency-Key"] == "notification-one"
    assert bulk.calls[0].request.content == b'{"expected_unread_count":2}'
    assert b'"expected_email_enabled":true' in update.calls[0].request.content
    assert len(inbox.calls) == 4
    assert len(preferences.calls) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_safe_profile_name_and_avatar_writes_are_versioned(tmp_path, monkeypatch) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["profile:read", "profile:write"])

    async def public_addresses(_: str):
        return {ip_address("93.184.216.34")}

    monkeypatch.setattr(MeoApi, "_public_addresses", staticmethod(public_addresses))
    with respx.mock:
        profile = respx.get("https://app.example.com/api/users/me").mock(
            side_effect=[
                httpx.Response(200, json=_profile()),
                httpx.Response(200, json=_profile(name="Catarchy", version="p2")),
                httpx.Response(200, json=_profile(name="Catarchy", version="p2")),
                httpx.Response(
                    200,
                    json=_profile(
                        name="Catarchy",
                        avatar_url="https://cdn.example/avatar.jpg",
                        version="p3",
                    ),
                ),
                httpx.Response(
                    200,
                    json=_profile(
                        name="Catarchy",
                        avatar_url="https://cdn.example/avatar.jpg",
                        version="p3",
                    ),
                ),
                httpx.Response(200, json=_profile(name="Catarchy", version="p4")),
            ]
        )
        rename = respx.put("https://app.example.com/api/users/me").mock(
            return_value=httpx.Response(200, json=_profile(name="Catarchy", version="p2"))
        )
        respx.get("https://93.184.216.34/avatar").mock(
            return_value=httpx.Response(
                200, content=b"safe-image", headers={"Content-Type": "image/jpeg"}
            )
        )
        avatar = respx.post("https://app.example.com/api/users/me/avatar").mock(
            return_value=httpx.Response(200, json={"data": {"avatar_url": "unused"}})
        )
        avatar_delete = respx.delete("https://app.example.com/api/users/me/avatar").mock(
            return_value=httpx.Response(204)
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            renamed = await _call(
                client,
                "update_my_profile_name",
                {"name": "Catarchy", "base_version": "p1", "idempotency_key": "profile-name"},
            )
            uploaded = await _call(
                client,
                "upload_my_avatar_from_url",
                {
                    "source_url": "https://images.example/avatar",
                    "base_version": "p2",
                    "idempotency_key": "profile-avatar",
                },
            )
            deleted = await _call(
                client,
                "delete_my_avatar",
                {
                    "expected_avatar_url": "https://cdn.example/avatar.jpg",
                    "base_version": "p3",
                    "idempotency_key": "profile-avatar-delete",
                },
            )

    assert renamed["structuredContent"]["profile"]["name"] == "Catarchy"
    assert uploaded["structuredContent"]["profile"]["avatar_url"].endswith("avatar.jpg")
    assert deleted["structuredContent"]["avatar_deleted"] is True
    assert rename.calls[0].request.content == (
        b'{"name":"Catarchy","email":"owner@example.test","base_version":"p1"}'
    )
    assert b'name="base_version"' in avatar.calls[0].request.content
    assert b'name="avatar"; filename="photo.jpg"' in avatar.calls[0].request.content
    assert b'"expected_avatar_url":"https://cdn.example/avatar.jpg"' in (
        avatar_delete.calls[0].request.content
    )
    assert len(profile.calls) == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_owner_weight_crud_uses_detail_versions_and_absence_verification(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ["profile:read", "profile:write"])
    weight_v1 = {
        "data": {
            "id": 8,
            "weight_kg": 62.4,
            "record_date": "2026-07-20T00:00:00.000000Z",
            "updated_at": "w1",
        }
    }
    weight_v2 = {
        "data": {
            "id": 8,
            "weight_kg": 62.8,
            "record_date": "2026-07-20T00:00:00.000000Z",
            "updated_at": "w2",
        }
    }
    with respx.mock:
        create = respx.post("https://app.example.com/api/users/me/owner-weights").mock(
            side_effect=[
                httpx.Response(201, json={"data": {"id": 8}}),
                httpx.Response(
                    409,
                    json={
                        "data": {
                            "code": "duplicate_candidate",
                            "existing_owner_weight_ids": [8],
                        }
                    },
                ),
            ]
        )
        detail = respx.get("https://app.example.com/api/users/me/owner-weights/8").mock(
            side_effect=[
                httpx.Response(200, json=weight_v1),
                httpx.Response(200, json=weight_v1),
                httpx.Response(200, json=weight_v2),
                httpx.Response(200, json=weight_v2),
                httpx.Response(404, json={"message": "missing"}),
            ]
        )
        update = respx.put("https://app.example.com/api/users/me/owner-weights/8").mock(
            return_value=httpx.Response(200, json=weight_v2)
        )
        delete = respx.delete("https://app.example.com/api/users/me/owner-weights/8").mock(
            return_value=httpx.Response(200, json={"data": True})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            created = await _call(
                client,
                "create_owner_weight",
                {
                    "weight_kg": 62.4,
                    "record_date": "2026-07-20",
                    "idempotency_key": "owner-weight-create",
                },
            )
            duplicate = await _call(
                client,
                "create_owner_weight",
                {
                    "weight_kg": 62.4,
                    "record_date": "2026-07-20",
                    "idempotency_key": "owner-weight-distinct-key",
                },
            )
            changed = await _call(
                client,
                "update_owner_weight",
                {
                    "owner_weight_id": 8,
                    "weight_kg": 62.8,
                    "base_version": "w1",
                    "idempotency_key": "owner-weight-update",
                },
            )
            deleted = await _call(
                client,
                "delete_owner_weight",
                {
                    "owner_weight_id": 8,
                    "expected_weight_kg": 62.8,
                    "expected_record_date": "2026-07-20",
                    "base_version": "w2",
                    "idempotency_key": "owner-weight-delete",
                },
            )

    assert created["structuredContent"]["weight"]["weight_id"] == 8
    assert duplicate["isError"] is True
    assert duplicate["structuredContent"]["error"]["code"] == "duplicate_candidate"
    assert duplicate["structuredContent"]["error"]["existing_owner_weight_ids"] == [8]
    assert changed["structuredContent"]["weight"]["weight_kg"] == 62.8
    assert deleted["structuredContent"]["deleted"] is True
    assert create.calls[0].request.headers["Idempotency-Key"] == "owner-weight-create"
    assert b'"base_version":"w1"' in update.calls[0].request.content
    assert b'"expected_record_date":"2026-07-20"' in delete.calls[0].request.content
    assert len(detail.calls) == 5
    await engine.dispose()


@pytest.mark.asyncio
async def test_account_invitation_create_revoke_and_duplicate_translation(tmp_path) -> None:
    app, engine, settings = await _app_with_token(
        tmp_path, ["invitations:read", "invitations:write"]
    )
    pending, revoked = (
        _invitation(email="invitee@example.test"),
        _invitation(email="invitee@example.test", status="revoked", version="i2"),
    )
    stats_pending = {"data": {"total": 1, "pending": 1, "accepted": 0, "expired": 0, "revoked": 0}}
    stats_revoked = {"data": {"total": 1, "pending": 0, "accepted": 0, "expired": 0, "revoked": 1}}
    with respx.mock:
        create = respx.post("https://app.example.com/api/invitations").mock(
            side_effect=[
                httpx.Response(201, json={"data": pending}),
                httpx.Response(
                    409,
                    json={
                        "data": {
                            "code": "duplicate_candidate",
                            "existing_invitation_ids": [31],
                        }
                    },
                ),
            ]
        )
        invitations = respx.get("https://app.example.com/api/invitations").mock(
            side_effect=[
                httpx.Response(200, json={"data": [pending]}),
                httpx.Response(200, json={"data": [pending]}),
                httpx.Response(200, json={"data": [revoked]}),
            ]
        )
        stats = respx.get("https://app.example.com/api/invitations/stats").mock(
            side_effect=[
                httpx.Response(200, json=stats_pending),
                httpx.Response(200, json=stats_pending),
                httpx.Response(200, json=stats_revoked),
            ]
        )
        revoke = respx.delete("https://app.example.com/api/invitations/31").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            created = await _call(
                client,
                "create_account_invitation",
                {"email": "Invitee@Example.Test", "idempotency_key": "account-invite"},
            )
            duplicate = await _call(
                client,
                "create_account_invitation",
                {
                    "email": "invitee@example.test",
                    "idempotency_key": "account-invite-distinct-key",
                },
            )
            removed = await _call(
                client,
                "revoke_account_invitation",
                {
                    "invitation_id": 31,
                    "expected_target_email": "invitee@example.test",
                    "base_version": "i1",
                    "idempotency_key": "account-invite-revoke",
                },
            )

    assert created["structuredContent"]["invitation"]["target_email"] == "invitee@example.test"
    assert duplicate["structuredContent"]["error"]["code"] == "duplicate_candidate"
    assert duplicate["structuredContent"]["error"]["existing_invitation_ids"] == [31]
    assert removed["structuredContent"]["invitation"]["status"] == "revoked"
    assert b'"email":"invitee@example.test"' in create.calls[0].request.content
    assert revoke.calls[0].request.headers["Idempotency-Key"] == "account-invite-revoke"
    assert b'"expected_target_email":"invitee@example.test"' in revoke.calls[0].request.content
    assert len(invitations.calls) == 3
    assert len(stats.calls) == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase4b3_write_scopes_are_required(tmp_path) -> None:
    app, engine, settings = await _app_with_token(
        tmp_path, ["notifications:read", "profile:read", "invitations:read"]
    )
    with respx.mock:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
            ) as client,
        ):
            denied = await _call(
                client,
                "create_owner_weight",
                {
                    "weight_kg": 62.4,
                    "record_date": "2026-07-20",
                    "idempotency_key": "denied",
                },
            )

    assert denied["isError"] is True
    assert denied["structuredContent"]["error"]["code"] == "scope_required"
    await engine.dispose()


def test_phase4b3_scopes_are_advertised() -> None:
    assert ALLOWED_SCOPES[-6:] == [
        "notifications:read",
        "notifications:write",
        "profile:read",
        "profile:write",
        "invitations:read",
        "invitations:write",
    ]


@pytest.mark.asyncio
async def test_phase4b3_tools_are_discoverable_without_notification_actions(tmp_path) -> None:
    app, engine, settings = await _app_with_token(tmp_path, ALLOWED_SCOPES)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
        ) as client,
    ):
        response = await client.post(
            "/mcp",
            headers={"Authorization": "Bearer access", "Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert len(names) == 169
    assert {
        "mark_notification_read",
        "mark_all_notifications_read",
        "update_notification_preference",
        "update_my_profile_name",
        "upload_my_avatar_from_url",
        "delete_my_avatar",
        "get_owner_weight",
        "create_owner_weight",
        "update_owner_weight",
        "delete_owner_weight",
        "create_account_invitation",
        "revoke_account_invitation",
    } <= names
    assert {
        "delete_weight",
        "delete_vaccination",
        "renew_vaccination",
        "upload_vaccination_photo_from_url",
        "delete_vaccination_photo",
        "delete_medical_record",
        "upload_medical_record_photo_from_url",
        "delete_medical_record_photo",
    } <= names
    assert "execute_notification_action" not in names
    await engine.dispose()
