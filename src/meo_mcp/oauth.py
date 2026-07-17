from __future__ import annotations

import re
from datetime import timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .database import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    AuthorizationRequest,
    Grant,
    OAuthClient,
    RefreshTokenRecord,
)
from .security import (
    TokenCipher,
    as_utc,
    digest,
    epoch_seconds,
    is_expired,
    now,
    signed_reference,
    token,
)

ACCESS_TOKEN_TTL = timedelta(hours=1)
AUTHORIZATION_CODE_TTL = timedelta(minutes=5)
CONSENT_TTL = timedelta(minutes=10)
REFRESH_TOKEN_TTL = timedelta(days=90)
ALLOWED_SCOPES = ["pets:read"]
PKCE_S256_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class DatabaseOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings):
        self.sessions = sessions
        self.settings = settings
        self.cipher = TokenCipher(settings.token_encryption_key)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(OAuthClient).where(OAuthClient.client_id == client_id)
            )
            return (
                OAuthClientInformationFull.model_validate(record.client_metadata)
                if record
                else None
            )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id or not client_info.redirect_uris:
            raise RegistrationError(
                "invalid_client_metadata",
                "A public client ID and at least one redirect URI are required.",
            )
        if client_info.token_endpoint_auth_method != "none" or client_info.client_secret:
            raise RegistrationError(
                "invalid_client_metadata",
                "Only public clients using token_endpoint_auth_method=none are supported.",
            )
        if any(uri.fragment or uri.username or uri.password for uri in client_info.redirect_uris):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Redirect URIs must not contain fragments or user information.",
            )
        stored_metadata = client_info.model_dump(mode="json", exclude={"client_secret"})
        stored_metadata["client_secret"] = None
        stored_metadata["client_secret_expires_at"] = None
        async with self.sessions() as session:
            present = await session.scalar(
                select(OAuthClient).where(OAuthClient.client_id == client_info.client_id)
            )
            if present:
                return
            session.add(
                OAuthClient(client_id=client_info.client_id, client_metadata=stored_metadata)
            )
            await session.commit()

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if params.resource != self.settings.resource:
            raise AuthorizeError(
                "invalid_request", "The resource parameter must name this MCP endpoint."
            )
        if not PKCE_S256_PATTERN.fullmatch(params.code_challenge):
            raise AuthorizeError("invalid_request", "A valid S256 PKCE challenge is required.")
        scopes = params.scopes or []
        if scopes != ALLOWED_SCOPES:
            raise AuthorizeError("invalid_scope", "Only pets:read is available.")
        request = AuthorizationRequest(
            client_id=client.client_id or "",
            redirect_uri=str(params.redirect_uri),
            redirect_uri_explicit=params.redirect_uri_provided_explicitly,
            state=params.state,
            scopes=scopes,
            code_challenge=params.code_challenge,
            resource=params.resource,
            client_name=client.client_name or client.client_id or "MCP client",
            expires_at=now() + CONSENT_TTL,
        )
        async with self.sessions() as session:
            session.add(request)
            await session.commit()
            await session.refresh(request)
        reference = signed_reference(
            {
                "request_id": str(request.id),
                "client_name": request.client_name,
                "scopes": scopes,
                "exp": int(request.expires_at.timestamp()),
            },
            self.settings.meo_connector_hmac_secret,
        )
        return f"{str(self.settings.meo_base_url).rstrip('/')}/mcp-connect?{urlencode({'request_ref': reference})}"

    async def complete_meo_callback(
        self, request_id: str, exchange_code: str | None, error: str | None
    ) -> str:
        async with self.sessions() as session:
            record = await session.get(AuthorizationRequest, UUID(request_id))
            if not record or record.consumed_at or is_expired(record.expires_at):
                raise AuthorizeError(
                    "access_denied", "Authorization request is invalid or expired."
                )
        if error:
            async with self.sessions() as session:
                denied_request = await session.get(
                    AuthorizationRequest, UUID(request_id), with_for_update=True
                )
                if (
                    not denied_request
                    or denied_request.consumed_at
                    or is_expired(denied_request.expires_at)
                ):
                    raise AuthorizeError(
                        "access_denied", "Authorization request is invalid or expired."
                    )
                denied_request.consumed_at = now()
                await session.commit()
            return self._client_redirect(record, error=error)
        if not exchange_code:
            raise AuthorizeError("access_denied", "Authorization was not completed.")
        payload = await self._exchange_meo_code(exchange_code)
        authorization_code = token()
        grant = Grant(
            id=uuid4(),
            client_id=record.client_id,
            subject=str(payload["user_id"]),
            scopes=record.scopes,
            delegated_token_ciphertext=self.cipher.encrypt(str(payload["sanctum_token"])),
            expires_at=now() + REFRESH_TOKEN_TTL,
        )
        try:
            async with self.sessions() as session:
                locked_request = await session.get(
                    AuthorizationRequest,
                    UUID(request_id),
                    with_for_update=True,
                )
                if (
                    not locked_request
                    or locked_request.consumed_at
                    or is_expired(locked_request.expires_at)
                ):
                    raise AuthorizeError(
                        "access_denied",
                        "Authorization request is invalid or expired.",
                    )

                session.add(grant)
                # The code references this grant. Flush explicitly so SQLAlchemy
                # cannot emit the authorization-code INSERT first.
                await session.flush()
                session.add(
                    AuthorizationCodeRecord(
                        code_hash=digest(authorization_code),
                        grant_id=grant.id,
                        client_id=locked_request.client_id,
                        scopes=locked_request.scopes,
                        code_challenge=locked_request.code_challenge,
                        redirect_uri=locked_request.redirect_uri,
                        redirect_uri_explicit=locked_request.redirect_uri_explicit,
                        resource=locked_request.resource,
                        subject=str(payload["user_id"]),
                        expires_at=now() + AUTHORIZATION_CODE_TTL,
                    )
                )
                locked_request.consumed_at = now()
                await session.commit()
        except Exception:
            await self._revoke_meo_token(str(payload["sanctum_token"]))
            raise
        return self._client_redirect(record, code=authorization_code)

    async def _exchange_meo_code(self, code: str) -> dict:
        headers = {"Authorization": f"Bearer {self.settings.meo_connector_api_key}"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{str(self.settings.meo_base_url).rstrip('/')}/api/mcp-auth/exchange",
                json={"code": code},
                headers=headers,
            )
        if response.status_code != 200:
            raise AuthorizeError("server_error", "Meo token exchange failed.")
        payload = response.json().get("data", response.json())
        if (
            not isinstance(payload, dict)
            or not payload.get("sanctum_token")
            or payload.get("user_id") is None
        ):
            raise AuthorizeError("server_error", "Meo token exchange returned an invalid response.")
        return payload

    async def _revoke_meo_token(self, delegated_token: str) -> None:
        headers = {"Authorization": f"Bearer {self.settings.meo_connector_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{str(self.settings.meo_base_url).rstrip('/')}/api/mcp-auth/revoke",
                    json={"token": delegated_token},
                    headers=headers,
                )
        except httpx.HTTPError:
            # Best effort: the local grant never committed, so no client-facing
            # credential can use this delegation even if upstream is unavailable.
            pass

    def _client_redirect(
        self, request: AuthorizationRequest, code: str | None = None, error: str | None = None
    ) -> str:
        parameters: dict[str, str] = {}
        if code:
            parameters["code"] = code
        if error:
            parameters["error"] = error
        if request.state:
            parameters["state"] = request.state
        delimiter = "&" if "?" in request.redirect_uri else "?"
        return request.redirect_uri + delimiter + urlencode(parameters)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(AuthorizationCodeRecord).where(
                    AuthorizationCodeRecord.code_hash == digest(authorization_code)
                )
            )
            if (
                not record
                or record.client_id != client.client_id
                or is_expired(record.expires_at)
                or record.consumed_at
            ):
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=record.scopes,
                expires_at=epoch_seconds(record.expires_at),
                client_id=record.client_id,
                code_challenge=record.code_challenge,
                redirect_uri=record.redirect_uri,
                redirect_uri_provided_explicitly=record.redirect_uri_explicit,
                resource=record.resource,
                subject=record.subject,
            )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        async with self.sessions() as session:
            record = await session.scalar(
                select(AuthorizationCodeRecord)
                .where(AuthorizationCodeRecord.code_hash == digest(authorization_code.code))
                .with_for_update()
            )
            if not record or record.consumed_at or is_expired(record.expires_at):
                raise TokenError("invalid_grant", "Authorization code is invalid or already used.")
            record.consumed_at = now()
            grant = await session.get(Grant, record.grant_id)
            if not grant or grant.revoked_at or is_expired(grant.expires_at):
                raise TokenError("invalid_grant", "Grant is no longer active.")
            response = await self._issue_tokens(
                session, grant, client.client_id or "", record.scopes
            )
            await session.commit()
            return response

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(RefreshTokenRecord).where(
                    RefreshTokenRecord.token_hash == digest(refresh_token)
                )
            )
            if (
                not record
                or record.client_id != client.client_id
                or is_expired(record.expires_at)
                or record.revoked_at
            ):
                return None
            return RefreshToken(
                token=refresh_token,
                client_id=record.client_id,
                scopes=record.scopes,
                expires_at=epoch_seconds(record.expires_at),
                subject=record.subject,
            )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        async with self.sessions() as session:
            record = await session.scalar(
                select(RefreshTokenRecord)
                .where(RefreshTokenRecord.token_hash == digest(refresh_token.token))
                .with_for_update()
            )
            if (
                not record
                or record.client_id != client.client_id
                or is_expired(record.expires_at)
                or record.revoked_at
            ):
                raise TokenError("invalid_grant", "Refresh token is invalid.")
            if record.consumed_at:
                grant = await session.get(Grant, record.grant_id)
                await session.execute(
                    update(RefreshTokenRecord)
                    .where(RefreshTokenRecord.family_id == record.family_id)
                    .values(revoked_at=now())
                )
                await session.execute(
                    update(AccessTokenRecord)
                    .where(AccessTokenRecord.grant_id == record.grant_id)
                    .values(revoked_at=now())
                )
                await session.execute(
                    update(Grant).where(Grant.id == record.grant_id).values(revoked_at=now())
                )
                await session.commit()
                if grant:
                    await self._revoke_grant_upstream(grant)
                raise TokenError(
                    "invalid_grant", "Refresh token replay detected; token family revoked."
                )
            if scopes and scopes != record.scopes:
                raise TokenError("invalid_scope", "Scope escalation is not allowed.")
            record.consumed_at = now()
            grant = await session.get(Grant, record.grant_id)
            if not grant or grant.revoked_at or is_expired(grant.expires_at):
                raise TokenError("invalid_grant", "Grant is no longer active.")
            response = await self._issue_tokens(
                session, grant, record.client_id, record.scopes, family_id=record.family_id
            )
            await session.commit()
            return response

    async def _issue_tokens(
        self, session: AsyncSession, grant: Grant, client_id: str, scopes: list[str], family_id=None
    ) -> OAuthToken:
        access_value, refresh_value = token(), token()
        expiry = now() + ACCESS_TOKEN_TTL
        refresh_expiry = min(now() + REFRESH_TOKEN_TTL, as_utc(grant.expires_at))
        session.add_all(
            [
                AccessTokenRecord(
                    token_hash=digest(access_value),
                    grant_id=grant.id,
                    client_id=client_id,
                    scopes=scopes,
                    subject=grant.subject,
                    resource=self.settings.resource,
                    expires_at=expiry,
                ),
                RefreshTokenRecord(
                    token_hash=digest(refresh_value),
                    family_id=family_id or uuid4(),
                    grant_id=grant.id,
                    client_id=client_id,
                    scopes=scopes,
                    subject=grant.subject,
                    expires_at=refresh_expiry,
                ),
            ]
        )
        return OAuthToken(
            access_token=access_value,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
            scope=" ".join(scopes),
            refresh_token=refresh_value,
        )

    async def load_access_token(self, value: str) -> AccessToken | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(AccessTokenRecord).where(AccessTokenRecord.token_hash == digest(value))
            )
            if (
                not record
                or record.revoked_at
                or is_expired(record.expires_at)
                or record.resource != self.settings.resource
            ):
                return None
            grant = await session.get(Grant, record.grant_id)
            if not grant or grant.revoked_at or is_expired(grant.expires_at):
                return None
            return AccessToken(
                token=value,
                client_id=record.client_id,
                scopes=record.scopes,
                expires_at=epoch_seconds(record.expires_at),
                resource=record.resource,
                subject=record.subject,
            )

    async def revoke_token(self, value: AccessToken | RefreshToken) -> None:
        grant: Grant | None = None
        async with self.sessions() as session:
            access = await session.scalar(
                select(AccessTokenRecord).where(AccessTokenRecord.token_hash == digest(value.token))
            )
            refresh = await session.scalar(
                select(RefreshTokenRecord).where(
                    RefreshTokenRecord.token_hash == digest(value.token)
                )
            )
            grant_id = access.grant_id if access else refresh.grant_id if refresh else None
            if grant_id:
                grant = await session.get(Grant, grant_id)
                await session.execute(
                    update(Grant).where(Grant.id == grant_id).values(revoked_at=now())
                )
                await session.execute(
                    update(AccessTokenRecord)
                    .where(AccessTokenRecord.grant_id == grant_id)
                    .values(revoked_at=now())
                )
                await session.execute(
                    update(RefreshTokenRecord)
                    .where(RefreshTokenRecord.grant_id == grant_id)
                    .values(revoked_at=now())
                )
                await session.commit()
        if grant:
            await self._revoke_grant_upstream(grant)

    async def _revoke_grant_upstream(self, grant: Grant) -> None:
        try:
            delegated_token = self.cipher.decrypt(grant.delegated_token_ciphertext)
        except Exception:
            return
        await self._revoke_meo_token(delegated_token)
