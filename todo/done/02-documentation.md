# Documentation improvements

Status: done

## Goal

Grow public, reusable documentation beyond the current `README.md` +
`docs/deployment.md` so humans and agents can understand architecture, auth,
scopes, and the tool surface — without copying private live inventory into this
repo.

## Current state

| Artifact | Status |
|----------|--------|
| `README.md` | Minimal (MVP vertical-slice blurb) |
| `docs/deployment.md` | Public-safe deploy model; private live facts deferred to the operator runbook |
| `AGENTS.md` | Always-on agent rules |
| Architecture / auth / tool catalog | Missing |
| Live private inventory | Belongs in the private operator runbook only |

## Work items

### README

- [x] Expand README: what meo-mcp is, who it’s for, link to AGENTS.md, deployment,
      todo index, and (once written) architecture + skill
- [x] Keep README short; deep detail stays in `docs/`

### Architecture and auth

- [x] Add `docs/architecture.md`: request flow (client → OAuth → tools → Meo),
      component map (`main` / `oauth` / `meo_api` / `security` / DB), transport choice
- [x] Document OAuth + Meo bridge (authorize → `/mcp-connect` → callback → exchange →
      opaque tokens); scopes list and how they map to Sanctum abilities
- [x] Document error shapes and security middleware (origin allowlist, body cap,
      DNS-rebinding protection) at a public-safe level
- [x] Explain the public/private boundary: public endpoints and deploy mechanics may
      be documented; IPs, SSH identities, checkout paths, database identities,
      allowlisted users, CI IDs, and secret locations stay in the operator runbook

### Tool catalog

- [x] Add `docs/tools.md` (or section in architecture): each MCP tool name,
      description, scopes, read/write, upstream Meo endpoints
- [x] Keep catalog updated as `todo/01-mcp-feature-coverage.md` phases land
- [x] Note that some clients may also surface a client-side auth helper (not
      defined in this repo)

### Agent onboarding

- [x] Short “connect an MCP client” steps using placeholders, OAuth consent, and
      `list_pets` / health; maintainers use the private runbook for live values
- [x] Link planned skill: `.agents/skills/meo-mcp/SKILL.md` (`todo/03-agent-skill.md`)
- [x] Clarify AGENTS vs skill vs meo-mai-moi-skill (gateway rules vs ops workflow vs
      product domain)

### Hygiene

- [x] Ensure AGENTS.md pointers stay accurate as docs are added
- [x] When a todo plan finishes, graduate durable sections into `docs/` and move the
      plan to `todo/done/`
- [x] No API keys, encryption keys, or other secret values in any public doc
- [x] Run a repository leak scan for workstation paths, IPs, SSH targets, database
      identities, allowlisted emails, CI IDs, and secret-manager paths

## Definition of done

- New contributor (or agent) can explain auth + how to add a tool from docs alone
- Tool catalog exists and matches implemented tools
- Live private facts remain only in the operator runbook
- README is a clear entry point with links

## Notes

- Prefer one level of depth: AGENTS points to docs; docs mention the private operator
  runbook only when maintainer-only live values are required.
- Do not invent a second skill document under `docs/SKILL.md`; link the canonical
  `.agents/skills/meo-mcp/SKILL.md` from AGENTS.
