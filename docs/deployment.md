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

## Future production (not provisioned)

Production will use `main`, a distinct public hostname, distinct database
credentials, and a host/port chosen after a fresh inventory. Track cutover work
in `todo/04-prod-and-hardening.md` and record private live facts only in the
operator runbook.
