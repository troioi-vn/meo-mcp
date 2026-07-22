# Active plans

Working milestone plans for meo-mcp. These are implementation checklists, not
durable architecture docs. When a plan is finished, move it to `done/` and
graduate lasting truth into `docs/`. Live deploy inventory stays in
the private operator runbook only.

## How we use this folder

1. One plan file per milestone (Status / Goal / Work Items).
2. Keep plans concrete and phased; do not mix unrelated work.
3. Update Status as work progresses (`not started` → `in progress` → `done`).
4. Move completed plans to `todo/done/`.
5. Do not put private hosts, checkout paths, CI IDs, or secrets here — point at
   the private operator runbook for those facts.

## Index

| Plan | Focus | Status |
|------|-------|--------|
| [06-vaccination-overdue-semantics.md](06-vaccination-overdue-semantics.md) | Authoritative overdue-renewal filter and schema | Not started |
| [07-openclaw-direct-mcp-call.md](07-openclaw-direct-mcp-call.md) | Upstream generic MCP tool-call command | Not started |

## Execution order

Plans 05 and 06 may proceed independently. Plan 07 is an upstream OpenClaw
contribution and may proceed in parallel with both. Complete and archive each
plan independently; an upstream review wait must not block Meo releases.

## Completed plans

| Plan | Focus |
|------|-------|
| [00-mvp-stabilization.md](done/00-mvp-stabilization.md) | OAuth, transport, security, and client acceptance foundation |
| [02-documentation.md](done/02-documentation.md) | Self-contained architecture, OAuth, security, errors, clients, and tool catalog |
| [03-agent-skill.md](done/03-agent-skill.md) | Cross-client connect, smoke, diagnosis, deploy, and tool-development workflow |
| [01-mcp-feature-coverage.md](done/01-mcp-feature-coverage.md) | Full end-user MCP tool/scope coverage and durable exclusions |
| [04-prod-and-hardening.md](done/04-prod-and-hardening.md) | Production cutover, auth policy, observability, write safety, and rollback acceptance |
| [05-agent-authorization-ux.md](done/05-agent-authorization-ux.md) | Public skill and OpenClaw connection/OAuth UX |
