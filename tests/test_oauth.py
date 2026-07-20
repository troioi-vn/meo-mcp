import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
import respx
from mcp.server.auth.provider import AccessToken, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import select

from meo_mcp.config import Settings
from meo_mcp.database import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    AuthorizationRequest,
    Base,
    Grant,
    OAuthClient,
    RefreshTokenRecord,
    make_session_factory,
)
from meo_mcp.main import create_app
from meo_mcp.oauth import (
    ACCESS_TOKEN_TTL,
    ALLOWED_SCOPES,
    AUTHORIZATION_CODE_TTL,
    CONSENT_TTL,
    REFRESH_TOKEN_TTL,
    DatabaseOAuthProvider,
)
from meo_mcp.security import TokenCipher, digest, now


def settings_for(database_url: str) -> Settings:
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    return Settings(
        database_url=database_url,
        public_base_url="https://mcp.example.test",
        meo_base_url="https://meo.example.test",
        token_encryption_key=key,
        meo_connector_hmac_secret="test-hmac",
        meo_connector_api_key="test-api-key",
    )


def public_client(client_id: str = "public-client") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=["http://127.0.0.1/callback"],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="pets:read",
        client_name="Test MCP client",
    )


def s256(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


async def oauth_store(tmp_path, name: str):
    database_url = f"sqlite+aiosqlite:///{tmp_path / name}"
    engine, sessions = make_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, sessions, settings_for(database_url)


@pytest.mark.asyncio
async def test_dcr_accepts_only_public_clients_and_persists_no_secret(tmp_path) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "dcr.db")
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(settings.public_base_url)
    ) as client:
        response = await client.post(
            "/register",
            json={
                "redirect_uris": ["http://127.0.0.1/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "pets:read",
                "client_name": "Public test client",
            },
        )
        assert response.status_code == 201
        registration = response.json()
        assert registration.get("client_secret") is None

        confidential = await client.post(
            "/register",
            json={
                "redirect_uris": ["https://client.example.test/callback"],
                "token_endpoint_auth_method": "client_secret_post",
            },
        )
        invalid_scope = await client.post(
            "/register",
            json={
                "redirect_uris": ["https://client.example.test/callback"],
                "token_endpoint_auth_method": "none",
                "scope": "pets:write",
            },
        )
        invalid_redirect = await client.post(
            "/register",
            json={
                "redirect_uris": ["https://user:password@client.example.test/callback#fragment"],
                "token_endpoint_auth_method": "none",
            },
        )

    assert confidential.status_code == 400
    assert confidential.json()["error"] == "invalid_client_metadata"
    assert invalid_scope.status_code == 400
    assert invalid_scope.json()["error"] == "invalid_client_metadata"
    assert invalid_redirect.status_code == 400
    assert invalid_redirect.json()["error"] == "invalid_redirect_uri"
    async with sessions() as session:
        stored = await session.scalar(
            select(OAuthClient).where(OAuthClient.client_id == registration["client_id"])
        )
        assert stored is not None
        assert stored.client_metadata.get("client_secret") is None
        assert "test-api-key" not in str(stored.client_metadata)
    await engine.dispose()


@pytest.mark.asyncio
async def test_authorize_requires_exact_redirect_pkce_resource_and_scope(tmp_path) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "authorize.db")
    provider = DatabaseOAuthProvider(sessions, settings)
    client_info = public_client()
    await provider.register_client(client_info)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    verifier = "a" * 64
    base_params = {
        "client_id": client_info.client_id,
        "redirect_uri": "http://127.0.0.1/callback",
        "response_type": "code",
        "code_challenge": s256(verifier),
        "code_challenge_method": "S256",
        "state": "state-1",
        "scope": "pets:read",
        "resource": settings.resource,
    }
    async with httpx.AsyncClient(
        transport=transport, base_url=str(settings.public_base_url)
    ) as client:
        accepted = await client.get("/authorize", params=base_params, follow_redirects=False)
        health_only = await client.get(
            "/authorize",
            params={**base_params, "scope": "health:read"},
            follow_redirects=False,
        )
        wrong_redirect = await client.get(
            "/authorize",
            params={**base_params, "redirect_uri": "http://127.0.0.1/callback/extra"},
            follow_redirects=False,
        )
        missing_pkce = await client.get(
            "/authorize",
            params={key: value for key, value in base_params.items() if key != "code_challenge"},
            follow_redirects=False,
        )
        plain_pkce = await client.get(
            "/authorize",
            params={**base_params, "code_challenge_method": "plain"},
            follow_redirects=False,
        )
        malformed_pkce = await client.get(
            "/authorize",
            params={**base_params, "code_challenge": "too-short"},
            follow_redirects=False,
        )
        wrong_resource = await client.get(
            "/authorize",
            params={**base_params, "resource": "https://other.example.test/mcp"},
            follow_redirects=False,
        )
        escalated_scope = await client.get(
            "/authorize",
            params={**base_params, "scope": "pets:read pets:write"},
            follow_redirects=False,
        )
        duplicate_scope = await client.get(
            "/authorize",
            params={**base_params, "scope": "pets:read pets:read"},
            follow_redirects=False,
        )

    assert accepted.status_code == 302
    assert health_only.status_code == 302
    assert accepted.headers["location"].startswith("https://meo.example.test/mcp-connect?")
    assert wrong_redirect.status_code == 400
    assert wrong_redirect.json()["error"] == "invalid_request"
    for response in (
        missing_pkce,
        plain_pkce,
        malformed_pkce,
        wrong_resource,
        escalated_scope,
        duplicate_scope,
    ):
        assert response.status_code == 302
        query = parse_qs(urlparse(response.headers["location"]).query)
        assert query["error"][0] in {"invalid_request", "invalid_scope"}
        assert query["state"] == ["state-1"]

    async with sessions() as session:
        request = await session.scalar(select(AuthorizationRequest))
        assert request is not None
        remaining = request.expires_at.replace(tzinfo=now().tzinfo) - now()
        assert CONSENT_TTL - timedelta(seconds=5) <= remaining <= CONSENT_TTL
    await engine.dispose()


