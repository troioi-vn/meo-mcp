"""The ext-auth client_credentials grant for Meo agent clients."""

import base64
from datetime import timedelta

import httpx
import pytest
import respx
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    CLIENT_INFO_META_KEY,
    LATEST_PROTOCOL_VERSION,
    PROTOCOL_VERSION_META_KEY,
)
from sqlalchemy import select
from test_oauth import oauth_store

from meo_mcp.database import AccessTokenRecord, Grant, RefreshTokenRecord
from meo_mcp.main import create_app
from meo_mcp.oauth import CLIENT_CREDENTIALS_EXTENSION
from meo_mcp.security import TokenCipher, now

AGENT_TOKEN_URL = "https://meo.example.test/api/mcp-auth/agent-token"
RESOURCE = "https://mcp.example.test/mcp"


def issued(scopes=("pets:read",), minutes: int = 60) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "data": {
                "user_id": 42,
                "scopes": list(scopes),
                "sanctum_token": "9|agent-sanctum",
                "expires_at": (now() + timedelta(minutes=minutes)).isoformat(),
            },
        },
    )


async def gateway(tmp_path, name: str, enabled: bool = True):
    engine, sessions, settings = await oauth_store(tmp_path, name)
    settings.agent_clients_enabled = enabled
    app = create_app(settings)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=str(settings.public_base_url)
    )
    return engine, sessions, settings, app, client


def form(**extra) -> dict:
    return {"grant_type": "client_credentials", "resource": RESOURCE, **extra}


@pytest.mark.asyncio
async def test_form_credentials_mint_an_hour_token_with_no_refresh(tmp_path) -> None:
    engine, sessions, settings, _, client = await gateway(tmp_path, "cc.db")
    with respx.mock:
        upstream = respx.post(AGENT_TOKEN_URL).mock(return_value=issued())
        async with client:
            response = await client.post(
                "/token",
                data=form(client_id="meo_ac_one", client_secret="meo_agent_secret"),
            )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"].lower() == "bearer"
    assert body["scope"] == "pets:read"
    assert "refresh_token" not in body
    assert 3500 <= body["expires_in"] <= 3600
    assert response.headers["cache-control"] == "no-store"

    sent = upstream.calls[0].request
    assert sent.headers["Authorization"] == "Bearer test-api-key"
    assert b'"client_secret":"meo_agent_secret"' in sent.content
    assert b"scopes" not in sent.content

    async with sessions() as session:
        grant = (await session.scalars(select(Grant))).one()
        assert grant.client_id == "meo_ac_one"
        assert grant.subject == "42"
        assert (
            TokenCipher(settings.token_encryption_key).decrypt(grant.delegated_token_ciphertext)
            == "9|agent-sanctum"
        )
        assert (await session.scalars(select(AccessTokenRecord))).one().resource == RESOURCE
        assert (await session.scalars(select(RefreshTokenRecord))).all() == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_basic_auth_and_scope_subset_are_forwarded(tmp_path) -> None:
    engine, _, _, _, client = await gateway(tmp_path, "basic.db")
    basic = base64.b64encode(b"meo_ac_one:meo_agent_secret").decode()
    with respx.mock:
        upstream = respx.post(AGENT_TOKEN_URL).mock(return_value=issued())
        async with client:
            response = await client.post(
                "/token",
                data=form(scope="pets:read"),
                headers={"Authorization": f"Basic {basic}"},
            )
    assert response.status_code == 200, response.text
    assert b'"scopes":["pets:read"]' in upstream.calls[0].request.content
    await engine.dispose()


@pytest.mark.asyncio
async def test_access_token_never_outlives_the_upstream_token(tmp_path) -> None:
    engine, _, _, _, client = await gateway(tmp_path, "short.db")
    with respx.mock:
        respx.post(AGENT_TOKEN_URL).mock(return_value=issued(minutes=10))
        async with client:
            response = await client.post(
                "/token", data=form(client_id="meo_ac_one", client_secret="s")
            )
    assert response.json()["expires_in"] <= 600
    await engine.dispose()


