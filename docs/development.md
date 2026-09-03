# Development

This guide is for contributors to the gateway. If you are connecting an agent,
start with [clients.md](clients.md) instead.

## Local validation

Python 3.12 and [`uv`](https://docs.astral.sh/uv/) are required. A fresh clone
does not need Meo credentials or PostgreSQL for the automated suite:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

Tests create isolated SQLite stores and inject non-secret cryptographic test
material. Do not point tests or migration experiments at a shared environment.

## Run locally

Copy `.env.example` to a local, untracked `.env` and replace placeholders with
values for an isolated PostgreSQL database and a local Meo-compatible setup.
The variables are documented by name only in `.env.example`; never commit real
credentials.

The Compose topology expects an operator-provided PostgreSQL `DATABASE_URL` and
an existing external `shared-services` Docker network. For migrations and
deployment mechanics, read [deployment.md](deployment.md). For versioning and
promotion, read [release.md](release.md).

## Full local stack against a local Meo

Working on tools against the development deployment costs a push, a CI run, and
a deploy per iteration. The whole loop runs locally instead, and nothing in the
gateway requires TLS to do it: `public_base_url` is an `AnyHttpUrl`, so plain
`http://localhost` is a valid issuer.

Start Meo itself first (`./utils/deploy.sh --seed` in the app checkout; it
serves `http://localhost:8000`). Then link the two sides. The connection is
three environment variables that must hold identical values in both places:
`MCP_CONNECTOR_API_KEY` authenticates the gateway's exchange calls to Meo, and
`MCP_CONNECTOR_HMAC_SECRET` signs the authorization reference that travels
through the user's browser. There is no registration UI and nothing to seed;
generate a pair of random values and write them into the gateway's `.env` and
Meo's `backend/.env` together, with `MCP_CONNECTOR_URL` naming the gateway.
Laravel caches config, so clear it and restart the backend afterwards or the
connector stays invisible.

Point `DATABASE_URL` at a database of its own — the Meo Compose Postgres is
fine, with a separate database beside the app's — then `uv run alembic upgrade
head` and:

```bash
uv run uvicorn meo_mcp.main:create_app --factory --host 127.0.0.1 --port 8020
```

`GET /health` reports the running version, which is the quickest way to confirm
which build answered.

### Driving a grant without a client

An OAuth grant can be completed with an HTTP client alone, which is how the
protocol surface gets exercised without waiting for a real MCP client: register
via `/register`, call `/authorize` with S256 PKCE, follow the redirect to Meo's
consent screen, sign in as a seeded account, `POST /api/mcp-auth/confirm` with
the `request_ref`, follow the returned `redirect_url` back through
`/oauth/meo/callback`, and exchange the code at `/token`.

Two traps make this fail in ways the error message does not explain. The
consent endpoint carries `reject.pat`, so a personal access token will not
work: it needs a real first-party session. And Laravel's `XSRF-TOKEN` cookie is
URL-encoded, so it has to be decoded before it goes into the `X-XSRF-TOKEN`
header or every request answers `419 CSRF token mismatch`.

## Contribution boundaries

Meo Mai Moi is authoritative for business rules and resource authorization.
Before adding a tool, inspect the Meo API and update [tools.md](tools.md) with
its semantic intent, scope, ability, endpoints, schemas, errors, annotations,
and risk. Keep admin and internal connector routes outside the user tool
surface.
