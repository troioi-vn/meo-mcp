# Connect an MCP client

## What you need

- The environment's public base URL, written below as `<MCP_BASE_URL>`.
- A verified, non-banned Meo account.
- An MCP client supporting remote Streamable HTTP and OAuth.

Do not configure a bearer token manually. Point the client at
`<MCP_BASE_URL>/mcp`; OAuth discovery supplies the authorization server and the
currently advertised narrow read and write scopes.

## Generic flow

1. Add a remote **Streamable HTTP** server named `meo-mai-moi` with URL
   `<MCP_BASE_URL>/mcp`.
2. Choose **Authenticate**, **Connect**, or the client's equivalent OAuth action.
3. Sign in to Meo, review the client name and scopes, and approve or deny.
4. Return to the client. It should initialize the `Meo Mai Moi` server and
   discover the tools in [tools.md](tools.md).
5. Call a tool covered by the approved scopes. For example, `list_pets` with
   an empty input returns a top-level `pets` array.

Clients may display a local authentication helper or connection control next to
the server's tools. Such helpers belong to the client; they are not MCP tools
defined by this repository. The gateway's canonical tool list is
[tools.md](tools.md).

## Agent instruction layers

These neighboring instruction surfaces have different jobs:

- The public [Meo Mai Moi MCP skill](https://github.com/troioi-vn/meo-mcp-skill)
  is the opt-in, consumer-facing workflow for connecting and using this OAuth
  gateway across SKILL.md-compatible agents.
- The [Meo Mai Moi REST API skill](https://github.com/troioi-vn/meo-mai-moi-skill)
  is a separate direct-API/PAT integration path. Do not substitute a personal
  API token for MCP OAuth.
- [`AGENTS.md`](../AGENTS.md) and the in-repository
  [gateway skill](../.agents/skills/meo-mcp/SKILL.md) are maintainer-facing
  engineering guidance, not installation instructions for end users.

## Scope presets

Scope selection is task-driven. Prefer the narrowest grant that covers the
intended work:

- **Narrow task**: request only that domain's read or read/write pair.
- **Everyday care** (default for an unqualified “connect Meo Mai Moi” /
  “manage my pets” request):
  `pets:read pets:write health:read health:write habits:read habits:write microchips:read microchips:write`.
- **Full management**: all currently advertised scopes. Use only after an
  explicit user choice, and warn first that it permits sensitive reads and
  writes across finances, messages, sharing, placement, groups, profile, and
  invitations. Never select it by inference.

Scope upgrades remain additive by missing domain unless the user changes
preset. The public [Meo Mai Moi MCP skill](https://github.com/troioi-vn/meo-mcp-skill)
carries the agent-facing selection and recovery wording.

## Codex CLI, app, and IDE extension

Codex clients on the same host share MCP configuration. Add and authenticate the
remote server from the CLI:

```bash
codex mcp add meo-mai-moi --url <MCP_BASE_URL>/mcp
codex mcp login meo-mai-moi --scopes pets:read,health:read
codex mcp list
```

Request only `pets:read` when the client needs pet profiles but not health
history. For a broad connect request, use the Everyday care scope set above.
OAuth accepts either narrow scope or a documented combination, and each tool
still enforces its own required scope.

Placement, helper-profile, and messaging inspection use independent
`placement:read`, `helpers:read`, and `messages:read` scopes. Message reads can
contain private correspondence but do not update read receipts. Request only
the domains the client needs.

Keep the read-only command above for ordinary inspection. Request
`pets:write` together with `pets:read`, or `health:write` together with
`health:read`, only for an intended write workflow. Habits similarly pair
`habits:read,habits:write`, and microchips pair
`microchips:read,microchips:write`; pet-photo workflows use the pet pair. Write
tools require stable IDs, idempotency keys, and—for updates, lifecycle actions,
and deletes—the version returned by the matching read tool.

Pet sharing pairs `sharing:read,sharing:write`. These high-impact tools require
fresh sharing or invitation state plus exact expected pet, role, user, or
relationship targets. Invitation preview/accept/decline accepts either the
64-character token or the exact Meo HTTPS invitation URL; clients must treat
both as credentials and must not log or paste them into conversation history.

Phase 3 writes pair each independent write scope with its matching read scope:
`placement:read,placement:write`, `helpers:read,helpers:write`, or
`messages:read,messages:write`. Opening a placement chat additionally requires
`placement:read`. These high-impact tools require explicit stable targets,
fresh expected names or status where applicable, versions for existing
resources, unique idempotency keys, and post-write verification.

Alternatively, open **Settings → MCP servers**, add a Streamable HTTP server,
then select **Authenticate** and restart the app or IDE extension when prompted.
In the terminal UI, `/mcp` shows configured servers and tools. See OpenAI's
[current MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).

## Cursor

Add a remote server through Cursor's MCP settings, or use a project
`.cursor/mcp.json` / global `~/.cursor/mcp.json` entry:

```json
{
  "mcpServers": {
    "meo-mai-moi": {
      "url": "<MCP_BASE_URL>/mcp"
    }
  }
}
```

Reload Cursor if requested, then use its authentication action for the server.
Cursor supports OAuth for remote Streamable HTTP servers; consult its
[MCP documentation](https://docs.cursor.com/context/model-context-protocol) if
the settings labels have changed.

## OpenClaw

Current OpenClaw releases have a native MCP registry and OAuth client. The
public [Meo Mai Moi MCP skill](https://github.com/troioi-vn/meo-mcp-skill)
instructs an OpenClaw agent with execution access to perform this setup itself
after the user explicitly asks it to connect or authorize Meo.

Treat readiness as four distinct states: configured server entry, OAuth
success, MCP probe success, and native tool projection in the current session.
Do not collapse them.

For manual setup, save the unauthenticated server first (Everyday care by
default), then start OAuth:

```bash
openclaw mcp add meo-mai-moi \
  --url <MCP_BASE_URL>/mcp \
  --transport streamable-http \
  --auth oauth \
  --oauth-scope 'pets:read pets:write health:read health:write habits:read habits:write microchips:read microchips:write' \
  --no-probe
openclaw mcp login meo-mai-moi
```

That Everyday care grant covers pet profiles, health, habits, and microchips.
The consent screen remains the final approval boundary. For a named narrower
task, replace it with only the relevant read/write pair. Full management
requires an explicit choice and the sensitivity warning above.

OpenClaw's headless OAuth flow prints an authorization URL and then accepts a
short-lived code with `openclaw mcp login meo-mai-moi --code <code>`. Prefer a
local browser callback when available. In a private one-to-one channel, a human
may paste a bare code, a `code&state=...` tail, or a full localhost callback
URL; extract only the `code` parameter before exchange. Treat those values as
temporary credentials: exchange immediately, never echo or log them, and never
use them in groups, issues, or screenshots. Use a local shell when the
conversation is not private. Never ask for access tokens, refresh tokens,
client secrets, or stored OAuth files.

Verify configuration, then start a fresh agent session before the first Meo
call:

```bash
openclaw mcp status --verbose
openclaw mcp probe meo-mai-moi
openclaw mcp reload
```

`openclaw mcp probe` is the configuration and authentication check. `openclaw
mcp reload` refreshes CLI/runtime configuration but does not retrofit native
MCP tools into an already-created agent thread—ask the user for `/new` or
`/reset`, then confirm with a native `list_pets` call. An empty or unrelated
`tool_search` result is not proof that the Meo server lacks tools. If a later
call reports `insufficient_scope`, add only the missing domain's read/write
pair and repeat OAuth. Expired-code cases need a new login; projection failure
after a successful probe needs a session reset, not another authorization. See
OpenClaw's [native MCP documentation](https://docs.openclaw.ai/cli/mcp) for
current command details.

## MCP Inspector

Start the official Inspector UI:

```bash
npx -y @modelcontextprotocol/inspector
```

In the browser UI:

1. Select **Streamable HTTP** and enter `<MCP_BASE_URL>/mcp`.
2. Open **Authentication** and choose **Quick OAuth Flow**.
3. Complete Meo consent, return to the connection screen, and connect.
4. Open **Tools**, list tools, select `list_pets`, and run it.

Keep the Inspector proxy bound to localhost and leave its session-token
authentication enabled. See the official
[MCP Inspector repository](https://github.com/modelcontextprotocol/inspector).

## Public checks without credentials

These calls contain no secrets:

```bash
curl -fsS <MCP_BASE_URL>/health
curl -fsS <MCP_BASE_URL>/.well-known/oauth-protected-resource/mcp
curl -fsS <MCP_BASE_URL>/.well-known/oauth-authorization-server
```

Expected invariants are `{"status":"ok"}`, resource metadata naming
`<MCP_BASE_URL>/mcp`, and authorization metadata advertising `S256` plus only
the scopes currently listed in [tools.md](tools.md).

## Troubleshooting

| Symptom | Meaning / next action |
|---------|-----------------------|
| Initial `401 invalid_token` | Normal discovery trigger; start the client's OAuth action |
| Consent says the account is ineligible | Use an account authorized for that environment; operators manage live policy privately |
| Redirect or PKCE error | Remove stale registration/auth state and reconnect with a current OAuth-capable client |
| `authorization_inactive` or upstream `401` | Reconnect to create a new delegated grant |
| `upstream_rate_limited` / retryable `5xx` | Back off and retry later |
| Tools do not refresh after a release | Restart/reload the client and run tool discovery again |
| OpenClaw probe OK but tools missing in chat | Start a new session with `/new` or `/reset`; do not reauthorize |
| OpenClaw expired authorization code | Start a new `mcp login`; never reuse the old code |

Never paste access tokens, refresh tokens, authorization URLs, callback query
strings, or full debug headers into issues or logs.
