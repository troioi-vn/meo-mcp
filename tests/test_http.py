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


@pytest.mark.asyncio
async def test_health_and_oauth_challenge_are_exposed() -> None:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///ignored.db",
            token_encryption_key=key,
            meo_connector_hmac_secret="hmac",
            meo_connector_api_key="key",
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=str(app.state.settings.public_base_url),
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
        response = await client.post("/mcp", json={})
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]
    assert 'scope="pets:read"' in response.headers["www-authenticate"]
    assert metadata.json()["scopes_supported"] == ALLOWED_SCOPES


@pytest.mark.asyncio
async def test_request_log_is_structured_and_omits_query_values(caplog) -> None:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///ignored.db",
            token_encryption_key=key,
            meo_connector_hmac_secret="hmac",
            meo_connector_api_key="key",
        )
    )
    transport = httpx.ASGITransport(app=app)
    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(
            transport=transport,
            base_url=str(app.state.settings.public_base_url),
        ) as client:
            response = await client.get(
                "/health?access_token=must-not-appear",
                headers={"X-Request-ID": "request-log-test"},
            )

    assert response.status_code == 200
    events = [json.loads(record.message) for record in caplog.records]
    request_event = next(event for event in events if event.get("event") == "http_request")
    assert request_event["request_id"] == "request-log-test"
    assert request_event["method"] == "GET"
    assert request_event["endpoint"] == "/health"
    assert request_event["status"] == 200
    assert isinstance(request_event["latency_ms"], float)
    assert "must-not-appear" not in caplog.text


