from __future__ import annotations

from datetime import date

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .database import AccessTokenRecord, Grant
from .security import TokenCipher, digest


class MeoApi:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings):
        self.sessions, self.settings, self.cipher = sessions, settings, TokenCipher(settings.token_encryption_key)

    async def list_pets(self) -> dict:
        access = get_access_token()
        if not access or "pets:read" not in access.scopes:
            raise ToolError("pets:read authorization is required.")
        async with self.sessions() as session:
            record = await session.scalar(select(AccessTokenRecord).where(AccessTokenRecord.token_hash == digest(access.token)))
            grant = await session.get(Grant, record.grant_id) if record else None
        if not grant or grant.revoked_at:
            raise ToolError("Authorization is no longer active. Reconnect Meo Mai Moi.")
        delegated = self.cipher.decrypt(grant.delegated_token_ciphertext)
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(f"{str(self.settings.meo_base_url).rstrip('/')}/api/my-pets", headers={"Authorization": f"Bearer {delegated}"})
        except httpx.HTTPError as exc:
            raise ToolError("Meo Mai Moi is temporarily unavailable. Try again shortly.") from exc
        if response.status_code in (401, 403):
            raise ToolError("Meo Mai Moi authorization was rejected. Reconnect your account.")
        if response.status_code == 429:
            raise ToolError("Meo Mai Moi is rate-limiting requests. Try again shortly.")
        if response.status_code >= 500:
            raise ToolError("Meo Mai Moi is temporarily unavailable. Try again shortly.")
        if response.status_code != 200:
            raise ToolError("Meo Mai Moi returned an unexpected response.")
        payload = response.json()
        pets = payload.get("data", payload)
        if not isinstance(pets, list):
            raise ToolError("Meo Mai Moi returned malformed pet data.")
        return {"pets": [self._pet(pet) for pet in pets if isinstance(pet, dict)]}

    @staticmethod
    def _pet(pet: dict) -> dict:
        birthday = pet.get("birthday")
        age = pet.get("age")
        if age is None and isinstance(birthday, str):
            try:
                born = date.fromisoformat(birthday[:10])
                age = date.today().year - born.year - ((date.today().month, date.today().day) < (born.month, born.day))
            except ValueError:
                age = None
        return {"id": pet.get("id"), "name": pet.get("name"), "species": (pet.get("pet_type") or {}).get("name") if isinstance(pet.get("pet_type"), dict) else pet.get("species"), "sex": pet.get("sex"), "age": age, "photo_url": pet.get("photo_url")}
