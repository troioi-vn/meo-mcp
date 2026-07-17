# meo-mcp

`meo-mcp` is Meo Mai Moi's protocol-independent agent gateway. MCP clients
authenticate with OAuth, receive gateway-owned opaque tokens, and call semantic
tools that delegate to the Meo Laravel API with a narrowly scoped Sanctum token.
Meo remains the product and authorization authority; this repository is a thin
adapter, not a second implementation of its domain rules.

The current development baseline exposes one read-only tool, `list_pets`, over
stateless Streamable HTTP. It requests only `pets:read` and delegates only the
Meo `read` ability.

## Start here

| Guide | Purpose |
|-------|---------|
| [Architecture](docs/architecture.md) | Boundaries, request flow, components, and how to add a tool |
| [OAuth](docs/oauth.md) | Discovery, consent bridge, tokens, refresh, and revocation |
| [Security](docs/security.md) | Trust boundaries, stored credentials, HTTP guards, and documentation hygiene |
| [Errors](docs/errors.md) | HTTP, OAuth, and MCP tool error contracts |
| [Connect a client](docs/clients.md) | Generic setup plus Codex, Cursor, and MCP Inspector examples |
| [Tool catalog](docs/tools.md) | Canonical scope, upstream endpoint, schema, annotation, and risk matrix |
| [Deployment](docs/deployment.md) | Public-safe local and development release mechanics |

Repository-specific agent rules are in [AGENTS.md](AGENTS.md), and active work
is sequenced in [todo/README.md](todo/README.md). The reusable gateway workflow
skill is planned in [Plan 03](todo/03-agent-skill.md); its canonical location
will be `.agents/skills/meo-mcp/SKILL.md`.

## Local validation

Python 3.12 and [`uv`](https://docs.astral.sh/uv/) are required. A fresh clone
does not need production credentials or PostgreSQL to run the automated suite:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

Use local values based on [.env.example](.env.example) only when running the
service or Alembic against your own PostgreSQL database. Never point local
tests or migration experiments at a shared environment.
