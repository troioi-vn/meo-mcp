from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
HABIT_VALUE_TYPES = {"yes_no", "integer_scale"}
HABIT_SUMMARY_MODES = {"average_scored_pets", "average_all_pets", "sum"}
SHARING_ROLES = {"owner", "editor", "viewer"}
RELATIONSHIP_TYPES = SHARING_ROLES | {"foster", "sitter"}
PLACEMENT_REQUEST_TYPES = {"permanent", "foster_free", "foster_paid", "pet_sitting"}
INVITATION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9]{64}$")
PHOTO_MAX_BYTES = 10 * 1024 * 1024
PHOTO_REDIRECT_LIMIT = 3
PHOTO_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
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

    async def list_habits(self) -> dict[str, Any]:
        delegated = await self._delegated_token("habits:read")
        payload = await self._get(delegated, "/api/habits")
        return {"habits": [self._habit(item) for item in self._items(payload)]}

    async def get_habit(self, habit_id: int) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        delegated = await self._delegated_token("habits:read")
        payload = await self._get(delegated, f"/api/habits/{habit_id}")
        return {"habit": self._habit(self._object(payload))}

    async def get_habit_heatmap(
        self, habit_id: int, weeks: int = 52, end_date: date | None = None
    ) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        if isinstance(weeks, bool) or not isinstance(weeks, int) or not 1 <= weeks <= 104:
            self._error("validation_error", "weeks must be between 1 and 104.", False)
        delegated = await self._delegated_token("habits:read")
        params: dict[str, Any] = {"weeks": weeks}
        if end_date is not None:
            params["end_date"] = end_date.isoformat()
        payload = await self._get(delegated, f"/api/habits/{habit_id}/heatmap", params)
        return {"days": [self._habit_day_summary(item) for item in self._items(payload)]}

    async def get_habit_day_entries(self, habit_id: int, entry_date: date) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        delegated = await self._delegated_token("habits:read")
        payload = self._object(
            await self._get(
                delegated,
                f"/api/habits/{habit_id}/entries/{entry_date.isoformat()}",
            )
        )
        return self._habit_day(payload)

    async def create_habit(
        self,
        name: str,
        value_type: str,
        pet_ids: list[int],
        idempotency_key: str,
        timezone: str | None = None,
        scale_min: int | None = None,
        scale_max: int | None = None,
        day_summary_mode: str = "average_scored_pets",
        share_with_coowners: bool = False,
        reminder_enabled: bool = False,
        reminder_time: str | None = None,
        reminder_weekdays: list[int] | None = None,
    ) -> dict[str, Any]:
        key = self._idempotency_key(idempotency_key)
        upstream = self._habit_configuration(
            name=name,
            value_type=value_type,
            pet_ids=pet_ids,
            timezone=timezone,
            scale_min=scale_min,
            scale_max=scale_max,
            day_summary_mode=day_summary_mode,
            share_with_coowners=share_with_coowners,
            reminder_enabled=reminder_enabled,
            reminder_time=reminder_time,
            reminder_weekdays=reminder_weekdays,
            creating=True,
        )
        delegated = await self._delegated_token("habits:read", "habits:write")
        created = await self._request(
            delegated,
            "POST",
            "/api/habits",
            json_data=upstream,
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        habit_id = self._response_id(created)
        verified = await self._verify(self.get_habit, habit_id)
        return {"habit": verified["habit"], "verified": True}

    async def update_habit(
        self,
        habit_id: int,
        base_version: str,
        idempotency_key: str,
        name: str | None = None,
        timezone: str | None = None,
        scale_min: int | None = None,
        scale_max: int | None = None,
        day_summary_mode: str | None = None,
        share_with_coowners: bool | None = None,
        reminder_enabled: bool | None = None,
        reminder_time: str | None = None,
        reminder_weekdays: list[int] | None = None,
        pet_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_habit(habit_id))["habit"]
        self._require_version_available(current)
        upstream = self._habit_configuration(
            name=name,
            pet_ids=pet_ids,
            timezone=timezone,
            scale_min=scale_min,
            scale_max=scale_max,
            day_summary_mode=day_summary_mode,
            share_with_coowners=share_with_coowners,
            reminder_enabled=reminder_enabled,
            reminder_time=reminder_time,
            reminder_weekdays=reminder_weekdays,
            creating=False,
        )
        self._require_changes(upstream)
        upstream["base_version"] = base_version
        delegated = await self._delegated_token("habits:read", "habits:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/habits/{habit_id}",
            json_data=upstream,
            idempotency_key=key,
        )
        verified = await self._verify(self.get_habit, habit_id)
        return {"habit": verified["habit"], "verified": True}

    async def save_habit_day_entries(
        self,
        habit_id: int,
        entry_date: date,
        entries: list[dict[str, int | None]],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        key = self._idempotency_key(idempotency_key)
        normalized_entries = self._habit_entries(entries)
        await self.get_habit_day_entries(habit_id, entry_date)
        delegated = await self._delegated_token("habits:read", "habits:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/habits/{habit_id}/entries/{entry_date.isoformat()}",
            json_data={"entries": normalized_entries},
            idempotency_key=key,
        )
        verified = await self._verify(self.get_habit_day_entries, habit_id, entry_date)
        return {**verified, "verified": True}

    async def archive_habit(
        self, habit_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._habit_lifecycle(habit_id, base_version, idempotency_key, "archive")

    async def restore_habit(
        self, habit_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._habit_lifecycle(habit_id, base_version, idempotency_key, "restore")

    async def delete_habit(
        self, habit_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        try:
            current = (await self.get_habit(habit_id))["habit"]
        except MeoApiError as exc:
            if exc.payload.get("code") != "upstream_not_found":
                raise
        else:
            self._require_version_available(current)
        delegated = await self._delegated_token("habits:read", "habits:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/habits/{habit_id}",
            json_data={"base_version": base_version},
            idempotency_key=key,
        )
        await self._verify_absent(self.get_habit, habit_id)
        return {"habit_id": habit_id, "deleted": True, "verified": True}

    async def list_pet_photos(self, pet_id: int) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        delegated = await self._delegated_token("pets:read")
        pet = self._object(await self._get(delegated, f"/api/pets/{pet_id}"))
        return {
            "pet_id": pet_id,
            "pet_version": pet.get("updated_at"),
            "photos": self._pet_photos(pet),
        }

    async def upload_pet_photo_from_url(
        self,
        pet_id: int,
        base_version: str,
        source_url: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = await self.list_pet_photos(pet_id)
        if not isinstance(current.get("pet_version"), str):
            self._error("upstream_malformed", "Meo did not return a pet version.", True)
        filename, content, content_type = await self._fetch_public_image(source_url)
        delegated = await self._delegated_token("pets:read", "pets:write")
        created = await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/photos",
            form_data={"base_version": base_version},
            files={"photo": (filename, content, content_type)},
            idempotency_key=key,
        )
        created_pet = self._object(created)
        created_photos = self._pet_photos(created_pet)
        primary = next((photo for photo in created_photos if photo["is_primary"]), None)
        if primary is None:
            self._error(
                "post_write_verification_failed",
                "Meo accepted the photo but did not return its stable ID.",
                True,
            )
        verified = await self._verify(self.list_pet_photos, pet_id)
        if primary["id"] not in {photo["id"] for photo in verified["photos"]}:
            self._error(
                "post_write_verification_failed",
                "Meo accepted the photo but it could not be verified.",
                True,
            )
        return {"photo": primary, **verified, "verified": True}

    async def set_primary_pet_photo(
        self,
        pet_id: int,
        photo_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(photo_id, "photo_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = await self.list_pet_photos(pet_id)
        if photo_id not in {photo["id"] for photo in current["photos"]}:
            self._error("validation_error", "photo_id is not attached to this pet.", False)
        delegated = await self._delegated_token("pets:read", "pets:write")
        await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/photos/{photo_id}/set-primary",
            json_data={"base_version": base_version},
            idempotency_key=key,
        )
        verified = await self._verify(self.list_pet_photos, pet_id)
        photo = next((item for item in verified["photos"] if item["id"] == photo_id), None)
        if photo is None or not photo["is_primary"]:
            self._error(
                "post_write_verification_failed",
                "Meo accepted the change but the primary photo could not be verified.",
                True,
            )
        return {"photo": photo, **verified, "verified": True}

    async def delete_pet_photo(
        self,
        pet_id: int,
        photo_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(photo_id, "photo_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        await self.list_pet_photos(pet_id)
        delegated = await self._delegated_token("pets:read", "pets:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/pets/{pet_id}/photos/{photo_id}",
            json_data={"base_version": base_version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        verified = await self._verify(self.list_pet_photos, pet_id)
        if photo_id in {photo["id"] for photo in verified["photos"]}:
            self._error(
                "post_write_verification_failed",
                "Meo accepted the deletion but the photo is still present.",
                True,
            )
        return {"photo_id": photo_id, **verified, "deleted": True, "verified": True}

    async def list_microchips(self, pet_id: int, page: int = 1) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(page, "page")
        delegated = await self._delegated_token("microchips:read")
        payload = await self._get(delegated, f"/api/pets/{pet_id}/microchips", {"page": page})
        return {
            "microchips": [self._microchip(item) for item in self._items(payload)],
            "pagination": self._pagination(payload),
        }

    async def get_microchip(self, pet_id: int, microchip_id: int) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(microchip_id, "microchip_id")
        delegated = await self._delegated_token("microchips:read")
        item = self._object(
            await self._get(delegated, f"/api/pets/{pet_id}/microchips/{microchip_id}")
        )
        return {"microchip": self._microchip(item)}

    async def add_microchip(
        self,
        pet_id: int,
        chip_number: str,
        idempotency_key: str,
        issuer: str | None = None,
        implanted_at: date | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        key = self._idempotency_key(idempotency_key)
        upstream: dict[str, Any] = {"chip_number": self._chip_number(chip_number)}
        issuer = self._optional_text(issuer, "issuer", 255)
        if issuer is not None:
            upstream["issuer"] = issuer
        if implanted_at is not None:
            upstream["implanted_at"] = implanted_at.isoformat()
        delegated = await self._delegated_token("microchips:read", "microchips:write")
        created = await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/microchips",
            json_data=upstream,
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        microchip_id = self._response_id(created)
        verified = await self._verify(self.get_microchip, pet_id, microchip_id)
        return {"microchip": verified["microchip"], "verified": True}

    async def update_microchip(
        self,
        pet_id: int,
        microchip_id: int,
        base_version: str,
        idempotency_key: str,
        chip_number: str | None = None,
        issuer: str | None = None,
        implanted_at: date | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(microchip_id, "microchip_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_microchip(pet_id, microchip_id))["microchip"]
        self._require_version_available(current)
        upstream: dict[str, Any] = {}
        if chip_number is not None:
            upstream["chip_number"] = self._chip_number(chip_number)
        if issuer is not None:
            upstream["issuer"] = self._required_text(issuer, "issuer", 255)
        if implanted_at is not None:
            upstream["implanted_at"] = implanted_at.isoformat()
        self._require_changes(upstream)
        upstream["base_version"] = base_version
        delegated = await self._delegated_token("microchips:read", "microchips:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/pets/{pet_id}/microchips/{microchip_id}",
            json_data=upstream,
            idempotency_key=key,
        )
        verified = await self._verify(self.get_microchip, pet_id, microchip_id)
        return {"microchip": verified["microchip"], "verified": True}

    async def delete_microchip(
        self,
        pet_id: int,
        microchip_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(microchip_id, "microchip_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        try:
            current = (await self.get_microchip(pet_id, microchip_id))["microchip"]
        except MeoApiError as exc:
            if exc.payload.get("code") != "upstream_not_found":
                raise
        else:
            self._require_version_available(current)
        delegated = await self._delegated_token("microchips:read", "microchips:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/pets/{pet_id}/microchips/{microchip_id}",
            params={"linked_transaction": "keep"},
            json_data={"base_version": base_version},
            idempotency_key=key,
        )
        await self._verify_absent(self.get_microchip, pet_id, microchip_id)
        return {"microchip_id": microchip_id, "deleted": True, "verified": True}

    async def get_pet_sharing(self, pet_id: int) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        delegated = await self._delegated_token("sharing:read")
        item = self._object(await self._get(delegated, f"/api/pets/{pet_id}/sharing"))
        return {"sharing": self._pet_sharing(item)}

    async def list_pet_relationship_suggestions(self, pet_id: int) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        delegated = await self._delegated_token("sharing:read")
        payload = await self._get(delegated, f"/api/pets/{pet_id}/relationship-suggestions")
        return {
            "suggestions": [
                {"user_id": item.get("id"), "user_name": item.get("name")}
                for item in self._items(payload)
            ]
        }

    async def list_pet_invitations(self, pet_id: int) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        delegated = await self._delegated_token("sharing:read")
        payload = await self._get(delegated, f"/api/pets/{pet_id}/invitations")
        return {"invitations": [self._invitation(item) for item in self._items(payload)]}

    async def preview_pet_invitation(self, invitation: str) -> dict[str, Any]:
        token = self._invitation_token(invitation)
        delegated = await self._delegated_token("sharing:read")
        payload = await self._request(
            delegated,
            "POST",
            "/api/mcp/resource-invitations/preview",
            json_data={"token": token},
        )
        return {"invitation": self._invitation_preview(self._object(payload))}

    async def add_pet_collaborator(
        self,
        pet_id: int,
        user_id: int,
        relationship_type: str,
        sharing_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(user_id, "user_id")
        role = self._sharing_role(relationship_type)
        version = self._version(sharing_base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_pet_sharing(pet_id))["sharing"]
        suggestions = (await self.list_pet_relationship_suggestions(pet_id))["suggestions"]
        already_granted = self._find_relationship(current, user_id, role) is not None
        if not already_granted and user_id not in {item.get("user_id") for item in suggestions}:
            self._error(
                "validation_error",
                "user_id is not present in the fresh relationship suggestions.",
                False,
            )
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/users",
            json_data={
                "user_id": user_id,
                "relationship_type": role,
                "base_version": version,
            },
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        verified = await self._verify(self.get_pet_sharing, pet_id)
        relationship = self._find_relationship(verified["sharing"], user_id, role)
        if relationship is None:
            self._verification_error("The granted collaborator role could not be verified.")
        return {"relationship": relationship, **verified, "verified": True}

    async def change_pet_collaborator_role(
        self,
        pet_id: int,
        user_id: int,
        relationship_type: str,
        sharing_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(user_id, "user_id")
        role = self._sharing_role(relationship_type)
        version = self._version(sharing_base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_pet_sharing(pet_id))["sharing"]
        if not any(item.get("user_id") == user_id for item in current["relationships"]):
            self._error("validation_error", "user_id is not an active collaborator.", False)
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/pets/{pet_id}/users/{user_id}",
            json_data={"relationship_type": role, "base_version": version},
            idempotency_key=key,
        )
        verified = await self._verify(self.get_pet_sharing, pet_id)
        relationship = self._find_relationship(verified["sharing"], user_id, role)
        if relationship is None:
            self._verification_error("The collaborator role change could not be verified.")
        return {"relationship": relationship, **verified, "verified": True}

    async def remove_pet_collaborator(
        self,
        pet_id: int,
        user_id: int,
        sharing_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(user_id, "user_id")
        version = self._version(sharing_base_version)
        key = self._idempotency_key(idempotency_key)
        try:
            current = (await self.get_pet_sharing(pet_id))["sharing"]
        except MeoApiError as exc:
            if exc.payload.get("code") not in {"upstream_forbidden", "upstream_not_found"}:
                raise
        else:
            self._require_version_available(current)
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/pets/{pet_id}/users/{user_id}",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        verified = await self._verify(self.get_pet_sharing, pet_id)
        if any(item.get("user_id") == user_id for item in verified["sharing"]["relationships"]):
            self._verification_error("The removed collaborator is still active.")
        return {"user_id": user_id, **verified, "removed": True, "verified": True}

    async def create_pet_invitation(
        self,
        pet_id: int,
        relationship_type: str,
        sharing_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        role = self._sharing_role(relationship_type)
        version = self._version(sharing_base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_pet_sharing(pet_id))["sharing"]
        self._require_version_available(current)
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        created = self._object(
            await self._request(
                delegated,
                "POST",
                f"/api/pets/{pet_id}/invitations",
                json_data={"relationship_type": role, "base_version": version},
                idempotency_key=key,
                expected_statuses={200, 201},
            )
        )
        raw = created.get("invitation")
        if not isinstance(raw, dict):
            self._verification_error("Meo did not return a stable invitation.")
        invitation = self._invitation(raw)
        invitations = (await self._verify(self.list_pet_invitations, pet_id))["invitations"]
        verified = next(
            (item for item in invitations if item["invitation_id"] == invitation["invitation_id"]),
            None,
        )
        if verified is None:
            self._verification_error("The created invitation could not be verified.")
        return {"invitation": verified, "verified": True}

    async def revoke_pet_invitation(
        self,
        pet_id: int,
        invitation_id: int,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._positive(invitation_id, "invitation_id")
        version = self._version(invitation_base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.list_pet_invitations(pet_id))["invitations"]
        invitation = next(
            (item for item in current if item["invitation_id"] == invitation_id), None
        )
        if invitation is not None:
            self._require_version_available(invitation)
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/pets/{pet_id}/invitations/{invitation_id}",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        verified = (await self._verify(self.list_pet_invitations, pet_id))["invitations"]
        if any(item["invitation_id"] == invitation_id for item in verified):
            self._verification_error("The revoked invitation is still pending.")
        return {"invitation_id": invitation_id, "revoked": True, "verified": True}

    async def accept_pet_invitation(
        self,
        invitation: str,
        expected_pet_name: str,
        expected_relationship_type: str,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._consume_pet_invitation(
            invitation,
            expected_pet_name,
            expected_relationship_type,
            invitation_base_version,
            idempotency_key,
            "accept",
        )

    async def decline_pet_invitation(
        self,
        invitation: str,
        expected_pet_name: str,
        expected_relationship_type: str,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._consume_pet_invitation(
            invitation,
            expected_pet_name,
            expected_relationship_type,
            invitation_base_version,
            idempotency_key,
            "decline",
        )

    async def leave_shared_pet(
        self,
        pet_id: int,
        sharing_base_version: str,
        expected_relationship_types: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        version = self._version(sharing_base_version)
        key = self._idempotency_key(idempotency_key)
        expected = self._relationship_type_set(expected_relationship_types)
        try:
            current = (await self.get_pet_sharing(pet_id))["sharing"]
        except MeoApiError as exc:
            if exc.payload.get("code") not in {"upstream_forbidden", "upstream_not_found"}:
                raise
        else:
            if set(current["relationship_types"]) != expected:
                self._error(
                    "relationship_mismatch",
                    "The caller's fresh relationship set does not match the expected set.",
                    False,
                )
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        await self._request(
            delegated,
            "POST",
            f"/api/pets/{pet_id}/leave",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        try:
            after = await self.get_pet_sharing(pet_id)
        except MeoApiError as exc:
            if exc.payload.get("code") in {"upstream_forbidden", "upstream_not_found"}:
                return {"pet_id": pet_id, "left": True, "verified": True}
            raise self._tool_error(
                "post_write_verification_failed",
                "Meo accepted the leave but access loss could not be verified.",
                True,
            ) from exc
        if after["sharing"]["viewer_permissions"]["has_active_relationship"]:
            self._verification_error("The caller still has an active pet relationship.")
        return {"pet_id": pet_id, "left": True, "verified": True}

    async def list_placement_opportunities(
        self,
        request_type: str | None = None,
        country: str | None = None,
        city: str | None = None,
        pet_type_id: int | None = None,
    ) -> dict[str, Any]:
        request_type = self._placement_request_type(request_type, optional=True)
        country = self._country_code(country, optional=True)
        city = self._optional_text(city, "city", 255)
        if pet_type_id is not None:
            self._positive(pet_type_id, "pet_type_id")
        delegated = await self._delegated_token("placement:read")
        payload = await self._get(delegated, "/api/pets/placement-requests")
        opportunities = [self._placement_opportunity(item) for item in self._items(payload)]
        matches = []
        for item in opportunities:
            requests = [
                request
                for request in item["requests"]
                if request_type is None or request.get("request_type") == request_type
            ]
            if not requests:
                continue
            if country is not None and str(item.get("country") or "").upper() != country:
                continue
            if city is not None and city.casefold() not in str(item.get("city") or "").casefold():
                continue
            if pet_type_id is not None and item.get("pet_type_id") != pet_type_id:
                continue
            matches.append({**item, "requests": requests})
        return {"opportunities": matches}

    async def get_placement_request(self, placement_request_id: int) -> dict[str, Any]:
        self._positive(placement_request_id, "placement_request_id")
        delegated = await self._delegated_token("placement:read")
        request_payload, context_payload = await asyncio.gather(
            self._get(delegated, f"/api/placement-requests/{placement_request_id}"),
            self._get(delegated, f"/api/placement-requests/{placement_request_id}/me"),
        )
        return {
            "placement_request": self._placement_request(self._object(request_payload)),
            "viewer_context": self._placement_viewer_context(self._object(context_payload)),
        }

    async def list_placement_responses(self, placement_request_id: int) -> dict[str, Any]:
        current = await self.get_placement_request(placement_request_id)
        if current["viewer_context"].get("viewer_role") != "owner":
            self._error(
                "upstream_forbidden",
                "Only the placement request owner can review all responses.",
                False,
                403,
            )
        delegated = await self._delegated_token("placement:read")
        payload = await self._get(
            delegated, f"/api/placement-requests/{placement_request_id}/responses"
        )
        return {
            "placement_request": current["placement_request"],
            "responses": [self._placement_response(item) for item in self._items(payload)],
        }

    async def search_helper_profiles(
        self,
        country: str | None = None,
        city: str | None = None,
        request_type: str | None = None,
        pet_type_id: int | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        country = self._country_code(country, optional=True)
        city = self._optional_text(city, "city", 255)
        request_type = self._placement_request_type(request_type, optional=True)
        search = self._optional_text(search, "search", 255)
        if pet_type_id is not None:
            self._positive(pet_type_id, "pet_type_id")
        params = {
            key: value
            for key, value in {
                "country": country,
                "city": city,
                "request_type": request_type,
                "pet_type_id": pet_type_id,
                "search": search,
            }.items()
            if value is not None
        }
        delegated = await self._delegated_token("helpers:read")
        payload = await self._get(delegated, "/api/helpers", params)
        return {
            "helper_profiles": [self._public_helper_profile(item) for item in self._items(payload)]
        }

    async def get_public_helper_profile(self, helper_profile_id: int) -> dict[str, Any]:
        self._positive(helper_profile_id, "helper_profile_id")
        delegated = await self._delegated_token("helpers:read")
        payload = await self._get(delegated, f"/api/helpers/{helper_profile_id}")
        return {"helper_profile": self._public_helper_profile(self._object(payload))}

    async def list_my_helper_profiles(self) -> dict[str, Any]:
        delegated = await self._delegated_token("helpers:read")
        payload = await self._get(delegated, "/api/helper-profiles")
        return {
            "helper_profiles": [self._private_helper_profile(item) for item in self._items(payload)]
        }

    async def get_helper_profile(self, helper_profile_id: int) -> dict[str, Any]:
        self._positive(helper_profile_id, "helper_profile_id")
        delegated = await self._delegated_token("helpers:read")
        payload = await self._get(delegated, f"/api/helper-profiles/{helper_profile_id}")
        return {"helper_profile": self._private_helper_profile(self._object(payload))}

    async def list_helper_location_options(
        self, country: str | None = None, search: str | None = None
    ) -> dict[str, Any]:
        country = self._country_code(country, optional=True)
        search = self._optional_text(search, "search", 50)
        if search is not None and country is None:
            self._error("validation_error", "search requires country.", False)
        delegated = await self._delegated_token("helpers:read")
        if country is None:
            payload = await self._get(delegated, "/api/countries")
            return {
                "countries": [
                    {key: item.get(key) for key in ("code", "name", "phone_prefix")}
                    for item in self._items(payload)
                ],
                "cities": [],
            }
        params = {"country": country, **({"search": search} if search is not None else {})}
        payload = await self._get(delegated, "/api/cities", params)
        return {
            "countries": [],
            "cities": [self._city_option(item) for item in self._items(payload)],
        }

    async def list_chats(self) -> dict[str, Any]:
        delegated = await self._delegated_token("messages:read")
        payload = await self._get(delegated, "/api/msg/chats")
        return {"chats": [self._chat(item) for item in self._items(payload)]}

    async def get_chat(self, chat_id: int) -> dict[str, Any]:
        self._positive(chat_id, "chat_id")
        delegated = await self._delegated_token("messages:read")
        payload = await self._get(delegated, f"/api/msg/chats/{chat_id}")
        return {"chat": self._chat(self._object(payload))}

    async def list_chat_messages(
        self, chat_id: int, cursor: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        self._positive(chat_id, "chat_id")
        cursor = self._optional_text(cursor, "cursor", 64)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            self._error("validation_error", "limit must be between 1 and 100.", False)
        delegated = await self._delegated_token("messages:read")
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        payload = self._object(
            await self._get(delegated, f"/api/msg/chats/{chat_id}/messages", params)
        )
        messages = payload.get("data")
        meta = payload.get("meta")
        if not isinstance(messages, list) or not isinstance(meta, dict):
            self._error("upstream_malformed", "Meo returned malformed message data.", True)
        return {
            "messages": [self._chat_message(item) for item in messages if isinstance(item, dict)],
            "pagination": {
                "has_more": bool(meta.get("has_more")),
                "next_cursor": meta.get("next_cursor"),
            },
            "counterparty_read_at": meta.get("counterparty_read_at"),
        }

    async def get_unread_message_count(self) -> dict[str, Any]:
        delegated = await self._delegated_token("messages:read")
        payload = self._object(await self._get(delegated, "/api/msg/unread-count"))
        count = payload.get("unread_message_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            self._error("upstream_malformed", "Meo returned a malformed unread count.", True)
        return {"unread_message_count": count}

    async def list_groups(self) -> dict[str, Any]:
        delegated = await self._delegated_token("groups:read")
        payload = await self._get(delegated, "/api/groups")
        return {"groups": [self._group_summary(item) for item in self._items(payload)]}

    async def get_group_overview(self, group_id: int) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        delegated = await self._delegated_token("groups:read")
        item = self._object(await self._get(delegated, f"/api/groups/{group_id}"))
        return {"group": self._group(item)}

    async def list_group_member_suggestions(self, group_id: int) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        delegated = await self._delegated_token("groups:read")
        payload = await self._get(delegated, f"/api/groups/{group_id}/member-suggestions")
        return {"suggestions": [self._user_reference(item) for item in self._items(payload)]}

    async def list_group_invitations(self, group_id: int) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        delegated = await self._delegated_token("groups:read")
        payload = await self._get(delegated, f"/api/groups/{group_id}/invitations")
        return {"invitations": [self._resource_invitation(item) for item in self._items(payload)]}

    async def preview_group_invitation(self, invitation: str) -> dict[str, Any]:
        token = self._invitation_token(invitation)
        delegated = await self._delegated_token("groups:read")
        payload = await self._request(
            delegated,
            "POST",
            "/api/mcp/group-invitations/preview",
            json_data={"token": token},
        )
        return {"invitation": self._group_invitation_preview(self._object(payload))}

    async def create_group(
        self,
        name: str,
        pet_ids: list[int],
        idempotency_key: str,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        name = self._required_text(name, "name", 255)
        pets = self._positive_id_list(pet_ids, "pet_ids", allow_empty=True)
        key = self._idempotency_key(idempotency_key)
        existing = (await self.list_groups())["groups"]
        duplicates = [
            item for item in existing if str(item.get("name", "")).casefold() == name.casefold()
        ]
        if duplicates and not allow_duplicate:
            self._error(
                "duplicate_candidate",
                "A group with the same normalized name already exists; inspect its stable ID or explicitly allow a distinct duplicate.",
                False,
                extra={
                    "candidates": [
                        {"group_id": item.get("group_id"), "name": item.get("name")}
                        for item in duplicates
                    ]
                },
            )
        delegated = await self._delegated_token("groups:read", "groups:write")
        created = await self._request(
            delegated,
            "POST",
            "/api/groups",
            json_data={"name": name, "pet_ids": pets},
            idempotency_key=key,
            expected_statuses={200, 201},
        )
        group_id = self._response_id(created)
        verified = await self._verify(self.get_group_overview, group_id)
        return {"group": verified["group"], "verified": True}

    async def update_group(
        self,
        group_id: int,
        base_version: str,
        name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        version = self._version(base_version)
        name = self._required_text(name, "name", 255)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_group_overview(group_id))["group"]
        self._require_version_available(current)
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/groups/{group_id}",
            json_data={"name": name, "base_version": version},
            idempotency_key=key,
        )
        verified = await self._verify(self.get_group_overview, group_id)
        if verified["group"].get("name") != name:
            self._verification_error("The group rename could not be verified.")
        return {"group": verified["group"], "verified": True}

    async def delete_group(
        self,
        group_id: int,
        base_version: str,
        expected_group_name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        version = self._version(base_version)
        expected = self._required_text(expected_group_name, "expected_group_name", 255)
        key = self._idempotency_key(idempotency_key)
        try:
            current = (await self.get_group_overview(group_id))["group"]
        except MeoApiError as exc:
            if exc.payload.get("code") != "upstream_not_found":
                raise
        else:
            if current.get("name") != expected:
                self._error("target_mismatch", "The group name does not match.", False)
            self._require_version_available(current)
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/groups/{group_id}",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        groups = (await self._verify(self.list_groups))["groups"]
        if any(item.get("group_id") == group_id for item in groups):
            self._verification_error("The deleted group is still visible.")
        return {"group_id": group_id, "deleted": True, "verified": True}

    async def add_group_member(
        self,
        group_id: int,
        user_id: int,
        role: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._group_member_change(
            group_id, user_id, role, None, base_version, idempotency_key, "add"
        )

    async def update_group_member_role(
        self,
        group_id: int,
        user_id: int,
        role: str,
        expected_current_role: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._group_member_change(
            group_id,
            user_id,
            role,
            expected_current_role,
            base_version,
            idempotency_key,
            "update",
        )

    async def remove_group_member(
        self,
        group_id: int,
        user_id: int,
        expected_current_role: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._group_member_change(
            group_id,
            user_id,
            None,
            expected_current_role,
            base_version,
            idempotency_key,
            "remove",
        )

    async def leave_group(
        self,
        group_id: int,
        expected_caller_role: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        role = self._group_role(expected_caller_role)
        version = self._version(base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_group_overview(group_id))["group"]
        if current.get("viewer_role") != role:
            self._error("target_mismatch", "The caller's fresh group role does not match.", False)
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            "POST",
            f"/api/groups/{group_id}/leave",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        groups = (await self._verify(self.list_groups))["groups"]
        if any(item.get("group_id") == group_id for item in groups):
            self._verification_error("The caller still has group access.")
        return {"group_id": group_id, "left": True, "verified": True}

    async def add_group_pets(
        self,
        group_id: int,
        pet_ids: list[int],
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        pets = self._positive_id_list(pet_ids, "pet_ids")
        version = self._version(base_version)
        key = self._idempotency_key(idempotency_key)
        await self.get_group_overview(group_id)
        owned_ids = {item.get("id") for item in (await self.list_pets())["pets"]}
        if not set(pets) <= owned_ids:
            self._error("target_mismatch", "Every pet_id must be in the fresh pet list.", False)
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            "POST",
            f"/api/groups/{group_id}/pets",
            json_data={"pet_ids": pets, "base_version": version},
            idempotency_key=key,
        )
        verified = await self._verify(self.get_group_overview, group_id)
        present = {item.get("pet_id") for item in verified["group"].get("pets", [])}
        if not set(pets) <= present:
            self._verification_error("The group pet assignments could not be verified.")
        return {"group": verified["group"], "verified": True}

    async def remove_group_pet(
        self,
        group_id: int,
        pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        self._positive(pet_id, "pet_id")
        expected = self._required_text(expected_pet_name, "expected_pet_name", 255)
        version = self._version(base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_group_overview(group_id))["group"]
        target = next(
            (item for item in current.get("pets", []) if item.get("pet_id") == pet_id), None
        )
        if target is not None and target.get("pet_name") != expected:
            self._error("target_mismatch", "The group pet name does not match.", False)
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/groups/{group_id}/pets/{pet_id}",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        verified = await self._verify(self.get_group_overview, group_id)
        if any(item.get("pet_id") == pet_id for item in verified["group"].get("pets", [])):
            self._verification_error("The removed pet is still assigned to the group.")
        return {"group": verified["group"], "pet_id": pet_id, "removed": True, "verified": True}

    async def create_group_invitation(
        self,
        group_id: int,
        role: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        role = self._group_role(role)
        version = self._version(base_version)
        key = self._idempotency_key(idempotency_key)
        await self.get_group_overview(group_id)
        delegated = await self._delegated_token("groups:read", "groups:write")
        created = self._object(
            await self._request(
                delegated,
                "POST",
                f"/api/groups/{group_id}/invitations",
                json_data={"role": role, "base_version": version},
                idempotency_key=key,
                expected_statuses={200, 201},
            )
        )
        raw = created.get("invitation")
        if not isinstance(raw, dict):
            self._verification_error("Meo did not return a stable group invitation.")
        invitation = self._resource_invitation(raw)
        invitations = (await self._verify(self.list_group_invitations, group_id))["invitations"]
        verified = next(
            (
                item
                for item in invitations
                if item.get("invitation_id") == invitation.get("invitation_id")
            ),
            None,
        )
        if verified is None:
            self._verification_error("The created group invitation could not be verified.")
        return {"invitation": verified, "verified": True}

    async def revoke_group_invitation(
        self,
        group_id: int,
        invitation_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        self._positive(invitation_id, "invitation_id")
        version = self._version(base_version)
        key = self._idempotency_key(idempotency_key)
        await self.list_group_invitations(group_id)
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/groups/{group_id}/invitations/{invitation_id}",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        after = (await self._verify(self.list_group_invitations, group_id))["invitations"]
        if any(item.get("invitation_id") == invitation_id for item in after):
            self._verification_error("The revoked group invitation is still pending.")
        return {"invitation_id": invitation_id, "revoked": True, "verified": True}

    async def accept_group_invitation(
        self,
        invitation: str,
        expected_group_name: str,
        expected_role: str,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._consume_group_invitation(
            invitation,
            expected_group_name,
            expected_role,
            invitation_base_version,
            idempotency_key,
            "accept",
        )

    async def decline_group_invitation(
        self,
        invitation: str,
        expected_group_name: str,
        expected_role: str,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._consume_group_invitation(
            invitation,
            expected_group_name,
            expected_role,
            invitation_base_version,
            idempotency_key,
            "decline",
        )

    async def list_currencies(self) -> dict[str, Any]:
        delegated = await self._delegated_token("finance:read")
        payload = await self._get(delegated, "/api/currencies")
        return {"currencies": [self._currency(item) for item in self._items(payload)]}

    async def list_ledgers(self, archived: bool = False) -> dict[str, Any]:
        delegated = await self._delegated_token("finance:read")
        payload = await self._get(delegated, "/api/ledgers", {"archived": archived})
        return {"ledgers": [self._ledger(item) for item in self._items(payload)]}

    async def get_ledger_overview(self, ledger_id: int) -> dict[str, Any]:
        self._positive(ledger_id, "ledger_id")
        delegated = await self._delegated_token("finance:read")
        paths = (
            f"/api/ledgers/{ledger_id}",
            f"/api/ledgers/{ledger_id}/dashboard",
            f"/api/ledgers/{ledger_id}/accounts",
            f"/api/ledgers/{ledger_id}/categories",
            f"/api/ledgers/{ledger_id}/members",
            f"/api/ledgers/{ledger_id}/pets",
        )
        detail, dashboard, accounts, categories, members, pets = await asyncio.gather(
            *(self._get(delegated, path) for path in paths)
        )
        return {
            "ledger": self._ledger(self._object(detail)),
            "dashboard": self._ledger_dashboard(self._object(dashboard)),
            "accounts": [self._ledger_account(item) for item in self._items(accounts)],
            "categories": [self._ledger_category(item) for item in self._items(categories)],
            "members": [self._ledger_member(item) for item in self._items(members)],
            "pets": [self._ledger_pet(item) for item in self._items(pets)],
        }

    async def list_ledger_member_suggestions(self, ledger_id: int) -> dict[str, Any]:
        self._positive(ledger_id, "ledger_id")
        delegated = await self._delegated_token("finance:read")
        payload = await self._get(delegated, f"/api/ledgers/{ledger_id}/member-suggestions")
        return {"suggestions": [self._user_reference(item) for item in self._items(payload)]}

    async def list_ledger_invitations(self, ledger_id: int) -> dict[str, Any]:
        self._positive(ledger_id, "ledger_id")
        delegated = await self._delegated_token("finance:read")
        payload = await self._get(delegated, f"/api/ledgers/{ledger_id}/invitations")
        return {"invitations": [self._resource_invitation(item) for item in self._items(payload)]}

    async def list_ledger_transactions(
        self,
        ledger_id: int,
        page: int = 1,
        per_page: int = 25,
        date_from: date | None = None,
        date_to: date | None = None,
        transaction_type: str | None = None,
        account_id: int | None = None,
        category_id: int | None = None,
        pet_id: int | None = None,
        creator_id: int | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        self._positive(ledger_id, "ledger_id")
        self._bounded_page(page, per_page)
        if date_from and date_to and date_to < date_from:
            self._error("validation_error", "date_to must not precede date_from.", False)
        if transaction_type is not None and transaction_type not in {"income", "expense"}:
            self._error("validation_error", "transaction_type must be income or expense.", False)
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        for key, value in {
            "account_id": account_id,
            "category_id": category_id,
            "pet_id": pet_id,
            "creator_id": creator_id,
        }.items():
            if value is not None:
                self._positive(value, key)
                params[key] = value
        if date_from is not None:
            params["date_from"] = date_from.isoformat()
        if date_to is not None:
            params["date_to"] = date_to.isoformat()
        if transaction_type is not None:
            params["type"] = transaction_type
        if search is not None:
            params["search"] = self._required_text(search, "search", 255)
        delegated = await self._delegated_token("finance:read")
        data = self._object(
            await self._get(delegated, f"/api/ledgers/{ledger_id}/transactions", params)
        )
        items = data.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            self._error("upstream_malformed", "Meo returned malformed transaction data.", True)
        return {
            "transactions": [self._ledger_transaction(item) for item in items],
            "pagination": self._simple_pagination(data),
        }

    async def get_ledger_transaction(self, ledger_id: int, transaction_id: int) -> dict[str, Any]:
        self._positive(ledger_id, "ledger_id")
        self._positive(transaction_id, "transaction_id")
        delegated = await self._delegated_token("finance:read")
        item = self._object(
            await self._get(delegated, f"/api/ledgers/{ledger_id}/transactions/{transaction_id}")
        )
        return {"transaction": self._ledger_transaction(item)}

    async def list_pet_finance_transactions(self, pet_id: int, page: int = 1) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        self._bounded_page(page, 20)
        delegated = await self._delegated_token("finance:read")
        data = self._object(
            await self._get(delegated, f"/api/pets/{pet_id}/finance-transactions", {"page": page})
        )
        items = data.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            self._error("upstream_malformed", "Meo returned malformed transaction data.", True)
        return {
            "transactions": [self._ledger_transaction(item) for item in items],
            "pagination": self._simple_pagination(data, default_per_page=20),
        }

    async def get_notification_inbox(
        self, limit: int = 20, include_notifications: bool = True
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            self._error("validation_error", "limit must be between 1 and 50.", False)
        delegated = await self._delegated_token("notifications:read")
        data = self._object(
            await self._get(
                delegated,
                "/api/notifications/unified",
                {"limit": limit, "include_bell_notifications": include_notifications},
            )
        )
        notifications = data.get("bell_notifications")
        if not isinstance(notifications, list) or any(
            not isinstance(item, dict) for item in notifications
        ):
            self._error("upstream_malformed", "Meo returned malformed notification data.", True)
        counts = (data.get("unread_bell_count"), data.get("unread_message_count"))
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            self._error("upstream_malformed", "Meo returned malformed unread counts.", True)
        return {
            "notifications": [self._notification(item) for item in notifications],
            "unread_bell_count": counts[0],
            "unread_message_count": counts[1],
        }

    async def get_notification_preferences(self) -> dict[str, Any]:
        delegated = await self._delegated_token("notifications:read")
        payload = await self._get(delegated, "/api/notification-preferences")
        return {
            "preferences": [self._notification_preference(item) for item in self._items(payload)]
        }

    async def get_my_profile(self) -> dict[str, Any]:
        delegated = await self._delegated_token("profile:read")
        item = self._object(await self._get(delegated, "/api/users/me"))
        return {"profile": self._profile(item)}

    async def list_owner_weights(self, page: int = 1) -> dict[str, Any]:
        self._bounded_page(page, 25)
        delegated = await self._delegated_token("profile:read")
        data = self._object(
            await self._get(delegated, "/api/users/me/owner-weights", {"page": page})
        )
        items, meta = data.get("data"), data.get("meta")
        if (
            not isinstance(items, list)
            or any(not isinstance(item, dict) for item in items)
            or not isinstance(meta, dict)
        ):
            self._error("upstream_malformed", "Meo returned malformed owner-weight data.", True)
        return {
            "weights": [self._owner_weight(item) for item in items],
            "pagination": self._simple_pagination(meta, default_per_page=25),
        }

    async def get_account_invitation_summary(self) -> dict[str, Any]:
        delegated = await self._delegated_token("invitations:read")
        invitations, stats = await asyncio.gather(
            self._get(delegated, "/api/invitations"),
            self._get(delegated, "/api/invitations/stats"),
        )
        counts = self._object(stats)
        for key in ("total", "pending", "accepted", "expired", "revoked"):
            value = counts.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                self._error("upstream_malformed", "Meo returned malformed invitation totals.", True)
        return {
            "invitations": [self._account_invitation(item) for item in self._items(invitations)],
            "counts": {
                key: counts[key] for key in ("total", "pending", "accepted", "expired", "revoked")
            },
        }

    async def create_placement_request(
        self,
        pet_id: int,
        expected_pet_name: str,
        request_type: str,
        start_date: date,
        idempotency_key: str,
        end_date: date | None = None,
        notes: str | None = None,
        expires_at: date | None = None,
    ) -> dict[str, Any]:
        self._positive(pet_id, "pet_id")
        expected_pet_name = self._required_text(expected_pet_name, "expected_pet_name", 255)
        request_type = self._placement_request_type(request_type)
        key = self._idempotency_key(idempotency_key)
        if end_date and end_date < start_date:
            self._error("validation_error", "end_date must not precede start_date.", False)
        delegated = await self._delegated_token("placement:read", "placement:write")
        payload = await self._request(
            delegated,
            "POST",
            "/api/placement-requests",
            json_data={
                "pet_id": pet_id,
                "request_type": request_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat() if end_date else None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "notes": self._optional_text(notes, "notes"),
            },
            idempotency_key=key,
            expected_statuses={201},
        )
        created = self._placement_request(self._object(payload))
        if created.get("pet", {}).get("pet_name") not in {None, expected_pet_name}:
            self._verification_error("The created placement request pet did not match.")
        request_id = created.get("placement_request_id")
        self._positive(request_id, "placement_request_id")
        verified = await self._verify(self.get_placement_request, request_id)
        verified_pet = verified["placement_request"].get("pet")
        if (
            verified["placement_request"].get("pet_id") != pet_id
            or not isinstance(verified_pet, dict)
            or verified_pet.get("pet_name") != expected_pet_name
        ):
            self._verification_error("The created placement request could not be verified.")
        return {**verified, "created": True, "verified": True}

    async def delete_placement_request(
        self,
        placement_request_id: int,
        expected_pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        try:
            await self._checked_placement(placement_request_id, expected_pet_id, expected_pet_name)
        except MeoApiError as exc:
            if exc.payload.get("code") not in {"upstream_not_found", "upstream_forbidden"}:
                raise
        version, key = self._version(base_version), self._idempotency_key(idempotency_key)
        delegated = await self._delegated_token("placement:read", "placement:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/placement-requests/{placement_request_id}",
            json_data={"base_version": version},
            idempotency_key=key,
            expected_statuses={204},
        )
        try:
            await self.get_placement_request(placement_request_id)
        except MeoApiError as exc:
            if exc.payload.get("code") in {"upstream_not_found", "upstream_forbidden"}:
                return {
                    "placement_request_id": placement_request_id,
                    "deleted": True,
                    "verified": True,
                }
            raise
        self._verification_error("The placement request still exists after deletion.")

    async def respond_to_placement_request(
        self,
        placement_request_id: int,
        helper_profile_id: int,
        expected_pet_name: str,
        idempotency_key: str,
        message: str | None = None,
    ) -> dict[str, Any]:
        current = await self.get_placement_request(placement_request_id)
        if current["placement_request"].get("pet", {}).get("pet_name") != self._required_text(
            expected_pet_name, "expected_pet_name", 255
        ):
            self._error("target_mismatch", "The placement request pet does not match.", False)
        profile = (await self.get_helper_profile(helper_profile_id))["helper_profile"]
        if profile.get("helper_profile_id") != helper_profile_id:
            self._error("target_mismatch", "The helper profile does not match.", False)
        delegated = await self._delegated_token("placement:read", "placement:write", "helpers:read")
        payload = await self._request(
            delegated,
            "POST",
            f"/api/placement-requests/{placement_request_id}/responses",
            json_data={
                "helper_profile_id": helper_profile_id,
                "message": self._optional_text(message, "message"),
            },
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses={201},
        )
        response = self._placement_response(self._object(payload))
        response_id = response.get("response_id")
        self._positive(response_id, "response_id")
        after = await self._verify(self.get_placement_request, placement_request_id)
        mine = after["viewer_context"].get("my_response")
        if not isinstance(mine, dict) or mine.get("id") != response_id:
            self._verification_error("The placement response could not be verified.")
        return {"response": response, "verified": True}

    async def accept_placement_response(
        self,
        placement_request_id: int,
        response_id: int,
        expected_helper_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._placement_response_action(
            placement_request_id,
            response_id,
            expected_helper_name,
            base_version,
            idempotency_key,
            "accept",
            "accepted",
        )

    async def reject_placement_response(
        self,
        placement_request_id: int,
        response_id: int,
        expected_helper_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._placement_response_action(
            placement_request_id,
            response_id,
            expected_helper_name,
            base_version,
            idempotency_key,
            "reject",
            "rejected",
        )

    async def cancel_placement_response(
        self, placement_request_id: int, response_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        current = await self.get_placement_request(placement_request_id)
        mine = current["viewer_context"].get("my_response")
        if isinstance(mine, dict) and mine.get("id") != response_id:
            self._error(
                "target_mismatch", "The response is not the caller's current response.", False
            )
        delegated = await self._delegated_token("placement:read", "placement:write")
        await self._request(
            delegated,
            "POST",
            f"/api/placement-responses/{response_id}/cancel",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        after = await self._verify(self.get_placement_request, placement_request_id)
        after_mine = after["viewer_context"].get("my_response")
        if isinstance(after_mine, dict) and after_mine.get("status") not in {
            "cancelled",
            "canceled",
        }:
            self._verification_error("The response cancellation could not be verified.")
        return {
            "placement_request": after["placement_request"],
            "response_id": response_id,
            "status": "cancelled",
            "verified": True,
        }

    async def confirm_pet_transfer(
        self, placement_request_id: int, transfer_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._transfer_action(
            placement_request_id, transfer_id, base_version, idempotency_key, "confirm", "confirmed"
        )

    async def reject_pet_transfer(
        self, placement_request_id: int, transfer_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._transfer_action(
            placement_request_id, transfer_id, base_version, idempotency_key, "reject", "rejected"
        )

    async def cancel_pet_transfer(
        self, placement_request_id: int, transfer_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._transfer_action(
            placement_request_id, transfer_id, base_version, idempotency_key, "cancel", "canceled"
        )

    async def finalize_temporary_placement(
        self,
        placement_request_id: int,
        expected_pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        await self._checked_placement(placement_request_id, expected_pet_id, expected_pet_name)
        delegated = await self._delegated_token("placement:read", "placement:write")
        await self._request(
            delegated,
            "POST",
            f"/api/placement-requests/{placement_request_id}/finalize",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        after = await self._verify(self.get_placement_request, placement_request_id)
        if after["placement_request"].get("status") != "finalized":
            self._verification_error("The temporary placement finalization could not be verified.")
        return {**after, "verified": True}

    async def create_helper_profile(
        self,
        country: str,
        city_ids: list[int],
        phone_number: str,
        experience: str,
        has_pets: bool,
        has_children: bool,
        request_types: list[str],
        idempotency_key: str,
        state: str | None = None,
        address: str | None = None,
        zip_code: str | None = None,
        offer: str | None = None,
        contact_details: list[dict[str, str]] | None = None,
        pet_type_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        data = self._helper_profile_write_data(
            country,
            city_ids,
            phone_number,
            experience,
            has_pets,
            has_children,
            request_types,
            state,
            address,
            zip_code,
            offer,
            contact_details,
            pet_type_ids,
        )
        delegated = await self._delegated_token("helpers:read", "helpers:write")
        payload = await self._request(
            delegated,
            "POST",
            "/api/helper-profiles",
            json_data=data,
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses={201},
        )
        item = self._private_helper_profile(self._object(payload))
        profile_id = item.get("helper_profile_id")
        self._positive(profile_id, "helper_profile_id")
        verified = await self._verify(self.get_helper_profile, profile_id)
        return {"helper_profile": verified["helper_profile"], "created": True, "verified": True}

    async def update_helper_profile(
        self, helper_profile_id: int, base_version: str, idempotency_key: str, **changes: Any
    ) -> dict[str, Any]:
        self._positive(helper_profile_id, "helper_profile_id")
        await self.get_helper_profile(helper_profile_id)
        clean = {key: value for key, value in changes.items() if value is not None}
        if not clean:
            self._error("validation_error", "Provide at least one helper-profile change.", False)
        clean["base_version"] = self._version(base_version)
        delegated = await self._delegated_token("helpers:read", "helpers:write")
        await self._request(
            delegated,
            "PUT",
            f"/api/helper-profiles/{helper_profile_id}",
            json_data=clean,
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        verified = await self._verify(self.get_helper_profile, helper_profile_id)
        if not self._helper_profile_matches_changes(verified["helper_profile"], clean):
            self._verification_error("The helper profile update could not be verified.")
        return {"helper_profile": verified["helper_profile"], "verified": True}

    async def archive_helper_profile(
        self, helper_profile_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._helper_lifecycle(
            helper_profile_id, base_version, idempotency_key, "archive", "archived"
        )

    async def restore_helper_profile(
        self, helper_profile_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._helper_lifecycle(
            helper_profile_id, base_version, idempotency_key, "restore", "private"
        )

    async def delete_helper_profile(
        self, helper_profile_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        try:
            await self.get_helper_profile(helper_profile_id)
        except MeoApiError as exc:
            if exc.payload.get("code") not in {"upstream_not_found", "upstream_forbidden"}:
                raise
        delegated = await self._delegated_token("helpers:read", "helpers:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/helper-profiles/{helper_profile_id}",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses={204},
        )
        try:
            await self.get_helper_profile(helper_profile_id)
        except MeoApiError as exc:
            if exc.payload.get("code") in {"upstream_not_found", "upstream_forbidden"}:
                return {"helper_profile_id": helper_profile_id, "deleted": True, "verified": True}
            raise
        self._verification_error("The helper profile still exists after deletion.")

    async def upload_helper_profile_photo_from_url(
        self, helper_profile_id: int, source_url: str, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        before = (await self.get_helper_profile(helper_profile_id))["helper_profile"]
        before_ids = {p.get("id") for p in before.get("photos", [])}
        filename, content, mime = await self._fetch_public_image(source_url)
        delegated = await self._delegated_token("helpers:read", "helpers:write")
        payload = self._object(
            await self._request(
                delegated,
                "POST",
                f"/api/helper-profiles/{helper_profile_id}",
                form_data={"base_version": self._version(base_version)},
                files={"photos[]": (filename, content, mime)},
                idempotency_key=self._idempotency_key(idempotency_key),
            )
        )
        uploaded_ids = payload.get("uploaded_photo_ids")
        if (
            not isinstance(uploaded_ids, list)
            or len(uploaded_ids) != 1
            or isinstance(uploaded_ids[0], bool)
            or not isinstance(uploaded_ids[0], int)
            or uploaded_ids[0] <= 0
        ):
            self._verification_error("Meo did not identify the uploaded helper-profile photo.")
        uploaded_id = uploaded_ids[0]
        after = (await self._verify(self.get_helper_profile, helper_profile_id))["helper_profile"]
        uploaded = next((p for p in after.get("photos", []) if p.get("id") == uploaded_id), None)
        if uploaded is None or (
            uploaded_id in before_ids and before.get("version") != after.get("version")
        ):
            self._verification_error("The helper profile photo upload could not be verified.")
        return {"helper_profile": after, "photo": uploaded, "verified": True}

    async def set_primary_helper_profile_photo(
        self, helper_profile_id: int, photo_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._helper_photo_action(
            helper_profile_id, photo_id, base_version, idempotency_key, "set-primary"
        )

    async def delete_helper_profile_photo(
        self, helper_profile_id: int, photo_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        return await self._helper_photo_action(
            helper_profile_id, photo_id, base_version, idempotency_key, "delete"
        )

    async def open_placement_chat(
        self,
        placement_request_id: int,
        recipient_user_id: int,
        expected_recipient_name: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        await self.get_placement_request(placement_request_id)
        expected_recipient_name = self._required_text(
            expected_recipient_name, "expected_recipient_name", 255
        )
        delegated = await self._delegated_token("placement:read", "messages:read", "messages:write")
        payload = await self._request(
            delegated,
            "POST",
            "/api/msg/chats",
            json_data={
                "type": "direct",
                "recipient_id": recipient_user_id,
                "contextable_type": "PlacementRequest",
                "contextable_id": placement_request_id,
            },
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses={200, 201},
        )
        chat = self._chat(self._object(payload))
        if not any(
            p.get("user_id") == recipient_user_id and p.get("user_name") == expected_recipient_name
            for p in chat.get("participants", [])
        ):
            self._error("target_mismatch", "The placement chat recipient did not match.", False)
        chat_id = chat.get("chat_id")
        self._positive(chat_id, "chat_id")
        verified = await self._verify(self.get_chat, chat_id)
        return {"chat": verified["chat"], "verified": True}

    async def send_chat_message(
        self, chat_id: int, expected_recipient_user_id: int, content: str, idempotency_key: str
    ) -> dict[str, Any]:
        chat = await self._checked_chat(chat_id, expected_recipient_user_id)
        content = self._required_text(content, "content", 5000)
        delegated = await self._delegated_token("messages:read", "messages:write")
        payload = await self._request(
            delegated,
            "POST",
            f"/api/msg/chats/{chat_id}/messages",
            json_data={"type": "text", "content": content},
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses={201},
        )
        message = self._chat_message(self._object(payload))
        if message.get("chat_id") != chat.get("chat_id") or not message.get("is_mine"):
            self._verification_error("The sent message could not be verified.")
        verified = await self._find_chat_message(chat_id, message.get("message_id"))
        if (
            verified is None
            or not verified.get("is_mine")
            or verified.get("type") != "text"
            or verified.get("content") != content
        ):
            self._verification_error("The sent message could not be verified after creation.")
        return {"message": verified, "verified": True}

    async def send_chat_image_from_url(
        self, chat_id: int, expected_recipient_user_id: int, source_url: str, idempotency_key: str
    ) -> dict[str, Any]:
        await self._checked_chat(chat_id, expected_recipient_user_id)
        filename, content, mime = await self._fetch_public_image(source_url)
        if len(content) > 5 * 1024 * 1024:
            self._error("source_image_too_large", "Chat images are limited to 5 MiB.", False)
        delegated = await self._delegated_token("messages:read", "messages:write")
        payload = await self._request(
            delegated,
            "POST",
            f"/api/msg/chats/{chat_id}/messages",
            form_data={"type": "image"},
            files={"image": (filename, content, mime)},
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses={201},
        )
        message = self._chat_message(self._object(payload))
        if message.get("chat_id") != chat_id or message.get("type") != "image":
            self._verification_error("The sent image message could not be verified.")
        verified = await self._find_chat_message(chat_id, message.get("message_id"))
        if verified is None or not verified.get("is_mine") or verified.get("type") != "image":
            self._verification_error("The sent image message could not be verified after creation.")
        return {"message": verified, "verified": True}

    async def mark_chat_read(
        self, chat_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        await self.get_chat(chat_id)
        delegated = await self._delegated_token("messages:read", "messages:write")
        payload = self._object(
            await self._request(
                delegated,
                "POST",
                f"/api/msg/chats/{chat_id}/read",
                json_data={"base_version": self._version(base_version)},
                idempotency_key=self._idempotency_key(idempotency_key),
            )
        )
        if payload.get("chat_id") != chat_id or not isinstance(payload.get("last_read_at"), str):
            self._verification_error("Meo did not return a verifiable chat read receipt.")
        after = await self._verify(self.get_chat, chat_id)
        if after["chat"].get("unread_count") not in {None, 0}:
            self._verification_error("The chat read receipt could not be verified.")
        return {"chat": after["chat"], "marked_read": True, "verified": True}

    async def delete_own_message(
        self,
        chat_id: int,
        message_id: int,
        expected_content: str,
        base_version: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._positive(message_id, "message_id")
        target = await self._find_chat_message(chat_id, message_id)
        if target is not None and (
            not target.get("is_mine") or target.get("content") != expected_content
        ):
            self._error(
                "target_mismatch", "The own message target or content does not match.", False
            )
        delegated = await self._delegated_token("messages:read", "messages:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/msg/messages/{message_id}",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        if await self._find_chat_message(chat_id, message_id) is not None:
            self._verification_error("The message still appears after deletion.")
        return {"message_id": message_id, "deleted": True, "verified": True}

    async def _find_chat_message(
        self, chat_id: int, message_id: Any, max_pages: int = 10
    ) -> dict[str, Any] | None:
        self._positive(message_id, "message_id")
        cursor: str | None = None
        for _ in range(max_pages):
            page = await self.list_chat_messages(chat_id, cursor=cursor, limit=100)
            target = next(
                (item for item in page["messages"] if item.get("message_id") == message_id), None
            )
            if target is not None:
                return target
            pagination = page["pagination"]
            cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not isinstance(cursor, str):
                return None
        self._error(
            "target_not_in_bounded_history",
            "The message was not found in the newest 1,000 chat messages.",
            False,
        )

    async def leave_chat(
        self, chat_id: int, expected_recipient_user_id: int, base_version: str, idempotency_key: str
    ) -> dict[str, Any]:
        try:
            await self._checked_chat(chat_id, expected_recipient_user_id)
        except MeoApiError as exc:
            if exc.payload.get("code") not in {"upstream_not_found", "upstream_forbidden"}:
                raise
        delegated = await self._delegated_token("messages:read", "messages:write")
        await self._request(
            delegated,
            "DELETE",
            f"/api/msg/chats/{chat_id}",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        try:
            await self.get_chat(chat_id)
        except MeoApiError as exc:
            if exc.payload.get("code") in {"upstream_not_found", "upstream_forbidden"}:
                return {"chat_id": chat_id, "left": True, "verified": True}
            raise
        self._verification_error("The chat is still visible after leaving.")

    async def _checked_placement(
        self, placement_request_id: int, expected_pet_id: int, expected_pet_name: str
    ) -> dict[str, Any]:
        self._positive(placement_request_id, "placement_request_id")
        self._positive(expected_pet_id, "expected_pet_id")
        expected_pet_name = self._required_text(expected_pet_name, "expected_pet_name", 255)
        current = await self.get_placement_request(placement_request_id)
        request = current["placement_request"]
        pet = request.get("pet") if isinstance(request.get("pet"), dict) else {}
        if request.get("pet_id") != expected_pet_id or pet.get("pet_name") != expected_pet_name:
            self._error("target_mismatch", "The placement request pet does not match.", False)
        self._require_version_available(request)
        return current

    async def _placement_response_action(
        self,
        placement_request_id: int,
        response_id: int,
        expected_helper_name: str,
        base_version: str,
        idempotency_key: str,
        action: str,
        expected_status: str,
    ) -> dict[str, Any]:
        self._positive(response_id, "response_id")
        expected_helper_name = self._required_text(
            expected_helper_name, "expected_helper_name", 255
        )
        responses = (await self.list_placement_responses(placement_request_id))["responses"]
        target = next((item for item in responses if item.get("response_id") == response_id), None)
        helper = target.get("helper_profile") if isinstance(target, dict) else None
        if not isinstance(helper, dict) or helper.get("user_name") != expected_helper_name:
            self._error("target_mismatch", "The placement response helper does not match.", False)
        delegated = await self._delegated_token("placement:read", "placement:write")
        await self._request(
            delegated,
            "POST",
            f"/api/placement-responses/{response_id}/{action}",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        after = (await self._verify(self.list_placement_responses, placement_request_id))[
            "responses"
        ]
        verified = next((item for item in after if item.get("response_id") == response_id), None)
        if not verified or verified.get("status") != expected_status:
            self._verification_error("The placement response transition could not be verified.")
        return {"response": verified, "verified": True}

    async def _transfer_action(
        self,
        placement_request_id: int,
        transfer_id: int,
        base_version: str,
        idempotency_key: str,
        action: str,
        expected_status: str,
    ) -> dict[str, Any]:
        self._positive(transfer_id, "transfer_id")
        current = await self.get_placement_request(placement_request_id)
        transfer = current["viewer_context"].get("my_transfer")
        if not isinstance(transfer, dict) or transfer.get("transfer_id") != transfer_id:
            self._error(
                "target_mismatch", "The transfer is not the caller's current handover.", False
            )
        delegated = await self._delegated_token("placement:read", "placement:write")
        method = "DELETE" if action == "cancel" else "POST"
        path = f"/api/transfer-requests/{transfer_id}" + (
            "" if action == "cancel" else f"/{action}"
        )
        await self._request(
            delegated,
            method,
            path,
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        after = await self._verify(self.get_placement_request, placement_request_id)
        verified = after["viewer_context"].get("my_transfer")
        if isinstance(verified, dict) and verified.get("status") != expected_status:
            self._verification_error("The transfer transition could not be verified.")
        return {
            "placement_request": after["placement_request"],
            "transfer_id": transfer_id,
            "status": expected_status,
            "verified": True,
        }

    def _helper_profile_write_data(
        self,
        country: str,
        city_ids: list[int],
        phone_number: str,
        experience: str,
        has_pets: bool,
        has_children: bool,
        request_types: list[str],
        state: str | None,
        address: str | None,
        zip_code: str | None,
        offer: str | None,
        contact_details: list[dict[str, str]] | None,
        pet_type_ids: list[int] | None,
    ) -> dict[str, Any]:
        country = self._required_text(country, "country", 2).upper()
        if len(country) != 2 or not country.isalpha() or not city_ids:
            self._error("validation_error", "country and at least one city_id are required.", False)
        for city_id in city_ids:
            self._positive(city_id, "city_id")
        normalized_types = [self._placement_request_type(value) for value in request_types]
        if not normalized_types:
            self._error("validation_error", "At least one request_type is required.", False)
        for pet_type_id in pet_type_ids or []:
            self._positive(pet_type_id, "pet_type_id")
        return {
            "country": country,
            "city_ids": city_ids,
            "phone_number": self._required_text(phone_number, "phone_number", 20),
            "experience": self._required_text(experience, "experience", 10000),
            "has_pets": has_pets,
            "has_children": has_children,
            "request_types": normalized_types,
            "state": self._optional_text(state, "state"),
            "address": self._optional_text(address, "address"),
            "zip_code": self._optional_text(zip_code, "zip_code"),
            "offer": self._optional_text(offer, "offer"),
            "contact_details": contact_details or [],
            "pet_type_ids": pet_type_ids or [],
        }

    @staticmethod
    def _helper_profile_matches_changes(profile: dict[str, Any], changes: dict[str, Any]) -> bool:
        direct_fields = {
            "country",
            "phone_number",
            "experience",
            "has_pets",
            "has_children",
            "state",
            "address",
            "zip_code",
            "offer",
            "status",
        }
        for field in direct_fields & changes.keys():
            expected = changes[field]
            if field == "country" and isinstance(expected, str):
                expected = expected.upper()
            if profile.get(field) != expected:
                return False
        if "city_ids" in changes:
            actual = [
                item.get("city_id") for item in profile.get("cities", []) if isinstance(item, dict)
            ]
            if not all(isinstance(item, int) and not isinstance(item, bool) for item in actual):
                return False
            if set(actual) != set(changes["city_ids"]):
                return False
        if "pet_type_ids" in changes:
            actual = [
                item.get("id") for item in profile.get("pet_types", []) if isinstance(item, dict)
            ]
            if not all(isinstance(item, int) and not isinstance(item, bool) for item in actual):
                return False
            if set(actual) != set(changes["pet_type_ids"]):
                return False
        if "request_types" in changes and sorted(profile.get("request_types", [])) != sorted(
            changes["request_types"]
        ):
            return False
        if "contact_details" in changes:
            actual = {
                (item.get("type"), item.get("value"))
                for item in profile.get("contact_details", [])
                if isinstance(item, dict)
            }
            expected = {
                (item.get("type"), item.get("value"))
                for item in changes["contact_details"]
                if isinstance(item, dict)
            }
            if actual != expected:
                return False
        return True

    async def _helper_lifecycle(
        self,
        helper_profile_id: int,
        base_version: str,
        idempotency_key: str,
        action: str,
        expected_status: str,
    ) -> dict[str, Any]:
        await self.get_helper_profile(helper_profile_id)
        delegated = await self._delegated_token("helpers:read", "helpers:write")
        await self._request(
            delegated,
            "POST",
            f"/api/helper-profiles/{helper_profile_id}/{action}",
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
        )
        after = (await self._verify(self.get_helper_profile, helper_profile_id))["helper_profile"]
        if after.get("status") != expected_status:
            self._verification_error("The helper profile lifecycle change could not be verified.")
        return {"helper_profile": after, "verified": True}

    async def _helper_photo_action(
        self,
        helper_profile_id: int,
        photo_id: int,
        base_version: str,
        idempotency_key: str,
        action: str,
    ) -> dict[str, Any]:
        self._positive(photo_id, "photo_id")
        before = (await self.get_helper_profile(helper_profile_id))["helper_profile"]
        photo_exists = any(photo.get("id") == photo_id for photo in before.get("photos", []))
        if not photo_exists and action != "delete":
            self._error(
                "target_mismatch", "The photo does not belong to the helper profile.", False
            )
        delegated = await self._delegated_token("helpers:read", "helpers:write")
        path = f"/api/helper-profiles/{helper_profile_id}/photos/{photo_id}"
        method, expected = ("DELETE", {204}) if action == "delete" else ("POST", {200})
        if action != "delete":
            path += "/set-primary"
        await self._request(
            delegated,
            method,
            path,
            json_data={"base_version": self._version(base_version)},
            idempotency_key=self._idempotency_key(idempotency_key),
            expected_statuses=expected,
        )
        after = (await self._verify(self.get_helper_profile, helper_profile_id))["helper_profile"]
        photo = next((p for p in after.get("photos", []) if p.get("id") == photo_id), None)
        if (action == "delete" and photo is not None) or (
            action != "delete" and (not photo or not photo.get("is_primary"))
        ):
            self._verification_error("The helper profile photo change could not be verified.")
        return {
            "helper_profile": after,
            "photo_id": photo_id,
            "deleted": action == "delete",
            "verified": True,
        }

    async def _checked_chat(self, chat_id: int, expected_recipient_user_id: int) -> dict[str, Any]:
        self._positive(chat_id, "chat_id")
        self._positive(expected_recipient_user_id, "expected_recipient_user_id")
        chat = (await self.get_chat(chat_id))["chat"]
        if not any(
            p.get("user_id") == expected_recipient_user_id for p in chat.get("participants", [])
        ):
            self._error("target_mismatch", "The chat recipient does not match.", False)
        return chat

    async def _consume_pet_invitation(
        self,
        invitation: str,
        expected_pet_name: str,
        expected_relationship_type: str,
        invitation_base_version: str,
        idempotency_key: str,
        action: str,
    ) -> dict[str, Any]:
        token = self._invitation_token(invitation)
        expected_name = self._required_text(expected_pet_name, "expected_pet_name", 255)
        expected_role = self._sharing_role(expected_relationship_type)
        version = self._version(invitation_base_version)
        key = self._idempotency_key(idempotency_key)
        preview = (await self.preview_pet_invitation(token))["invitation"]
        if preview["pet_name"] != expected_name or preview["relationship_type"] != expected_role:
            self._error(
                "invitation_mismatch",
                "The fresh invitation preview does not match the expected pet and role.",
                False,
            )
        delegated = await self._delegated_token("sharing:read", "sharing:write")
        result = await self._request(
            delegated,
            "POST",
            f"/api/mcp/resource-invitations/{action}",
            json_data={"token": token, "base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        if action == "accept":
            item = self._object(result)
            pet_id = item.get("pet_id")
            self._positive(pet_id, "pet_id")
            sharing = await self._verify(self.get_pet_sharing, pet_id)
            if expected_role not in sharing["sharing"]["relationship_types"]:
                self._verification_error("The accepted collaborator role could not be verified.")
            return {"sharing": sharing["sharing"], "accepted": True, "verified": True}
        after = (await self.preview_pet_invitation(token))["invitation"]
        if after["is_valid"]:
            self._verification_error("The declined invitation is still valid.")
        return {"declined": True, "verified": True}

    async def _consume_group_invitation(
        self,
        invitation: str,
        expected_group_name: str,
        expected_role: str,
        invitation_base_version: str,
        idempotency_key: str,
        action: str,
    ) -> dict[str, Any]:
        token = self._invitation_token(invitation)
        expected_name = self._required_text(expected_group_name, "expected_group_name", 255)
        role = self._group_role(expected_role)
        version = self._version(invitation_base_version)
        key = self._idempotency_key(idempotency_key)
        preview = (await self.preview_group_invitation(token))["invitation"]
        if preview.get("group_name") != expected_name or preview.get("role") != role:
            self._error(
                "invitation_mismatch",
                "The fresh invitation preview does not match the expected group and role.",
                False,
            )
        delegated = await self._delegated_token("groups:read", "groups:write")
        result = await self._request(
            delegated,
            "POST",
            f"/api/mcp/group-invitations/{action}",
            json_data={"token": token, "base_version": version},
            idempotency_key=key,
            expected_statuses={200, 204},
        )
        if action == "accept":
            item = self._object(result)
            group_id = item.get("group_id")
            self._positive(group_id, "group_id")
            verified = await self._verify(self.get_group_overview, group_id)
            if verified["group"].get("viewer_role") != role:
                self._verification_error("The accepted group role could not be verified.")
            return {"group": verified["group"], "accepted": True, "verified": True}
        after = (await self.preview_group_invitation(token))["invitation"]
        if after.get("is_valid"):
            self._verification_error("The declined group invitation is still valid.")
        return {"declined": True, "verified": True}

    async def _group_member_change(
        self,
        group_id: int,
        user_id: int,
        role: str | None,
        expected_current_role: str | None,
        base_version: str,
        idempotency_key: str,
        action: str,
    ) -> dict[str, Any]:
        self._positive(group_id, "group_id")
        self._positive(user_id, "user_id")
        normalized_role = self._group_role(role) if role is not None else None
        expected = (
            self._group_role(expected_current_role) if expected_current_role is not None else None
        )
        version = self._version(base_version)
        key = self._idempotency_key(idempotency_key)
        current = (await self.get_group_overview(group_id))["group"]
        member = next(
            (item for item in current.get("members", []) if item.get("user_id") == user_id),
            None,
        )
        if action == "add":
            if member is None:
                suggestions = (await self.list_group_member_suggestions(group_id))["suggestions"]
                if user_id not in {item.get("user_id") for item in suggestions}:
                    self._error(
                        "target_mismatch",
                        "user_id is not present in the fresh group suggestions.",
                        False,
                    )
        elif member is None or member.get("role") != expected:
            self._error(
                "target_mismatch",
                "The member's fresh role does not match the expected role.",
                False,
            )
        method = {"add": "POST", "update": "PUT", "remove": "DELETE"}[action]
        path = (
            f"/api/groups/{group_id}/members"
            if action == "add"
            else f"/api/groups/{group_id}/members/{user_id}"
        )
        payload: dict[str, Any] = {"base_version": version}
        if normalized_role is not None:
            payload["role"] = normalized_role
        if action == "add":
            payload["user_id"] = user_id
        delegated = await self._delegated_token("groups:read", "groups:write")
        await self._request(
            delegated,
            method,
            path,
            json_data=payload,
            idempotency_key=key,
            expected_statuses={200, 201, 204},
        )
        verified = await self._verify(self.get_group_overview, group_id)
        after = next(
            (
                item
                for item in verified["group"].get("members", [])
                if item.get("user_id") == user_id
            ),
            None,
        )
        if action == "remove":
            if after is not None:
                self._verification_error("The removed group member is still active.")
            return {
                "group": verified["group"],
                "user_id": user_id,
                "removed": True,
                "verified": True,
            }
        if after is None or after.get("role") != normalized_role:
            self._verification_error("The group member role could not be verified.")
        return {"group": verified["group"], "member": after, "verified": True}

    async def _habit_lifecycle(
        self,
        habit_id: int,
        base_version: str,
        idempotency_key: str,
        action: str,
    ) -> dict[str, Any]:
        self._positive(habit_id, "habit_id")
        key = self._idempotency_key(idempotency_key)
        base_version = self._version(base_version)
        current = (await self.get_habit(habit_id))["habit"]
        self._require_version_available(current)
        delegated = await self._delegated_token("habits:read", "habits:write")
        await self._request(
            delegated,
            "POST",
            f"/api/habits/{habit_id}/{action}",
            json_data={"base_version": base_version},
            idempotency_key=key,
        )
        verified = await self._verify(self.get_habit, habit_id)
        archived = verified["habit"].get("archived_at") is not None
        if archived != (action == "archive"):
            self._error(
                "post_write_verification_failed",
                "Meo accepted the lifecycle change but it could not be verified.",
                True,
            )
        return {"habit": verified["habit"], "verified": True}

    async def _fetch_public_image(self, source_url: str) -> tuple[str, bytes, str]:
        current_url = self._required_text(source_url, "source_url", 2048)
        try:
            async with httpx.AsyncClient(
                timeout=12, follow_redirects=False, trust_env=False
            ) as client:
                for redirect_count in range(PHOTO_REDIRECT_LIMIT + 1):
                    pinned_url, hostname = await self._pinned_public_url(current_url)
                    async with client.stream(
                        "GET",
                        pinned_url,
                        headers={"Host": hostname, "Accept": "image/*"},
                        extensions={"sni_hostname": hostname},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if redirect_count >= PHOTO_REDIRECT_LIMIT or not location:
                                self._error(
                                    "source_url_rejected",
                                    "The photo source redirect chain is not allowed.",
                                    False,
                                )
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code != 200:
                            self._error(
                                "source_fetch_failed",
                                "The validated photo source could not be fetched.",
                                True,
                            )
                        content_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        extension = PHOTO_MIME_EXTENSIONS.get(content_type)
                        if extension is None:
                            self._error(
                                "source_image_invalid",
                                "The photo source did not return a supported image type.",
                                False,
                            )
                        declared = response.headers.get("content-length")
                        if declared is not None:
                            try:
                                declared_size = int(declared)
                            except ValueError:
                                self._error(
                                    "source_image_invalid",
                                    "The photo source declared an invalid size.",
                                    False,
                                )
                            if declared_size > PHOTO_MAX_BYTES:
                                self._error(
                                    "source_image_too_large",
                                    "The photo source exceeds the 10 MiB limit.",
                                    False,
                                )
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > PHOTO_MAX_BYTES:
                                self._error(
                                    "source_image_too_large",
                                    "The photo source exceeds the 10 MiB limit.",
                                    False,
                                )
                            chunks.append(chunk)
                        if size == 0:
                            self._error(
                                "source_image_invalid",
                                "The photo source returned an empty body.",
                                False,
                            )
                        return f"photo{extension}", b"".join(chunks), content_type
        except MeoApiError:
            raise
        except (httpx.HTTPError, OSError, UnicodeError, ValueError) as exc:
            raise self._tool_error(
                "source_fetch_failed",
                "The validated photo source could not be fetched.",
                True,
            ) from exc
        self._error("source_fetch_failed", "The photo source could not be fetched.", True)

    async def _pinned_public_url(self, source_url: str) -> tuple[str, str]:
        try:
            parsed = urlsplit(source_url)
            port = parsed.port
        except ValueError:
            self._error("source_url_rejected", "The photo source URL is invalid.", False)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or port not in {None, 443}
        ):
            self._error(
                "source_url_rejected",
                "The photo source must be a public HTTPS URL on port 443.",
                False,
            )
        try:
            hostname = parsed.hostname.encode("idna").decode("ascii")
            addresses = await self._public_addresses(hostname)
        except (OSError, UnicodeError, ValueError) as exc:
            raise self._tool_error(
                "source_url_rejected",
                "The photo source host is not a public internet destination.",
                False,
            ) from exc
        if not addresses or any(not address.is_global for address in addresses):
            self._error(
                "source_url_rejected",
                "The photo source host is not a public internet destination.",
                False,
            )
        address = sorted(addresses, key=lambda item: (item.version != 4, str(item)))[0]
        netloc = f"[{address}]" if address.version == 6 else str(address)
        return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, "")), hostname

    @staticmethod
    async def _public_addresses(
        hostname: str,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            literal = ipaddress.ip_address(hostname)
            addresses = {literal}
        except ValueError:
            loop = asyncio.get_running_loop()
            resolved = await loop.getaddrinfo(
                hostname,
                443,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
            addresses = {ipaddress.ip_address(item[4][0]) for item in resolved}
        if not addresses or any(not address.is_global for address in addresses):
            return set()
        return addresses

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
        form_data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
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
                    data=form_data,
                    files=files,
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
            conflict_code = data.get("code") if isinstance(data, dict) else None
            if conflict_code == "last_owner_conflict":
                self._error(
                    "last_owner_conflict",
                    "The change would leave the pet without an owner.",
                    False,
                    409,
                )
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
            if conflict_code == "active_placement_conflict":
                self._error(
                    "active_placement_conflict",
                    "This pet already has an active placement request of that type.",
                    False,
                    409,
                )
            if isinstance(data, dict) and data.get("server_version") is not None:
                self._error(
                    "concurrency_conflict",
                    "The target changed since it was read. Re-read and reconcile the update.",
                    False,
                    409,
                )
            if conflict_code == "idempotency_conflict":
                self._error(
                    "idempotency_conflict",
                    "The idempotency key was already used for a different write.",
                    False,
                    409,
                )
            self._error(
                "upstream_conflict",
                "Meo rejected the write because the target state conflicts with it.",
                False,
                409,
            )
        if response.status_code in errors:
            code, message, retryable = errors[response.status_code]
            self._error(code, message, retryable, response.status_code)
        if response.status_code == 410:
            self._error(
                "invitation_inactive",
                "The invitation is no longer active.",
                False,
                410,
            )
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
        if response.status_code == 204:
            return None
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
    def _habit(item: dict[str, Any]) -> dict[str, Any]:
        pets = item.get("pets") if isinstance(item.get("pets"), list) else []
        capabilities = (
            item.get("capabilities") if isinstance(item.get("capabilities"), dict) else {}
        )
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "timezone": item.get("timezone"),
            "value_type": item.get("value_type"),
            "scale_min": item.get("scale_min"),
            "scale_max": item.get("scale_max"),
            "day_summary_mode": item.get("day_summary_mode"),
            "share_with_coowners": bool(item.get("share_with_coowners")),
            "reminder_enabled": bool(item.get("reminder_enabled")),
            "reminder_time": item.get("reminder_time"),
            "reminder_weekdays": item.get("reminder_weekdays"),
            "archived_at": item.get("archived_at"),
            "pet_count": item.get("pet_count"),
            "pets": [
                {key: pet.get(key) for key in ("id", "name", "photo_url")}
                for pet in pets
                if isinstance(pet, dict)
            ],
            "capabilities": {
                key: bool(capabilities.get(key))
                for key in ("can_edit", "can_delete", "can_archive", "can_share")
            },
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _habit_day_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "date",
                "average_value",
                "display_value",
                "entry_count",
                "visible_pet_count",
                "normalized_intensity",
            )
        }

    @classmethod
    def _habit_day(cls, item: dict[str, Any]) -> dict[str, Any]:
        entries = item.get("entries") if isinstance(item.get("entries"), list) else []
        habit = item.get("habit")
        if not isinstance(habit, dict):
            cls._error("upstream_malformed", "Meo returned malformed habit day data.", True)
        return {
            "habit": cls._habit(habit),
            "date": item.get("date"),
            "entries": [
                {
                    key: entry.get(key)
                    for key in (
                        "entry_id",
                        "pet_id",
                        "pet_name",
                        "pet_photo_url",
                        "value_int",
                        "is_current_pet",
                        "has_entry",
                    )
                }
                for entry in entries
                if isinstance(entry, dict)
            ],
        }

    @staticmethod
    def _pet_photos(pet: dict[str, Any]) -> list[dict[str, Any]]:
        photos = pet.get("photos") if isinstance(pet.get("photos"), list) else []
        return [
            {
                key: photo.get(key)
                for key in (
                    "id",
                    "url",
                    "thumb_url",
                    "medium_url",
                    "width",
                    "height",
                    "is_primary",
                    "processing",
                )
            }
            for photo in photos
            if isinstance(photo, dict)
        ]

    @staticmethod
    def _microchip(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "chip_number": item.get("chip_number"),
            "issuer": item.get("issuer"),
            "implanted_at": item.get("implanted_at"),
            "version": item.get("updated_at", item.get("version")),
            "has_linked_transaction": bool(item.get("health_finance_link_exists")),
        }

    @classmethod
    def _pet_sharing(cls, item: dict[str, Any]) -> dict[str, Any]:
        permissions = (
            item.get("viewer_permissions")
            if isinstance(item.get("viewer_permissions"), dict)
            else {}
        )
        relationships = item.get("relationships")
        relationship_types = item.get("relationship_types")
        if not isinstance(relationships, list) or not isinstance(relationship_types, list):
            cls._error("upstream_malformed", "Meo returned malformed sharing data.", True)
        return {
            "pet_id": item.get("pet_id"),
            "pet_name": item.get("pet_name"),
            "version": item.get("version"),
            "viewer_permissions": {
                "can_manage_people": bool(permissions.get("can_manage_people")),
                "is_owner": bool(permissions.get("is_owner")),
                "has_active_relationship": bool(permissions.get("has_active_relationship")),
            },
            "relationship_types": [role for role in relationship_types if isinstance(role, str)],
            "relationships": [
                {
                    key: relationship.get(key)
                    for key in (
                        "relationship_id",
                        "user_id",
                        "user_name",
                        "relationship_type",
                        "version",
                    )
                }
                for relationship in relationships
                if isinstance(relationship, dict)
            ],
        }

    @staticmethod
    def _invitation(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "invitation_id": item.get("id", item.get("invitation_id")),
            "relationship_type": item.get("relationship_type"),
            "status": item.get("status"),
            "expires_at": item.get("expires_at"),
            "version": item.get("updated_at", item.get("version")),
            "share_url": item.get("invitation_url", item.get("share_url")),
        }

    @staticmethod
    def _invitation_preview(item: dict[str, Any]) -> dict[str, Any]:
        inviter = item.get("inviter") if isinstance(item.get("inviter"), dict) else {}
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        return {
            "status": item.get("status"),
            "expires_at": item.get("expires_at"),
            "is_valid": bool(item.get("is_valid")),
            "is_authenticated": bool(item.get("is_authenticated")),
            "is_self_invitation": bool(item.get("is_self_invitation")),
            "inviter_name": inviter.get("name"),
            "pet_name": target.get("name"),
            "relationship_type": target.get("role"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _group_invitation_preview(item: dict[str, Any]) -> dict[str, Any]:
        inviter = item.get("inviter") if isinstance(item.get("inviter"), dict) else {}
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        return {
            "status": item.get("status"),
            "expires_at": item.get("expires_at"),
            "is_valid": bool(item.get("is_valid")),
            "is_authenticated": bool(item.get("is_authenticated")),
            "is_self_invitation": bool(item.get("is_self_invitation")),
            "inviter_name": inviter.get("name"),
            "group_id": target.get("group_id"),
            "group_name": target.get("name"),
            "role": target.get("role"),
            "version": item.get("updated_at", item.get("version")),
        }

    @classmethod
    def _placement_opportunity(cls, item: dict[str, Any]) -> dict[str, Any]:
        pet_type = item.get("pet_type") if isinstance(item.get("pet_type"), dict) else {}
        city = item.get("city")
        requests = (
            item.get("placement_requests")
            if isinstance(item.get("placement_requests"), list)
            else []
        )
        return {
            "pet_id": item.get("id"),
            "pet_name": item.get("name"),
            "pet_type_id": pet_type.get("id", item.get("pet_type_id")),
            "species": pet_type.get("name", item.get("species")),
            "photo_url": item.get("photo_url"),
            "country": item.get("country"),
            "state": item.get("state"),
            "city": city.get("name") if isinstance(city, dict) else city,
            "requests": [
                cls._placement_request(request)
                for request in requests
                if isinstance(request, dict) and request.get("status") == "open"
            ],
        }

    @classmethod
    def _placement_request(cls, item: dict[str, Any]) -> dict[str, Any]:
        pet = item.get("pet") if isinstance(item.get("pet"), dict) else None
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else None
        translation = (
            item.get("notes_translation")
            if isinstance(item.get("notes_translation"), dict)
            else None
        )
        result = {
            "placement_request_id": item.get("id", item.get("placement_request_id")),
            **{
                key: item.get(key)
                for key in (
                    "pet_id",
                    "request_type",
                    "status",
                    "notes",
                    "notes_locale",
                    "expires_at",
                    "start_date",
                    "end_date",
                    "response_count",
                )
            },
        }
        result.update(
            {
                "notes_translation": cls._content_translation(translation),
                "pet": cls._placement_pet(pet) if pet is not None else None,
                "owner": (
                    {"user_id": owner.get("id"), "user_name": owner.get("name")}
                    if owner is not None
                    else None
                ),
                "version": item.get("updated_at", item.get("version")),
            }
        )
        return result

    @classmethod
    def _placement_viewer_context(cls, item: dict[str, Any]) -> dict[str, Any]:
        response = item.get("my_response")
        transfer = item.get("my_transfer")
        actions = item.get("available_actions")
        return {
            "viewer_role": item.get("viewer_role"),
            "my_response": (
                {
                    key: response.get(key)
                    for key in (
                        "id",
                        "status",
                        "message",
                        "responded_at",
                        "accepted_at",
                        "rejected_at",
                        "cancelled_at",
                        "updated_at",
                    )
                }
                if isinstance(response, dict)
                else None
            ),
            "my_response_id": item.get("my_response_id"),
            "my_transfer": (
                {
                    "transfer_id": transfer.get("id"),
                    "status": transfer.get("status"),
                    "from_user_id": transfer.get("from_user_id"),
                    "to_user_id": transfer.get("to_user_id"),
                    "confirmed_at": transfer.get("confirmed_at"),
                    "version": transfer.get("updated_at", transfer.get("version")),
                }
                if isinstance(transfer, dict)
                else None
            ),
            "available_actions": (
                {key: bool(value) for key, value in actions.items() if isinstance(key, str)}
                if isinstance(actions, dict)
                else {}
            ),
            "chat_id": item.get("chat_id"),
        }

    @classmethod
    def _placement_response(cls, item: dict[str, Any]) -> dict[str, Any]:
        profile = item.get("helper_profile")
        transfer = item.get("transfer_request")
        return {
            "response_id": item.get("id"),
            "placement_request_id": item.get("placement_request_id"),
            "helper_profile_id": item.get("helper_profile_id"),
            "status": item.get("status"),
            "message": item.get("message"),
            "responded_at": item.get("responded_at"),
            "accepted_at": item.get("accepted_at"),
            "rejected_at": item.get("rejected_at"),
            "cancelled_at": item.get("cancelled_at"),
            "helper_profile": (
                cls._public_helper_profile(profile) if isinstance(profile, dict) else None
            ),
            "transfer": (
                {
                    "transfer_id": transfer.get("id"),
                    "status": transfer.get("status"),
                    "version": transfer.get("updated_at", transfer.get("version")),
                }
                if isinstance(transfer, dict)
                else None
            ),
            "version": item.get("updated_at", item.get("version")),
        }

    @classmethod
    def _public_helper_profile(cls, item: dict[str, Any]) -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        cities = item.get("cities") if isinstance(item.get("cities"), list) else []
        pet_types = item.get("pet_types") if isinstance(item.get("pet_types"), list) else []
        photos = item.get("photos") if isinstance(item.get("photos"), list) else []
        translation = (
            item.get("experience_translation")
            if isinstance(item.get("experience_translation"), dict)
            else None
        )
        return {
            "helper_profile_id": item.get("id"),
            "user_id": item.get("user_id", user.get("id")),
            "user_name": user.get("name"),
            "user_avatar_url": user.get("avatar_url"),
            "country": item.get("country"),
            "state": item.get("state"),
            "cities": [cls._city_option(city) for city in cities if isinstance(city, dict)],
            "experience": item.get("experience"),
            "experience_locale": item.get("experience_locale"),
            "experience_translation": cls._content_translation(translation),
            "offer": item.get("offer"),
            "has_pets": bool(item.get("has_pets")),
            "has_children": bool(item.get("has_children")),
            "request_types": [
                value for value in item.get("request_types", []) if isinstance(value, str)
            ]
            if isinstance(item.get("request_types"), list)
            else [],
            "pet_types": [
                {key: pet_type.get(key) for key in ("id", "name", "slug")}
                for pet_type in pet_types
                if isinstance(pet_type, dict)
            ],
            "photos": [cls._media_photo(photo) for photo in photos if isinstance(photo, dict)],
        }

    @classmethod
    def _private_helper_profile(cls, item: dict[str, Any]) -> dict[str, Any]:
        contacts = item.get("contact_details")
        return {
            **cls._public_helper_profile(item),
            "address": item.get("address"),
            "zip_code": item.get("zip_code"),
            "phone_number": item.get("phone_number"),
            "contact_details": [
                {"type": contact.get("type"), "value": contact.get("value")}
                for contact in contacts
                if isinstance(contact, dict)
            ]
            if isinstance(contacts, list)
            else [],
            "approval_status": item.get("approval_status"),
            "status": item.get("status"),
            "archived_at": item.get("archived_at"),
            "restored_at": item.get("restored_at"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _city_option(item: dict[str, Any]) -> dict[str, Any]:
        name = item.get("name")
        if isinstance(name, dict):
            name = next((value for value in name.values() if isinstance(value, str)), None)
        return {"city_id": item.get("id"), "name": name, "country": item.get("country")}

    @staticmethod
    def _placement_pet(item: dict[str, Any]) -> dict[str, Any]:
        pet_type = item.get("pet_type") if isinstance(item.get("pet_type"), dict) else {}
        city = item.get("city")
        return {
            "pet_id": item.get("id"),
            "pet_name": item.get("name"),
            "pet_type_id": pet_type.get("id", item.get("pet_type_id")),
            "species": pet_type.get("name", item.get("species")),
            "photo_url": item.get("photo_url"),
            "country": item.get("country"),
            "state": item.get("state"),
            "city": city.get("name") if isinstance(city, dict) else city,
        }

    @staticmethod
    def _content_translation(item: dict[str, Any] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            key: item.get(key)
            for key in (
                "original_locale",
                "viewer_locale",
                "translated",
                "status",
                "is_translated",
            )
        }

    @staticmethod
    def _media_photo(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "id",
                "url",
                "thumb_url",
                "medium_url",
                "width",
                "height",
                "is_primary",
                "processing",
            )
        }

    @classmethod
    def _chat(cls, item: dict[str, Any]) -> dict[str, Any]:
        participants = item.get("participants")
        latest = item.get("latest_message")
        return {
            "chat_id": item.get("id"),
            "type": item.get("type"),
            "context_type": item.get("contextable_type"),
            "context_id": item.get("contextable_id"),
            "participants": [
                cls._chat_participant(participant)
                for participant in participants
                if isinstance(participant, dict)
            ]
            if isinstance(participants, list)
            else [],
            "other_participant": (
                cls._chat_participant(item["other_participant"])
                if isinstance(item.get("other_participant"), dict)
                else None
            ),
            "latest_message": (
                {
                    "message_id": latest.get("id"),
                    "type": latest.get("type"),
                    "content_preview": str(latest.get("content") or "")[:200],
                    "sender_name": latest.get("sender_name"),
                    "created_at": latest.get("created_at"),
                }
                if isinstance(latest, dict)
                else None
            ),
            "unread_count": item.get("unread_count"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _chat_participant(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": item.get("id", item.get("user_id")),
            "user_name": item.get("name", item.get("user_name")),
            "avatar_url": item.get("avatar_url"),
        }

    @classmethod
    def _chat_message(cls, item: dict[str, Any]) -> dict[str, Any]:
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
        return {
            "message_id": item.get("id"),
            "chat_id": item.get("chat_id"),
            "sender": cls._chat_participant(sender),
            "type": item.get("type"),
            "content": item.get("content"),
            "is_mine": bool(item.get("is_mine")),
            "created_at": item.get("created_at"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _group_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "group_id": item.get("id"),
            "name": item.get("name"),
            "viewer_role": item.get("viewer_role"),
            "member_count": item.get("member_count"),
            "pet_count": item.get("pet_count"),
        }

    @classmethod
    def _group(cls, item: dict[str, Any]) -> dict[str, Any]:
        members = item.get("members") if isinstance(item.get("members"), list) else []
        pets = item.get("pets") if isinstance(item.get("pets"), list) else []
        return {
            **cls._group_summary(item),
            "created_at": item.get("created_at"),
            "version": item.get("updated_at", item.get("version")),
            "members": [cls._group_member(value) for value in members if isinstance(value, dict)],
            "pets": [cls._group_pet(value) for value in pets if isinstance(value, dict)],
        }

    @staticmethod
    def _group_member(item: dict[str, Any]) -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        return {
            "user_id": item.get("user_id", user.get("id")),
            "user_name": user.get("name", item.get("name")),
            "role": item.get("role"),
            "start_at": item.get("start_at"),
        }

    @staticmethod
    def _group_pet(item: dict[str, Any]) -> dict[str, Any]:
        pet_type = item.get("pet_type") if isinstance(item.get("pet_type"), dict) else {}
        return {
            "pet_id": item.get("id", item.get("pet_id")),
            "pet_name": item.get("name", item.get("pet_name")),
            "pet_type_id": pet_type.get("id", item.get("pet_type_id")),
            "species": pet_type.get("name", item.get("species")),
            "photo_url": item.get("photo_url"),
        }

    @staticmethod
    def _user_reference(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": item.get("id", item.get("user_id")),
            "user_name": item.get("name", item.get("user_name")),
        }

    @staticmethod
    def _resource_invitation(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "invitation_id": item.get("id", item.get("invitation_id")),
            "type": item.get("type"),
            "status": item.get("status"),
            "group_id": item.get("group_id"),
            "group_name": item.get("group_name"),
            "ledger_id": item.get("ledger_id"),
            "ledger_title": item.get("ledger_title"),
            "role": item.get("role"),
            "expires_at": item.get("expires_at"),
            "created_at": item.get("created_at"),
            "version": item.get("updated_at", item.get("version")),
            "invitation_url": item.get("invitation_url"),
        }

    @staticmethod
    def _currency(item: dict[str, Any]) -> dict[str, Any]:
        return {key: item.get(key) for key in ("code", "name", "symbol", "minor_units")}

    @classmethod
    def _ledger(cls, item: dict[str, Any]) -> dict[str, Any]:
        currency = item.get("currency") if isinstance(item.get("currency"), dict) else None
        members = item.get("members") if isinstance(item.get("members"), list) else []
        return {
            "ledger_id": item.get("id", item.get("ledger_id")),
            "title": item.get("title"),
            "currency_code": item.get("currency_code"),
            "currency": cls._currency(currency) if currency is not None else None,
            "group_id": item.get("group_id"),
            "sync_group_pets": bool(item.get("sync_group_pets")),
            "archived_at": item.get("archived_at"),
            "member_count": item.get("member_count"),
            "pet_count": item.get("pet_count"),
            "can_delete": bool(item.get("can_delete")),
            "members": [cls._ledger_member(value) for value in members if isinstance(value, dict)],
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _ledger_member(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": item.get("user_id", item.get("id")),
            "user_name": item.get("name", item.get("user_name")),
            "start_at": item.get("start_at"),
        }

    @staticmethod
    def _ledger_account(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "account_id": item.get("id", item.get("account_id")),
            "name": item.get("name"),
            "archived_at": item.get("archived_at"),
            "income_minor": item.get("income_minor"),
            "expense_minor": item.get("expense_minor"),
            "net_activity_minor": item.get("net_activity_minor"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _ledger_category(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "category_id": item.get("id", item.get("category_id")),
            "name": item.get("name"),
            "applies_to": item.get("applies_to"),
            "archived_at": item.get("archived_at"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _ledger_pet(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "pet_id": item.get("id", item.get("pet_id")),
            "pet_name": item.get("name", item.get("pet_name")),
            "photo_url": item.get("photo_url"),
            "can_view_profile": bool(item.get("can_view_profile")),
            "sources": [value for value in item.get("sources", []) if isinstance(value, str)]
            if isinstance(item.get("sources"), list)
            else [],
            "income_minor": item.get("income_minor"),
            "expense_minor": item.get("expense_minor"),
            "net_activity_minor": item.get("net_activity_minor"),
        }

    @classmethod
    def _ledger_dashboard(cls, item: dict[str, Any]) -> dict[str, Any]:
        def records(key: str, mapper) -> list[dict[str, Any]]:
            values = item.get(key)
            return (
                [mapper(value) for value in values if isinstance(value, dict)]
                if isinstance(values, list)
                else []
            )

        def totals(value: Any) -> dict[str, Any]:
            value = value if isinstance(value, dict) else {}
            return {key: value.get(key) for key in ("income", "expense", "net_activity")}

        def named_total(value: dict[str, Any]) -> dict[str, Any]:
            return {key: value.get(key) for key in ("id", "name", "total")}

        return {
            "current_month": totals(item.get("current_month")),
            "previous_month": totals(item.get("previous_month")),
            "accounts": records("accounts", cls._ledger_account),
            "spending_by_category": records("spending_by_category", named_total),
            "income_by_category": records("income_by_category", named_total),
            "spending_by_pet": records("spending_by_pet", named_total),
            "monthly_trend": records(
                "monthly_trend",
                lambda value: {key: value.get(key) for key in ("month", "income", "expense")},
            ),
            "recent_transactions": records("recent_transactions", cls._ledger_transaction),
        }

    @staticmethod
    def _ledger_transaction(item: dict[str, Any]) -> dict[str, Any]:
        creator = item.get("created_by") if isinstance(item.get("created_by"), dict) else {}
        pets = item.get("pets") if isinstance(item.get("pets"), list) else []
        return {
            "transaction_id": item.get("id", item.get("transaction_id")),
            "ledger_id": item.get("ledger_id"),
            "account_id": item.get("account_id"),
            "account_name": item.get("account_name"),
            "category_id": item.get("category_id"),
            "category_name": item.get("category_name"),
            "type": item.get("type"),
            "amount_minor": item.get("amount_minor"),
            "amount": item.get("amount"),
            "occurred_on": item.get("occurred_on"),
            "description": item.get("description"),
            "created_by": {"user_id": creator.get("id"), "user_name": creator.get("name")},
            "pets": [
                {
                    "pet_id": value.get("id"),
                    "pet_name": value.get("name"),
                    "pet_name_snapshot": value.get("name_snapshot"),
                }
                for value in pets
                if isinstance(value, dict)
            ],
            "has_receipt": bool(item.get("has_receipt")),
            "created_at": item.get("created_at"),
            "version": item.get("updated_at", item.get("version")),
        }

    @classmethod
    def _notification(cls, item: dict[str, Any]) -> dict[str, Any]:
        actions = item.get("actions") if isinstance(item.get("actions"), list) else []
        return {
            "notification_id": item.get("id", item.get("notification_id")),
            "level": item.get("level"),
            "title": item.get("title"),
            "body": item.get("body"),
            "url": cls._safe_app_path(item.get("url")),
            "actions": [
                {
                    "key": action.get("key", action.get("action_key")),
                    "label": action.get("label"),
                    "style": action.get("style"),
                }
                for action in actions
                if isinstance(action, dict)
            ],
            "created_at": item.get("created_at"),
            "read_at": item.get("read_at"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _notification_preference(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "type",
                "label",
                "description",
                "group",
                "group_label",
                "email_enabled",
                "in_app_enabled",
                "telegram_enabled",
            )
        }

    @staticmethod
    def _profile(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": item.get("id", item.get("user_id")),
            "name": item.get("name"),
            "email": item.get("email"),
            "locale": item.get("locale", item.get("language")),
            "timezone": item.get("timezone"),
            "avatar_url": item.get("avatar_url"),
            "has_password": bool(item.get("has_password")),
            "email_verified_at": item.get("email_verified_at"),
            "is_premium": bool(item.get("is_premium")),
            "is_banned": bool(item.get("is_banned")),
            "banned_at": item.get("banned_at"),
            "ban_reason": item.get("ban_reason"),
            "storage_used_bytes": item.get("storage_used_bytes"),
            "storage_limit_bytes": item.get("storage_limit_bytes"),
            "owner_weight_kg": item.get("owner_weight_kg"),
            "owner_weight_recorded_at": item.get("owner_weight_recorded_at"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _owner_weight(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "weight_id": item.get("id", item.get("weight_id")),
            "weight_kg": item.get("weight_kg"),
            "record_date": item.get("record_date"),
            "notes": item.get("notes"),
            "version": item.get("updated_at", item.get("version")),
        }

    @staticmethod
    def _account_invitation(item: dict[str, Any]) -> dict[str, Any]:
        recipient = item.get("recipient") if isinstance(item.get("recipient"), dict) else None
        return {
            "invitation_id": item.get("id", item.get("invitation_id")),
            "code": item.get("code"),
            "status": item.get("status"),
            "expires_at": item.get("expires_at"),
            "created_at": item.get("created_at"),
            "invitation_url": item.get("invitation_url"),
            "recipient": (
                {
                    "user_id": recipient.get("id"),
                    "user_name": recipient.get("name"),
                    "email": recipient.get("email"),
                }
                if recipient is not None
                else None
            ),
        }

    @classmethod
    def _bounded_page(cls, page: int, per_page: int) -> None:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            cls._error("validation_error", "page must be a positive integer.", False)
        if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 100:
            cls._error("validation_error", "per_page must be between 1 and 100.", False)

    @staticmethod
    def _simple_pagination(
        item: dict[str, Any], *, default_per_page: int | None = None
    ) -> dict[str, Any]:
        return {
            "current_page": item.get("current_page"),
            "last_page": item.get("last_page"),
            "per_page": item.get("per_page", default_per_page),
            "total": item.get("total"),
        }

    @staticmethod
    def _safe_app_path(value: Any) -> str | None:
        return (
            value
            if isinstance(value, str) and value.startswith("/") and not value.startswith("//")
            else None
        )

    @staticmethod
    def _find_relationship(
        sharing: dict[str, Any], user_id: int, role: str
    ) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in sharing.get("relationships", [])
                if item.get("user_id") == user_id and item.get("relationship_type") == role
            ),
            None,
        )

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

    async def _verify_absent(self, operation, *args) -> None:
        try:
            await operation(*args)
        except MeoApiError as exc:
            if exc.payload.get("code") == "upstream_not_found":
                return
            raise self._tool_error(
                "post_write_verification_failed",
                "Meo accepted the deletion but absence could not be verified. Re-read it later.",
                True,
            ) from exc
        self._error(
            "post_write_verification_failed",
            "Meo accepted the deletion but the target is still present.",
            True,
        )

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
    def _habit_configuration(
        cls,
        *,
        name: str | None = None,
        value_type: str | None = None,
        pet_ids: list[int] | None = None,
        timezone: str | None = None,
        scale_min: int | None = None,
        scale_max: int | None = None,
        day_summary_mode: str | None = None,
        share_with_coowners: bool | None = None,
        reminder_enabled: bool | None = None,
        reminder_time: str | None = None,
        reminder_weekdays: list[int] | None = None,
        creating: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if name is not None:
            result["name"] = cls._required_text(name, "name", 120)
        if value_type is not None:
            value_type = cls._required_text(value_type, "value_type").lower()
            if value_type not in HABIT_VALUE_TYPES:
                cls._error("validation_error", "value_type is not supported.", False)
            result["value_type"] = value_type
        if pet_ids is not None:
            if not pet_ids:
                cls._error("validation_error", "pet_ids must contain at least one pet.", False)
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in pet_ids
            ):
                cls._error("validation_error", "pet_ids must be positive integers.", False)
            if len(set(pet_ids)) != len(pet_ids):
                cls._error("validation_error", "pet_ids must be unique.", False)
            result["pet_ids"] = pet_ids
        if timezone is not None:
            timezone = cls._required_text(timezone, "timezone", 255)
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError:
                cls._error("validation_error", "timezone must be a valid IANA timezone.", False)
            result["timezone"] = timezone
        if scale_min is not None:
            if isinstance(scale_min, bool) or not isinstance(scale_min, int):
                cls._error("validation_error", "scale_min must be an integer.", False)
            result["scale_min"] = scale_min
        if scale_max is not None:
            if isinstance(scale_max, bool) or not isinstance(scale_max, int):
                cls._error("validation_error", "scale_max must be an integer.", False)
            result["scale_max"] = scale_max
        if scale_min is not None and scale_max is not None and scale_max < scale_min:
            cls._error("validation_error", "scale_max must be at least scale_min.", False)
        if creating and value_type == "integer_scale" and (scale_min is None or scale_max is None):
            cls._error("validation_error", "integer_scale requires both scale bounds.", False)
        if creating and value_type == "yes_no" and (scale_min is not None or scale_max is not None):
            cls._error("validation_error", "yes_no habits cannot define scale bounds.", False)
        if day_summary_mode is not None:
            if day_summary_mode not in HABIT_SUMMARY_MODES:
                cls._error("validation_error", "day_summary_mode is not supported.", False)
            result["day_summary_mode"] = day_summary_mode
        if share_with_coowners is not None:
            result["share_with_coowners"] = share_with_coowners
        if reminder_enabled is not None:
            result["reminder_enabled"] = reminder_enabled
        if reminder_time is not None:
            reminder_time = cls._required_text(reminder_time, "reminder_time")
            if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", reminder_time) is None:
                cls._error("validation_error", "reminder_time must use HH:MM.", False)
            result["reminder_time"] = reminder_time
        if creating and reminder_enabled and reminder_time is None:
            cls._error("validation_error", "Enabled reminders require reminder_time.", False)
        if reminder_weekdays is not None:
            if any(
                isinstance(day, bool) or not isinstance(day, int) or day not in range(7)
                for day in reminder_weekdays
            ):
                cls._error(
                    "validation_error",
                    "reminder_weekdays must contain values from 0 through 6.",
                    False,
                )
            if len(set(reminder_weekdays)) != len(reminder_weekdays):
                cls._error("validation_error", "reminder_weekdays must be unique.", False)
            result["reminder_weekdays"] = reminder_weekdays
        if creating and (
            "name" not in result or "value_type" not in result or "pet_ids" not in result
        ):
            cls._error("validation_error", "name, value_type, and pet_ids are required.", False)
        return result

    @classmethod
    def _habit_entries(cls, entries: list[dict[str, int | None]]) -> list[dict[str, int | None]]:
        if not isinstance(entries, list) or not entries:
            cls._error("validation_error", "entries must contain at least one row.", False)
        result: list[dict[str, int | None]] = []
        seen: set[int] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                cls._error("validation_error", "Each entry must be an object.", False)
            pet_id, value = entry.get("pet_id"), entry.get("value_int")
            if isinstance(pet_id, bool) or not isinstance(pet_id, int) or pet_id < 1:
                cls._error("validation_error", "Each entry requires a positive pet_id.", False)
            if pet_id in seen:
                cls._error("validation_error", "Entry pet_ids must be unique.", False)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                cls._error("validation_error", "value_int must be an integer or null.", False)
            seen.add(pet_id)
            result.append({"pet_id": pet_id, "value_int": value})
        return result

    @classmethod
    def _chip_number(cls, value: str) -> str:
        value = cls._required_text(value, "chip_number", 20)
        if len(value) < 10:
            cls._error("validation_error", "chip_number must be 10-20 characters.", False)
        return value

    @classmethod
    def _sharing_role(cls, value: str) -> str:
        value = cls._required_text(value, "relationship_type", 32).lower()
        if value not in SHARING_ROLES:
            cls._error(
                "validation_error",
                "relationship_type must be owner, editor, or viewer.",
                False,
            )
        return value

    @classmethod
    def _placement_request_type(cls, value: str | None, *, optional: bool = False) -> str | None:
        if value is None and optional:
            return None
        normalized = cls._required_text(value, "request_type", 32).lower()
        if normalized not in PLACEMENT_REQUEST_TYPES:
            cls._error(
                "validation_error",
                "request_type must be permanent, foster_free, foster_paid, or pet_sitting.",
                False,
            )
        return normalized

    @classmethod
    def _country_code(cls, value: str | None, *, optional: bool = False) -> str | None:
        if value is None and optional:
            return None
        normalized = cls._required_text(value, "country", 2).upper()
        if len(normalized) != 2 or not normalized.isalpha():
            cls._error("validation_error", "country must be a two-letter code.", False)
        return normalized

    @classmethod
    def _relationship_type_set(cls, values: list[str]) -> set[str]:
        if not isinstance(values, list) or not values:
            cls._error(
                "validation_error",
                "expected_relationship_types must contain at least one role.",
                False,
            )
        normalized = {
            cls._required_text(value, "expected_relationship_types", 32).lower() for value in values
        }
        if len(normalized) != len(values) or not normalized <= RELATIONSHIP_TYPES:
            cls._error(
                "validation_error",
                "expected_relationship_types must be unique supported roles.",
                False,
            )
        return normalized

    @classmethod
    def _group_role(cls, value: str) -> str:
        normalized = cls._required_text(value, "role", 16).lower()
        if normalized not in {"admin", "member"}:
            cls._error("validation_error", "role must be admin or member.", False)
        return normalized

    @classmethod
    def _positive_id_list(
        cls, values: list[int], field: str, *, allow_empty: bool = False
    ) -> list[int]:
        if not isinstance(values, list) or (not values and not allow_empty):
            cls._error(
                "validation_error",
                f"{field} must contain at least one positive integer.",
                False,
            )
        normalized: list[int] = []
        for value in values:
            cls._positive(value, field)
            normalized.append(value)
        if len(set(normalized)) != len(normalized):
            cls._error("validation_error", f"{field} must not contain duplicates.", False)
        return normalized

    def _invitation_token(self, value: str) -> str:
        value = self._required_text(value, "invitation", 2048)
        if INVITATION_TOKEN_PATTERN.fullmatch(value):
            return value
        try:
            parsed = urlsplit(value)
        except ValueError:
            parsed = None
        if parsed is not None:
            segments = [segment for segment in parsed.path.split("/") if segment]
            if (
                parsed.scheme == "https"
                and parsed.hostname == self.settings.meo_base_url.host
                and parsed.port in {None, 443}
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and len(segments) == 2
                and segments[0] == "invite"
                and INVITATION_TOKEN_PATTERN.fullmatch(segments[1])
            ):
                return segments[1]
        self._error(
            "validation_error",
            "invitation must be a 64-character token or an HTTPS /invite/token URL.",
            False,
        )

    @classmethod
    def _verification_error(cls, message: str) -> None:
        cls._error("post_write_verification_failed", message, True)

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
