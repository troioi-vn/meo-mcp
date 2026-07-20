from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .database import AccessTokenRecord, Grant
from .security import TokenCipher, digest


class MeoApiError(Exception):
    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload["message"])
        self.payload = payload


class MeoApi:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings):
        self.sessions = sessions
        self.settings = settings
        self.cipher = TokenCipher(settings.token_encryption_key)

    async def list_pets(self) -> dict[str, Any]:
        delegated = await self._delegated_token("pets:read")
        payload = await self._get(delegated, "/api/my-pets")
        return {"pets": [self._pet_summary(item) for item in self._items(payload)]}

    async def find_pets(
        self, name: str | None = None, species: str | None = None
    ) -> dict[str, Any]:
        name = self._optional_text(name, "name")
        species = self._optional_text(species, "species")
        if name is None and species is None:
            self._error("validation_error", "Provide a non-blank name or species.", False)
        pets = (await self.list_pets())["pets"]
        name_key, species_key = (name or "").casefold(), (species or "").casefold()
        matches = [
            pet
            for pet in pets
            if (not name_key or name_key in str(pet.get("name") or "").casefold())
            and (not species_key or species_key == str(pet.get("species") or "").casefold())
        ]
        matches.sort(
            key=lambda pet: (
                str(pet.get("name") or "").casefold() != name_key,
                str(pet.get("name") or "").casefold(),
                pet.get("id") or 0,
            )
        )
        return {"candidates": matches}

    async def get_pet(self, pet_id: int) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        delegated = await self._delegated_token("pets:read")
        payload = await self._get(delegated, f"/api/pets/{pet_id}")
        return {"pet": self._pet_detail(self._object(payload))}

    async def list_pet_types(self) -> dict[str, Any]:
        await self._delegated_token("pets:read")
        payload = await self._get(None, "/api/pet-types")
        fields = (
            "id",
            "name",
            "slug",
            "placement_requests_allowed",
            "weight_tracking_allowed",
            "microchips_allowed",
        )
        return {
            "pet_types": [{key: item.get(key) for key in fields} for item in self._items(payload)]
        }

    async def list_weights(self, pet_id: int, page: int = 1) -> dict[str, Any]:
        return await self._health_list(pet_id, page, "weights", "weights", self._weight)

    async def get_weight(self, pet_id: int, weight_id: int) -> dict[str, Any]:
        return {
            "weight": await self._health_detail(
                pet_id, weight_id, "weight_id", "weights", self._weight
            )
        }

    async def list_vaccinations(
        self, pet_id: int, page: int = 1, status: str = "active"
    ) -> dict[str, Any]:
        if status not in {"active", "completed", "all"}:
            self._error("validation_error", "status must be active, completed, or all.", False)
        return await self._health_list(
            pet_id,
            page,
            "vaccinations",
            "vaccinations",
            self._vaccination,
            {"status": status},
        )

    async def get_vaccination(self, pet_id: int, vaccination_id: int) -> dict[str, Any]:
        item = await self._health_detail(
            pet_id, vaccination_id, "vaccination_id", "vaccinations", self._vaccination
        )
        return {"vaccination": item}

    async def list_medical_records(
        self, pet_id: int, page: int = 1, record_type: str | None = None
    ) -> dict[str, Any]:
        record_type = self._optional_text(record_type, "record_type")
        return await self._health_list(
            pet_id,
            page,
            "medical-records",
            "medical_records",
            self._medical_record,
            {"record_type": record_type} if record_type else None,
        )

    async def get_medical_record(self, pet_id: int, record_id: int) -> dict[str, Any]:
        item = await self._health_detail(
            pet_id, record_id, "record_id", "medical-records", self._medical_record
        )
        return {"medical_record": item}

    async def get_pets_overview(
        self,
        name: str | None = None,
        species: str | None = None,
        only_with_upcoming_vaccination: bool = False,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> dict[str, Any]:
        if sort_by not in {
            "name",
            "next_vaccination_due_at",
            "next_birthday_at",
        } or sort_order not in {"asc", "desc"}:
            self._error("validation_error", "Invalid overview sort option.", False)
        await self._delegated_token("pets:read", "health:read")
        summaries = (
            (await self.find_pets(name, species))["candidates"]
            if name or species
            else (await self.list_pets())["pets"]
        )

        async def enrich(pet: dict[str, Any]) -> dict[str, Any]:
            pet_id = pet["id"]
            detail_result, vaccination_result, weight_result = await asyncio.gather(
                self.get_pet(pet_id),
                self.list_vaccinations(pet_id, status="active"),
                self.list_weights(pet_id),
                return_exceptions=True,
            )
            detail = detail_result.get("pet", {}) if isinstance(detail_result, dict) else {}
            vaccinations = (
                vaccination_result.get("vaccinations", [])
                if isinstance(vaccination_result, dict)
                else []
            )
            vaccinations = [
                {
                    key: vaccination.get(key)
                    for key in ("id", "vaccine_name", "administered_at", "due_at")
                }
                for vaccination in vaccinations
            ]
            vaccinations.sort(
                key=lambda item: (
                    item.get("due_at") is None,
                    item.get("due_at") or "9999-12-31",
                    item.get("administered_at") or "",
                    str(item.get("vaccine_name") or "").casefold(),
                )
            )
            weights = weight_result.get("weights", []) if isinstance(weight_result, dict) else []
            weights.sort(
                key=lambda item: (item.get("record_date") or "", item.get("id") or 0),
                reverse=True,
            )
            weights = weights[:5]
            upcoming = [
                v
                for v in vaccinations
                if v.get("due_at") and v["due_at"] >= date.today().isoformat()
            ]
            upcoming.sort(key=lambda item: item["due_at"])
            birthday = self._next_birthday(detail)
            return {
                **pet,
                **{
                    key: detail.get(key)
                    for key in (
                        "birthday_precision",
                        "birthday_year",
                        "birthday_month",
                        "birthday_day",
                    )
                },
                "next_birthday_at": birthday.isoformat() if birthday else None,
                "days_until_next_birthday": (birthday - date.today()).days if birthday else None,
                "active_vaccinations": vaccinations,
                "recent_weights": weights,
                "next_vaccination_due_at": upcoming[0].get("due_at") if upcoming else None,
                "next_vaccination_name": upcoming[0].get("vaccine_name") if upcoming else None,
                "vaccination_data_status": "available"
                if isinstance(vaccination_result, dict)
                else "unavailable",
                "weights_data_status": "available"
                if isinstance(weight_result, dict)
                else "unavailable",
            }

        items = list(await asyncio.gather(*(enrich(pet) for pet in summaries)))
        if only_with_upcoming_vaccination:
            items = [item for item in items if item["next_vaccination_due_at"]]
        key = "name" if sort_by == "name" else sort_by
        items.sort(
            key=lambda item: (item.get(key) is None, str(item.get(key) or "").casefold()),
            reverse=sort_order == "desc",
        )
        return {"pets": items}

    async def _health_list(
        self,
        pet_id: int,
        page: int,
        path: str,
        key: str,
        normalizer,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(page, "page")
        delegated = await self._delegated_token("health:read")
        query = {"page": page, **(params or {})}
        payload = await self._get(delegated, f"/api/pets/{pet_id}/{path}", query)
        return {
            key: [normalizer(item) for item in self._items(payload)],
            "pagination": self._pagination(payload),
        }

    async def _health_detail(
        self, pet_id: int, record_id: int, record_field: str, path: str, normalizer
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(record_id, record_field)
        delegated = await self._delegated_token("health:read")
        return normalizer(
            self._object(await self._get(delegated, f"/api/pets/{pet_id}/{path}/{record_id}"))
        )

    async def _delegated_token(self, *required_scopes: str) -> str:
        access = get_access_token()
        missing = [scope for scope in required_scopes if not access or scope not in access.scopes]
        if missing:
            self._error(
                "scope_required", f"{' and '.join(missing)} authorization is required.", False
            )
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
        return self.cipher.decrypt(grant.delegated_token_ciphertext)

    async def _get(
        self, delegated: str | None, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        headers = {"Authorization": f"Bearer {delegated}"} if delegated else {}
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(
                    f"{str(self.settings.meo_base_url).rstrip('/')}{path}",
                    headers=headers,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise self._tool_error(
                "upstream_unavailable",
                "Meo Mai Moi is temporarily unavailable. Try again shortly.",
                True,
            ) from exc
        errors = {
            401: (
                "upstream_unauthorized",
                "Meo Mai Moi authorization was rejected. Reconnect your account.",
                False,
            ),
            403: (
                "upstream_forbidden",
                "Meo Mai Moi denied access to the requested resource.",
                False,
            ),
            404: ("upstream_not_found", "The requested Meo Mai Moi resource was not found.", False),
            422: (
                "upstream_validation_failed",
                "Meo Mai Moi rejected the normalized request.",
                False,
            ),
            429: (
                "upstream_rate_limited",
                "Meo Mai Moi is rate-limiting requests. Try again shortly.",
                True,
            ),
        }
        if response.status_code in errors:
            code, message, retryable = errors[response.status_code]
            self._error(code, message, retryable, response.status_code)
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
            return response.json()
        except ValueError:
            self._error("upstream_malformed", "Meo Mai Moi returned malformed data.", True, 200)

    @classmethod
    def _unwrap(cls, payload: Any) -> Any:
        if not isinstance(payload, dict):
            cls._error("upstream_malformed", "Meo Mai Moi returned malformed data.", True, 200)
        return payload.get("data", payload)

    @classmethod
    def _items(cls, payload: Any) -> list[dict[str, Any]]:
        value = cls._unwrap(payload)
        if isinstance(value, dict) and isinstance(value.get("data"), list):
            value = value["data"]
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            cls._error("upstream_malformed", "Meo Mai Moi returned malformed list data.", True, 200)
        return value

    @classmethod
    def _object(cls, payload: Any) -> dict[str, Any]:
        value = cls._unwrap(payload)
        if not isinstance(value, dict):
            cls._error(
                "upstream_malformed", "Meo Mai Moi returned malformed object data.", True, 200
            )
        return value

    @classmethod
    def _pagination(cls, payload: Any) -> dict[str, Any]:
        outer = cls._unwrap(payload)
        meta = outer.get("meta", outer) if isinstance(outer, dict) else {}
        current, last, per_page, total = (
            meta.get("current_page", 1),
            meta.get("last_page", 1),
            meta.get("per_page", 25),
            meta.get("total", len(outer.get("data", [])) if isinstance(outer, dict) else 0),
        )
        return {
            "current_page": current,
            "last_page": last,
            "per_page": per_page,
            "total": total,
            "has_more": current < last,
        }

    @staticmethod
    def _pet_summary(pet: dict[str, Any]) -> dict[str, Any]:
        birthday, age = pet.get("birthday"), pet.get("age")
        if age is None and isinstance(birthday, str):
            try:
                born = date.fromisoformat(birthday[:10])
                today = date.today()
                age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            except ValueError:
                age = None
        pet_type = pet.get("pet_type")
        return {
            "id": pet.get("id"),
            "name": pet.get("name"),
            "species": pet_type.get("name") if isinstance(pet_type, dict) else pet.get("species"),
            "sex": pet.get("sex"),
            "age": age,
            "photo_url": pet.get("photo_url"),
        }

    # Compatibility alias retained for callers of the original MVP normalizer.
    _pet = _pet_summary

    @classmethod
    def _pet_detail(cls, pet: dict[str, Any]) -> dict[str, Any]:
        summary = cls._pet_summary(pet)
        fields = (
            "birthday",
            "birthday_year",
            "birthday_month",
            "birthday_day",
            "birthday_precision",
            "country",
            "state",
            "city",
            "description",
            "status",
        )
        return {
            **summary,
            **{
                key: (
                    pet.get(key, {}).get("name")
                    if key in {"country", "state", "city"} and isinstance(pet.get(key), dict)
                    else pet.get(key)
                )
                for key in fields
            },
        }

    @staticmethod
    def _weight(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "weight_kg": item.get("weight_kg", item.get("weight")),
            "record_date": item.get("record_date", item.get("date")),
        }

    @staticmethod
    def _vaccination(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "id",
                "vaccine_name",
                "administered_at",
                "due_at",
                "notes",
                "completed_at",
                "photo_url",
            )
        }

    @staticmethod
    def _medical_record(item: dict[str, Any]) -> dict[str, Any]:
        photos = item.get("photos") if isinstance(item.get("photos"), list) else []
        return {
            **{
                key: item.get(key)
                for key in ("id", "record_type", "description", "record_date", "vet_name")
            },
            "photos": [
                {key: photo.get(key) for key in ("id", "url", "thumb_url", "medium_url")}
                for photo in photos
                if isinstance(photo, dict)
            ],
        }

    @staticmethod
    def _next_birthday(pet: dict[str, Any]) -> date | None:
        if pet.get("birthday_precision") != "day":
            return None
        month, day = pet.get("birthday_month"), pet.get("birthday_day")
        if not isinstance(month, int) or not isinstance(day, int):
            birthday = pet.get("birthday")
            try:
                month, day = (
                    map(int, birthday[5:10].split("-"))
                    if isinstance(birthday, str)
                    else (None, None)
                )
            except ValueError:
                return None
        try:
            today = date.today()
            candidate = date(today.year, month, day)
            return candidate if candidate >= today else date(today.year + 1, month, day)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _positive(cls, value: int, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            cls._error("validation_error", f"{field} must be a positive integer.", False)

    @classmethod
    def _optional_text(cls, value: str | None, field: str) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            cls._error("validation_error", f"{field} must not be blank.", False)
        return value

    @staticmethod
    def _tool_error(
        code: str, message: str, retryable: bool, upstream_status: int | None = None
    ) -> MeoApiError:
        payload: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
        if upstream_status is not None:
            payload["upstream_status"] = upstream_status
        return MeoApiError(payload)

    @classmethod
    def _error(
        cls, code: str, message: str, retryable: bool, upstream_status: int | None = None
    ) -> None:
        raise cls._tool_error(code, message, retryable, upstream_status)