@pytest.mark.asyncio
async def test_callback_code_is_five_minutes_single_use_and_client_credentials_are_hashed(
    tmp_path,
) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "code.db")
    provider = DatabaseOAuthProvider(sessions, settings)
    client_info = public_client()
    await provider.register_client(client_info)
    request_id = uuid4()
    challenge = s256("v" * 64)
    async with sessions() as session:
        session.add(
            AuthorizationRequest(
                id=request_id,
                client_id=client_info.client_id or "",
                redirect_uri="http://127.0.0.1/callback",
                redirect_uri_explicit=True,
                state="callback-state",
                scopes=ALLOWED_SCOPES,
                code_challenge=challenge,
                resource=settings.resource,
                client_name="Test MCP client",
                expires_at=now() + CONSENT_TTL,
            )
        )
        await session.commit()

    with respx.mock:
        respx.post("https://meo.example.test/api/mcp-auth/exchange").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"sanctum_token": "1|delegated-secret", "user_id": 42}},
            )
        )
        redirect = await provider.complete_meo_callback(str(request_id), "meo-exchange-code", None)

    authorization_code = parse_qs(urlparse(redirect).query)["code"][0]
    async with sessions() as session:
        record = await session.scalar(select(AuthorizationCodeRecord))
        grant = await session.scalar(select(Grant))
        assert record is not None and grant is not None
        assert record.code_hash == digest(authorization_code)
        assert authorization_code not in record.code_hash
        assert "delegated-secret" not in grant.delegated_token_ciphertext
        assert (
            TokenCipher(settings.token_encryption_key).decrypt(grant.delegated_token_ciphertext)
            == "1|delegated-secret"
        )
        remaining = record.expires_at.replace(tzinfo=now().tzinfo) - now()
        assert AUTHORIZATION_CODE_TTL - timedelta(seconds=5) <= remaining <= AUTHORIZATION_CODE_TTL

    loaded = await provider.load_authorization_code(client_info, authorization_code)
    assert loaded is not None
    tokens = await provider.exchange_authorization_code(client_info, loaded)
    assert tokens.expires_in == int(ACCESS_TOKEN_TTL.total_seconds())
    assert await provider.load_authorization_code(client_info, authorization_code) is None
    with pytest.raises(TokenError, match="already used"):
        await provider.exchange_authorization_code(client_info, loaded)

    async with sessions() as session:
        access = await session.scalar(select(AccessTokenRecord))
        refresh = await session.scalar(select(RefreshTokenRecord))
        assert access is not None and refresh is not None
        assert access.token_hash == digest(tokens.access_token)
        assert refresh.token_hash == digest(tokens.refresh_token or "")
        assert tokens.access_token not in access.token_hash
        assert (tokens.refresh_token or "") not in refresh.token_hash
    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_and_replayed_consent_callbacks_are_rejected_before_exchange(
    tmp_path,
) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "expired-consent.db")
    provider = DatabaseOAuthProvider(sessions, settings)
    request_id = uuid4()
    async with sessions() as session:
        session.add(
            AuthorizationRequest(
                id=request_id,
                client_id="public-client",
                redirect_uri="http://127.0.0.1/callback",
                redirect_uri_explicit=True,
                state=None,
                scopes=ALLOWED_SCOPES,
                code_challenge=s256("v" * 64),
                resource=settings.resource,
                client_name="Test MCP client",
                expires_at=now() - timedelta(seconds=1),
            )
        )
        await session.commit()

    with respx.mock(assert_all_called=False) as router:
        exchange = router.post("https://meo.example.test/api/mcp-auth/exchange").mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(Exception, match="invalid or expired"):
            await provider.complete_meo_callback(str(request_id), "unused-code", None)
        assert not exchange.called

    async with sessions() as session:
        request = await session.get(AuthorizationRequest, request_id)
        assert request is not None
        request.expires_at = now() + timedelta(minutes=1)
        request.consumed_at = now()
        await session.commit()
    with pytest.raises(Exception, match="invalid or expired"):
        await provider.complete_meo_callback(str(request_id), None, "access_denied")
    await engine.dispose()


