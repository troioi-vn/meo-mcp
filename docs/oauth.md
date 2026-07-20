# OAuth and the Meo consent bridge

## Two credential layers

The gateway separates the credential presented by an MCP client from the
credential used to call Meo:

- **MCP credentials** are opaque access and refresh tokens issued by
  `meo-mcp`. Clients never receive the upstream Sanctum token.
- **Delegated credential** is a narrowly scoped Sanctum personal access token
  issued by Meo after consent. The gateway encrypts it at rest and uses it only
  for upstream Meo requests or revocation.

This separation lets the gateway enforce MCP audience, scope, expiry, rotation,
and revocation without making Meo understand each MCP client's token format.

## Discovery and endpoints

Given an MCP resource of `{PUBLIC_BASE_URL}/mcp`, clients discover OAuth from:

| Endpoint | Purpose |
|----------|---------|
| `/.well-known/oauth-protected-resource/mcp` | Resource identifier, authorization server, and supported scopes |
| `/.well-known/oauth-authorization-server` | Issuer, authorization/token/registration/revocation endpoints, PKCE methods, and scopes |
| `/register` | Dynamic registration for public OAuth clients |
| `/authorize` | Authorization request and redirect into Meo consent |
| `/token` | Authorization-code and refresh-token exchange |
| `/revoke` | Local grant/token revocation with best-effort upstream revocation |
| `/oauth/meo/callback` | Server-side return from Meo's one-time exchange bridge |

An unauthenticated MCP request returns `401` with a `WWW-Authenticate` header
whose `resource_metadata` parameter points to the path-scoped protected-resource
document.

## Authorization-code flow

```text
client          meo-mcp                         Meo
  │ discover + dynamic registration              │
  │───────────────▶│                              │
  │ /authorize: resource, scope, state, S256 PKCE │
  │───────────────▶│                              │
  │                │ signed, expiring request ref │
  │                ├──────── /mcp-connect ───────▶│
  │                │             user approves/denies
  │                │◀──── callback + one-time exchange code
  │                ├──── authenticated exchange ─▶│
  │                │◀──── user id + Sanctum PAT ──┤
  │◀── exact registered redirect + OAuth code ────│
  │ /token: code, verifier, exact resource         │
  │───────────────▶│                              │
  │◀──── opaque access token + rotating refresh ──│
```

Detailed behavior:

1. Dynamic registration accepts only public clients using
   `token_endpoint_auth_method=none`. At least one redirect URI is required;
   client secrets are rejected and never persisted.
2. The authorization request must use the exact MCP resource audience, the
   non-empty, duplicate-free subset of current scopes, and an S256 PKCE challenge. Redirect matching is
   exact against registered metadata.
3. The gateway persists a ten-minute authorization request and redirects the
   browser to Meo's `/mcp-connect` page with an HMAC-signed, expiring reference.
4. Meo displays the client name and requested scopes. Environment policy decides
   whether the signed-in account may approve; current development policy also
   requires a verified, non-banned, eligible account. Denial is single-use too.
5. Approval creates a Sanctum token with only the abilities mapped from those
   scopes and a five-minute, single-use exchange code. The exchange endpoints
   are server-to-server and authenticated with the configured connector key.
6. The gateway exchanges the code, encrypts the delegated token, creates a
   grant, and sends a five-minute OAuth authorization code to the client's exact
   redirect URI.
7. `/token` verifies the code, PKCE verifier, client, redirect, scope, and exact
   `resource` parameter before issuing opaque MCP credentials.

## Current scope mapping

| MCP scope | Consent meaning | Delegated Sanctum ability | Used by |
|-----------|-----------------|----------------------------|---------|
| `pets:read` | View the user's pet profiles and public pet-type reference data | `pets:read` (legacy PAT: `read`) | Pet list/find/detail, pet types, overview |
| `health:read` | View weight, vaccination, and medical history for accessible pets | `health:read` (legacy PAT: `read`) | Health list/detail tools, overview |

The complete tool-level mapping is in [tools.md](tools.md). Adding a scope
requires coordinated gateway OAuth metadata, tool enforcement, Meo consent
copy, and Sanctum abilities. Clients request a non-empty subset without
duplicates; each tool enforces its own scope requirement. A scope must not be
advertised before a tool needs it.

## Lifetimes and persistence

| Item | Lifetime | Storage behavior |
|------|----------|------------------|
| Consent/authorization request | 10 minutes | Database record; consumed once |
| Meo exchange code | 5 minutes | One-time upstream cache entry; only its SHA-256 digest is the lookup key |
| MCP authorization code | 5 minutes | Only a SHA-256 digest is stored; consumed once |
| MCP access token | 1 hour | Only a SHA-256 digest is stored |
| Grant and refresh capability | At most 90 days | Grant expiry caps every rotated refresh token |
| Delegated Sanctum token | Grant lifetime or earlier revocation | AES-256-GCM ciphertext at rest |

Refresh tokens rotate on every successful use. Reusing a consumed refresh token
is treated as replay: the entire refresh family, all access tokens for the grant,
and the grant itself are revoked locally before the gateway attempts upstream
Sanctum revocation. Explicitly revoking either an access or refresh token also
revokes the whole grant. Upstream revocation is best-effort; local revocation
does not depend on Meo being reachable.

## Failure and reconnect behavior

Expired, consumed, audience-mismatched, or scope-escalating credentials fail
without revealing stored values. If Meo rejects the delegated token, clients
receive a structured tool error instructing them to reconnect rather than the
upstream response body. See [errors.md](errors.md) for stable machine-readable
contracts.
