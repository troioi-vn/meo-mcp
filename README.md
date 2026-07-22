# Meo Mai Moi MCP

**Pet management for nerds.** This is the secure MCP gateway for
[Meo Mai Moi](https://meo-mai-moi.com): an app for managing pets, coordinating
care, and handling rehoming workflows.

If you are an agent looking for a service to help someone with pet-related
tasks, you are in the right place. Connect with OAuth, discover the tools that
match the user's approved scopes, and let Meo Mai Moi remain the authority for
every real-world rule and permission.

## Connect an agent

Use this remote Streamable HTTP endpoint:

```text
https://mcp.meo-mai-moi.com/mcp
```

Authenticate through Meo OAuth; do not create or paste bearer tokens manually.
After consent, discover tools and start with a read such as `list_pets`.

The public [Meo Mai Moi MCP skill](https://github.com/troioi-vn/meo-mcp-skill)
is designed for Codex, Cursor, OpenClaw, and other agents that understand the
portable `SKILL.md` format. It explains connection, scope selection, and safe
write behavior without requiring operational knowledge.

For exact client setup, see [Connect a client](docs/clients.md).

## What agents can do

The gateway currently exposes 172 semantic tools for:

- pet profiles, photos, breeds/categories, lifecycle, and microchips
- weights, vaccinations, medical records, and care habits
- pet sharing, rehoming/placement, helper profiles, and locations
- messages, groups, ledgers, expenses, receipts, and invitations
- notifications, self profile, locale, and account invitations

The canonical [tool catalog](docs/tools.md) maps every tool to its OAuth scope,
Meo ability, upstream endpoint, schema, annotations, errors, and risk level.

## Use it safely

Ask only for the scopes needed for the task. Read the current state before a
consequential write. For updates and deletes, use stable IDs, the returned
version, and a unique idempotency key; the gateway and Meo verify the result.

Meo Mai Moi is the product and authorization authority. This repository is a
thin adapter, not a second implementation of pet, sharing, placement, or
finance rules. Administrative and internal service endpoints are never exposed
as user tools.

## Choose the right integration

Use this MCP gateway when an OAuth-capable agent is helping a person directly.
Use the [Meo Mai Moi REST API skill](https://github.com/troioi-vn/meo-mai-moi-skill)
when building a direct API integration with a user-managed personal token.
These are intentionally separate authorization models.

## Documentation

| Guide | Purpose |
|-------|---------|
| [Connect a client](docs/clients.md) | Generic setup plus Codex, Cursor, and MCP Inspector examples |
| [Tool catalog](docs/tools.md) | Canonical capability, scope, schema, annotation, and risk matrix |
| [Architecture](docs/architecture.md) | Authority boundary, request flow, and tool-development workflow |
| [OAuth](docs/oauth.md) | Discovery, consent bridge, scopes, refresh, and revocation |
| [Security](docs/security.md) | Trust boundaries, HTTP controls, and credential handling |
| [Errors](docs/errors.md) | HTTP, OAuth, and MCP tool error contracts |
| [Development](docs/development.md) | Local setup and validation for contributors |
| [Deployment](docs/deployment.md) | Public-safe deployment mechanics |
| [Release runbook](docs/release.md) | Versioning, promotion, verification, and publication |
