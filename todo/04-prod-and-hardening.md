# Production cutover and hardening

Status: in progress — awaiting explicit production provisioning approval

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
  writes across every shipped domain. Multi-party and irreversible workflows remain
  explicit production acceptance items.
- Live regression acceptance confirms numeric notification IDs, single-notification
  writes, placement creation across an explicit `pet: null` create projection, and
  exact cleanup. Meo write throttles are route-scoped so unrelated hourly and minute
  policies cannot share counters or reset windows.
- Development environment only (see the private operator runbook).
- `main` has no deploy workflow; production is not provisioned.
- Meo permits verified, non-banned accounts to authorize MCP clients.

## Work items

### Production provision

- [x] Inventory the production host (ports, TLS, Docker networks) before choosing bind port
- [ ] Provision a distinct production database and credentials
- [ ] DNS + reverse proxy for the production public hostname
- [ ] Operator-managed `.env`; document secret recovery/CI injection in the private runbook
- [ ] CI deploy on `main` — document mechanics in `docs/deployment.md`, private live
      facts in the operator runbook
- [ ] Health checks: loopback + public `/health`
- [ ] Rollback procedure (prior SHA; additive migrations only)

### Auth and client registration

- [x] Require a verified, non-banned Meo account for MCP consent
- [ ] Review dynamic client registration posture for prod
- [ ] Scope catalog review: every granted scope maps to shipped tools
- [ ] Refresh token family / revocation smoke tests before prod cutover

### Observability

- [ ] Structured logs already use request IDs — verify no token leakage in prod config
- [ ] Define minimal metrics/alerts (health fail, OAuth error rate, Meo upstream 5xx)
- [ ] Retention and access for logs (private operator note)

### Write-tool safety

- [x] Confirm every development write phase already passed the safety gates in
      `todo/01-mcp-feature-coverage.md`; production review is an additional gate
- [ ] Before enabling write scopes in prod: audit tool descriptions for irreversible
      actions (delete pet, send message, finalize placement, finance mutations)
- [x] Prefer `readOnlyHint` / destructive annotations where FastMCP supports them
- [x] Require enforceable safeguards for high-impact actions: explicit targets,
      narrow scopes, idempotency where possible, read/preview before write, and
      post-write verification; descriptions alone are insufficient
- [x] Rate limits / body size guards reviewed under development write load; Meo
      route-specific write counters are isolated by route and authenticated actor
- [ ] Do not enable prod write tools without Meo ability + consent UI parity

### Docs sync

- [ ] Update `docs/deployment.md` when prod exists (keep public-safe)
- [ ] Update the private operator runbook with live production facts only
- [ ] Update AGENTS.md branch/deploy blurb when `main` deploys

## Definition of done

- Production public endpoint serves `/health` and OAuth-protected `/mcp`
- Deploy path for `main` is documented (mechanics here, inventory in the private runbook)
- Write tools in prod have explicit safety review checklist completed
- Development remains the default agent playground unless operators opt into prod MCP

## Notes

- Feature coverage can proceed on the development endpoint without waiting for prod.
- Do not treat “100% tools on dev” as automatic greenlight for prod writes.
- Coordinate Meo production MCP connector config with meo-mai-moi release process.
