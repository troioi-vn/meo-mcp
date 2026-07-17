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

| Plan | Focus |
|------|--------|
| [00-mvp-stabilization.md](00-mvp-stabilization.md) | Complete OAuth, transport, security, and client acceptance coverage |
| [01-mcp-feature-coverage.md](01-mcp-feature-coverage.md) | Full end-user MCP tool/scope coverage |
| [02-documentation.md](02-documentation.md) | Docs beyond deployment (architecture, catalog, README) |
| [03-agent-skill.md](03-agent-skill.md) | Cursor skill for operating/developing this gateway |
| [04-prod-and-hardening.md](04-prod-and-hardening.md) | Prod cutover, auth policy, observability, write safety |

## Execution order

Complete plans end-to-end in this order:

1. `00-mvp-stabilization.md`
2. `02-documentation.md`
3. `03-agent-skill.md`
4. `01-mcp-feature-coverage.md`, one phase at a time
5. `04-prod-and-hardening.md`

Do not begin a later plan merely because an earlier plan has partially landed.
Meet its definition of done, update durable docs, move it to `todo/done/`, and
verify the development client flow before continuing.
