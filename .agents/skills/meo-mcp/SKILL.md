---
name: meo-mcp
description: "Guides agents through operating and developing the Meo MCP gateway: connecting Streamable HTTP clients, completing OAuth, smoke-testing health and list_pets with pets:read, diagnosing structured failures, deploying safely, and adding narrowly scoped semantic tools. Use when work mentions Meo MCP, meo-mcp, Streamable HTTP, OAuth, list_pets, pets:read, gateway smoke tests, or extending the MCP tool surface. Do not use for end-user pet-management workflows; use the separate meo-mai-moi skill instead."
---

# Meo MCP gateway

Follow the repository's `AGENTS.md` first. Use this skill for on-demand gateway
workflows; keep always-applicable authority, branch, and security rules in
`AGENTS.md`. Use the separate `meo-mai-moi` skill for user-facing pet-management
workflows and product-domain concepts. Do not copy that knowledge here.

## Load only what the task needs

- Read [reference.md](reference.md) for the current tool/scope snapshot, public-safe probes,
  JSON-RPC examples, and common failures.
- Read the [client guide](../../../docs/clients.md) to connect Codex, Cursor, MCP Inspector, or a
  generic Streamable HTTP client.
- Read the [architecture](../../../docs/architecture.md) and
  [tool catalog](../../../docs/tools.md) before adding or changing a tool. Treat
  `docs/tools.md` as the canonical capability matrix.
- Read the [OAuth](../../../docs/oauth.md), [security](../../../docs/security.md),
  and [error](../../../docs/errors.md) guides for auth, trust-boundary, or
  failure-contract work.
- Read the [deployment guide](../../../docs/deployment.md) for public release mechanics. When a
  maintainer needs live values, locate the private operator runbook through
  workstation-level instructions; never embed its path or contents here.

## Connect and smoke-test

1. Resolve `<MCP_BASE_URL>` from user-provided environment information. For a
   maintainer live check, use the private operator runbook without printing
   private inventory.
2. Run the unauthenticated health and OAuth metadata probes from
   [reference.md](reference.md).
   Confirm that a bare MCP initialize request returns `401` with protected
   resource metadata. Do not mistake that expected discovery response for an
   outage.
3. Configure `<MCP_BASE_URL>/mcp` as a remote Streamable HTTP server. Prefer the
   client's native OAuth support; never ask the user to paste an MCP or Sanctum
   token.
4. Complete Meo consent in the browser. Do not record authorization URLs,
   callback query strings, codes, or tokens in chat, logs, screenshots, or
   issue text.
5. Discover tools before calling them. For the current baseline, confirm only
   the documented read tool and scope, then call `list_pets` with `{}`.
6. Report the client, tool, result status, and minimal acceptance evidence. Do
   not reproduce personal pet records unless the task genuinely needs them.

Prefer read-only acceptance. Do not widen OAuth scopes or create a write grant
merely to make a smoke test pass.

## Diagnose safely

1. Re-read current code, local state, and live metadata; do not rely on a stale
   tool list or cached OAuth assumption.
2. Separate layers: public health, OAuth discovery/consent, MCP bearer auth,
   tool scope, delegated Sanctum authorization, and the upstream Meo response.
3. Branch on stable structured error codes from `docs/errors.md`, not message
   wording. Preserve the request ID and inspect only redacted logs.
4. Treat an inactive grant or upstream `401` as a reconnect case. Back off for
   retryable rate-limit or server errors. Do not blind-retry non-retryable
   failures.
5. Never print `.env`, authorization headers, OAuth database rows, raw callback
   URLs, connector keys, HMAC material, encryption keys, MCP tokens, or
   delegated Sanctum tokens.

For deployment incidents, keep local revocation authoritative even when
upstream revocation fails. Roll back application code against the current
additive schema; do not run destructive database downgrades.

## Add or change a tool

1. Start with the semantic user intent. Inspect the Meo Laravel API as the
   authority and the GPT connector only for proven semantic shapes. Keep admin,
   Filament, and internal connector endpoints out of the tool surface.
2. Ensure Meo already enforces the product rule and user/resource permission.
   If a new endpoint, consent label, or Sanctum ability is required, implement
   and test it upstream in the same milestone before exposing the tool.
3. Define the `docs/tools.md` entry: intent, MCP scope, Sanctum ability, every
   upstream endpoint, stable input/output schemas, annotations, structured
   errors, and risk level.
4. Implement delegated calls and strict response narrowing in `meo_api.py`.
   Register the semantic tool with explicit annotations in `main.py`; do not
   mirror a REST route mechanically or duplicate domain logic.
5. Add the narrow domain scope to `ALLOWED_SCOPES` only when its tool ships, and
   coordinate OAuth metadata, Meo consent copy, delegated abilities, and tool
   enforcement. Never substitute a broad cross-domain scope.
6. For writes, require explicit stable targets, idempotency or duplicate
   handling, defined concurrency behavior, preview/read-before-write for high
   impact, and post-write verification. Tool-description confirmation language
   is guidance, not enforcement.
7. Test normalization, errors, scope enforcement, authenticated initialize,
   `tools/list`, `tools/call`, logging redaction, and write retry/concurrency
   behavior as applicable. Run the repository's documented test/lint commands.
8. Update `docs/tools.md` and the snapshot in `reference.md`, scan public files
   for private inventory, deploy through the authorized branch, monitor CI and
   deployment logs, verify the exact SHA and health, then repeat real-client
   discovery and the tool call.

## Preserve secrets and operational boundaries

- Never commit `.env` or real credentials. Use `.env.example` only for names and
  placeholder shapes.
- Keep IPs, SSH identities, checkout paths, database identities, allowlisted
  users, CI/repository IDs, and secret-manager locations in the private operator
  runbook only.
- Use `dev` for routine gateway work. Do not create or deploy production without
  the explicit production checkpoint required by repository policy.
- Keep durable engineering truth in `docs/`, the canonical tool matrix in
  `docs/tools.md`, and only concise reusable procedure in this skill.
