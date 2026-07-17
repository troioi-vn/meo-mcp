import base64
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

from meo_mcp.config import Settings
from meo_mcp.database import AccessTokenRecord, Base, Grant, make_session_factory
from meo_mcp.main import create_app
from meo_mcp.oauth import ALLOWED_SCOPES
from meo_mcp.security import digest, now


@pytest.mark.asyncio
async def test_health_and_oauth_challenge_are_exposed() -> None:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    app = create_app(Settings(database_url="sqlite+aiosqlite:///ignored.db", token_encryption_key=key, meo_connector_hmac_secret="hmac", meo_connector_api_key="key"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://mcp-dev.meo-mai-moi.com") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        response = await client.post("/mcp", json={})
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_authenticated_mcp_initialize_starts_streamable_http_manager(tmp_path) -> None:
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
        delegated_token_ciphertext="encrypted",
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
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="https://mcp-dev.meo-mai-moi.com",
        ) as client,
    ):
        response = await client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json, text/event-stream",
            },
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

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Meo Mai Moi"
    await engine.dispose()
