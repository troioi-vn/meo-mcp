# Security model

## Trust boundaries

`meo-mcp` is internet-facing protocol infrastructure, but it is not a product
authority. Trust is divided deliberately:

- The MCP client is untrusted. It must pass OAuth, audience, scope, host,
  origin, body-size, and schema checks.
- The gateway is trusted to hold encrypted delegation material and translate
  requests, but Meo does not trust it to bypass normal user permissions.
- Meo is authoritative for the user, account eligibility, data ownership,
  resource permissions, and product behavior.
- PostgreSQL and runtime configuration are sensitive infrastructure. Neither
  their live identities nor their credentials belong in this repository.

## Credential handling

| Material | Protection |
|----------|------------|
| OAuth client secret | Not supported; DCR accepts public clients only |
| MCP authorization codes | Random opaque values; only SHA-256 digests persisted |
| MCP access/refresh tokens | Random opaque values; only SHA-256 digests persisted |
| Delegated Sanctum token | AES-256-GCM with a fresh 96-bit nonce for each encryption |
| Consent request reference | HMAC-SHA-256 signed, contains an expiry, and is consumed once |
| Connector API key and HMAC/AES keys | Runtime configuration only; never returned to clients or committed |

Digests are appropriate for high-entropy client-facing tokens because the
service needs equality lookup, not recovery. The delegated token must be
recoverable for upstream calls, so it uses authenticated encryption instead.
Encryption keys must be unique per environment; production must never reuse
development credentials or data.

Refresh rotation and replay-family revocation are described in
[oauth.md](oauth.md). A failed upstream revocation cannot reactivate a locally
revoked grant.

## HTTP and transport controls

Requests pass through gateway guards before MCP or OAuth handlers:

- **Host validation:** the `Host` must match `PUBLIC_BASE_URL`. Only `/health`
  permits loopback hosts for container probes. This and FastMCP transport
  security reduce DNS-rebinding exposure.
- **Origin validation:** when a browser sends `Origin`, it must be an exact
  member of `ALLOWED_ORIGINS`. An empty list means no browser origin is trusted.
  This is request validation; it does not itself enable CORS.
- **Body limit:** `POST`, `PUT`, and `PATCH` bodies are capped at 1 MiB using
  both declared and actual length. Invalid `Content-Length` is rejected.
- **Audience binding:** OAuth authorization and token requests must name the
  exact `{PUBLIC_BASE_URL}/mcp` resource. Access-token records are checked
  against the same resource.
- **Request correlation:** every response receives `X-Request-ID`; a caller's
  value is preserved when supplied. Structured guard errors include it.
- **Transport lifecycle:** the FastMCP session manager is started and stopped
  with the parent Starlette lifespan.

Remote pet-photo ingestion has a second outbound boundary. It accepts only
HTTPS on port 443, rejects credentials and fragments, resolves every DNS answer
and rejects the whole host if any address is non-public, connects to one pinned
address while preserving TLS SNI/HTTP Host, and repeats validation for each of
at most three redirects. Only supported image MIME types are streamed, with a
10 MiB declared and actual size ceiling. Source response bodies and URLs are
not copied into errors or logs.

Reverse proxies must preserve the public host and HTTPS scheme consistently
with `PUBLIC_BASE_URL`. TLS termination, rate limits, firewall policy, backup,
and runtime monitoring are deployment controls rather than application
substitutes.

## OAuth controls

- Dynamic registration supports public clients only.
- Redirect URIs may not contain fragments or embedded user information and are
  matched exactly during authorization/token exchange.
- S256 PKCE is mandatory; plain PKCE is not supported.
- Authorization accepts a non-empty, duplicate-free subset of the advertised
  scopes; each tool checks its own requirements and refresh cannot escalate.
- Consent references, exchange codes, OAuth codes, and refresh tokens are
  short-lived or single-use as appropriate.
- Refresh replay and explicit revocation invalidate the entire local grant.

Tool annotations and descriptions are hints to clients. Actual safety comes
from OAuth scopes, upstream Sanctum abilities, stable target validation,
idempotency/concurrency controls for writes, and Meo's permission checks.

Current writes require a caller-supplied idempotency key that Meo binds to the
authenticated user and normalized request fingerprint. Updates additionally
require the target's last-read version; Meo rejects stale versions before
mutation. The gateway reads every successful write back through the normal
read scope, so write scopes alone cannot bypass inspection and verification.

## Logging and errors

Structured logging redacts fields named for access/refresh tokens, API keys,
authorization codes, delegated/Sanctum tokens, HMAC material, encryption keys,
and common `*_secret` or `*_token` variants before rendering. Code should log
only request IDs, safe endpoint identifiers, status, latency, and exception
types—not raw headers, bodies, query strings, or credential-bearing free text.

Tool errors replace upstream bodies with gateway-owned messages and stable
codes. This prevents internal or user-specific upstream detail from crossing
the MCP boundary. See [errors.md](errors.md).

Pet invitation URLs contain a bearer capability. MCP preview, accept, and
decline calls extract and validate the token locally, send it to dedicated Meo
endpoints in a JSON body, and never echo it in tool output. The gateway also
raises the HTTP transport libraries' log threshold so a future debug setting
cannot place request URLs in normal application logs. Meo records route
templates rather than concrete tokenized paths in its structured API log.

## Configuration and documentation boundary

Public source may contain environment variable names, placeholders, public
service URLs, and topology required to understand committed deployment files.
It must not contain secret values or private live inventory: IPs, SSH identities,
checkout paths, database identities, CI/repository IDs, or secret-manager
locations. Those facts belong only in the private operator runbook.

Use [.env.example](../.env.example) as a names-and-shapes template. A server
`.env` is operator-managed and must never enter Git. Local tests inject isolated
SQLite stores and non-secret test cryptographic material, so contributors do
not need live credentials.

## Security review checklist for a tool

Before shipping a tool, verify:

1. The upstream endpoint is user-facing and Meo independently enforces access.
2. Its MCP scope is narrow and maps to the least Sanctum ability required.
3. Inputs and outputs are explicit; responses do not pass arbitrary upstream
   fields through.
4. Errors are structured and do not expose upstream bodies or credentials.
5. A write has stable targets, retry/duplicate semantics, concurrency behavior,
   preview where impact is high, and post-write verification.
6. Boundary tests cover authorization, failure translation, and logs.
7. [tools.md](tools.md) records its schema, annotations, risks, and mapping.
