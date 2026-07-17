from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

import structlog
import uvicorn
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from .config import Settings, get_settings
from .database import make_session_factory
from .meo_api import MeoApi
from .oauth import ALLOWED_SCOPES, DatabaseOAuthProvider


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        if request.method in {"POST", "PUT", "PATCH"} and int(request.headers.get("content-length", "0") or 0) > 1_048_576:
            return JSONResponse({"error": "request_too_large"}, status_code=413)
        origin = request.headers.get("origin")
        allowed = request.app.state.settings.allowed_origins
        if origin and origin not in allowed:
            return JSONResponse({"error": "invalid_origin"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or get_settings()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level.upper(), logging.INFO)))
    engine, sessions = make_session_factory(settings.database_url)
    provider = DatabaseOAuthProvider(sessions, settings)
    api = MeoApi(sessions, settings)
    server = FastMCP(
        "Meo Mai Moi",
        instructions="Read-only access to your Meo Mai Moi pets.",
        auth_server_provider=provider,
        auth=AuthSettings(issuer_url=settings.issuer, resource_server_url=settings.resource, required_scopes=ALLOWED_SCOPES, client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=ALLOWED_SCOPES, default_scopes=ALLOWED_SCOPES), revocation_options=RevocationOptions(enabled=True)),
        stateless_http=True,
        json_response=True,
    )

    @server.tool(annotations={"readOnlyHint": True})
    async def list_pets() -> dict:
        """List the authenticated user's pets with basic profiles and photo URLs."""
        return await api.list_pets()

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    async def meo_callback(request: Request) -> Response:
        try:
            redirect = await provider.complete_meo_callback(request.query_params.get("request_id", ""), request.query_params.get("code"), request.query_params.get("error"))
            return RedirectResponse(redirect, status_code=303)
        except Exception:
            return JSONResponse({"error": "authorization_failed"}, status_code=400)

    @asynccontextmanager
    async def lifespan(_: Starlette):
        yield
        await engine.dispose()

    app = Starlette(routes=[Route("/health", health), Route("/oauth/meo/callback", meo_callback), Mount("/", server.streamable_http_app())], lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(GuardMiddleware)
    return app


app = create_app()

def run() -> None:
    uvicorn.run("meo_mcp.main:app", host="0.0.0.0", port=8020, proxy_headers=True)
