# Deployment

This repo ships deploy mechanics: Compose, Alembic, CI configuration, and an
NGINX development vhost. Public service names and topology required by those
artifacts may appear here. Private inventory belongs in the operator runbook.

Never publish IP addresses, SSH targets or usernames, checkout paths, database
or role names, allowlisted identities, CI/repository IDs, secret-manager paths,
or secret values. Maintainers can locate the private runbook through their
workstation-level agent instructions; public contributors must not need it for
local development or architecture comprehension.

## Environments

| Git branch | Role |
|------------|------|
| `dev` | Development: CI tests, migrates, rebuilds, and health-checks the long-lived checkout |
| `main` | Future production target; no deploy workflow yet |

## Release path (dev)

1. Push a tested change to `dev`.
2. CI runs tests, updates the remote checkout, applies Alembic migrations, rebuilds
   Compose, and checks health. Operator-specific targets and recovery commands
   live in the private runbook.
3. Roll back by deploying the preceding `dev` SHA. Migrations are additive; do not
   use a destructive downgrade during an incident.

## Configuration

The server-managed `.env` holds `DATABASE_URL`, public and Meo base URLs, the Meo
connector API key/HMAC secret, and a unique 32-byte base64url AES key. Do not
store it in Git. Recovery and CI injection of those values are documented in
the private operator runbook — not in this repository.

## Local baseline

The committed `docker-compose.yml` is the deployment topology: it expects an
operator-provided PostgreSQL database from `DATABASE_URL` and an existing
external `shared-services` Docker network. It is not a self-contained local
database stack. Public contributors can run all automated tests without either
dependency because tests create isolated SQLite stores and inject non-secret
test cryptographic material:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
```

Run Alembic or the application against PostgreSQL only after setting the names
from `.env.example` to local values. Never point tests or migration experiments
at a shared or production database.

## MVP security and rollback invariants

- Dynamic registration accepts public clients only; clients must use exact
  registered redirect URIs and S256 PKCE.
- Authorization requests live for 10 minutes, authorization codes for 5
  minutes, access tokens for 1 hour, and grants/refresh tokens for at most 90
  days.
- Client-facing codes and tokens are stored as SHA-256 digests. The delegated
  Meo token is stored with AES-256-GCM authenticated encryption.
- Refresh tokens rotate. Reusing a consumed refresh token revokes its grant,
  access tokens, and refresh-token family locally before best-effort upstream
  revocation.
- OAuth token requests must carry the exact MCP resource audience. Browser
  origins, request hosts, and the 1 MiB request-body limit are enforced before
  application handlers.
- Tool failures use MCP `isError` results containing stable JSON fields:
  `code`, `message`, `retryable`, and (when applicable) `upstream_status`.
- Rollback means running the preceding application image against the current
  additive schema. Do not downgrade the database during incident rollback.

## Future production (not provisioned)

Production will use `main`, a distinct public hostname, distinct database
credentials, and a host/port chosen after a fresh inventory. Track cutover work
in `todo/04-prod-and-hardening.md` and record private live facts only in the
operator runbook.