@pytest.mark.asyncio
async def test_token_endpoint_enforces_pkce_redirect_and_resource(tmp_path) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "token-endpoint.db")
    client_info = public_client()
    provider = DatabaseOAuthProvider(sessions, settings)
    await provider.register_client(client_info)
    verifier = "correct-verifier-" + "x" * 48
    code = "authorization-code"
    grant = Grant(
        id=uuid4(),
        client_id=client_info.client_id or "",
        subject="42",
        scopes=ALLOWED_SCOPES,
        delegated_token_ciphertext=TokenCipher(settings.token_encryption_key).encrypt(
            "1|delegated"
        ),
        expires_at=now() + REFRESH_TOKEN_TTL,
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        session.add(
            AuthorizationCodeRecord(
                code_hash=digest(code),
                grant_id=grant.id,
                client_id=client_info.client_id or "",
                scopes=ALLOWED_SCOPES,
                code_challenge=s256(verifier),
                redirect_uri="http://127.0.0.1/callback",
                redirect_uri_explicit=True,
                resource=settings.resource,
                subject="42",
                expires_at=now() + AUTHORIZATION_CODE_TTL,
            )
        )
        await session.commit()

    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://127.0.0.1/callback",
        "client_id": client_info.client_id,
        "code_verifier": verifier,
        "resource": settings.resource,
    }
    async with httpx.AsyncClient(
        transport=transport, base_url=str(settings.public_base_url)
    ) as client:
        wrong_resource = await client.post(
            "/token", data={**form, "resource": "https://other.example.test/mcp"}
        )
        missing_resource = await client.post(
            "/token", data={key: value for key, value in form.items() if key != "resource"}
        )
        wrong_redirect = await client.post(
            "/token", data={**form, "redirect_uri": "http://127.0.0.1/other"}
        )
        wrong_verifier = await client.post(
            "/token", data={**form, "code_verifier": "incorrect-verifier"}
        )
        accepted = await client.post("/token", data=form)
        replay = await client.post("/token", data=form)

    assert wrong_resource.json()["error"] == "invalid_target"
    assert missing_resource.json()["error"] == "invalid_target"
    assert wrong_redirect.json()["error"] == "invalid_request", wrong_redirect.text
    assert wrong_verifier.json()["error"] == "invalid_grant", wrong_verifier.text
    assert accepted.status_code == 200
    assert accepted.json()["expires_in"] == 3600
    assert replay.json()["error"] == "invalid_grant"
    await engine.dispose()


