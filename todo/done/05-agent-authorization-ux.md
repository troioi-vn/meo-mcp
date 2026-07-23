# Agent authorization and OpenClaw UX

Status: done

## Goal

Make the public Meo Mai Moi MCP skill lead an agent from a plain-language
connection request to a usable, newly projected MCP tool surface. Make scope
selection convenient without silently granting maximum authority, and make the
headless OpenClaw OAuth handoff tolerant of the callback forms humans actually
paste.

The canonical end-user skill remains in the separate public `meo-mcp-skill`
repository. The skill under this repository is the maintainer/developer skill
and must not absorb duplicated end-user product guidance.

## Product decisions

- An explicit narrow task still uses only the scopes it needs.
- A broad or unqualified request such as “connect Meo Mai Moi” defaults to the
  **Everyday care** preset:
  `pets:read pets:write health:read health:write habits:read habits:write microchips:read microchips:write`.
- **Full management** is available only after explicit user selection and grants
  all 26 current scopes:
  `pets:read health:read habits:read microchips:read pets:write health:write habits:write microchips:write sharing:read sharing:write placement:read placement:write helpers:read helpers:write messages:read messages:write groups:read groups:write finance:read finance:write notifications:read notifications:write profile:read profile:write invitations:read invitations:write`.
- The Full management choice must say plainly that it permits sensitive reads
  and writes across finances, messages, sharing, placement, groups, profile, and
  invitations. It is never selected by inference.
- Scope upgrades remain task-driven. Reauthorization asks only for the missing
  domain scopes unless the user explicitly changes preset.

## Work items

### Public skill

- [x] Re-read the current `meo-mcp-skill` repository instructions and the
      environment's `skill-creator` instructions before editing
- [x] Update the canonical public `meo-mai-moi-mcp/SKILL.md` and its connection
      reference with the two named presets and selection rules above
- [x] Keep the main skill concise; put client-specific commands and scope tables
      in references loaded only when relevant
- [x] Teach the agent to distinguish configuration, OAuth success, MCP probe
      success, and native tool projection instead of treating them as one state
- [x] Do not duplicate pet-domain operating knowledge from the separate
      `meo-mai-moi-skill`

### OpenClaw connection lifecycle

- [x] Correct the documented flow: configure the server, complete OAuth, run a
      harmless probe, then instruct the user to start a new OpenClaw session with
      `/new` (or `/reset`) before requesting the first Meo operation
- [x] Explain that `openclaw mcp reload` refreshes the CLI/runtime configuration
      but does not retrofit native MCP tools into an already-created Codex thread
- [x] Use `openclaw mcp probe` as the configuration/authentication check; do not
      use an unrelated or empty `tool_search` result as proof that Meo tools are
      missing from the server
- [x] Document the Codex-backed OpenClaw MCP namespace behavior only as far as
      needed for recovery; avoid coupling the skill to private implementation
      details
- [x] After reset, verify a native read-only call such as `list_pets` before
      claiming the connection is usable

### Headless OAuth handoff

- [x] In a private one-to-one channel, accept a bare authorization code, a
      `code&state=...` tail, or a full localhost callback URL
- [x] Parse only the `code` parameter client-side, reject an empty or unbounded
      value, exchange it immediately as a one-time credential, and never echo or
      log the code/callback
- [x] Continue to prefer a local browser callback when available; never ask for
      access tokens, refresh tokens, client secrets, or stored OAuth files in chat
- [x] Make errors state the recovery action: expired device/code flow means start
      a new authorization; projection failure after successful probe means reset
      the agent session rather than authorize again

### Documentation and publication

- [x] Align public connection/client documentation in this repository with the
      skill without turning it into an OpenClaw manual
- [x] Update skill version and changelog/release metadata using the public skill
      repository's established convention
- [x] Validate the skill with `skill-creator` tooling and inspect all public files
      for credentials or private infrastructure values
- [x] Publish the updated skill through its normal GitHub and ClawHub release
      workflows, preserving the existing package identity

## Acceptance tests

- Fresh Codex and Cursor sessions can connect using a narrow explicit scope and
  call `list_pets` after OAuth.
- A fresh OpenClaw profile given only “connect Meo Mai Moi” offers/uses Everyday
  care, completes OAuth, probes successfully, directs the user to `/new`, and
  calls `list_pets` through the native projected MCP surface in the new session.
- Full management is never granted without an explicit user choice and its
  warning is visible before authorization.
- OpenClaw successfully handles each supported callback form without exposing it
  in logs or later agent output.
- Expired-code, insufficient-scope, failed-probe, and stale-session cases produce
  distinct, actionable recovery guidance.

## Definition of done

- The public skill is validated, released on GitHub and ClawHub, and discoverable
  under its existing name.
- Durable Meo client docs agree with the skill's presets and lifecycle.
- Fresh-client acceptance proves that “authorized” leads to callable tools after
  the documented session reset, with evidence recorded in the release notes.
- The plan is moved to `todo/done/` after durable facts have graduated to docs.

