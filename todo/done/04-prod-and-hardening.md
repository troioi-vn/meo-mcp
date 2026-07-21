# Production cutover and hardening

Status: done — production cutover and acceptance completed 2026-07-22

## Goal

Separate ops and safety work from feature coverage so write tools and prod
exposure do not land accidentally. Provision production when ready; harden auth,
observability, and destructive-tool safeguards.

IPs, SSH identities, checkouts, database identities, CI IDs, and secret-store
inventory belong only in the private operator runbook. Public service names and
reusable deployment mechanics may remain in this repository.

## Current state

- Plans 00, 02, 03, and 01 are complete and archived under `todo/done/`.
- Development exposes the audited 172-tool, 26-scope surface documented in
  `docs/tools.md`; broad cross-domain scopes are not used.
- Comprehensive fresh-client development smoke testing covers reads and reversible
  writes across every shipped domain. Multi-party and irreversible workflows
  retain automated coverage and were safety-reviewed rather than mutating live
  production user relationships or data solely for acceptance.
- Live regression acceptance confirms numeric notification IDs, single-notification
  writes, placement creation across an explicit `pet: null` create projection, and
  exact cleanup. Meo write throttles are route-scoped so unrelated hourly and minute
  policies cannot share counters or reset windows.
- Development remains the default agent playground (see the private operator
  runbook for live inventory).
- `main` deploys a distinct production environment at the public production
  endpoint documented in `docs/deployment.md`.
- Meo permits verified, non-banned accounts to authorize MCP clients.

## Work items

### Production provision

- [x] Inventory the production host (ports, TLS, Docker networks) before choosing bind port
- [x] Provision a distinct production database and credentials
- [x] DNS + reverse proxy for the production public hostname
- [x] Operator-managed `.env`; document secret recovery/CI injection in the private runbook
- [x] CI deploy on `main` — document mechanics in `docs/deployment.md`, private live
      facts in the operator runbook
- [x] Health checks: loopback + public `/health`
- [x] Rollback procedure (prior SHA; additive migrations only)

### Auth and client registration

- [x] Require a verified, non-banned Meo account for MCP consent
- [x] Review dynamic client registration posture for prod
- [x] Scope catalog review: every granted scope maps to shipped tools
- [x] Refresh token family / revocation smoke tests before prod cutover

### Observability

- [x] Structured logs already use request IDs — verify no token leakage in prod config
- [x] Define minimal metrics/alerts (health fail, OAuth error rate, Meo upstream 5xx)
- [x] Retention and access for logs (private operator note)

### Write-tool safety

- [x] Confirm every development write phase already passed the safety gates in
      `todo/01-mcp-feature-coverage.md`; production review is an additional gate
- [x] Before enabling write scopes in prod: audit tool descriptions for irreversible
      actions (delete pet, send message, finalize placement, finance mutations)
- [x] Prefer `readOnlyHint` / destructive annotations where FastMCP supports them
- [x] Require enforceable safeguards for high-impact actions: explicit targets,
      narrow scopes, idempotency where possible, read/preview before write, and
      post-write verification; descriptions alone are insufficient
- [x] Rate limits / body size guards reviewed under development write load; Meo
      route-specific write counters are isolated by route and authenticated actor
- [x] Do not enable prod write tools without Meo ability + consent UI parity

### Docs sync

- [x] Update `docs/deployment.md` when prod exists (keep public-safe)
- [x] Update the private operator runbook with live production facts only
- [x] Update AGENTS.md branch/deploy blurb when `main` deploys

## Definition of done

- Production public endpoint serves `/health` and OAuth-protected `/mcp`
- Deploy path for `main` is documented (mechanics here, inventory in the private runbook)
- Write tools in prod have explicit safety review checklist completed
- Development remains the default agent playground unless operators opt into prod MCP

## Notes

- Feature coverage can proceed on the development endpoint without waiting for prod.
- Do not treat “100% tools on dev” as automatic greenlight for prod writes.
- Coordinate Meo production MCP connector config with meo-mai-moi release process.

## Completion evidence

- Production and development use distinct databases, connector credentials,
  encryption keys, Compose projects, TLS certificates, and deploy branches.
- Public and loopback health, OAuth/resource discovery, PKCE S256, the narrow
  `pets:read` registration default, and explicit-scope consent were verified.
- A real MCP client discovered all 172 tools, called `list_pets`, completed a
  verified notification-preference no-op, and confirmed the post-write state.
- Refresh rotation succeeded; replay of the consumed refresh token returned
  `invalid_grant` and revoked the token family, whose rotated access token then
  returned `401`.
- Production logging uses bounded container retention and dedicated reverse-
  proxy logs. Structured request events were present and configured secrets
  did not appear in the inspected logs.
- Critical write paths were re-audited for explicit stable targets, paired
  narrow read/write scopes, idempotency or concurrency controls, preview reads,
  destructive annotations, and post-write verification.
- The running application was rolled back to the previous production SHA
  without a database downgrade; loopback and public health remained green, and
  the accepted current SHA was restored through the normal production pipeline.
- Meo Mai Moi production was released with matching consent copy, Sanctum
  abilities, and connector configuration; both GPT connector environments
  remained operational.
