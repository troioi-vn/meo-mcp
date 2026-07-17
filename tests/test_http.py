import base64

import httpx
import pytest

from meo_mcp.config import Settings
from meo_mcp.main import create_app


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
