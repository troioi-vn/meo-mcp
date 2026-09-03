# meo-mcp

Protocol-independent agent gateway for Meo Mai Moi. MCP clients (Codex, Cursor, MCP Inspector) authenticate over OAuth, get opaque MCP tokens, and call semantic tools that reach the Meo Laravel API with a delegated Sanctum PAT.

Meo Mai Moi is the authority. This repo is a thin adapter: normalize inputs, narrow responses, translate errors. The test, from `docs/architecture.md`: could Meo enforce this without trusting the gateway? If not, it belongs upstream.

`../meo-mai-moi` is the main app (API authority, `/mcp-connect`, `/api/mcp-auth/*`). `../skills-public/meo-mcp-skill` is the agent-facing gateway skill and supersedes in-repo `.agents/skills/meo-mcp/`; update the published tree, not the copy here. Live hosts, secrets, and CI identities live only in the private operator runbook, found via workstation-level instructions.

## Stack

Python 3.12, `uv`, FastMCP + Starlette, uvicorn, SQLAlchemy async, Alembic, Postgres. Stateless Streamable HTTP (`json_response=True`) at `{PUBLIC_BASE_URL}/mcp`.

Things you will otherwise reach for and get wrong:

- `httpx`, not `requests`. Async throughout.
- `structlog` via `security.redact_log_event`, not stdlib `logging`. Direct logging bypasses redaction.
- `security.now()` and `as_utc()`, not `datetime.utcnow()`. Naive SQLite test timestamps and aware Postgres ones both need it, or comparisons shift silently.
- Woodpecker (`.woodpecker.yml`), not GitHub Actions.

## Invariants

These fail silently: no type, test, or error reports them. Other rules here are enforced by `uv run pytest`.

1. **No business rules here.** A validation rule added gateway-side passes tests; Meo never enforces it.
2. **Semantic tools, not REST mirrors.** Design for an LLM workflow; one tool may call several Meo endpoints. A 1:1 route copy works and is still wrong.
3. **Every scope needs a matching Meo Sanctum ability.** All 26 `ALLOWED_SCOPES` are advertised; `DEFAULT_SCOPES` is the full catalog on purpose (`oauth.py:75` explains). A scope with no Meo ability passes the local check, then 403s at runtime.
4. **No secrets in logs or in Git.** Log `request_id`, endpoint, status, latency. Never PATs, MCP tokens, API keys, or HMAC secrets. Nothing scans commits for you.
5. **End-user surface only.** Never expose Filament, admin, or internal connector endpoints as tools.

`tests/test_documentation.py` catches only workstation paths, private IPs, emails, and secret-store paths. SSH identities, database identities, and CI IDs are on you.

## Branch and deploy

Work lands on `dev`; pushing runs CI and deploys development. `main` deploys production after an accepted dev checkpoint, per `docs/release.md`. Keep Alembic migrations additive; no destructive downgrade during an incident.

## How to finish

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

A new tool means updating `docs/tools.md` too; a test asserts it matches the implemented scope mapping. Commit messages stay short, no attribution trailers.

## Where to look

| Your question | File |
|---|---|
| What should this tool do, at what risk? | `docs/tools.md` |
| Where is the boundary? Adding a tool? | `docs/architecture.md` |
| OAuth, consent, revocation? | `docs/oauth.md` |
| What should this failure return? | `docs/errors.md` |
| A client will not connect? | `docs/clients.md` |
| Trust boundaries? | `docs/security.md` |
| Running locally? | `docs/development.md` |
| How does it ship? | `docs/deployment.md`, `docs/release.md` |
| Smoke a live gateway? | `../skills-public/meo-mcp-skill` |
| What is planned? | `todo/` |

## Keeping this file short

Budget: 600 words. Adding something means moving something else out. If a lint rule, a type, or a test already catches it, it does not belong here. Route lessons by the table above; why a line of code is odd goes in a comment beside it.
