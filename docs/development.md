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

## Contribution boundaries

Meo Mai Moi is authoritative for business rules and resource authorization.
Before adding a tool, inspect the Meo API and update [tools.md](tools.md) with
its semantic intent, scope, ability, endpoints, schemas, errors, annotations,
and risk. Keep admin and internal connector routes outside the user tool
surface.
