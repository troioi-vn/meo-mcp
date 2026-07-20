# MCP feature coverage (100% end-user surface)

Status: in progress (Phases 1A, 1B, 2A, and 2B complete; Phase 3 is next)

## Goal

Expose all **end-user** Meo Mai Moi capabilities through semantic MCP tools so
agents can do anything a normal user can via the app — excluding Filament/admin.

“100%” means product domains below, not a 1:1 mirror of every OpenAPI path.
Tools stay semantic (LLM workflows), matching meo-gpt-connector design rules in
`AGENTS.md`.

## Inventory baseline

| Source | Use |
|--------|-----|
| `../meo-mai-moi/backend/routes/api.php` + OpenAPI tags | Full API surface |
| `../meo-gpt-connector` routers | Proven pets + health R/W shapes |
| `../meo-mai-moi/docs/api-integration.md` | PAT / ability contract for programmatic clients |
| Phase 0 baseline | `list_pets` only (`pets:read`); expand through the phases below |

### Domains in scope

Pets & profiles, photos, pet sharing/relationships, weights, medical records,
vaccinations, microchips, habits, placement/rehoming, helpers, messaging, groups,
finance/ledgers, notifications, resource invitations, user profile.

### Out of scope

Admin/Filament, ban APIs, internal connector auth endpoints as user tools,
infrastructure/IoT unless product explicitly wants agent access later.

## Phase 0 — launched, stabilization required

- [x] OAuth AS + Meo `mcp-auth` bridge
- [x] Streamable HTTP `/mcp`
- [x] Tool: `list_pets` (read-only)
- [x] Scope: `pets:read`
- [x] Complete `todo/00-mvp-stabilization.md` before expanding this surface

## Capability matrix prerequisite

Before implementing a phase, add its proposed tools to `docs/tools.md` with:

- semantic tool name and user journey
- read/write/destructive classification and MCP annotations
- exact MCP scope and matching Sanctum ability
- upstream Meo endpoint(s), input/output schema, and error mapping
- idempotency/concurrency strategy and risk level for writes

Do not use a broad scope across pets, health, messaging, placement, and finance.
Consent copy must describe each independently meaningful permission.

## Phase 1A — GPT-connector read parity

Match the read side of the ChatGPT connector so agents can inspect pets and core health.

### Likely tools (names indicative)

- Pets: list (done), get, find/search, overview
- Weights, vaccinations, and medical records: list/detail
- Supporting pet types / species lookup

### Work items

- [x] Map each GPT connector route to one or more MCP tools + input schemas
- [x] Expand `ALLOWED_SCOPES` with narrowly named read scopes in lockstep with
      Meo Sanctum abilities / MCP connector config in `meo-mai-moi`
- [x] Implement Meo client methods in `meo_api.py`; keep normalization in the gateway
- [x] Structured error translation for validation / 403 / 404
- [x] Tests per tool (auth required, happy path, Meo error mapping)
- [x] Update server `instructions` string as capabilities grow
- [x] Smoke on the development MCP endpoint after deploy using the private operator runbook

Development acceptance on 2026-07-20 covered OAuth discovery and consent in
MCP Inspector, a real `list_pets` call, and fresh Codex discovery of all 11 read
tools followed by successful pet, weight, vaccination, medical-record, and
overview calls. Only aggregate counts and status flags were retained.

## Phase 1B — Low-risk GPT-connector writes

- [x] Add pet create/update and weight/vaccination/medical-record add/update only
      after Phase 1A is stable
- [x] Define narrow write scopes, consent copy, matching Sanctum abilities, and
      explicit non-destructive/destructive annotations
- [x] Require explicit stable target IDs; do not let fuzzy search select a write target
- [x] Define idempotency and duplicate-submission behavior for every create action
- [x] Handle concurrent updates explicitly where the Meo API exposes versions/timestamps
- [x] Test validation, authorization, duplicate requests, stale updates, and upstream failure
- [x] Run read-before-write and post-write verification through a real development client

