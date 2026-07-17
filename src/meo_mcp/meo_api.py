from __future__ import annotations

from datetime import date

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .database import AccessTokenRecord, Grant
from .security import TokenCipher, digest


class MeoApiError(Exception):
    def __init__(self, payload: dict):
        super().__init__(payload["message"])
        self.payload = payload


class MeoApi:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings):
        self.sessions, self.settings, self.cipher = (
            sessions,
            settings,
            TokenCipher(settings.token_encryption_key),
        )

    async def list_pets(self) -> dict:
        access = get_access_token()
        if not access or "pets:read" not in access.scopes:
            self._error("scope_required", "pets:read authorization is required.", False)
        async with self.sessions() as session:
            record = await session.scalar(
                select(AccessTokenRecord).where(
                    AccessTokenRecord.token_hash == digest(access.token)
                )
            )
            grant = await session.get(Grant, record.grant_id) if record else None
        if not grant or grant.revoked_at:
            self._error(
                "authorization_inactive",
                "Authorization is no longer active. Reconnect Meo Mai Moi.",
                False,
            )
        delegated = self.cipher.decrypt(grant.delegated_token_ciphertext)
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(
                    f"{str(self.settings.meo_base_url).rstrip('/')}/api/my-pets",
                    headers={"Authorization": f"Bearer {delegated}"},
                )
        except httpx.HTTPError as exc:
            raise self._tool_error(
                "upstream_unavailable",
                "Meo Mai Moi is temporarily unavailable. Try again shortly.",
                True,
            ) from exc
        if response.status_code == 401:
            self._error(
                "upstream_unauthorized",
                "Meo Mai Moi authorization was rejected. Reconnect your account.",
                False,
                401,
            )
        if response.status_code == 403:
            self._error(
                "upstream_forbidden", "Meo Mai Moi denied access to the requested pets.", False, 403
            )
        if response.status_code == 404:
            self._error(
                "upstream_not_found",
                "The requested Meo Mai Moi resource was not found.",
                False,
                404,
            )
        if response.status_code == 429:
            self._error(
                "upstream_rate_limited",
                "Meo Mai Moi is rate-limiting requests. Try again shortly.",
                True,
                429,
            )
        if response.status_code >= 500:
            self._error(
                "upstream_server_error",
                "Meo Mai Moi is temporarily unavailable. Try again shortly.",
                True,
                response.status_code,
            )
        if response.status_code != 200:
            self._error(
                "upstream_unexpected",
                "Meo Mai Moi returned an unexpected response.",
                False,
                response.status_code,
            )
        try:
            payload = response.json()
        except ValueError:
            self._error("upstream_malformed", "Meo Mai Moi returned malformed pet data.", True, 200)
        if not isinstance(payload, dict):
            self._error("upstream_malformed", "Meo Mai Moi returned malformed pet data.", True, 200)
        pets = payload.get("data", payload)
        if not isinstance(pets, list):
            self._error("upstream_malformed", "Meo Mai Moi returned malformed pet data.", True, 200)
        return {"pets": [self._pet(pet) for pet in pets if isinstance(pet, dict)]}

    @staticmethod
    def _tool_error(
        code: str, message: str, retryable: bool, upstream_status: int | None = None
    ) -> MeoApiError:
        payload = {"code": code, "message": message, "retryable": retryable}
        if upstream_status is not None:
            payload["upstream_status"] = upstream_status
        return MeoApiError(payload)

    @classmethod
    def _error(
        cls, code: str, message: str, retryable: bool, upstream_status: int | None = None
    ) -> None:
        raise cls._tool_error(code, message, retryable, upstream_status)

    @staticmethod
    def _pet(pet: dict) -> dict:
        birthday = pet.get("birthday")
        age = pet.get("age")
        if age is None and isinstance(birthday, str):
            try:
                born = date.fromisoformat(birthday[:10])
                age = (
                    date.today().year
                    - born.year
                    - ((date.today().month, date.today().day) < (born.month, born.day))
                )
            except ValueError:
                age = None
        return {
            "id": pet.get("id"),
            "name": pet.get("name"),
            "species": (pet.get("pet_type") or {}).get("name")
            if isinstance(pet.get("pet_type"), dict)
            else pet.get("species"),
            "sex": pet.get("sex"),
            "age": age,
            "photo_url": pet.get("photo_url"),
        }
