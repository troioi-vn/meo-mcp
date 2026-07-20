# Meo MCP workflow reference

Use this as a compact operating snapshot. The canonical
[tool catalog](../../../docs/tools.md) remains the
canonical capability matrix, and the source code remains authoritative if this
snapshot ever disagrees.

## Placeholders

| Placeholder | Meaning |
|-------------|---------|
| `<MCP_BASE_URL>` | Public origin of the selected environment, without a trailing slash |
| `<MCP_ACCESS_TOKEN>` | Opaque gateway token obtained through client-driven OAuth; never paste it into chat or source |

Maintainers resolve live values through the private operator runbook. Public
contributors can use local values derived from `.env.example`.

## Current capability snapshot

| Tool | Input | Output | MCP scope | Sanctum ability | Upstream | Annotation | Risk |
|------|-------|--------|-----------|------------------|----------|------------|------|
| Pet discovery/profile: `list_pets`, `find_pets`, `get_pet`, `list_pet_types` | documented in catalog | narrowed pet/type objects | `pets:read` | `pets:read` | pet list/detail/types | read-only | Low |
| Cross-pet care: `get_pets_overview` | filters and sort options | pet summaries plus birthday/health context | `pets:read health:read` | both domain abilities | pet list/detail plus health lists | read-only | Moderate |
| Weight: `list_weights`, `get_weight` | explicit pet/record IDs | narrowed weight records | `health:read` | `health:read` | weight list/detail | read-only | Moderate |
| Vaccination: `list_vaccinations`, `get_vaccination` | explicit pet/record IDs | narrowed vaccination records | `health:read` | `health:read` | vaccination list/detail | read-only | Moderate |
| Medical: `list_medical_records`, `get_medical_record` | explicit pet/record IDs | narrowed medical records | `health:read` | `health:read` | medical list/detail | read-only | Moderate |
| Pet writes: `create_pet`, `update_pet` | explicit values/ID, idempotency key, update version | verified narrowed pet | `pets:read pets:write` | `pets:read pet:write` | pet type/create/update/detail | create or update | Moderate |
| Health writes: add/update weight, vaccination, medical record | explicit pet/record IDs, idempotency key, update version | verified narrowed record | `health:read health:write` | matching abilities | health create/update/detail | create or update | Moderate |
| Habit reads: list/detail/heatmap/day entries | explicit habit/date/range as applicable | narrowed habit and entry summaries | `habits:read` | `habits:read` | habit read endpoints | read-only | Moderate |
| Habit writes: create/update/day/lifecycle/delete | explicit IDs, idempotency key, version for lifecycle/update/delete | verified habit/day or absence | `habits:read habits:write` | matching abilities | habit mutation and verification reads | create/update/delete | Moderate to high |
| Pet photos: list/upload URL/set primary/delete | explicit pet/photo IDs, public HTTPS source for upload, idempotency key and pet version | narrowed photos and verified pet version | `pets:read pets:write` | `pets:read pet:write` | pet detail and photo mutations | read/create/update/delete | Moderate to high |
| Microchips: list/detail/add/update/delete | explicit pet/record IDs, idempotency key, version for update/delete | narrowed record or verified absence | `microchips:read microchips:write` | matching abilities | microchip endpoints | read/create/update/delete | Moderate to high |

Consult the canonical catalog for exact schemas and choose the narrowest
non-empty scope subset needed. Write scopes are paired with the corresponding
read scope so tools can preflight and verify. A client-side connection or
authentication helper is not a gateway tool. MCP exchange tokens use the
domain abilities; existing user-created generic PAT abilities remain compatible
at corresponding Meo endpoints through their legacy `read`, `create`, `update`,
and `delete` abilities.

## Unauthenticated probes

```bash
curl -fsS <MCP_BASE_URL>/health
curl -fsS <MCP_BASE_URL>/.well-known/oauth-protected-resource/mcp
curl -fsS <MCP_BASE_URL>/.well-known/oauth-authorization-server
```

Expect health `{"status":"ok"}`, resource metadata naming
`<MCP_BASE_URL>/mcp`, and authorization metadata advertising S256 plus only the
documented scopes.

Probe the bare MCP boundary without a credential:

```bash
curl -sS -D - -o /dev/null \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  <MCP_BASE_URL>/mcp
```

Expect `401` and a `WWW-Authenticate` header whose `resource_metadata` points to
the path-scoped protected-resource document.

## Client-driven OAuth

For Codex:

```bash
codex mcp add meo-mai-moi --url <MCP_BASE_URL>/mcp
codex mcp login meo-mai-moi --scopes pets:read,health:read
codex mcp list
```

For another client, configure a remote Streamable HTTP server at
`<MCP_BASE_URL>/mcp`, choose its OAuth/authenticate action, complete Meo consent,
then refresh tool discovery. Do not manually copy credentials between clients.

## Authenticated JSON-RPC examples

Prefer a real MCP client for OAuth and protocol handling. When diagnosing with
`curl`, load the temporary opaque MCP token into `MCP_ACCESS_TOKEN` without
echoing it or placing it directly in shell history.

Initialize:

```bash
curl -sS <MCP_BASE_URL>/mcp \
  -H "Authorization: Bearer ${MCP_ACCESS_TOKEN}" \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
```

Discover tools:

```bash
curl -sS <MCP_BASE_URL>/mcp \
  -H "Authorization: Bearer ${MCP_ACCESS_TOKEN}" \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Call a read tool (this example lists pets):

```bash
curl -sS <MCP_BASE_URL>/mcp \
  -H "Authorization: Bearer ${MCP_ACCESS_TOKEN}" \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_pets","arguments":{}}}'
```

Unset the temporary environment variable when finished.

## Common failures

| Symptom/code | Layer | Action |
|--------------|-------|--------|
| `401 invalid_token` on the first MCP request | OAuth discovery | Normal when unauthenticated; start the client's OAuth action |
| `invalid_origin` | HTTP guard | Use a trusted browser origin or a non-browser client; do not weaken the allowlist casually |
| `invalid_host` | HTTP guard | Check proxy/public-base configuration and the requested host |
| `invalid_target` | OAuth | Send the exact `<MCP_BASE_URL>/mcp` resource |
| `invalid_scope` | OAuth | Request only the currently advertised narrow scopes |
| Consent denied or account ineligible | Meo policy | Stop; use an account authorized for that environment |
| `authorization_inactive` | Gateway grant | Reconnect through OAuth |
| `upstream_unauthorized` (`401`) | Delegated Meo auth | Reconnect through OAuth |
| `upstream_forbidden` (`403`) | Meo permission | Stop or change the request; do not retry blindly |
| `upstream_not_found` (`404`) | Meo resource | Refresh target discovery before retrying |
| `upstream_rate_limited` (`429`) | Meo throttling | Back off and retry later |
| Retryable `upstream_server_error` | Meo availability | Retry later; preserve request context |
| `duplicate_candidate` | Pet-create preflight | Inspect the stable candidate IDs before choosing a distinct create intent |
| `idempotency_conflict` / `idempotency_in_progress` | Write retry | Reuse keys only for exact retries; wait on an in-progress request |
| `concurrency_conflict` | Update preflight | Re-read the explicit target and reconcile against its new version |
| `post_write_verification_failed` | Write read-back | Treat the outcome as uncertain and read the stable target before retrying |
| `source_url_rejected` / `source_image_invalid` | Photo-source validation | Choose a public HTTPS URL returning a supported image |

Tool failures use MCP `isError: true` and stable JSON fields `code`, `message`,
`retryable`, and optional `upstream_status`. Read
[error guide](../../../docs/errors.md) for the complete contract.
