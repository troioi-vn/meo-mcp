from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .database import AccessTokenRecord, Grant
from .security import TokenCipher, digest

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MEDICAL_RECORD_TYPES = {
    "checkup",
    "deworming",
    "flea_treatment",
    "surgery",
    "dental",
    "other",
}


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

    async def create_pet(
        self,
        name: str,
        species: str,
        country: str,
        idempotency_key: str,
        sex: str | None = None,
        birth_date: date | None = None,
        birth_month_year: str | None = None,
        age_months: int | None = None,
        description: str | None = None,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        delegated = await self._delegated_token("pets:read", "pets:write")
        key = self._idempotency_key(idempotency_key)
        name = self._required_text(name, "name", 255)
        species = self._required_text(species, "species", 255)
        country = self._country(country)
        description = self._optional_text(description, "description")
        normalized_sex = self._sex(sex)
        birthday = self._birth_fields(birth_date, birth_month_year, age_months)
        pet_type_id, _ = await self._resolve_pet_type(species)

        upstream: dict[str, Any] = {
            "name": name,
            "pet_type_id": pet_type_id,
            "country": country,
            "allow_duplicate": allow_duplicate,
            **birthday,
        }
        if normalized_sex is not None:
            upstream["sex"] = normalized_sex
        if description is not None:
            upstream["description"] = description
        created = await self._request(
            delegated,
            "POST",
            "/api/pets",
            json_data=upstream,
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        pet_id = self._response_id(created)
        verified = await self._verify(self.get_pet, pet_id)
        return {"pet": verified["pet"], "verified": True}

    async def update_pet(
        self,
        pet_id: int,
        base_version: str,
        idempotency_key: str,
        name: str | None = None,
        species: str | None = None,
        sex: str | None = None,
        birth_date: date | None = None,
        birth_month_year: str | None = None,
        age_months: int | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        await self._delegated_token("pets:read", "pets:write")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_pet(pet_id))["pet"]
        self._require_version_available(current)

        upstream: dict[str, Any] = {}
        if name is not None:
            upstream["name"] = self._required_text(name, "name", 255)
        if species is not None:
            upstream["pet_type_id"], _ = await self._resolve_pet_type(species)
        if sex is not None:
            upstream["sex"] = self._sex(sex)
        if description is not None:
            upstream["description"] = self._required_text(description, "description")
        upstream.update(self._birth_fields(birth_date, birth_month_year, age_months))
        self._require_changes(upstream)
        upstream["base_version"] = base_version
        delegated = await self._delegated_token("pets:read", "pets:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/pets/{pet_id}",
            json_data=upstream,
            idempotency_key=key,
        )
        verified = await self._verify(self.get_pet, pet_id)
        return {"pet": verified["pet"], "verified": True}

    async def add_weight(
        self,
        pet_id: int,
        weight_kg: float,
        record_date: date,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        weight = self._weight_value(weight_kg)
        key = self._idempotency_key(idempotency_key)
        delegated = await self._delegated_token("health:read", "health:write")
        created = await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/weights",
            json_data={"weight_kg": weight, "record_date": record_date.isoformat()},
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        weight_id = self._response_id(created)
        verified = await self._verify(self.get_weight, pet_id, weight_id)
        return {"weight": verified["weight"], "verified": True}

    async def update_weight(
        self,
        pet_id: int,
        weight_id: int,
        base_version: str,
        idempotency_key: str,
        weight_kg: float | None = None,
        record_date: date | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(weight_id, "weight_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_weight(pet_id, weight_id))["weight"]
        self._require_version_available(current)
        upstream: dict[str, Any] = {}
        if weight_kg is not None:
            upstream["weight_kg"] = self._weight_value(weight_kg)
        if record_date is not None:
            upstream["record_date"] = record_date.isoformat()
        self._require_changes(upstream)
        upstream["base_version"] = base_version
        delegated = await self._delegated_token("health:read", "health:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/pets/{pet_id}/weights/{weight_id}",
            json_data=upstream,
            idempotency_key=key,
        )
        verified = await self._verify(self.get_weight, pet_id, weight_id)
        return {"weight": verified["weight"], "verified": True}

    async def add_vaccination(
        self,
        pet_id: int,
        vaccine_name: str,
        administered_at: date,
        idempotency_key: str,
        due_at: date | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        key = self._idempotency_key(idempotency_key)
        upstream: dict[str, Any] = {
            "vaccine_name": self._required_text(vaccine_name, "vaccine_name", 255),
            "administered_at": administered_at.isoformat(),
        }
        if due_at is not None:
            if due_at < administered_at:
                self._error("validation_error", "due_at must not precede administered_at.", False)
            upstream["due_at"] = due_at.isoformat()
        notes = self._optional_text(notes, "notes", 1000)
        if notes is not None:
            upstream["notes"] = notes
        delegated = await self._delegated_token("health:read", "health:write")
        created = await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/vaccinations",
            json_data=upstream,
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        vaccination_id = self._response_id(created)
        verified = await self._verify(self.get_vaccination, pet_id, vaccination_id)
        return {"vaccination": verified["vaccination"], "verified": True}

    async def update_vaccination(
        self,
        pet_id: int,
        vaccination_id: int,
        base_version: str,
        idempotency_key: str,
        vaccine_name: str | None = None,
        administered_at: date | None = None,
        due_at: date | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(vaccination_id, "vaccination_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_vaccination(pet_id, vaccination_id))["vaccination"]
        self._require_version_available(current)
        upstream: dict[str, Any] = {}
        if vaccine_name is not None:
            upstream["vaccine_name"] = self._required_text(vaccine_name, "vaccine_name", 255)
        if administered_at is not None:
            upstream["administered_at"] = administered_at.isoformat()
        if due_at is not None:
            upstream["due_at"] = due_at.isoformat()
        if notes is not None:
            upstream["notes"] = self._required_text(notes, "notes", 1000)
        self._require_changes(upstream)
        upstream["base_version"] = base_version
        delegated = await self._delegated_token("health:read", "health:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/pets/{pet_id}/vaccinations/{vaccination_id}",
            json_data=upstream,
            idempotency_key=key,
        )
        verified = await self._verify(self.get_vaccination, pet_id, vaccination_id)
        return {"vaccination": verified["vaccination"], "verified": True}

    async def add_medical_record(
        self,
        pet_id: int,
        record_type: str,
        record_date: date,
        idempotency_key: str,
        description: str | None = None,
        vet_name: str | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        key = self._idempotency_key(idempotency_key)
        record_type = self._record_type(record_type)
        upstream: dict[str, Any] = {
            "record_type": record_type,
            "record_date": record_date.isoformat(),
        }
        description = self._optional_text(description, "description", 2000)
        vet_name = self._optional_text(vet_name, "vet_name", 255)
        if description is not None:
            upstream["description"] = description
        if vet_name is not None:
            upstream["vet_name"] = vet_name
        delegated = await self._delegated_token("health:read", "health:write")
        created = await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/medical-records",
            json_data=upstream,
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        record_id = self._response_id(created)
        verified = await self._verify(self.get_medical_record, pet_id, record_id)
        return {"medical_record": verified["medical_record"], "verified": True}

    async def update_medical_record(
        self,
        pet_id: int,
        record_id: int,
        base_version: str,
        idempotency_key: str,
        record_type: str | None = None,
        record_date: date | None = None,
        description: str | None = None,
        vet_name: str | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(record_id, "record_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_medical_record(pet_id, record_id))["medical_record"]
        self._require_version_available(current)
        upstream: dict[str, Any] = {}
        if record_type is not None:
            upstream["record_type"] = self._record_type(record_type)
        if record_date is not None:
            upstream["record_date"] = record_date.isoformat()
        if description is not None:
            upstream["description"] = self._required_text(description, "description", 2000)
        if vet_name is not None:
            upstream["vet_name"] = self._required_text(vet_name, "vet_name", 255)
        self._require_changes(upstream)
        upstream["base_version"] = base_version
        delegated = await self._delegated_token("health:read", "health:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/pets/{pet_id}/medical-records/{record_id}",
            json_data=upstream,
            idempotency_key=key,
        )
        verified = await self._verify(self.get_medical_record, pet_id, record_id)
        return {"medical_record": verified["medical_record"], "verified": True}

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
        return await self._request(delegated, "GET", path, params=params)

    async def _request(
        self,
        delegated: str | None,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        expected_statuses: set[int] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {delegated}"} if delegated else {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.request(
                    method,
                    f"{str(self.settings.meo_base_url).rstrip('/')}{path}",
                    headers=headers,
                    params=params,
                    json=json_data,
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
            425: (
                "idempotency_in_progress",
                "The same write is still being processed. Retry with the same idempotency key.",
                True,
            ),
        }
        if response.status_code == 409:
            try:
                conflict = response.json()
            except ValueError:
                conflict = None
            data = conflict.get("data") if isinstance(conflict, dict) else None
            existing_pet_ids = data.get("existing_pet_ids") if isinstance(data, dict) else None
            if isinstance(existing_pet_ids, list) and all(
                isinstance(value, int) and not isinstance(value, bool) and value > 0
                for value in existing_pet_ids
            ):
                self._error(
                    "duplicate_candidate",
                    "An existing pet has the same name and species.",
                    False,
                    409,
                    {"existing_pet_ids": existing_pet_ids},
                )
            if isinstance(data, dict) and data.get("server_version") is not None:
                self._error(
                    "concurrency_conflict",
                    "The target changed since it was read. Re-read and reconcile the update.",
                    False,
                    409,
                )
            self._error(
                "idempotency_conflict",
                "The idempotency key was already used for a different write.",
                False,
                409,
            )
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
        expected = expected_statuses or {200}
        if response.status_code not in expected:
            self._error(
                "upstream_unexpected",
                "Meo Mai Moi returned an unexpected response.",
                False,
                response.status_code,
            )
        try:
            return response.json()
        except ValueError:
            self._error(
                "upstream_malformed",
                "Meo Mai Moi returned malformed data.",
                True,
                response.status_code,
            )

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
            "updated_at",
        )
        detail = {
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
        detail["version"] = detail.pop("updated_at", None)
        return detail

    @staticmethod
    def _weight(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "weight_kg": item.get("weight_kg", item.get("weight")),
            "record_date": item.get("record_date", item.get("date")),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _vaccination(item: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            key: item.get(key)
            for key in (
                "id",
                "vaccine_name",
                "administered_at",
                "due_at",
                "notes",
                "completed_at",
                "photo_url",
                "updated_at",
            )
        }
        normalized["version"] = normalized.pop("updated_at", None)
        return normalized

    @staticmethod
    def _medical_record(item: dict[str, Any]) -> dict[str, Any]:
        photos = item.get("photos") if isinstance(item.get("photos"), list) else []
        normalized = {
            **{
                key: item.get(key)
                for key in (
                    "id",
                    "record_type",
                    "description",
                    "record_date",
                    "vet_name",
                    "updated_at",
                )
            },
            "photos": [
                {key: photo.get(key) for key in ("id", "url", "thumb_url", "medium_url")}
                for photo in photos
                if isinstance(photo, dict)
            ],
        }
        normalized["version"] = normalized.pop("updated_at", None)
        return normalized

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

    async def _resolve_pet_type(self, species: str) -> tuple[int, str]:
        species = self._required_text(species, "species", 255)
        items = self._items(await self._get(None, "/api/pet-types"))
        key = species.casefold()
        for item in items:
            name = str(item.get("name") or "").strip()
            slug = str(item.get("slug") or "").strip()
            raw_id = item.get("id")
            if key not in {name.casefold(), slug.casefold()}:
                continue
            if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id < 1:
                break
            return raw_id, name or slug
        self._error("validation_error", "species is not a supported pet type.", False)

    async def _verify(self, operation, *args) -> dict[str, Any]:
        try:
            return await operation(*args)
        except MeoApiError as exc:
            raise self._tool_error(
                "post_write_verification_failed",
                "Meo accepted the write but the target could not be verified. Re-read it later.",
                True,
            ) from exc

    @classmethod
    def _response_id(cls, payload: Any) -> int:
        item = cls._object(payload)
        value = item.get("id")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            cls._error(
                "post_write_verification_failed",
                "Meo accepted the write but did not return a stable target ID.",
                True,
            )
        return value

    @classmethod
    def _birth_fields(
        cls,
        birth_date: date | None,
        birth_month_year: str | None,
        age_months: int | None,
    ) -> dict[str, Any]:
        supplied = sum(value is not None for value in (birth_date, birth_month_year, age_months))
        if supplied > 1:
            cls._error(
                "validation_error",
                "Provide only one of birth_date, birth_month_year, or age_months.",
                False,
            )
        today = date.today()
        if birth_date is not None:
            if not isinstance(birth_date, date) or birth_date > today:
                cls._error("validation_error", "birth_date must not be in the future.", False)
            return {
                "birthday_year": birth_date.year,
                "birthday_month": birth_date.month,
                "birthday_day": birth_date.day,
                "birthday_precision": "day",
            }
        if birth_month_year is not None:
            match = re.fullmatch(r"(\d{4})-(\d{2})", birth_month_year.strip())
            if not match:
                cls._error("validation_error", "birth_month_year must use YYYY-MM.", False)
            year, month = int(match.group(1)), int(match.group(2))
            if (
                year < 1900
                or month not in range(1, 13)
                or (year, month)
                > (
                    today.year,
                    today.month,
                )
            ):
                cls._error(
                    "validation_error", "birth_month_year is outside the valid range.", False
                )
            return {
                "birthday_year": year,
                "birthday_month": month,
                "birthday_precision": "month",
            }
        if age_months is not None:
            if (
                isinstance(age_months, bool)
                or not isinstance(age_months, int)
                or not 0 <= age_months <= 600
            ):
                cls._error("validation_error", "age_months must be between 0 and 600.", False)
            absolute_month = today.year * 12 + today.month - 1 - age_months
            return {
                "birthday_year": absolute_month // 12,
                "birthday_month": absolute_month % 12 + 1,
                "birthday_precision": "month",
            }
        return {}

    @classmethod
    def _country(cls, value: str) -> str:
        value = cls._required_text(value, "country", 2).upper()
        if len(value) != 2 or not value.isascii() or not value.isalpha():
            cls._error("validation_error", "country must be a two-letter ISO code.", False)
        return value

    @classmethod
    def _sex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized == "unknown":
            normalized = "not_specified"
        if normalized not in {"male", "female", "not_specified"}:
            cls._error("validation_error", "sex is not supported.", False)
        return normalized

    @classmethod
    def _record_type(cls, value: str) -> str:
        value = cls._required_text(value, "record_type", 100).lower()
        if value not in MEDICAL_RECORD_TYPES:
            cls._error("validation_error", "record_type is not supported.", False)
        return value

    @classmethod
    def _weight_value(cls, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1000:
            cls._error(
                "validation_error", "weight_kg must be greater than 0 and at most 1000.", False
            )
        return float(value)

    @classmethod
    def _idempotency_key(cls, value: str) -> str:
        if not isinstance(value, str) or not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
            cls._error(
                "validation_error",
                "idempotency_key must use 1-128 letters, digits, underscores, or hyphens.",
                False,
            )
        return value

    @classmethod
    def _version(cls, value: str) -> str:
        value = cls._required_text(value, "base_version", 128)
        return value

    @classmethod
    def _require_version_available(cls, current: dict[str, Any]) -> None:
        version = current.get("version")
        if not isinstance(version, str) or not version:
            cls._error(
                "upstream_malformed",
                "Meo did not return a concurrency version for the target.",
                True,
            )

    @classmethod
    def _require_changes(cls, payload: dict[str, Any]) -> None:
        if not payload:
            cls._error("validation_error", "Provide at least one field to update.", False)

    @classmethod
    def _positive(cls, value: int, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            cls._error("validation_error", f"{field} must be a positive integer.", False)

    @classmethod
    def _optional_text(
        cls, value: str | None, field: str, max_length: int | None = None
    ) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            cls._error("validation_error", f"{field} must not be blank.", False)
        if max_length is not None and len(value) > max_length:
            cls._error(
                "validation_error", f"{field} must be at most {max_length} characters.", False
            )
        return value

    @classmethod
    def _required_text(cls, value: str, field: str, max_length: int | None = None) -> str:
        normalized = cls._optional_text(value, field, max_length)
        if normalized is None:
            cls._error("validation_error", f"{field} is required.", False)
        return normalized

    @staticmethod
    def _tool_error(
        code: str,
        message: str,
        retryable: bool,
        upstream_status: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> MeoApiError:
        payload: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
        if upstream_status is not None:
            payload["upstream_status"] = upstream_status
        if extra:
            payload.update(extra)
        return MeoApiError(payload)

    @classmethod
    def _error(
        cls,
        code: str,
        message: str,
        retryable: bool,
        upstream_status: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        raise cls._tool_error(code, message, retryable, upstream_status, extra)
