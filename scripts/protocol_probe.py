#!/usr/bin/env python3
"""Exercise the 2026-07-28 stateless path against a running gateway.

No MCP client speaks this revision yet: every client observed so far negotiates
2025-06-18 and the legacy `initialize` handshake. So nothing in normal traffic
touches the modern path, and a regression there would go unnoticed until the
first client ships support. This script is the substitute for that traffic.

It completes a real OAuth grant with an HTTP client alone, then makes
authenticated calls with no handshake. Intended for a local or development
gateway; it needs a password for a seeded account, so do not point it at
production.

    uv run python scripts/protocol_probe.py \
        --gateway http://localhost:8020 --meo http://localhost:8000 \
        --email <seeded account> --password <password>

Credentials may come from MEO_PROBE_EMAIL and MEO_PROBE_PASSWORD instead.
Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets
import sys
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    CLIENT_INFO_META_KEY,
    LATEST_PROTOCOL_VERSION,
    PROTOCOL_VERSION_META_KEY,
    SERVER_INFO_META_KEY,
)

REDIRECT_URI = "http://localhost:9999/callback"
SCOPES = "pets:read pets:write finance:read notifications:read"
CLIENT_NAME = "protocol-probe"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def obtain_access_token(gateway: str, meo: str, email: str, password: str) -> str:
    """Run the whole authorization-code flow and return the access token."""
    with httpx.Client(follow_redirects=False, timeout=30.0) as client:
        registration = client.post(
            f"{gateway}/register",
            json={
                "client_name": CLIENT_NAME,
                "redirect_uris": [REDIRECT_URI],
                # The gateway registers public clients only; a secret is refused.
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        registration.raise_for_status()
        client_id = registration.json()["client_id"]

        verifier = _b64(secrets.token_bytes(32))
        authorize = client.get(
            f"{gateway}/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "state": _b64(secrets.token_bytes(16)),
                "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
                "code_challenge_method": "S256",
                "resource": f"{gateway}/mcp",
            },
        )
        if authorize.status_code not in (302, 303, 307):
            raise SystemExit(f"authorize returned {authorize.status_code}: {authorize.text[:300]}")
        reference = parse_qs(urlparse(authorize.headers["location"]).query)["request_ref"][0]

    with httpx.Client(follow_redirects=True, timeout=30.0) as session:
        # Consent carries `reject.pat`, so a personal access token cannot stand
        # in for a first-party session here.
        session.get(f"{meo}/sanctum/csrf-cookie")
        login = session.post(
            f"{meo}/login",
            json={"email": email, "password": password},
            headers=_csrf_headers(session, meo),
        )
        if login.status_code >= 400:
            raise SystemExit(f"login returned {login.status_code}: {login.text[:300]}")

        confirm = session.post(
            f"{meo}/api/mcp-auth/confirm",
            json={"request_ref": reference},
            headers=_csrf_headers(session, meo),
        )
        if confirm.status_code != 200:
            raise SystemExit(f"consent returned {confirm.status_code}: {confirm.text[:300]}")
        callback_url = confirm.json()["data"]["redirect_url"]

    with httpx.Client(follow_redirects=False, timeout=30.0) as client:
        callback = client.get(callback_url)
        code = parse_qs(urlparse(callback.headers.get("location", "")).query).get("code", [None])[0]
        if not code:
            raise SystemExit(f"callback produced no code: {callback.status_code}")

        token = client.post(
            f"{gateway}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": f"{gateway}/mcp",
            },
        )
        if token.status_code != 200:
            raise SystemExit(f"token exchange returned {token.status_code}: {token.text[:300]}")
        return token.json()["access_token"]


def _csrf_headers(session: httpx.Client, meo: str) -> dict[str, str]:
    # Laravel URL-encodes XSRF-TOKEN; sending it back encoded is a 419.
    return {
        "X-XSRF-TOKEN": unquote(session.cookies.get("XSRF-TOKEN") or ""),
        "Accept": "application/json",
        "Referer": meo,
        "Origin": meo,
    }


class Checks:
    def __init__(self) -> None:
        self.failed = 0

    def record(self, label: str, passed: bool, detail: object = "") -> None:
        if not passed:
            self.failed += 1
        suffix = f" — {detail}" if detail != "" else ""
        print(f"  {'PASS' if passed else 'FAIL'}  {label}{suffix}")


def probe(gateway: str, token: str) -> int:
    meta = {
        PROTOCOL_VERSION_META_KEY: LATEST_PROTOCOL_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
        CLIENT_INFO_META_KEY: {"name": CLIENT_NAME, "version": "1.0"},
    }
    base = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Mcp-Protocol-Version": LATEST_PROTOCOL_VERSION,
    }

    def call(method: str, params: dict | None = None, headers: dict | None = None, rid: int = 1):
        return httpx.post(
            f"{gateway}/mcp",
            headers={**base, "Mcp-Method": method, **(headers or {})},
            json={
                "jsonrpc": "2.0",
                "id": rid,
                "method": method,
                "params": {**(params or {}), "_meta": meta},
            },
            timeout=60.0,
        )

    checks = Checks()
    print(f"\nProtocol {LATEST_PROTOCOL_VERSION} against {gateway}, no initialize handshake\n")

    response = call("server/discover")
    checks.record("server/discover answers a cold request", response.status_code == 200)
    discovered = response.json().get("result", {})
    checks.record(
        "advertises the revision",
        LATEST_PROTOCOL_VERSION in discovered.get("supportedVersions", []),
        discovered.get("supportedVersions"),
    )
    server_info = discovered.get("_meta", {}).get(SERVER_INFO_META_KEY, {})
    checks.record(
        "reports serverInfo",
        bool(server_info.get("name")) and bool(server_info.get("version")),
        server_info,
    )

    listed = call("tools/list", rid=2).json().get("result", {})
    checks.record(
        "tools/list returns the catalog",
        len(listed.get("tools", [])) > 100,
        len(listed.get("tools", [])),
    )
    checks.record(
        "carries the SEP-2549 cache hint",
        listed.get("ttlMs") == 3_600_000 and listed.get("cacheScope") == "private",
        f"ttlMs={listed.get('ttlMs')} cacheScope={listed.get('cacheScope')}",
    )

    # tools/call needs Mcp-Name as well, and it has to agree with params.name.
    called = (
        call(
            "tools/call",
            {"name": "list_pets", "arguments": {}},
            headers={"Mcp-Name": "list_pets"},
            rid=3,
        )
        .json()
        .get("result", {})
    )
    checks.record("tools/call reaches Meo and returns", not called.get("isError", True))
    checks.record(
        "result declares resultType",
        called.get("resultType") == "complete",
        called.get("resultType"),
    )

    for label, extra in (
        ("Mcp-Method", {"Mcp-Method": "tools/list", "Mcp-Name": "list_pets"}),
        ("Mcp-Name", {"Mcp-Name": "get_pet"}),
    ):
        mismatched = call(
            "tools/call", {"name": "list_pets", "arguments": {}}, headers=extra, rid=9
        )
        code = (mismatched.json().get("error") or {}).get("code")
        checks.record(f"mismatched {label} gives HeaderMismatch -32020", code == -32020, code)

    print(f"\n{'ALL PASS' if not checks.failed else f'{checks.failed} FAILED'}\n")
    return 1 if checks.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://localhost:8020")
    parser.add_argument("--meo", default="http://localhost:8000")
    parser.add_argument("--email", default=os.environ.get("MEO_PROBE_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("MEO_PROBE_PASSWORD"))
    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error("an account is required: pass --email/--password or set MEO_PROBE_*")

    token = obtain_access_token(
        args.gateway.rstrip("/"), args.meo.rstrip("/"), args.email, args.password
    )
    return probe(args.gateway.rstrip("/"), token)


if __name__ == "__main__":
    sys.exit(main())