@pytest.mark.asyncio
async def test_access_expiry_refresh_rotation_ceiling_and_replay_revocation(tmp_path) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "refresh.db")
    provider = DatabaseOAuthProvider(sessions, settings)
    client_info = public_client()
    await provider.register_client(client_info)
    grant = Grant(
        id=uuid4(),
        client_id=client_info.client_id or "",
        subject="42",
        scopes=ALLOWED_SCOPES,
        delegated_token_ciphertext=TokenCipher(settings.token_encryption_key).encrypt(
            "1|delegated"
        ),
        expires_at=now() + timedelta(days=2),
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        initial = await provider._issue_tokens(
            session, grant, client_info.client_id or "", ALLOWED_SCOPES
        )
        await session.commit()

    loaded_access = await provider.load_access_token(initial.access_token)
    assert loaded_access is not None
    assert isinstance(loaded_access.expires_at, int)
    assert 3595 <= (loaded_access.expires_at or 0) - int(now().timestamp()) <= 3600
    loaded_refresh = await provider.load_refresh_token(client_info, initial.refresh_token or "")
    assert loaded_refresh is not None
    rotated = await provider.exchange_refresh_token(client_info, loaded_refresh, ALLOWED_SCOPES)
    assert rotated.refresh_token != initial.refresh_token
    assert await provider.load_refresh_token(client_info, rotated.refresh_token or "") is not None

    async with sessions() as session:
        newest = await session.scalar(
            select(RefreshTokenRecord).where(
                RefreshTokenRecord.token_hash == digest(rotated.refresh_token or "")
            )
        )
        assert newest is not None
        assert newest.expires_at.replace(tzinfo=now().tzinfo) <= grant.expires_at.replace(
            tzinfo=now().tzinfo
        )

    with pytest.raises(TokenError, match="Scope escalation"):
        await provider.exchange_refresh_token(
            client_info,
            await provider.load_refresh_token(client_info, rotated.refresh_token or ""),
            ["pets:write"],
        )

    with respx.mock:
        respx.post("https://meo.example.test/api/mcp-auth/revoke").mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(TokenError, match="replay detected"):
            await provider.exchange_refresh_token(client_info, loaded_refresh, ALLOWED_SCOPES)

    assert await provider.load_access_token(rotated.access_token) is None
    assert await provider.load_refresh_token(client_info, rotated.refresh_token or "") is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_revocation_is_local_even_when_upstream_revocation_fails(tmp_path) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "revoke.db")
    provider = DatabaseOAuthProvider(sessions, settings)
    grant = Grant(
        id=uuid4(),
        client_id="public-client",
        subject="42",
        scopes=ALLOWED_SCOPES,
        delegated_token_ciphertext=TokenCipher(settings.token_encryption_key).encrypt(
            "1|delegated"
        ),
        expires_at=now() + REFRESH_TOKEN_TTL,
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        issued = await provider._issue_tokens(session, grant, "public-client", ALLOWED_SCOPES)
        await session.commit()

    with respx.mock:
        upstream = respx.post("https://meo.example.test/api/mcp-auth/revoke").mock(
            side_effect=httpx.ConnectError("offline")
        )
        await provider.revoke_token(
            AccessToken(
                token=issued.access_token,
                client_id="public-client",
                scopes=ALLOWED_SCOPES,
                resource=settings.resource,
            )
        )
        assert upstream.called

    assert await provider.load_access_token(issued.access_token) is None
    assert await provider.load_refresh_token(public_client(), issued.refresh_token or "") is None
    async with sessions() as session:
        access = await session.scalar(select(AccessTokenRecord))
        refresh = await session.scalar(select(RefreshTokenRecord))
        stored_grant = await session.get(Grant, grant.id)
        assert access is not None and access.revoked_at is not None
        assert refresh is not None and refresh.revoked_at is not None
        assert stored_grant is not None and stored_grant.revoked_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_access_refresh_and_grant_are_not_loaded(tmp_path) -> None:
    engine, sessions, settings = await oauth_store(tmp_path, "expiry.db")
    provider = DatabaseOAuthProvider(sessions, settings)
    grant = Grant(
        id=uuid4(),
        client_id="public-client",
        subject="42",
        scopes=ALLOWED_SCOPES,
        delegated_token_ciphertext=TokenCipher(settings.token_encryption_key).encrypt(
            "1|delegated"
        ),
        expires_at=now() - timedelta(seconds=1),
    )
    async with sessions() as session:
        session.add(grant)
        await session.flush()
        session.add_all(
            [
                AccessTokenRecord(
                    token_hash=digest("access"),
                    grant_id=grant.id,
                    client_id="public-client",
                    scopes=ALLOWED_SCOPES,
                    subject="42",
                    resource=settings.resource,
                    expires_at=now() + ACCESS_TOKEN_TTL,
                ),
                RefreshTokenRecord(
                    token_hash=digest("refresh"),
                    family_id=uuid4(),
                    grant_id=grant.id,
                    client_id="public-client",
                    scopes=ALLOWED_SCOPES,
                    subject="42",
                    expires_at=now() - timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()
    assert await provider.load_access_token("access") is None
    assert await provider.load_refresh_token(public_client(), "refresh") is None
    await engine.dispose()
