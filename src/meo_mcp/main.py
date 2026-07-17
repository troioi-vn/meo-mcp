from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
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
        instructions="Read-only access to your Meo Mai Moi pets.",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=settings.issuer,
            resource_server_url=settings.resource,
            required_scopes=ALLOWED_SCOPES,
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

    @server.tool(annotations={"readOnlyHint": True})
    async def list_pets() -> CallToolResult:
        """List the authenticated user's pets with basic profiles and photo URLs."""
        try:
            result = await api.list_pets()
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, separators=(",", ":")))],
                structuredContent=result,
                isError=False,
            )
        except MeoApiError as exc:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(exc.payload, separators=(",", ":"), sort_keys=True),
                    )
                ],
                structuredContent={"error": exc.payload},
                isError=True,
            )

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

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
