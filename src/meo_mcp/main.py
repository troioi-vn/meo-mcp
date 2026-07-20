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
            "Read and safely update Meo Mai Moi pet profiles and core health history. "
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
