from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal
from urllib.parse import parse_qs, urlsplit

import structlog
import uvicorn
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from .config import Settings, get_settings
from .database import make_session_factory
from .meo_api import MeoApi, MeoApiError
from .oauth import ALLOWED_SCOPES, DatabaseOAuthProvider
from .security import redact_log_event

logger = structlog.get_logger()


class HabitEntryInput(BaseModel):
    pet_id: int = Field(ge=1)
    value_int: int | None = None


class HelperContactInput(BaseModel):
    type: Literal[
        "telegram",
        "whatsapp",
        "zalo",
        "facebook",
        "instagram",
        "x_twitter",
        "linkedin",
        "tiktok",
        "wechat",
        "viber",
        "line",
        "website",
        "email",
        "other",
    ]
    value: str = Field(min_length=1, max_length=255)


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        def error(code: str, message: str, status_code: int) -> JSONResponse:
            return JSONResponse(
                {
                    "error": {
                        "code": code,
                        "message": message,
                        "request_id": request.state.request_id,
                    }
                },
                status_code=status_code,
                headers={"X-Request-ID": request.state.request_id},
            )

        host = request.headers.get("host", "")
        public_host = request.app.state.settings.public_base_url.host
        hostname = urlsplit(f"//{host}").hostname
        loopback_health = request.url.path == "/health" and hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
        if hostname != public_host and not loopback_health:
            return error("invalid_host", "The request Host is not allowed.", 421)

        if request.method in {"POST", "PUT", "PATCH"}:
            raw_length = request.headers.get("content-length")
            try:
                declared_length = int(raw_length) if raw_length is not None else None
            except ValueError:
                return error("invalid_content_length", "Content-Length must be an integer.", 400)
            if declared_length is not None and declared_length > 1_048_576:
                return error("request_too_large", "The request body exceeds 1 MiB.", 413)
            body = await request.body()
            if len(body) > 1_048_576:
                return error("request_too_large", "The request body exceeds 1 MiB.", 413)
            if request.url.path == "/token":
                form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
                if form.get("resource") != [request.app.state.settings.resource]:
                    return JSONResponse(
                        {
                            "error": "invalid_target",
                            "error_description": "The resource parameter must name this MCP endpoint.",
                        },
                        status_code=400,
                        headers={
                            "Cache-Control": "no-store",
                            "Pragma": "no-cache",
                            "X-Request-ID": request.state.request_id,
                        },
                    )
        origin = request.headers.get("origin")
        allowed = request.app.state.settings.allowed_origins
        if origin and origin not in allowed:
            return error("invalid_origin", "The request Origin is not allowed.", 403)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or get_settings()
    # httpx logs complete request URLs at INFO. Keep transport diagnostics at
    # WARNING so sensitive URL material cannot enter normal application logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    structlog.configure(
        processors=[redact_log_event, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    engine, sessions = make_session_factory(settings.database_url)
    provider = DatabaseOAuthProvider(sessions, settings)
    api = MeoApi(sessions, settings)
    public_host = settings.public_base_url.host
    server = FastMCP(
        "Meo Mai Moi",
        instructions=(
            "Read and safely update Meo Mai Moi pets, health history, habits, photos, "
            "microchips, pet sharing, placement opportunities, helper profiles, messages, "
            "groups, finances, notifications, self profile, and invitations. "
            "Resolve names to stable IDs, read targets before updates, preserve the returned "
            "version, and reuse an idempotency key only for an exact write retry."
        ),
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=settings.issuer,
            resource_server_url=settings.resource,
            required_scopes=[],
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=ALLOWED_SCOPES, default_scopes=ALLOWED_SCOPES
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host, f"{public_host}:*"],
            allowed_origins=settings.allowed_origins,
        ),
    )

    read_annotations = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
    create_annotations = {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
    update_annotations = {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }

    def tool_result(result: dict) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, separators=(",", ":")))],
            structuredContent=result,
            isError=False,
        )

    def tool_error(exc: MeoApiError) -> CallToolResult:
        return CallToolResult(
            content=[
                TextContent(
                    type="text", text=json.dumps(exc.payload, separators=(",", ":"), sort_keys=True)
                )
            ],
            structuredContent={"error": exc.payload},
            isError=True,
        )

    async def call(operation, *args, **kwargs) -> CallToolResult:
        try:
            return tool_result(await operation(*args, **kwargs))
        except MeoApiError as exc:
            return tool_error(exc)

    @server.tool(annotations=read_annotations)
    async def list_pets() -> CallToolResult:
        """List the authenticated user's pets with basic profiles and photo URLs."""
        return await call(api.list_pets)

    @server.tool(annotations=read_annotations)
    async def find_pets(name: str | None = None, species: str | None = None) -> CallToolResult:
        """Find pet candidates by partial name and/or exact species before targeted work."""
        return await call(api.find_pets, name, species)

    @server.tool(annotations=read_annotations)
    async def get_pet(pet_id: int) -> CallToolResult:
        """Get a narrowed pet profile using an explicit stable pet ID."""
        return await call(api.get_pet, pet_id)

    @server.tool(annotations=read_annotations)
    async def list_pet_types() -> CallToolResult:
        """List supported species and pet-care capability flags."""
        return await call(api.list_pet_types)

    @server.tool(annotations=read_annotations)
    async def list_weights(pet_id: int, page: int = 1) -> CallToolResult:
        """List one pet's paginated weight history."""
        return await call(api.list_weights, pet_id, page)

    @server.tool(annotations=read_annotations)
    async def get_weight(pet_id: int, weight_id: int) -> CallToolResult:
        """Get one explicit weight record belonging to a pet."""
        return await call(api.get_weight, pet_id, weight_id)

    @server.tool(annotations=read_annotations)
    async def list_vaccinations(
        pet_id: int,
        page: int = 1,
        status: Literal["active", "completed", "all"] = "active",
    ) -> CallToolResult:
        """List a pet's vaccinations, optionally filtered by lifecycle status."""
        return await call(api.list_vaccinations, pet_id, page, status)

    @server.tool(annotations=read_annotations)
    async def get_vaccination(pet_id: int, vaccination_id: int) -> CallToolResult:
        """Get one explicit vaccination record belonging to a pet."""
        return await call(api.get_vaccination, pet_id, vaccination_id)

    @server.tool(annotations=read_annotations)
    async def list_medical_records(
        pet_id: int, page: int = 1, record_type: str | None = None
    ) -> CallToolResult:
        """List a pet's medical history, optionally filtered by record type."""
        return await call(api.list_medical_records, pet_id, page, record_type)

    @server.tool(annotations=read_annotations)
    async def get_medical_record(pet_id: int, record_id: int) -> CallToolResult:
        """Get one explicit medical record belonging to a pet."""
        return await call(api.get_medical_record, pet_id, record_id)

    @server.tool(annotations=read_annotations)
    async def get_pets_overview(
        name: str | None = None,
        species: str | None = None,
        only_with_upcoming_vaccination: bool = False,
        sort_by: Literal["name", "next_vaccination_due_at", "next_birthday_at"] = "name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> CallToolResult:
        """Compare pets with birthday context, active vaccinations, and recent weights."""
        return await call(
            api.get_pets_overview,
            name,
            species,
            only_with_upcoming_vaccination,
            sort_by,
            sort_order,
        )

    @server.tool(annotations=create_annotations)
    async def create_pet(
        name: str,
        species: str,
        country: str,
        idempotency_key: str,
        sex: Literal["male", "female", "not_specified", "unknown"] | None = None,
        birth_date: date | None = None,
        birth_month_year: str | None = None,
        age_months: int | None = None,
        description: str | None = None,
        allow_duplicate: bool = False,
    ) -> CallToolResult:
        """Create a pet after exact duplicate checks; use one key per distinct intent."""
        return await call(
            api.create_pet,
            name,
            species,
            country,
            idempotency_key,
            sex,
            birth_date,
            birth_month_year,
            age_months,
            description,
            allow_duplicate,
        )

    @server.tool(annotations=update_annotations)
    async def update_pet(
        pet_id: int,
        base_version: str,
        idempotency_key: str,
        name: str | None = None,
        species: str | None = None,
        sex: Literal["male", "female", "not_specified", "unknown"] | None = None,
        birth_date: date | None = None,
        birth_month_year: str | None = None,
        age_months: int | None = None,
        description: str | None = None,
    ) -> CallToolResult:
        """Update an explicit pet using the version returned by get_pet."""
        return await call(
            api.update_pet,
            pet_id,
            base_version,
            idempotency_key,
            name,
            species,
            sex,
            birth_date,
            birth_month_year,
            age_months,
            description,
        )

    @server.tool(annotations=create_annotations)
    async def add_weight(
        pet_id: int,
        weight_kg: float,
        record_date: date,
        idempotency_key: str,
    ) -> CallToolResult:
        """Add one dated weight to an explicit pet and verify the created record."""
        return await call(api.add_weight, pet_id, weight_kg, record_date, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def update_weight(
        pet_id: int,
        weight_id: int,
        base_version: str,
        idempotency_key: str,
        weight_kg: float | None = None,
        record_date: date | None = None,
    ) -> CallToolResult:
        """Update an explicit weight using the version returned by get_weight."""
        return await call(
            api.update_weight,
            pet_id,
            weight_id,
            base_version,
            idempotency_key,
            weight_kg,
            record_date,
        )

    @server.tool(annotations=create_annotations)
    async def add_vaccination(
        pet_id: int,
        vaccine_name: str,
        administered_at: date,
        idempotency_key: str,
        due_at: date | None = None,
        notes: str | None = None,
    ) -> CallToolResult:
        """Add one vaccination to an explicit pet and verify the created record."""
        return await call(
            api.add_vaccination,
            pet_id,
            vaccine_name,
            administered_at,
            idempotency_key,
            due_at,
            notes,
        )

    @server.tool(annotations=update_annotations)
    async def update_vaccination(
        pet_id: int,
        vaccination_id: int,
        base_version: str,
        idempotency_key: str,
        vaccine_name: str | None = None,
        administered_at: date | None = None,
        due_at: date | None = None,
        notes: str | None = None,
    ) -> CallToolResult:
        """Update an explicit vaccination using the version returned by get_vaccination."""
        return await call(
            api.update_vaccination,
            pet_id,
            vaccination_id,
            base_version,
            idempotency_key,
            vaccine_name,
            administered_at,
            due_at,
            notes,
        )

    @server.tool(annotations=create_annotations)
    async def add_medical_record(
        pet_id: int,
        record_type: Literal[
            "checkup", "deworming", "flea_treatment", "surgery", "dental", "other"
        ],
        record_date: date,
        idempotency_key: str,
        description: str | None = None,
        vet_name: str | None = None,
    ) -> CallToolResult:
        """Add one dated medical event to an explicit pet and verify it."""
        return await call(
            api.add_medical_record,
            pet_id,
            record_type,
            record_date,
            idempotency_key,
            description,
            vet_name,
        )

    @server.tool(annotations=update_annotations)
    async def update_medical_record(
        pet_id: int,
        record_id: int,
        base_version: str,
        idempotency_key: str,
        record_type: Literal["checkup", "deworming", "flea_treatment", "surgery", "dental", "other"]
        | None = None,
        record_date: date | None = None,
        description: str | None = None,
        vet_name: str | None = None,
    ) -> CallToolResult:
        """Update an explicit medical record using its read version."""
        return await call(
            api.update_medical_record,
            pet_id,
            record_id,
            base_version,
            idempotency_key,
            record_type,
            record_date,
            description,
            vet_name,
        )

    @server.tool(annotations=read_annotations)
    async def list_habits() -> CallToolResult:
        """List visible habit trackers with narrowed configuration."""
        return await call(api.list_habits)

    @server.tool(annotations=read_annotations)
    async def get_habit(habit_id: int) -> CallToolResult:
        """Get one explicit habit and its concurrency version."""
        return await call(api.get_habit, habit_id)

    @server.tool(annotations=read_annotations)
    async def get_habit_heatmap(
        habit_id: int, weeks: int = 52, end_date: date | None = None
    ) -> CallToolResult:
        """Read bounded daily summary values for one habit."""
        return await call(api.get_habit_heatmap, habit_id, weeks, end_date)

    @server.tool(annotations=read_annotations)
    async def get_habit_day_entries(habit_id: int, entry_date: date) -> CallToolResult:
        """Read editable per-pet entries for an explicit habit date."""
        return await call(api.get_habit_day_entries, habit_id, entry_date)

    @server.tool(annotations=create_annotations)
    async def create_habit(
        name: str,
        value_type: Literal["yes_no", "integer_scale"],
        pet_ids: list[int],
        idempotency_key: str,
        timezone: str | None = None,
        scale_min: int | None = None,
        scale_max: int | None = None,
        day_summary_mode: Literal[
            "average_scored_pets", "average_all_pets", "sum"
        ] = "average_scored_pets",
        share_with_coowners: bool = False,
        reminder_enabled: bool = False,
        reminder_time: str | None = None,
        reminder_weekdays: list[int] | None = None,
    ) -> CallToolResult:
        """Create and verify a habit for explicit owned pet IDs."""
        return await call(
            api.create_habit,
            name,
            value_type,
            pet_ids,
            idempotency_key,
            timezone,
            scale_min,
            scale_max,
            day_summary_mode,
            share_with_coowners,
            reminder_enabled,
            reminder_time,
            reminder_weekdays,
        )

    @server.tool(annotations=update_annotations)
    async def update_habit(
        habit_id: int,
        base_version: str,
        idempotency_key: str,
        name: str | None = None,
        timezone: str | None = None,
        scale_min: int | None = None,
        scale_max: int | None = None,
        day_summary_mode: Literal["average_scored_pets", "average_all_pets", "sum"] | None = None,
        share_with_coowners: bool | None = None,
        reminder_enabled: bool | None = None,
        reminder_time: str | None = None,
        reminder_weekdays: list[int] | None = None,
        pet_ids: list[int] | None = None,
    ) -> CallToolResult:
        """Update and verify an explicit habit using its read version."""
        return await call(
            api.update_habit,
            habit_id,
            base_version,
            idempotency_key,
            name,
            timezone,
            scale_min,
            scale_max,
            day_summary_mode,
            share_with_coowners,
            reminder_enabled,
            reminder_time,
            reminder_weekdays,
            pet_ids,
        )

    @server.tool(annotations=update_annotations)
    async def save_habit_day_entries(
        habit_id: int,
        entry_date: date,
        entries: list[HabitEntryInput],
        idempotency_key: str,
    ) -> CallToolResult:
        """Upsert explicit per-pet values for one habit date and verify them."""
        return await call(
            api.save_habit_day_entries,
            habit_id,
            entry_date,
            [entry.model_dump() for entry in entries],
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def archive_habit(
        habit_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Archive and verify an explicit habit using its read version."""
        return await call(api.archive_habit, habit_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def restore_habit(
        habit_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Restore and verify an explicit archived habit using its read version."""
        return await call(api.restore_habit, habit_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def delete_habit(
        habit_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Permanently delete an explicit habit and verify its absence."""
        return await call(api.delete_habit, habit_id, base_version, idempotency_key)

    @server.tool(annotations=read_annotations)
    async def list_pet_photos(pet_id: int) -> CallToolResult:
        """List one pet's photos and the pet concurrency version."""
        return await call(api.list_pet_photos, pet_id)

    @server.tool(annotations=create_annotations)
    async def upload_pet_photo_from_url(
        pet_id: int,
        base_version: str,
        source_url: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Attach a validated public HTTPS image and verify the photo."""
        return await call(
            api.upload_pet_photo_from_url,
            pet_id,
            base_version,
            source_url,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def set_primary_pet_photo(
        pet_id: int,
        photo_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Set an explicit attached photo as primary and verify it."""
        return await call(
            api.set_primary_pet_photo, pet_id, photo_id, base_version, idempotency_key
        )

    @server.tool(annotations=update_annotations)
    async def delete_pet_photo(
        pet_id: int,
        photo_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Delete an explicit attached photo and verify its absence."""
        return await call(api.delete_pet_photo, pet_id, photo_id, base_version, idempotency_key)

    @server.tool(annotations=read_annotations)
    async def list_microchips(pet_id: int, page: int = 1) -> CallToolResult:
        """List one pet's paginated microchip records."""
        return await call(api.list_microchips, pet_id, page)

    @server.tool(annotations=read_annotations)
    async def get_microchip(pet_id: int, microchip_id: int) -> CallToolResult:
        """Get one explicit microchip record and its concurrency version."""
        return await call(api.get_microchip, pet_id, microchip_id)

    @server.tool(annotations=create_annotations)
    async def add_microchip(
        pet_id: int,
        chip_number: str,
        idempotency_key: str,
        issuer: str | None = None,
        implanted_at: date | None = None,
    ) -> CallToolResult:
        """Add and verify a microchip without finance authority."""
        return await call(
            api.add_microchip,
            pet_id,
            chip_number,
            idempotency_key,
            issuer,
            implanted_at,
        )

    @server.tool(annotations=update_annotations)
    async def update_microchip(
        pet_id: int,
        microchip_id: int,
        base_version: str,
        idempotency_key: str,
        chip_number: str | None = None,
        issuer: str | None = None,
        implanted_at: date | None = None,
    ) -> CallToolResult:
        """Update and verify an explicit microchip using its read version."""
        return await call(
            api.update_microchip,
            pet_id,
            microchip_id,
            base_version,
            idempotency_key,
            chip_number,
            issuer,
            implanted_at,
        )

    @server.tool(annotations=update_annotations)
    async def delete_microchip(
        pet_id: int,
        microchip_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Delete a microchip, preserve linked finance data, and verify absence."""
        return await call(
            api.delete_microchip,
            pet_id,
            microchip_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=read_annotations)
    async def get_pet_sharing(pet_id: int) -> CallToolResult:
        """Read active collaborators, caller permissions, and sharing version."""
        return await call(api.get_pet_sharing, pet_id)

    @server.tool(annotations=read_annotations)
    async def list_pet_relationship_suggestions(pet_id: int) -> CallToolResult:
        """List stable known-user candidates eligible for direct pet sharing."""
        return await call(api.list_pet_relationship_suggestions, pet_id)

    @server.tool(annotations=read_annotations)
    async def list_pet_invitations(pet_id: int) -> CallToolResult:
        """List pending bearer invitation links for one explicitly owned pet."""
        return await call(api.list_pet_invitations, pet_id)

    @server.tool(annotations=read_annotations)
    async def preview_pet_invitation(invitation: str) -> CallToolResult:
        """Preview a supplied invitation token or link without echoing it."""
        return await call(api.preview_pet_invitation, invitation)

    @server.tool(annotations=update_annotations)
    async def add_pet_collaborator(
        pet_id: int,
        user_id: int,
        relationship_type: Literal["owner", "editor", "viewer"],
        sharing_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Grant a freshly suggested stable user a role and verify it."""
        return await call(
            api.add_pet_collaborator,
            pet_id,
            user_id,
            relationship_type,
            sharing_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def change_pet_collaborator_role(
        pet_id: int,
        user_id: int,
        relationship_type: Literal["owner", "editor", "viewer"],
        sharing_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Change an explicit collaborator role at a known sharing version."""
        return await call(
            api.change_pet_collaborator_role,
            pet_id,
            user_id,
            relationship_type,
            sharing_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def remove_pet_collaborator(
        pet_id: int,
        user_id: int,
        sharing_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Remove one explicit collaborator and verify access is absent."""
        return await call(
            api.remove_pet_collaborator,
            pet_id,
            user_id,
            sharing_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def create_pet_invitation(
        pet_id: int,
        relationship_type: Literal["owner", "editor", "viewer"],
        sharing_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Create and verify a role-specific bearer invitation link."""
        return await call(
            api.create_pet_invitation,
            pet_id,
            relationship_type,
            sharing_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def revoke_pet_invitation(
        pet_id: int,
        invitation_id: int,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Revoke one explicit pending invitation and verify its absence."""
        return await call(
            api.revoke_pet_invitation,
            pet_id,
            invitation_id,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def accept_pet_invitation(
        invitation: str,
        expected_pet_name: str,
        expected_relationship_type: Literal["owner", "editor", "viewer"],
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Accept after fresh pet/role preview and authority-side version check."""
        return await call(
            api.accept_pet_invitation,
            invitation,
            expected_pet_name,
            expected_relationship_type,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def decline_pet_invitation(
        invitation: str,
        expected_pet_name: str,
        expected_relationship_type: Literal["owner", "editor", "viewer"],
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Decline after fresh pet/role preview and authority-side version check."""
        return await call(
            api.decline_pet_invitation,
            invitation,
            expected_pet_name,
            expected_relationship_type,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def leave_shared_pet(
        pet_id: int,
        sharing_base_version: str,
        expected_relationship_types: list[str],
        idempotency_key: str,
    ) -> CallToolResult:
        """Leave only when the fresh relationship set exactly matches expectation."""
        return await call(
            api.leave_shared_pet,
            pet_id,
            sharing_base_version,
            expected_relationship_types,
            idempotency_key,
        )

    @server.tool(annotations=read_annotations)
    async def list_placement_opportunities(
        request_type: Literal["permanent", "foster_free", "foster_paid", "pet_sitting"]
        | None = None,
        country: str | None = None,
        city: str | None = None,
        pet_type_id: int | None = None,
    ) -> CallToolResult:
        """Find open placement opportunities using optional care and location filters."""
        return await call(
            api.list_placement_opportunities, request_type, country, city, pet_type_id
        )

    @server.tool(annotations=read_annotations)
    async def get_placement_request(placement_request_id: int) -> CallToolResult:
        """Read one placement request and the authenticated viewer's role and actions."""
        return await call(api.get_placement_request, placement_request_id)

    @server.tool(annotations=read_annotations)
    async def list_placement_responses(placement_request_id: int) -> CallToolResult:
        """List responses for a placement request owned by the authenticated user."""
        return await call(api.list_placement_responses, placement_request_id)

    @server.tool(annotations=read_annotations)
    async def search_helper_profiles(
        country: str | None = None,
        city: str | None = None,
        request_type: Literal["permanent", "foster_free", "foster_paid", "pet_sitting"]
        | None = None,
        pet_type_id: int | None = None,
        search: str | None = None,
    ) -> CallToolResult:
        """Search approved public helper profiles without private contact or address fields."""
        return await call(
            api.search_helper_profiles,
            country,
            city,
            request_type,
            pet_type_id,
            search,
        )

    @server.tool(annotations=read_annotations)
    async def get_public_helper_profile(helper_profile_id: int) -> CallToolResult:
        """Read one approved public helper profile without private contact details."""
        return await call(api.get_public_helper_profile, helper_profile_id)

    @server.tool(annotations=read_annotations)
    async def list_my_helper_profiles() -> CallToolResult:
        """List helper profiles visible to the authenticated user, including own private fields."""
        return await call(api.list_my_helper_profiles)

    @server.tool(annotations=read_annotations)
    async def get_helper_profile(helper_profile_id: int) -> CallToolResult:
        """Read one helper profile visible to the authenticated user."""
        return await call(api.get_helper_profile, helper_profile_id)

    @server.tool(annotations=read_annotations)
    async def list_helper_location_options(
        country: str | None = None, search: str | None = None
    ) -> CallToolResult:
        """List countries or search cities for helper-profile and placement filtering."""
        return await call(api.list_helper_location_options, country, search)

    @server.tool(annotations=read_annotations)
    async def list_chats() -> CallToolResult:
        """List the authenticated user's chats with narrowed participants and unread counts."""
        return await call(api.list_chats)

    @server.tool(annotations=read_annotations)
    async def get_chat(chat_id: int) -> CallToolResult:
        """Read one explicit chat visible to the authenticated user."""
        return await call(api.get_chat, chat_id)

    @server.tool(annotations=read_annotations)
    async def list_chat_messages(
        chat_id: int, cursor: str | None = None, limit: int = 50
    ) -> CallToolResult:
        """List messages without creating a read receipt; paginate with the returned cursor."""
        return await call(api.list_chat_messages, chat_id, cursor, limit)

    @server.tool(annotations=read_annotations)
    async def get_unread_message_count() -> CallToolResult:
        """Get the authenticated user's total unread message count."""
        return await call(api.get_unread_message_count)

    @server.tool(annotations=read_annotations)
    async def list_groups() -> CallToolResult:
        """List groups the caller belongs to with role, member, and pet counts."""
        return await call(api.list_groups)

    @server.tool(annotations=read_annotations)
    async def get_group_overview(group_id: int) -> CallToolResult:
        """Read one explicit group with narrowed members, roles, pets, and version."""
        return await call(api.get_group_overview, group_id)

    @server.tool(annotations=read_annotations)
    async def list_group_member_suggestions(group_id: int) -> CallToolResult:
        """List known-user candidates before an explicit group membership write."""
        return await call(api.list_group_member_suggestions, group_id)

    @server.tool(annotations=read_annotations)
    async def list_group_invitations(group_id: int) -> CallToolResult:
        """List pending bearer invitations for one explicitly managed group."""
        return await call(api.list_group_invitations, group_id)

    @server.tool(annotations=read_annotations)
    async def preview_group_invitation(invitation: str) -> CallToolResult:
        """Preview a group bearer invitation without placing its token in an upstream URL."""
        return await call(api.preview_group_invitation, invitation)

    @server.tool(annotations=create_annotations)
    async def create_group(
        name: str,
        pet_ids: list[int],
        idempotency_key: str,
        allow_duplicate: bool = False,
    ) -> CallToolResult:
        """Create and verify a named group with explicit initial pet IDs."""
        return await call(api.create_group, name, pet_ids, idempotency_key, allow_duplicate)

    @server.tool(annotations=update_annotations)
    async def update_group(
        group_id: int, base_version: str, name: str, idempotency_key: str
    ) -> CallToolResult:
        """Rename one exact group from the version returned by get_group_overview."""
        return await call(api.update_group, group_id, base_version, name, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def delete_group(
        group_id: int,
        base_version: str,
        expected_group_name: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Permanently delete a versioned group whose exact name matches."""
        return await call(
            api.delete_group,
            group_id,
            base_version,
            expected_group_name,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def add_group_member(
        group_id: int,
        user_id: int,
        role: Literal["admin", "member"],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Grant one freshly suggested stable user an explicit group role."""
        return await call(
            api.add_group_member, group_id, user_id, role, base_version, idempotency_key
        )

    @server.tool(annotations=update_annotations)
    async def update_group_member_role(
        group_id: int,
        user_id: int,
        role: Literal["admin", "member"],
        expected_current_role: Literal["admin", "member"],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Change one exact member role after matching its fresh current role."""
        return await call(
            api.update_group_member_role,
            group_id,
            user_id,
            role,
            expected_current_role,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def remove_group_member(
        group_id: int,
        user_id: int,
        expected_current_role: Literal["admin", "member"],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Remove one exact member after matching its fresh current role."""
        return await call(
            api.remove_group_member,
            group_id,
            user_id,
            expected_current_role,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def leave_group(
        group_id: int,
        expected_caller_role: Literal["admin", "member"],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Leave one exact group after matching the caller's fresh role."""
        return await call(
            api.leave_group,
            group_id,
            expected_caller_role,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def add_group_pets(
        group_id: int,
        pet_ids: list[int],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Assign explicit freshly readable pets to one versioned group."""
        return await call(api.add_group_pets, group_id, pet_ids, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def remove_group_pet(
        group_id: int,
        pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Remove one exact named pet from a versioned group."""
        return await call(
            api.remove_group_pet,
            group_id,
            pet_id,
            expected_pet_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def create_group_invitation(
        group_id: int,
        role: Literal["admin", "member"],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Create and verify one role-specific bearer invitation for an exact group."""
        return await call(
            api.create_group_invitation, group_id, role, base_version, idempotency_key
        )

    @server.tool(annotations=update_annotations)
    async def revoke_group_invitation(
        group_id: int,
        invitation_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Revoke one exact pending group invitation and verify its absence."""
        return await call(
            api.revoke_group_invitation,
            group_id,
            invitation_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def accept_group_invitation(
        invitation: str,
        expected_group_name: str,
        expected_role: Literal["admin", "member"],
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Accept only after an exact fresh group/role invitation preview."""
        return await call(
            api.accept_group_invitation,
            invitation,
            expected_group_name,
            expected_role,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def decline_group_invitation(
        invitation: str,
        expected_group_name: str,
        expected_role: Literal["admin", "member"],
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Decline only after an exact fresh group/role invitation preview."""
        return await call(
            api.decline_group_invitation,
            invitation,
            expected_group_name,
            expected_role,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=read_annotations)
    async def list_currencies() -> CallToolResult:
        """List supported finance currency codes, symbols, and minor-unit precision."""
        return await call(api.list_currencies)

    @server.tool(annotations=read_annotations)
    async def list_ledgers(archived: bool = False) -> CallToolResult:
        """List the caller's accessible active or archived finance ledgers."""
        return await call(api.list_ledgers, archived)

    @server.tool(annotations=read_annotations)
    async def get_ledger_overview(ledger_id: int) -> CallToolResult:
        """Aggregate one ledger's detail, totals, configuration, members, pets, and trend."""
        return await call(api.get_ledger_overview, ledger_id)

    @server.tool(annotations=read_annotations)
    async def list_ledger_member_suggestions(ledger_id: int) -> CallToolResult:
        """List known-user candidates before an explicit ledger membership write."""
        return await call(api.list_ledger_member_suggestions, ledger_id)

    @server.tool(annotations=read_annotations)
    async def list_ledger_invitations(ledger_id: int) -> CallToolResult:
        """List pending bearer invitations for one explicitly managed ledger."""
        return await call(api.list_ledger_invitations, ledger_id)

    @server.tool(annotations=read_annotations)
    async def list_ledger_transactions(
        ledger_id: int,
        page: int = 1,
        per_page: int = 25,
        date_from: date | None = None,
        date_to: date | None = None,
        transaction_type: Literal["income", "expense"] | None = None,
        account_id: int | None = None,
        category_id: int | None = None,
        pet_id: int | None = None,
        creator_id: int | None = None,
        search: str | None = None,
    ) -> CallToolResult:
        """Page and filter transactions in one explicit accessible ledger."""
        return await call(
            api.list_ledger_transactions,
            ledger_id,
            page,
            per_page,
            date_from,
            date_to,
            transaction_type,
            account_id,
            category_id,
            pet_id,
            creator_id,
            search,
        )

    @server.tool(annotations=read_annotations)
    async def get_ledger_transaction(ledger_id: int, transaction_id: int) -> CallToolResult:
        """Read one exact transaction and whether an authority-held receipt exists."""
        return await call(api.get_ledger_transaction, ledger_id, transaction_id)

    @server.tool(annotations=read_annotations)
    async def list_pet_finance_transactions(pet_id: int, page: int = 1) -> CallToolResult:
        """List finance transactions linked to one pet across accessible ledgers."""
        return await call(api.list_pet_finance_transactions, pet_id, page)

    @server.tool(annotations=read_annotations)
    async def preview_ledger_invitation(invitation: str) -> CallToolResult:
        """Preview a ledger bearer invitation without placing its token in an upstream URL."""
        return await call(api.preview_ledger_invitation, invitation)

    @server.tool(annotations=create_annotations)
    async def create_ledger(
        title: str,
        currency_code: str,
        idempotency_key: str,
        allow_duplicate: bool = False,
    ) -> CallToolResult:
        """Create and verify a ledger with an explicit currency code."""
        return await call(api.create_ledger, title, currency_code, idempotency_key, allow_duplicate)

    @server.tool(annotations=update_annotations)
    async def update_ledger(
        ledger_id: int,
        base_version: str,
        title: str,
        idempotency_key: str,
        currency_code: str | None = None,
    ) -> CallToolResult:
        """Rename one exact ledger from the version returned by get_ledger_overview."""
        return await call(
            api.update_ledger, ledger_id, base_version, title, idempotency_key, currency_code
        )

    @server.tool(annotations=update_annotations)
    async def archive_ledger(
        ledger_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Archive one exact versioned ledger and verify its archived state."""
        return await call(api.archive_ledger, ledger_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def restore_ledger(
        ledger_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Restore one exact archived ledger and verify it is active again."""
        return await call(api.restore_ledger, ledger_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def delete_ledger(
        ledger_id: int,
        base_version: str,
        expected_title: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Permanently delete an unused versioned ledger whose exact title matches."""
        return await call(
            api.delete_ledger, ledger_id, base_version, expected_title, idempotency_key
        )

    @server.tool(annotations=create_annotations)
    async def add_ledger_member(
        ledger_id: int,
        user_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Add one freshly suggested stable user as an equal ledger member."""
        return await call(api.add_ledger_member, ledger_id, user_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def remove_ledger_member(
        ledger_id: int,
        user_id: int,
        expected_user_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Remove one exact ledger member after a versioned name preview."""
        return await call(
            api.remove_ledger_member,
            ledger_id,
            user_id,
            expected_user_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def leave_ledger(
        ledger_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Leave one exact ledger after a versioned overview preview."""
        return await call(api.leave_ledger, ledger_id, base_version, idempotency_key)

    @server.tool(annotations=create_annotations)
    async def add_ledger_pet(
        ledger_id: int,
        pet_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Assign one exact manageable pet ID to a versioned ledger."""
        return await call(api.add_ledger_pet, ledger_id, pet_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def remove_ledger_pet(
        ledger_id: int,
        pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Remove one exact manual pet assignment after a versioned name preview."""
        return await call(
            api.remove_ledger_pet,
            ledger_id,
            pet_id,
            expected_pet_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def link_ledger_group(
        ledger_id: int,
        group_id: int,
        base_version: str,
        idempotency_key: str,
        import_pets: bool = False,
        sync_group_pets: bool = False,
    ) -> CallToolResult:
        """Link one exact group to a versioned ledger with optional pet import/sync."""
        return await call(
            api.link_ledger_group,
            ledger_id,
            group_id,
            base_version,
            idempotency_key,
            import_pets,
            sync_group_pets,
        )

    @server.tool(annotations=update_annotations)
    async def unlink_ledger_group(
        ledger_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Unlink the group from one exact versioned ledger."""
        return await call(api.unlink_ledger_group, ledger_id, base_version, idempotency_key)

    @server.tool(annotations=create_annotations)
    async def create_ledger_invitation(
        ledger_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Create a bearer invitation for one exact versioned ledger."""
        return await call(api.create_ledger_invitation, ledger_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def revoke_ledger_invitation(
        ledger_id: int,
        invitation_id: int,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Revoke one exact pending ledger invitation and verify its absence."""
        return await call(
            api.revoke_ledger_invitation,
            ledger_id,
            invitation_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def accept_ledger_invitation(
        invitation: str,
        expected_ledger_title: str,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Accept only after an exact fresh ledger invitation preview."""
        return await call(
            api.accept_ledger_invitation,
            invitation,
            expected_ledger_title,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def decline_ledger_invitation(
        invitation: str,
        expected_ledger_title: str,
        invitation_base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Decline only after an exact fresh ledger invitation preview."""
        return await call(
            api.decline_ledger_invitation,
            invitation,
            expected_ledger_title,
            invitation_base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def create_ledger_account(
        ledger_id: int,
        name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Create and verify one account on an exact versioned ledger."""
        return await call(api.create_ledger_account, ledger_id, name, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def update_ledger_account(
        ledger_id: int,
        account_id: int,
        name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Rename one exact ledger account from its current version."""
        return await call(
            api.update_ledger_account,
            ledger_id,
            account_id,
            name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def archive_ledger_account(
        ledger_id: int,
        account_id: int,
        expected_archived: bool,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Toggle archive on one exact account after matching expected_archived."""
        return await call(
            api.archive_ledger_account,
            ledger_id,
            account_id,
            expected_archived,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def create_ledger_category(
        ledger_id: int,
        name: str,
        applies_to: Literal["income", "expense", "both"],
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Create and verify one category on an exact versioned ledger."""
        return await call(
            api.create_ledger_category,
            ledger_id,
            name,
            applies_to,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def update_ledger_category(
        ledger_id: int,
        category_id: int,
        base_version: str,
        idempotency_key: str,
        name: str | None = None,
        applies_to: Literal["income", "expense", "both"] | None = None,
    ) -> CallToolResult:
        """Update one exact ledger category from its current version."""
        return await call(
            api.update_ledger_category,
            ledger_id,
            category_id,
            base_version,
            idempotency_key,
            name,
            applies_to,
        )

    @server.tool(annotations=update_annotations)
    async def archive_ledger_category(
        ledger_id: int,
        category_id: int,
        expected_archived: bool,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Toggle archive on one exact category after matching expected_archived."""
        return await call(
            api.archive_ledger_category,
            ledger_id,
            category_id,
            expected_archived,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def create_ledger_transaction(
        ledger_id: int,
        account_id: int,
        transaction_type: Literal["income", "expense"],
        amount: str,
        occurred_on: str,
        base_version: str,
        idempotency_key: str,
        category_id: int | None = None,
        description: str | None = None,
        pet_ids: list[int] | None = None,
    ) -> CallToolResult:
        """Create and verify one ledger transaction from a versioned ledger preview."""
        return await call(
            api.create_ledger_transaction,
            ledger_id,
            account_id,
            transaction_type,
            amount,
            occurred_on,
            base_version,
            idempotency_key,
            category_id,
            description,
            pet_ids,
        )

    @server.tool(annotations=update_annotations)
    async def update_ledger_transaction(
        ledger_id: int,
        transaction_id: int,
        base_version: str,
        idempotency_key: str,
        account_id: int | None = None,
        category_id: int | None = None,
        transaction_type: Literal["income", "expense"] | None = None,
        amount: str | None = None,
        occurred_on: str | None = None,
        description: str | None = None,
        pet_ids: list[int] | None = None,
    ) -> CallToolResult:
        """Update one exact ledger transaction from its current version."""
        return await call(
            api.update_ledger_transaction,
            ledger_id,
            transaction_id,
            base_version,
            idempotency_key,
            account_id,
            category_id,
            transaction_type,
            amount,
            occurred_on,
            description,
            pet_ids,
        )

    @server.tool(annotations=update_annotations)
    async def delete_ledger_transaction(
        ledger_id: int,
        transaction_id: int,
        expected_type: Literal["income", "expense"],
        expected_amount: str,
        expected_occurred_on: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Delete one exact transaction after matching type, amount, and date."""
        return await call(
            api.delete_ledger_transaction,
            ledger_id,
            transaction_id,
            expected_type,
            expected_amount,
            expected_occurred_on,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=read_annotations)
    async def get_notification_inbox(
        limit: int = 20, include_notifications: bool = True
    ) -> CallToolResult:
        """Read bounded bell notifications and unread bell/message counts without mutation."""
        return await call(api.get_notification_inbox, limit, include_notifications)

    @server.tool(annotations=read_annotations)
    async def get_notification_preferences() -> CallToolResult:
        """Read per-event email, in-app, and Telegram delivery preferences."""
        return await call(api.get_notification_preferences)

    @server.tool(annotations=read_annotations)
    async def get_my_profile() -> CallToolResult:
        """Read a narrowed self profile, account state, storage, and weight summary."""
        return await call(api.get_my_profile)

    @server.tool(annotations=read_annotations)
    async def list_owner_weights(page: int = 1) -> CallToolResult:
        """Page the caller's own body-weight history."""
        return await call(api.list_owner_weights, page)

    @server.tool(annotations=read_annotations)
    async def get_account_invitation_summary() -> CallToolResult:
        """Read sent onboarding invitations and their lifecycle totals."""
        return await call(api.get_account_invitation_summary)

    @server.tool(annotations=create_annotations)
    async def create_placement_request(
        pet_id: int,
        expected_pet_name: str,
        request_type: Literal["permanent", "foster_free", "foster_paid", "pet_sitting"],
        start_date: date,
        idempotency_key: str,
        end_date: date | None = None,
        notes: str | None = None,
        expires_at: date | None = None,
    ) -> CallToolResult:
        """Create one explicit pet placement request and verify its stable ID."""
        return await call(
            api.create_placement_request,
            pet_id,
            expected_pet_name,
            request_type,
            start_date,
            idempotency_key,
            end_date,
            notes,
            expires_at,
        )

    @server.tool(annotations=update_annotations)
    async def delete_placement_request(
        placement_request_id: int,
        expected_pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Permanently delete an owned placement request after an exact fresh preview."""
        return await call(
            api.delete_placement_request,
            placement_request_id,
            expected_pet_id,
            expected_pet_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def respond_to_placement_request(
        placement_request_id: int,
        helper_profile_id: int,
        expected_pet_name: str,
        idempotency_key: str,
        message: str | None = None,
    ) -> CallToolResult:
        """Submit one helper profile response to an explicit placement request."""
        return await call(
            api.respond_to_placement_request,
            placement_request_id,
            helper_profile_id,
            expected_pet_name,
            idempotency_key,
            message,
        )

    @server.tool(annotations=update_annotations)
    async def accept_placement_response(
        placement_request_id: int,
        response_id: int,
        expected_helper_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Accept an exact owner-reviewed response and begin its handover lifecycle."""
        return await call(
            api.accept_placement_response,
            placement_request_id,
            response_id,
            expected_helper_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def reject_placement_response(
        placement_request_id: int,
        response_id: int,
        expected_helper_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Reject an exact owner-reviewed placement response."""
        return await call(
            api.reject_placement_response,
            placement_request_id,
            response_id,
            expected_helper_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def cancel_placement_response(
        placement_request_id: int, response_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Cancel the caller's explicit current placement response."""
        return await call(
            api.cancel_placement_response,
            placement_request_id,
            response_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def confirm_pet_transfer(
        placement_request_id: int, transfer_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Confirm receipt for the caller's exact pending pet handover."""
        return await call(
            api.confirm_pet_transfer,
            placement_request_id,
            transfer_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def reject_pet_transfer(
        placement_request_id: int, transfer_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Reject the caller's exact pending pet handover."""
        return await call(
            api.reject_pet_transfer,
            placement_request_id,
            transfer_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def cancel_pet_transfer(
        placement_request_id: int, transfer_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Cancel the caller's exact initiated pending pet handover."""
        return await call(
            api.cancel_pet_transfer,
            placement_request_id,
            transfer_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def finalize_temporary_placement(
        placement_request_id: int,
        expected_pet_id: int,
        expected_pet_name: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """End an active temporary placement after an exact owner preview."""
        return await call(
            api.finalize_temporary_placement,
            placement_request_id,
            expected_pet_id,
            expected_pet_name,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def create_helper_profile(
        country: str,
        city_ids: list[int],
        phone_number: str,
        experience: str,
        has_pets: bool,
        has_children: bool,
        request_types: list[Literal["permanent", "foster_free", "foster_paid", "pet_sitting"]],
        idempotency_key: str,
        state: str | None = None,
        address: str | None = None,
        zip_code: str | None = None,
        offer: str | None = None,
        contact_details: list[HelperContactInput] | None = None,
        pet_type_ids: list[int] | None = None,
    ) -> CallToolResult:
        """Create and verify one private helper profile using stable location IDs."""
        contacts = [item.model_dump() for item in contact_details or []]
        return await call(
            api.create_helper_profile,
            country,
            city_ids,
            phone_number,
            experience,
            has_pets,
            has_children,
            request_types,
            idempotency_key,
            state,
            address,
            zip_code,
            offer,
            contacts,
            pet_type_ids,
        )

    @server.tool(annotations=update_annotations)
    async def update_helper_profile(
        helper_profile_id: int,
        base_version: str,
        idempotency_key: str,
        country: str | None = None,
        city_ids: list[int] | None = None,
        phone_number: str | None = None,
        experience: str | None = None,
        has_pets: bool | None = None,
        has_children: bool | None = None,
        request_types: list[Literal["permanent", "foster_free", "foster_paid", "pet_sitting"]]
        | None = None,
        state: str | None = None,
        address: str | None = None,
        zip_code: str | None = None,
        offer: str | None = None,
        contact_details: list[HelperContactInput] | None = None,
        pet_type_ids: list[int] | None = None,
        status: Literal["private", "public"] | None = None,
    ) -> CallToolResult:
        """Update selected fields on one exact helper profile and version."""
        changes = {
            "country": country,
            "city_ids": city_ids,
            "phone_number": phone_number,
            "experience": experience,
            "has_pets": has_pets,
            "has_children": has_children,
            "request_types": request_types,
            "state": state,
            "address": address,
            "zip_code": zip_code,
            "offer": offer,
            "contact_details": [item.model_dump() for item in contact_details]
            if contact_details is not None
            else None,
            "pet_type_ids": pet_type_ids,
            "status": status,
        }
        return await call(
            api.update_helper_profile, helper_profile_id, base_version, idempotency_key, **changes
        )

    @server.tool(annotations=update_annotations)
    async def archive_helper_profile(
        helper_profile_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Archive one exact helper profile when it has no placement responses."""
        return await call(
            api.archive_helper_profile, helper_profile_id, base_version, idempotency_key
        )

    @server.tool(annotations=update_annotations)
    async def restore_helper_profile(
        helper_profile_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Restore one exact archived helper profile as private."""
        return await call(
            api.restore_helper_profile, helper_profile_id, base_version, idempotency_key
        )

    @server.tool(annotations=update_annotations)
    async def delete_helper_profile(
        helper_profile_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Permanently delete one exact unused helper profile and its photos."""
        return await call(
            api.delete_helper_profile, helper_profile_id, base_version, idempotency_key
        )

    @server.tool(annotations=create_annotations)
    async def upload_helper_profile_photo_from_url(
        helper_profile_id: int, source_url: str, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Import one bounded public HTTPS image into an exact helper profile."""
        return await call(
            api.upload_helper_profile_photo_from_url,
            helper_profile_id,
            source_url,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def set_primary_helper_profile_photo(
        helper_profile_id: int, photo_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Make one exact existing helper-profile photo primary."""
        return await call(
            api.set_primary_helper_profile_photo,
            helper_profile_id,
            photo_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def delete_helper_profile_photo(
        helper_profile_id: int, photo_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Permanently delete one exact helper-profile photo."""
        return await call(
            api.delete_helper_profile_photo,
            helper_profile_id,
            photo_id,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def open_placement_chat(
        placement_request_id: int,
        recipient_user_id: int,
        expected_recipient_name: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Open or find a direct chat with an exact placement counterparty."""
        return await call(
            api.open_placement_chat,
            placement_request_id,
            recipient_user_id,
            expected_recipient_name,
            idempotency_key,
        )

    @server.tool(annotations=create_annotations)
    async def send_chat_message(
        chat_id: int, expected_recipient_user_id: int, content: str, idempotency_key: str
    ) -> CallToolResult:
        """Send one replay-safe text message to an exact chat counterparty."""
        return await call(
            api.send_chat_message, chat_id, expected_recipient_user_id, content, idempotency_key
        )

    @server.tool(annotations=create_annotations)
    async def send_chat_image_from_url(
        chat_id: int, expected_recipient_user_id: int, source_url: str, idempotency_key: str
    ) -> CallToolResult:
        """Send one bounded public HTTPS image to an exact chat counterparty."""
        return await call(
            api.send_chat_image_from_url,
            chat_id,
            expected_recipient_user_id,
            source_url,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def mark_chat_read(
        chat_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Explicitly advance the caller's read receipt for one chat."""
        return await call(api.mark_chat_read, chat_id, base_version, idempotency_key)

    @server.tool(annotations=update_annotations)
    async def delete_own_message(
        chat_id: int,
        message_id: int,
        expected_content: str,
        base_version: str,
        idempotency_key: str,
    ) -> CallToolResult:
        """Soft-delete one exact own message after matching its current content."""
        return await call(
            api.delete_own_message,
            chat_id,
            message_id,
            expected_content,
            base_version,
            idempotency_key,
        )

    @server.tool(annotations=update_annotations)
    async def leave_chat(
        chat_id: int, expected_recipient_user_id: int, base_version: str, idempotency_key: str
    ) -> CallToolResult:
        """Leave one exact direct chat after a fresh participant preview."""
        return await call(
            api.leave_chat, chat_id, expected_recipient_user_id, base_version, idempotency_key
        )

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    async def protected_resource(_: Request) -> Response:
        return JSONResponse(
            {
                "resource": settings.resource,
                "authorization_servers": [str(settings.issuer)],
                "scopes_supported": ALLOWED_SCOPES,
            }
        )

    async def meo_callback(request: Request) -> Response:
        raw_request_id = request.query_params.get("request_id", "")
        try:
            redirect = await provider.complete_meo_callback(
                raw_request_id,
                request.query_params.get("code"),
                request.query_params.get("error"),
            )
            return RedirectResponse(redirect, status_code=303)
        except Exception as exc:
            try:
                safe_request_id = str(uuid.UUID(raw_request_id))
            except (ValueError, AttributeError):
                safe_request_id = "invalid"
            logger.error(
                "oauth_callback_failed",
                request_id=safe_request_id,
                error_type=type(exc).__name__,
            )
            return JSONResponse({"error": "authorization_failed"}, status_code=400)

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with server.session_manager.run():
            yield
        await engine.dispose()

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/.well-known/oauth-protected-resource", protected_resource),
            Route("/.well-known/oauth-protected-resource/mcp", protected_resource),
            Route("/oauth/meo/callback", meo_callback),
            Mount("/", server.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(GuardMiddleware)
    return app


def run() -> None:
    uvicorn.run(
        "meo_mcp.main:create_app", factory=True, host="0.0.0.0", port=8020, proxy_headers=True
    )
