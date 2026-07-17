import base64
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import respx
from sqlalchemy import func, select

from meo_mcp.config import Settings
from meo_mcp.database import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    AuthorizationRequest,
    Base,
    Grant,
    make_session_factory,
)
from meo_mcp.oauth import ALLOWED_SCOPES, DatabaseOAuthProvider
from meo_mcp.security import digest, now


@pytest.mark.asyncio
async def test_callback_persists_grant_before_authorization_code(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'oauth.db'}"
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    settings = Settings(
        database_url=database_url,
        meo_base_url="https://meo.example.test",
        meo_connector_api_key="connector-key",
        meo_connector_hmac_secret="hmac",
        token_encryption_key=key,
    )
    engine, sessions = make_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    request_id = uuid4()
    async with sessions() as session:
        session.add(
            AuthorizationRequest(
                id=request_id,
                client_id="client-id",
                redirect_uri="http://127.0.0.1/callback",
                redirect_uri_explicit=True,
                state="state",
                scopes=ALLOWED_SCOPES,
                code_challenge="challenge",
                resource=settings.resource,
                client_name="Test client",
                expires_at=now() + timedelta(minutes=10),
            )
        )
        await session.commit()

    provider = DatabaseOAuthProvider(sessions, settings)
    with respx.mock:
        respx.post("https://meo.example.test/api/mcp-auth/exchange").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"sanctum_token": "1|delegated", "user_id": 42}},
            )
        )
        redirect = await provider.complete_meo_callback(str(request_id), "exchange-code", None)

    assert redirect.startswith("http://127.0.0.1/callback?code=")
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Grant)) == 1
        assert await session.scalar(select(func.count()).select_from(AuthorizationCodeRecord)) == 1
        request = await session.get(AuthorizationRequest, request_id)
        assert request is not None and request.consumed_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_load_access_token_converts_database_timestamp_to_integer_epoch(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'access-token.db'}"
    key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    settings = Settings(database_url=database_url, token_encryption_key=key)
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

    loaded = await DatabaseOAuthProvider(sessions, settings).load_access_token(access_token)

    assert loaded is not None
    assert isinstance(loaded.expires_at, int)

    await engine.dispose()