@pytest.mark.asyncio
async def test_authenticated_mcp_initialize_list_and_call_cross_asgi_boundary(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'mcp.db'}"
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

    access_token = "access-token"
    grant = Grant(
        id=uuid4(),
        client_id="client-id",
        subject="42",
        scopes=ALLOWED_SCOPES,
        delegated_token_ciphertext=TokenCipher(key).encrypt("1|delegated-pat"),
        expires_at=now() + timedelta(days=1),
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        session.add(
            AccessTokenRecord(
                token_hash=digest(access_token),
                grant_id=grant.id,
                client_id=grant.client_id,
                scopes=grant.scopes,
                subject=grant.subject,
                resource=settings.resource,
                expires_at=now() + timedelta(hours=1, microseconds=123456),
            )
        )
        await session.commit()

    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json, text/event-stream",
    }
    with respx.mock:
        upstream = respx.get("https://app.example.com/api/my-pets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 7,
                            "name": "Miso",
                            "pet_type": {"name": "Cat"},
                            "sex": "female",
                        }
                    ]
                },
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url=str(settings.public_base_url),
            ) as client,
        ):
            response = await client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                },
            )
            tools = await client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            called = await client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "list_pets", "arguments": {}},
                },
            )

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Meo Mai Moi"
    assert [tool["name"] for tool in tools.json()["result"]["tools"]] == [
        "list_pets",
        "find_pets",
        "get_pet",
        "list_pet_types",
        "list_pet_categories",
        "create_pet_category",
        "list_weights",
        "get_weight",
        "list_vaccinations",
        "get_vaccination",
        "list_medical_records",
        "get_medical_record",
        "get_pets_overview",
        "create_pet",
        "update_pet",
        "update_pet_status",
        "delete_pet",
        "add_weight",
        "update_weight",
        "delete_weight",
        "add_vaccination",
        "update_vaccination",
        "delete_vaccination",
        "renew_vaccination",
        "upload_vaccination_photo_from_url",
        "delete_vaccination_photo",
        "add_medical_record",
        "update_medical_record",
        "delete_medical_record",
        "upload_medical_record_photo_from_url",
        "delete_medical_record_photo",
        "list_habits",
        "get_habit",
        "get_habit_heatmap",
        "get_habit_day_entries",
        "create_habit",
        "update_habit",
        "save_habit_day_entries",
        "archive_habit",
        "restore_habit",
        "delete_habit",
        "list_pet_photos",
        "upload_pet_photo_from_url",
        "set_primary_pet_photo",
        "delete_pet_photo",
        "list_microchips",
        "get_microchip",
        "add_microchip",
        "update_microchip",
        "delete_microchip",
        "get_pet_sharing",
        "list_pet_relationship_suggestions",
        "list_pet_invitations",
        "preview_pet_invitation",
        "add_pet_collaborator",
        "change_pet_collaborator_role",
        "remove_pet_collaborator",
        "create_pet_invitation",
        "revoke_pet_invitation",
        "accept_pet_invitation",
        "decline_pet_invitation",
        "leave_shared_pet",
        "list_placement_opportunities",
        "get_placement_request",
        "list_placement_responses",
        "search_helper_profiles",
        "get_public_helper_profile",
        "list_my_helper_profiles",
        "get_helper_profile",
        "list_helper_location_options",
        "create_helper_city_option",
        "list_chats",
        "get_chat",
        "list_chat_messages",
        "get_unread_message_count",
        "list_groups",
        "get_group_overview",
        "list_group_member_suggestions",
        "list_group_invitations",
        "preview_group_invitation",
        "create_group",
        "update_group",
        "delete_group",
        "add_group_member",
        "update_group_member_role",
        "remove_group_member",
        "leave_group",
        "add_group_pets",
        "remove_group_pet",
        "create_group_invitation",
        "revoke_group_invitation",
        "accept_group_invitation",
        "decline_group_invitation",
        "list_currencies",
        "list_ledgers",
        "get_ledger_overview",
        "list_ledger_member_suggestions",
        "list_ledger_invitations",
        "list_ledger_transactions",
        "get_ledger_transaction",
        "inspect_ledger_transaction_receipt",
        "list_pet_finance_transactions",
        "preview_ledger_invitation",
        "create_ledger",
        "update_ledger",
        "archive_ledger",
        "restore_ledger",
        "delete_ledger",
        "add_ledger_member",
        "remove_ledger_member",
        "leave_ledger",
        "add_ledger_pet",
        "remove_ledger_pet",
        "link_ledger_group",
        "unlink_ledger_group",
        "create_ledger_invitation",
        "revoke_ledger_invitation",
        "accept_ledger_invitation",
        "decline_ledger_invitation",
        "create_ledger_account",
        "update_ledger_account",
        "archive_ledger_account",
        "create_ledger_category",
        "update_ledger_category",
        "archive_ledger_category",
        "create_ledger_transaction",
        "update_ledger_transaction",
        "delete_ledger_transaction",
        "upload_ledger_transaction_receipt_from_url",
        "delete_ledger_transaction_receipt",
        "get_notification_inbox",
        "get_notification_preferences",
        "get_my_profile",
        "list_owner_weights",
        "get_account_invitation_summary",
        "mark_notification_read",
        "mark_all_notifications_read",
        "update_notification_preference",
        "update_my_profile_name",
        "update_my_locale",
        "upload_my_avatar_from_url",
        "delete_my_avatar",
        "get_owner_weight",
        "create_owner_weight",
        "update_owner_weight",
        "delete_owner_weight",
        "create_account_invitation",
        "revoke_account_invitation",
        "create_placement_request",
        "delete_placement_request",
        "respond_to_placement_request",
        "accept_placement_response",
        "reject_placement_response",
        "cancel_placement_response",
        "confirm_pet_transfer",
        "reject_pet_transfer",
        "cancel_pet_transfer",
        "finalize_temporary_placement",
        "create_helper_profile",
        "update_helper_profile",
        "archive_helper_profile",
        "restore_helper_profile",
        "delete_helper_profile",
        "upload_helper_profile_photo_from_url",
        "set_primary_helper_profile_photo",
        "delete_helper_profile_photo",
        "open_placement_chat",
        "send_chat_message",
        "send_chat_image_from_url",
        "mark_chat_read",
        "delete_own_message",
        "leave_chat",
    ]
    assert tools.json()["result"]["tools"][0]["annotations"]["readOnlyHint"] is True
    by_name = {tool["name"]: tool for tool in tools.json()["result"]["tools"]}
    assert by_name["create_pet"]["annotations"]["destructiveHint"] is False
    assert by_name["update_pet"]["annotations"]["destructiveHint"] is True
    assert by_name["list_habits"]["annotations"]["readOnlyHint"] is True
    assert by_name["list_chat_messages"]["annotations"]["readOnlyHint"] is True
    assert by_name["get_ledger_overview"]["annotations"]["readOnlyHint"] is True
    assert by_name["create_habit"]["annotations"]["destructiveHint"] is False
    assert by_name["create_placement_request"]["annotations"]["destructiveHint"] is False
    assert by_name["delete_own_message"]["annotations"]["destructiveHint"] is True
    assert by_name["delete_habit"]["annotations"]["destructiveHint"] is True
    assert by_name["save_habit_day_entries"]["inputSchema"]["$defs"]["HabitEntryInput"][
        "required"
    ] == ["pet_id"]
    assert by_name["upload_pet_photo_from_url"]["inputSchema"]["required"] == [
        "pet_id",
        "base_version",
        "source_url",
        "idempotency_key",
    ]
    assert called.status_code == 200
    assert json.loads(called.json()["result"]["content"][0]["text"]) == {
        "pets": [
            {
                "id": 7,
                "name": "Miso",
                "species": "Cat",
                "sex": "female",
                "age": None,
                "photo_url": None,
            }
        ]
    }
    assert upstream.calls[0].request.headers["Authorization"] == "Bearer 1|delegated-pat"
    await engine.dispose()


