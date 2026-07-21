# Deployment

This repo ships deploy mechanics: Compose, Alembic, CI configuration, and NGINX
vhosts for both environments. Public service names and topology required by those
artifacts may appear here. Private inventory belongs in the operator runbook.

Never publish IP addresses, SSH targets or usernames, checkout paths, database
or role names, CI/repository IDs, secret-manager paths, or secret values.
Maintainers can locate the private runbook through their
workstation-level agent instructions; public contributors must not need it for
local development or architecture comprehension.

## Environments

| Git branch | Role |
|------------|------|
| `dev` | Development: CI tests, migrates, rebuilds, and health-checks the long-lived checkout |
| `main` | Production: CI tests, migrates the distinct production database, rebuilds, and checks loopback plus public health |

## Release paths

1. Push routine tested changes to `dev` and accept the development deployment.
2. Promote the accepted commit to `main` through an intentional merge.
3. CI runs tests, updates the remote checkout, applies Alembic migrations, rebuilds
   Compose, and checks the environment's health. Operator-specific targets and
   recovery commands live in the private runbook.
4. Roll back by deploying the preceding branch SHA. Migrations are additive; do
   not use a destructive downgrade during an incident.

## Configuration

The server-managed `.env` holds `DATABASE_URL`, public and Meo base URLs, the Meo
connector API key/HMAC secret, and a unique 32-byte base64url AES key. Do not
store it in Git. Recovery and CI injection of those values are documented in
the private operator runbook — not in this repository.

Application logs are structured JSON and retain request ID, method, endpoint,
status, and latency without query strings, headers, bodies, or credentials.
Upstream 5xx events record only the request ID, stable error code, and status.
Compose rotates container JSON logs at 10 MiB with three files; the reverse
proxy keeps environment-specific access and error logs under host log rotation.

The minimal production alert policy is intentionally derivable from those
stable events:

- treat two consecutive public or loopback `/health` failures as an immediate
  service alert; deployment pipelines fail on the same health boundary
- investigate OAuth endpoint failures above 5% with at least 10 requests in a
  five-minute window
- investigate three `meo_upstream_error` events in five minutes, and escalate
  if that rate persists for ten minutes

Alert delivery and live log access are operator concerns documented in the
private runbook. The public contract is the health endpoint and the structured,
credential-free events above.

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
uv run ruff format --check src tests
```

Run Alembic or the application against PostgreSQL only after setting the names
from `.env.example` to local values. Never point tests or migration experiments
at a shared or production database.

## MVP security and rollback invariants

The durable security model is documented in [`security.md`](security.md), OAuth
lifecycles in [`oauth.md`](oauth.md), and caller-visible failures in
[`errors.md`](errors.md). The deployment-specific invariants are summarized
below.

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

## Production

Production serves `https://mcp.meo-mai-moi.com/mcp` from `main`. It has a
distinct database, credentials, delegated-token encryption key, connector
credentials, Compose project, TLS certificate, and server-managed environment.
Development remains the default integration playground. Promote only accepted
commits, and keep all live inventory and recovery material in the private
operator runbook.

Production cutover acceptance must cover OAuth discovery and PKCE, explicit
narrow-scope client registration and consent, authenticated tool discovery and
one representative read/write cycle, refresh rotation and replay-family
revocation, log-redaction review, and an application rollback to a prior SHA
without downgrading the additive database schema.