@pytest.mark.asyncio
async def test_refusals_map_to_oauth_errors(tmp_path) -> None:
    engine, sessions, _, _, client = await gateway(tmp_path, "refuse.db")
    basic = base64.b64encode(b"meo_ac_one:wrong").decode()
    with respx.mock:
        route = respx.post(AGENT_TOKEN_URL)
        async with client:
            route.mock(return_value=httpx.Response(401, json={"message": "invalid_client"}))
            bad_secret = await client.post(
                "/token", data=form(), headers={"Authorization": f"Basic {basic}"}
            )
            route.mock(return_value=httpx.Response(400, json={"message": "invalid_scope"}))
            too_wide = await client.post(
                "/token", data=form(client_id="a", client_secret="b", scope="pets:write")
            )
            unknown_scope = await client.post(
                "/token", data=form(client_id="a", client_secret="b", scope="admin:all")
            )
            missing = await client.post("/token", data=form())
            both = await client.post(
                "/token",
                data=form(client_id="a", client_secret="b"),
                headers={"Authorization": f"Basic {basic}"},
            )
            no_resource = await client.post(
                "/token",
                data={"grant_type": "client_credentials", "client_id": "a", "client_secret": "b"},
            )
            route.mock(return_value=httpx.Response(422, json={"message": "too long"}))
            malformed = await client.post(
                "/token", data=form(client_id="x" * 99, client_secret="b")
            )
            route.mock(side_effect=httpx.ConnectError("down"))
            down = await client.post("/token", data=form(client_id="a", client_secret="b"))

    assert bad_secret.status_code == 401
    assert bad_secret.json()["error"] == "invalid_client"
    assert bad_secret.headers["www-authenticate"].startswith("Basic")
    assert (too_wide.status_code, too_wide.json()["error"]) == (400, "invalid_scope")
    assert (unknown_scope.status_code, unknown_scope.json()["error"]) == (400, "invalid_scope")
    assert (missing.status_code, missing.json()["error"]) == (401, "invalid_client")
    assert (both.status_code, both.json()["error"]) == (400, "invalid_request")
    assert (no_resource.status_code, no_resource.json()["error"]) == (400, "invalid_target")
    assert (malformed.status_code, malformed.json()["error"]) == (401, "invalid_client")
    assert (down.status_code, down.json()["error"]) == (503, "server_error")
    async with sessions() as session:
        assert (await session.scalars(select(Grant))).all() == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_gateway_leaves_token_endpoint_to_the_sdk(tmp_path) -> None:
    engine, _, _, _, client = await gateway(tmp_path, "off.db", enabled=False)
    with respx.mock:
        upstream = respx.post(AGENT_TOKEN_URL).mock(return_value=issued())
        async with client:
            response = await client.post(
                "/token", data=form(client_id="meo_ac_one", client_secret="s")
            )
            metadata = (await client.get("/.well-known/oauth-authorization-server")).json()
    assert response.status_code in {400, 401}
    assert not upstream.called
    assert "client_credentials" not in metadata["grant_types_supported"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_metadata_and_capabilities_advertise_the_extension(tmp_path) -> None:
    engine, _, _, app, client = await gateway(tmp_path, "meta.db")
    async with app.router.lifespan_context(app), client:
        metadata = (await client.get("/.well-known/oauth-authorization-server")).json()
        initialized = await client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
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
    assert "client_credentials" in metadata["grant_types_supported"]
    assert "authorization_code" in metadata["grant_types_supported"]
    assert "client_secret_basic" in metadata["token_endpoint_auth_methods_supported"]
    assert metadata["registration_endpoint"].endswith("/register")
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    # Unauthenticated MCP calls still get the challenge, not the catalog.
    assert initialized.status_code == 401
    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_token_reaches_tools(tmp_path) -> None:
    engine, _, _, app, client = await gateway(tmp_path, "tools.db")
    with respx.mock:
        respx.post(AGENT_TOKEN_URL).mock(return_value=issued())
        pets = respx.get("https://meo.example.test/api/my-pets").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        async with app.router.lifespan_context(app), client:
            token = (
                await client.post("/token", data=form(client_id="meo_ac_one", client_secret="s"))
            ).json()["access_token"]
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            }
            meta = {
                PROTOCOL_VERSION_META_KEY: LATEST_PROTOCOL_VERSION,
                CLIENT_CAPABILITIES_META_KEY: {},
                CLIENT_INFO_META_KEY: {"name": "agent-test", "version": "1.0"},
            }
            discovered = await client.post(
                "/mcp",
                headers={
                    **headers,
                    "Mcp-Protocol-Version": LATEST_PROTOCOL_VERSION,
                    "Mcp-Method": "server/discover",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "server/discover",
                    "params": {"_meta": meta},
                },
            )
            called = await client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "list_pets", "arguments": {}},
                },
            )
    assert discovered.status_code == 200, discovered.text
    extensions = discovered.json()["result"]["capabilities"]["extensions"]
    assert CLIENT_CREDENTIALS_EXTENSION in extensions
    assert called.status_code == 200
    assert called.json()["result"]["isError"] is False
    assert pets.calls[0].request.headers["Authorization"] == "Bearer 9|agent-sanctum"
    await engine.dispose()


@pytest.mark.asyncio
async def test_malformed_upstream_bodies_and_repeated_fields_are_oauth_errors(tmp_path) -> None:
    engine, sessions, _, _, client = await gateway(tmp_path, "malformed.db")
    creds = "client_id=a&client_secret=b&grant_type=client_credentials&resource=" + RESOURCE
    urlencoded = {"Content-Type": "application/x-www-form-urlencoded"}
    with respx.mock:
        route = respx.post(AGENT_TOKEN_URL)
        async with client:
            route.mock(return_value=httpx.Response(200, text="<html>oops</html>"))
            not_json = await client.post("/token", data=form(client_id="a", client_secret="b"))
            route.mock(return_value=httpx.Response(200, json=["not", "an", "object"]))
            not_object = await client.post("/token", data=form(client_id="a", client_secret="b"))
            route.mock(return_value=issued())
            two_scopes = await client.post(
                "/token",
                content=creds + "&scope=pets:read&scope=pets:write",
                headers=urlencoded,
            )
            two_ids = await client.post(
                "/token", content=creds + "&client_id=c", headers=urlencoded
            )

    for response in (not_json, not_object):
        assert (response.status_code, response.json()["error"]) == (503, "server_error")
        assert response.headers["cache-control"] == "no-store"
    for response in (two_scopes, two_ids):
        assert (response.status_code, response.json()["error"]) == (400, "invalid_request")
    assert route.call_count == 2
    async with sessions() as session:
        assert (await session.scalars(select(Grant))).all() == []
    await engine.dispose()
