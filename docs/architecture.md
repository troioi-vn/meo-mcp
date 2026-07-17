# Architecture

## Purpose and boundary

`meo-mcp` gives MCP clients a stable, semantic interface to Meo Mai Moi. It
owns protocol translation, MCP OAuth credentials, delegated-token storage,
input normalization, response narrowing, and structured error translation.
The Meo Laravel application remains authoritative for users, pets,
permissions, consent eligibility, and every product rule.

The key test for gateway code is: could Meo enforce this behavior without
trusting the gateway? If not, the rule belongs upstream before a tool ships.

```text
MCP client
  │  OAuth discovery, authorization, opaque access token
  ▼
meo-mcp ── PostgreSQL: clients, grants, token digests, encrypted delegation
  │  decrypted delegated Sanctum token, only for an upstream request
  ▼
Meo Mai Moi API ── authoritative user data and permission checks
```

## Runtime request flow

1. A client connects to `{PUBLIC_BASE_URL}/mcp` using Streamable HTTP.
2. Without a valid gateway token, the resource returns `401` and points the
   client to protected-resource metadata.
3. The client completes OAuth. Browser consent happens in Meo, while this
   service issues and persists the MCP-facing grant and opaque tokens.
4. An authenticated `tools/list` exposes the gateway's registered end-user
   tools. Each call still enforces its required scope.
5. For `tools/call`, the gateway validates the MCP access token and scope,
   loads its grant, and decrypts the delegated Sanctum token in memory.
6. The semantic implementation calls a user-facing Meo API endpoint. Meo
   applies the delegated token's ability and its normal resource permissions.
7. The gateway returns a deliberately narrowed result or a structured MCP tool
   error. It does not pass arbitrary upstream payloads through.

The transport is stateless Streamable HTTP with JSON responses. Stateless here
means MCP requests do not depend on an application-process session; OAuth and
grant state is still durable in PostgreSQL. The FastMCP session manager runs for
the parent application's lifespan even in stateless mode.

## Component map

| Module | Responsibility |
|--------|----------------|
| `main.py` | App factory, FastMCP server, tool registration, lifespan, health endpoint, callback route, and request guards |
| `oauth.py` | Database-backed OAuth provider, allowed scopes, Meo consent redirect/exchange, token issue/rotation/revocation |
| `meo_api.py` | Delegated Meo HTTP calls, response normalization, and upstream error mapping |
| `security.py` | UTC/token helpers, SHA-256 digests, AES-256-GCM encryption, signed consent references, and structured-log redaction |
| `database.py` | SQLAlchemy models and async session factory for OAuth clients, authorization requests, grants, codes, and tokens |
| `config.py` | Environment-backed settings and derived issuer/resource URLs |
| `migrations/` | Additive PostgreSQL schema history |

FastMCP supplies the MCP transport and OAuth endpoint plumbing. Starlette owns
the composed HTTP application and middleware. Alembic manages schema changes.

## Data ownership

| Data | System of record | Gateway behavior |
|------|------------------|------------------|
| User identity and account eligibility | Meo | Receives only an upstream user identifier after approved consent |
| Pets and product permissions | Meo | Reads through documented user-facing APIs and narrows the response |
| MCP client registration | meo-mcp | Stores public-client metadata; no client secret is accepted |
| MCP authorization grants and tokens | meo-mcp | Stores grant state and only digests of client-facing codes/tokens |
| Delegated Sanctum token | Meo issues; meo-mcp stores | Encrypts at rest and decrypts only for an upstream call or revocation |

## Adding a tool

A tool is a product/security change, not merely a new Python function.

1. Start from a user workflow and confirm the required public Meo endpoint and
   authorization behavior exist. Do not expose admin, Filament, or internal
   connector endpoints as tools.
2. Define the semantic intent, stable input/output schema, read/write risk,
   annotations, duplicate or idempotency behavior, and structured errors.
3. Choose a narrow domain scope. Map it explicitly to the delegated Sanctum
   ability and coordinate the consent copy and token abilities in Meo.
4. Add the scope to the OAuth allowlist only when the tool that needs it ships.
   Never use a broad cross-domain scope as a shortcut.
5. Implement upstream calls and normalization in `meo_api.py`; keep domain
   decisions in Meo. Register the semantic tool in `main.py`.
6. Test the adapter, authenticated MCP boundary, scope enforcement, upstream
   failures, and any write retry/concurrency behavior.
7. Update the canonical matrix in [tools.md](tools.md), then validate through a
   real OAuth client and the development deployment.

For writes, the target must be explicit and stable. High-impact actions require
a read or preview before mutation and post-write verification. Description text
may guide a model, but it is never an authorization or safety control.

## Public and private operational information

This repository documents reusable architecture, public endpoints where useful,
and the deployment mechanics required to understand committed artifacts. Live
inventory—IPs, SSH identities, checkout paths, database identities, allowlisted
users, CI/repository IDs, and secret-manager locations—belongs only in the
private operator runbook. Public contributors do not need that runbook to build,
test, or understand this service.
