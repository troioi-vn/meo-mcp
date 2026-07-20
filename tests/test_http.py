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
    assert metadata.json()["scopes_supported"] == ["pets:read", "health:read"]


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
        "list_weights",
        "get_weight",
        "list_vaccinations",
        "get_vaccination",
        "list_medical_records",
        "get_medical_record",
        "get_pets_overview",
    ]
    assert tools.json()["result"]["tools"][0]["annotations"]["readOnlyHint"] is True
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
    tmp_path, status: int, expected_code: str, retryable: bool
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
    with respx.mock:
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
    await engine.dispose()
