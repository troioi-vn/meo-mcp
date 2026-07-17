# MVP stabilization and acceptance coverage

Status: done

## Goal

Turn the working `list_pets` vertical slice into a dependable foundation before
adding scopes or write tools. Close the OAuth, transport, persistence, security,
and real-client test gaps from the launch acceptance plan.

## Work items

### OAuth and persistence

- [x] Test DCR metadata validation and exact redirect URI matching
- [x] Test PKCE `S256`, missing/invalid challenges, resource/audience enforcement,
      and scope rejection/escalation
- [x] Test five-minute codes, single-use consumption, ten-minute consent sessions,
      and expired/replayed callback references
- [x] Test one-hour access-token expiry and integer UTC epoch conversion
- [x] Test refresh rotation, 90-day grant ceiling, replay family revocation, and
      local revocation of access/refresh tokens
- [x] Test delegated-token AES-GCM round trips and ensure only hashes of client
      credentials are persisted
- [x] Test best-effort upstream revocation without weakening local revocation

### HTTP, MCP, and error behavior

- [x] Keep an authenticated MCP `initialize` integration test that runs the parent
      lifespan and Streamable HTTP session manager
- [x] Test `tools/list` and `tools/call` for `list_pets` through the ASGI boundary
- [x] Test Origin and Host validation, request-size limits, request IDs, and
      unauthenticated `WWW-Authenticate` discovery
- [x] Test upstream `401`, `403`, `404`, `429`, and `5xx` structured translations
- [x] Add a log-capture test proving MCP tokens, Sanctum PATs, API keys, authorization
      codes, and HMAC material are redacted

### Meo integration and real clients

- [x] In `meo-mai-moi`, cover allow, deny, unauthenticated, unverified, banned,
      non-allowlisted, malformed, expired, and replayed consent flows
- [x] Verify existing GPT connector behavior remains unchanged
- [x] Run OAuth plus `list_pets` through MCP Inspector
- [x] Run OAuth plus `list_pets` through Codex CLI using the configured resource
- [x] Verify a non-allowlisted development account cannot authorize

### Developer and deployment baseline

- [x] Make `uv run pytest` succeed in a fresh clone without a real `.env` or module
      import of production credentials
- [x] Add a local-development Compose option or state explicitly that the shipped
      Compose file requires an operator-provided PostgreSQL service/network
- [x] Verify migrations from an empty PostgreSQL database and rollback to the prior
      application image without destructive schema changes
- [x] Replace environment-specific application defaults with public-safe placeholders
      while keeping runtime values operator-managed
- [x] Generalize environment-specific CI variable and Docker-network labels only
      after compatible runtime/secret aliases exist; verify the deployment pipeline
      before removing the old labels

## Definition of done

- All launch acceptance behaviors above have automated coverage where practical
- Inspector and Codex complete OAuth and invoke `list_pets` against development
- A fresh clone can run the documented test command
- No additional scope or write tool has been introduced
- Durable behavior is documented, the development endpoint remains healthy, and
  this plan is moved to `todo/done/`

## Safety boundary

Public tests and docs may contain example domains and intentionally public service
URLs. They must not contain IPs, SSH identities, checkout paths, database identities,
allowlisted emails, CI IDs, secret-manager paths, or credentials. Live verification
details stay in the private operator runbook.
