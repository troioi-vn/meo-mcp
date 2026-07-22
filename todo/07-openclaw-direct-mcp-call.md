# Upstream OpenClaw direct MCP tool call

Status: upstream PR open

## Goal

Contribute a generic, scriptable OpenClaw CLI escape hatch for invoking one
configured MCP tool. This is an operator/developer diagnostic path, not a Meo-
specific workaround and not a replacement for native tool projection in agent
sessions.

Target an upstream pull request. Upstream review may proceed independently and
must not block Meo releases.

## Upstream links

- Issue: https://github.com/openclaw/openclaw/issues/112761
- PR: https://github.com/openclaw/openclaw/pull/112765
- Branch (fork): `troioi-vn/openclaw` `feat/mcp-call-cli`

## Proposed interface

```text
openclaw mcp call <server> <tool> [--input <json-object> | --input-file <path-or->]
```

- Omitted input means `{}`; `--input-file -` reads one JSON object from stdin.
- Emit the MCP result as JSON on stdout and diagnostics on stderr so the command
  is safely scriptable.
- Return the upstream project's standard non-zero failure status for invalid
  input, unknown/disabled server or tool, missing/expired authorization,
  transport failure, timeout, policy denial, and MCP tool error.
- Never accept bearer/refresh tokens or client secrets as command-line options.

## Work items

### Upstream grounding and design

- [x] Locate the canonical OpenClaw source and read its contribution, CLI,
      testing, MCP runtime, credential-store, tool-filter, and approval-policy
      instructions completely
- [x] Search for an existing equivalent or pending proposal before opening work;
      join it if it already satisfies this contract
- [x] Open a concise design issue when required by upstream policy, linking the
      real projection/debugging use case without including private account data
- [x] Keep command naming and help formatting consistent with the existing
      `openclaw mcp` command group; request upstream feedback only if the project
      has a conflicting established convention

### Implementation

- [x] Reuse the same configured MCP runtime, OAuth credential store, refresh
      behavior, server enablement, tool filtering, approval gates, timeouts, and
      redaction path used by normal OpenClaw MCP sessions
- [x] Resolve the configured server and discover the named tool before calling;
      reject ambiguous, filtered, or unavailable tools with actionable errors
- [x] Parse exactly one JSON object from `--input`, a file, or stdin; bound input
      size and reject arrays, scalars, trailing data, and conflicting input flags
- [x] Preserve structured MCP success content and structured tool errors rather
      than flattening them into prose
- [x] Ensure Ctrl-C, timeout, and transport failures close the MCP session and do
      not corrupt or print stored OAuth state
- [x] Add CLI help and operator documentation that position `call` beside
      `probe`: probe diagnoses connection/catalog state; call verifies one tool

### Upstream delivery

- [x] Add focused tests using upstream fixtures rather than real credentials
- [x] Run the upstream documented lint, type, unit, CLI integration, and package
      checks
- [x] Commit on a dedicated contribution branch, push only to an authorized fork,
      and open an upstream pull request with interface, security, and test notes
- [ ] Address review without weakening credential handling, filters, or approval
      enforcement; record the issue/PR link in this plan
- [x] Do not vendor an unmerged OpenClaw patch into Meo repositories

## Test cases

- No-input read tool receives `{}` and returns machine-readable JSON.
- Inline JSON, file JSON, and stdin JSON produce equivalent requests.
- Invalid/oversized/non-object input and conflicting flags fail before network
  activity and never echo credential material.
- Unknown or disabled server, unknown/filtered tool, and policy denial fail
  without invocation.
- Missing authorization gives a login/reconnect action; expired authorization
  follows the existing refresh or reauthorization policy.
- Structured MCP tool errors, transport failures, and timeouts remain
  distinguishable and close resources.
- Existing `probe`, OAuth, native agent projection, and tool-policy tests remain
  green.
- Optional live acceptance uses an isolated OpenClaw profile and a harmless Meo
  `list_pets {}` call; retain only result shape/count and no personal pet data.

## Definition of done

- A tested upstream pull request implements the generic command and passes the
  maintainer's CI/review requirements.
- The merged/released OpenClaw version is recorded if upstream accepts it; an
  open review does not block or alter Meo releases.
- Once generally available, the public Meo skill may mention the command as an
  optional diagnostic path with an explicit minimum OpenClaw version.
- This plan is archived when the contribution is merged/released, or updated
  with the durable upstream disposition if maintainers choose a different
  equivalent solution.