Development acceptance on 2026-07-20 used a fresh Codex four-scope grant and
discovered all 19 tools. It verified exact create replay, changed-payload
idempotency conflict, duplicate-candidate handling, optimistic-concurrency
conflict, and read-before/post-write verification for pet, weight, vaccination,
and medical-record creates and updates. Only stable acceptance IDs and status
flags were retained. The live exercise also found and closed a bearer-PAT
authentication gap ahead of Meo's idempotency middleware.

## Phase 2 — Remaining pet-care

- [x] Phase 2A: habits (list, entries by date, heatmap, configuration and lifecycle writes)
- [x] Phase 2A: pet photos (guarded public-URL upload, list, primary selection, delete)
- [x] Phase 2A: microchips (CRUD while preserving linked finance records on delete)
- [x] Phase 2A: narrow scopes, Meo abilities, tests, deployment, and real-client smoke
- [x] Phase 2B: pet user relationships / leave / invitations as a separate high-impact milestone
- [x] Phase 2B: narrow scopes, Meo abilities, tests, deployment, and real-client smoke

Phase 2A development acceptance on 2026-07-20 used a fresh Codex eight-scope
grant and discovered all 38 tools. Habit acceptance verified exact create replay,
day entry and heatmap reads, update, stale-version conflict, archive, restore,
delete, and cleanup. Photo acceptance imported a bounded public PNG, verified
primary selection and deletion, and left no photo artifact. Microchip acceptance
verified create/update/delete, absence of a linked finance transaction, the
preserve-finance delete path, and cleanup. Meo pipeline `#312` deployed
`74030ffd`; gateway pipeline `#23` deployed `799e76d`.

Phase 2B development acceptance on 2026-07-20 used a fresh Codex ten-scope
grant and discovered all 50 tools. It verified narrowed sharing, suggestion,
and pending-invitation reads, then created one viewer invitation, proved exact
create replay returned the same stable target, revoked it, proved exact revoke
replay, and verified cleanup. Invitation bearer material was not retained.
Meo pipeline `#313` deployed `3a78d580`; gateway pipeline `#25` deployed
`ae74e91`.

## Phase 3 — Placement, helpers, messaging

- [ ] Placement requests + responses (create, confirm, reject, finalize — semantic bundles)
- [ ] Helper profiles (public browse + own profile manage)
- [ ] Messaging (`/api/msg/*`: chats, send, unread)
- [ ] Treat messaging and placement as high-impact: require explicit targets,
      idempotency where applicable, read/preview before write, and post-write verification;
      tool-description confirmation language is not an enforcement mechanism
- [ ] Scopes + Meo abilities + tests + development-endpoint smoke

## Phase 4 — Groups, finance, notifications, profile

- [ ] Groups + invitations
- [ ] Finance/ledgers: ship read summaries first; put mutations in a separately
      reviewed milestone with narrow scopes and audit-friendly semantics
- [ ] Notifications inbox + mark read / actions
- [ ] User profile (me, safe settings; no password change via MCP unless explicitly required)
- [ ] Resource invitations as needed for share flows
- [ ] Scopes + Meo abilities + tests + development-endpoint smoke
- [ ] Coverage checklist against OpenAPI tags: every in-scope domain has at least
      agent-useful read coverage; writes where product wants agent action

## Meo-side work (coordinate in meo-mai-moi)

When scopes expand beyond `pets:read`:

- [x] MCP connector allowlist / ability grants for new scopes
- [x] Consent UI (`/mcp-connect`) copy lists new scopes clearly
- [x] Exchange issues Sanctum tokens with matching abilities
- [x] Docs in meo-mai-moi if API integration contract changes

## Definition of done

- Every in-scope domain has documented MCP tools (catalog in `docs/` — see
  `todo/02-documentation.md`)
- Scopes and Meo abilities match tool annotations (`readOnlyHint` / writes)
- Tests cover auth gate + representative success/failure per domain
- Live `list_pets`-class smoke still passes on the development endpoint after each phase

## Notes

- Prefer porting semantics from meo-gpt-connector before inventing new shapes.
- Product domain knowledge for *how to care for pets* lives in `meo-mai-moi-skill`;
  this plan is only about exposing APIs through MCP tools.
- Development write-safety gates live in this plan; production-specific review and
  cutover live in `todo/04-prod-and-hardening.md`.
