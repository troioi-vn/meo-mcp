# Agent skill for meo-mcp

Status: done

## Goal

Add an open-standard repository skill that teaches Codex, Cursor, and compatible
agents how to **operate and develop** the
meo-mcp gateway (connect, smoke, OAuth expectations, add tools safely). Keep it
out of always-on context; AGENTS.md only points to it.

Do **not** duplicate product-domain guidance from `../meo-mai-moi-skill`.

## Good practice (why a skill)

| Layer | Load | Contents |
|-------|------|----------|
| `AGENTS.md` | Always | Mission, hard rules, branch policy, short pointers |
| `.agents/skills/meo-mcp/` | On demand | Step-by-step connect/smoke/dev workflows |
| `docs/` | On demand | Durable architecture and tool catalog |
| `meo-mai-moi-skill` | Separate | How Meo product domains work for end users |

Skills are for *workflows* triggered by description (“when working with Meo MCP…”).
Project knowledge needed on every edit stays in AGENTS.md.

## Target layout

```
.agents/skills/meo-mcp/
├── SKILL.md       # required — under ~500 lines
└── reference.md   # tool catalog snapshot, error/auth shapes, curl examples
```

Optional later: `examples.md` for sample tool call transcripts.

## SKILL.md requirements

### Frontmatter

- `name`: `meo-mcp` (lowercase, hyphens)
- `description`: third person; WHAT + WHEN; include trigger terms such as
  Meo MCP, meo-mcp, Streamable HTTP, OAuth, `list_pets`, pets:read
- Prefer discoverable invocation (do not set `disable-model-invocation: true`
  unless we intentionally want manual-only)

### Body (concise)

- [x] When to use this skill vs AGENTS.md vs meo-mai-moi-skill
- [x] Connect / smoke: health and OAuth metadata with placeholders; expected 401 on
      bare `/mcp`; Codex CLI and generic client configuration; OAuth consent; call
      `list_pets`; maintainers resolve live values through the operator runbook
- [x] Auth model summary (opaque MCP token → delegated Sanctum); never log tokens
- [x] How to discover tools; prefer read-only; do not widen scopes without explicit ask
- [x] How to add a tool: Meo API authority first → `meo_api.py` → `@server.tool` →
      scopes → tests → update docs/catalog
- [x] Secrets: never commit `.env`; live secret *locations* only in the private operator runbook
- [x] Link to `reference.md` and `docs/deployment.md`; mention the private operator
      runbook without embedding a workstation path

### reference.md

- [x] Current tool list (start with `list_pets`)
- [x] Scope list and meaning
- [x] Public-safe curl / JSON-RPC style examples for initialize / tools/list / tools/call
      (use environment placeholders; maintainers resolve live values privately)
- [x] Common failure modes (401 invalid_token, invalid_origin, Meo 403/404 mapping)

## Work items

- [x] Create `.agents/skills/meo-mcp/SKILL.md` + `reference.md`
- [x] Ensure `AGENTS.md` pointer matches the real path (already stubbed)
- [x] Align with `todo/02-documentation.md` so tool catalog isn’t duplicated awkwardly
      (skill reference can summarize; `docs/tools.md` is canonical once written)
- [x] Validate the skill with the repository's available skill-authoring/validation
      tooling, then smoke it in fresh Codex and Cursor turns mentioning “meo-mcp OAuth”
- [x] Keep under 500 lines; progressive disclosure only one level deep

## Out of scope

- Marketplace / `npx skills` packaging (project-local skill is enough)
- Writing meo-mai-moi product workflows into this skill
- Embedding live hosts, checkout paths, CI IDs, or secret values

## Definition of done

- Skill file exists under `.agents/skills/meo-mcp/`
- Description triggers on Meo MCP / OAuth / Streamable HTTP terms
- AGENTS.md links to it
- An agent can connect and smoke `list_pets` following the skill, using the private
  operator runbook only when live maintainer values are required

## Notes

- Follow the open Agent Skills format and use the current environment's skill-creator
  instructions when implementing this plan.
- Keep `.agents/skills/` canonical. Add a client-specific compatibility pointer only
  if testing proves a supported client cannot discover the standard location.
