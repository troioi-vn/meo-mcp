# meo-mcp

Protocol-independent agent gateway for Meo Mai Moi. MCP clients such as Codex,
Cursor, and MCP Inspector authenticate via OAuth, receive opaque MCP tokens, and call semantic tools
that delegate to the Meo Laravel API with a stored Sanctum PAT.

Meo Mai Moi remains the authority. This repo is a thin adapter: normalize inputs,
translate errors, never duplicate domain logic.

Related trees:

- `../meo-mai-moi` — main app (API authority, `/mcp-connect`, `/api/mcp-auth/*`)
- `../meo-gpt-connector` — ChatGPT Actions connector (proven semantic tool shapes)
- `../meo-mai-moi-skill` — product-domain skill for agents (do not duplicate here)
- private operator runbook — live deploy inventory and verification; locate it
  through workstation-level instructions when available

---

## Architecture Overview

```
MCP client → OAuth (this service) → opaque MCP access token
          → Streamable HTTP /mcp → tools
          → decrypt delegated Sanctum PAT → Meo Mai Moi API
```

### Key decisions

- **Stack**: Python 3.12, FastMCP + Starlette, uvicorn, SQLAlchemy async, Alembic, Postgres.
- **Transport**: Stateless Streamable HTTP (`json_response=True`) at `{PUBLIC_BASE_URL}/mcp`.
- **Auth**: MCP OAuth authorization server (DB-backed) + Meo consent/exchange bridge.
  Delegated Sanctum PATs are encrypted at rest (AES-256-GCM). Access tokens ~1h;
  refresh tokens rotate with family revocation on replay.
- **Boundary**: Thin adapter only. Tools call Meo APIs; no business rules here.
- **MVP baseline**: read-only `list_pets` with scope `pets:read`.

### Project structure

```
src/meo_mcp/
├── main.py       # FastMCP app, GuardMiddleware, /health, /oauth/meo/callback
├── oauth.py      # OAuth AS provider, scopes, Meo authorize/callback
├── meo_api.py    # Meo HTTP client + tool implementations
├── security.py   # AES-GCM, digests, HMAC request refs
├── database.py   # SQLAlchemy models / session factory
└── config.py     # Pydantic settings
```

---

## Key Design Rules

1. **Meo is the authority.** Never invent tools or fields that the main app cannot enforce.
2. **Semantic tools, not REST mirrors.** Design for LLM workflows (like meo-gpt-connector),
   not 1:1 route copies. One tool may call multiple Meo endpoints.
3. **Scopes stay narrow until needed.** Expand `ALLOWED_SCOPES` and Meo Sanctum abilities
   together; do not grant write scopes for unused tools.
4. **Structured errors always.** Machine-readable shapes; no opaque free-text failures.
5. **No secrets or tokens in logs.** Log `request_id`, endpoint, status, latency — never
   PATs, MCP tokens, API keys, or HMAC secrets.
6. **No secrets in Git.** Server `.env` is operator-managed. Prefer secret-manager resource
   *names* in private ops notes; never paste values into this repo.
7. **End-user surface only.** Do not expose Filament/admin APIs via MCP.
8. **Public vs private docs.** Reusable product/engineering truth lives here (`docs/`,
   `AGENTS.md`). Public endpoints and required deployment topology may appear in
   source-controlled deploy artifacts. IPs, SSH identities, checkout paths,
   database identities, CI IDs, and secret locations belong only in the private
   operator runbook.

---

## Branch and deploy policy

- Routine work lands on **`dev`**. Pushing `dev` runs CI and deploys the development
  environment (operator-specific details are in the private runbook).
- **`main` / production** is not provisioned yet. See `docs/deployment.md` and
  `todo/04-prod-and-hardening.md`.
- Prefer additive Alembic migrations. Do not run destructive downgrades during incidents.

---

## Environment (names only)

See `.env.example`: `DATABASE_URL`, `PUBLIC_BASE_URL`, `MEO_BASE_URL`,
`MEO_CONNECTOR_API_KEY`, `MEO_CONNECTOR_HMAC_SECRET`, `TOKEN_ENCRYPTION_KEY`,
`MEO_MCP_PORT`, `ALLOWED_ORIGINS`. Never commit real values.

---

## Validation

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

For live health and OAuth metadata checks, maintainers should use the private
operator runbook. Public contributors can use placeholders from `.env.example`.

Unauthenticated `POST` to `/mcp` should return **401** with `WWW-Authenticate` /
resource metadata. After a client completes OAuth, smoke with `list_pets`.

---

## Pointers

| Path | Role |
|------|------|
| `docs/architecture.md` | System boundary, component map, and tool-development workflow |
| `docs/oauth.md` | OAuth discovery, consent bridge, scopes, tokens, and revocation |
| `docs/security.md` | Security controls, credential handling, and public/private boundary |
| `docs/errors.md` | Stable HTTP, OAuth, and MCP tool error contracts |
| `docs/clients.md` | Client connection and OAuth acceptance guide |
| `docs/tools.md` | Canonical capability, scope, schema, annotation, and risk matrix |
| `docs/deployment.md` | Public-safe deploy model |
| `todo/` | Active milestone plans; move finished ones to `todo/done/` |
| `.agents/skills/meo-mcp/SKILL.md` | Cross-client connect, smoke, diagnosis, deploy, and tool-development workflow |
| private operator runbook | Live hosts, endpoints, secrets, CI; intentionally outside this repo |