@pytest.mark.asyncio
async def test_guard_validates_host_origin_size_and_request_ids() -> None:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    settings = Settings(
        database_url="sqlite+aiosqlite:///ignored.db",
        public_base_url="https://mcp.example.test",
        token_encryption_key=key,
        meo_connector_hmac_secret="hmac",
        meo_connector_api_key="key",
        allowed_origins=["https://client.example.test"],
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(settings.public_base_url)
    ) as client:
        accepted = await client.get(
            "/health",
            headers={"Origin": "https://client.example.test", "X-Request-ID": "request-123"},
        )
        bad_origin = await client.get("/health", headers={"Origin": "https://evil.example.test"})
        too_large = await client.post(
            "/register",
            content=b"x" * (1_048_576 + 1),
            headers={"Content-Type": "application/json"},
        )
        invalid_length = await client.post(
            "/register",
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "not-an-integer"},
        )
    evil_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=evil_transport, base_url="https://evil.example.test"
    ) as client:
        bad_host = await client.get("/health")

    assert accepted.status_code == 200
    assert accepted.headers["X-Request-ID"] == "request-123"
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error"]["code"] == "invalid_origin"
    assert bad_origin.headers["X-Request-ID"]
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "request_too_large"
    assert invalid_length.status_code == 400
    assert invalid_length.json()["error"]["code"] == "invalid_content_length"
    assert bad_host.status_code == 421
    assert bad_host.json()["error"]["code"] == "invalid_host"


@pytest.mark.parametrize(
    ("status", "expected_code", "retryable"),
    [
        (401, "upstream_unauthorized", False),
        (403, "upstream_forbidden", False),
        (404, "upstream_not_found", False),
        (429, "upstream_rate_limited", True),
        (503, "upstream_server_error", True),
        (200, "upstream_malformed", True),
    ],
)
@pytest.mark.asyncio
async def test_list_pets_translates_upstream_errors_to_structured_tool_results(
    tmp_path, caplog, status: int, expected_code: str, retryable: bool
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / f'upstream-{status}.db'}"
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
        client_id="client-id",
        subject="42",
        scopes=ALLOWED_SCOPES,
        delegated_token_ciphertext=TokenCipher(key).encrypt("1|delegated-pat"),
        expires_at=now() + timedelta(days=1),
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        session.add(
            AccessTokenRecord(
                token_hash=digest("access-token"),
                grant_id=grant.id,
                client_id=grant.client_id,
                scopes=grant.scopes,
                subject=grant.subject,
                resource=settings.resource,
                expires_at=now() + timedelta(hours=1),
            )
        )
        await session.commit()

    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    with respx.mock, caplog.at_level(logging.INFO):
        respx.get("https://app.example.com/api/my-pets").mock(
            return_value=httpx.Response(
                status,
                json=[] if status == 200 else {"message": "upstream detail"},
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport, base_url=str(settings.public_base_url)
            ) as client,
        ):
            response = await client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer access-token",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "list_pets", "arguments": {}},
                },
            )

    result = response.json()["result"]
    assert result["isError"] is True
    error = json.loads(result["content"][0]["text"])
    assert error == {
        "code": expected_code,
        "message": error["message"],
        "retryable": retryable,
        "upstream_status": status,
    }
    assert "upstream detail" not in result["content"][0]["text"]
    if status == 503:
        events = [
            json.loads(record.message)
            for record in caplog.records
            if record.message.startswith("{")
        ]
        upstream_event = next(
            event for event in events if event.get("event") == "meo_upstream_error"
        )
        assert upstream_event["request_id"] != "unbound"
        assert upstream_event["error_kind"] == "upstream_server_error"
        assert upstream_event["upstream_status"] == 503
        assert "delegated-pat" not in caplog.text
    await engine.dispose()
