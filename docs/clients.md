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

## Codex CLI, app, and IDE extension

Codex clients on the same host share MCP configuration. Add and authenticate the
remote server from the CLI:

```bash
codex mcp add meo-mai-moi --url <MCP_BASE_URL>/mcp
codex mcp login meo-mai-moi --scopes pets:read,health:read
codex mcp list
```

Request only `pets:read` when the client needs pet profiles but not health
history. OAuth accepts either narrow scope or the documented combination, and
each tool still enforces its own required scope.

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

For manual setup, save the unauthenticated server first, then start OAuth:

```bash
openclaw mcp add meo-mai-moi \
  --url <MCP_BASE_URL>/mcp \
  --transport streamable-http \
  --auth oauth \
  --oauth-scope 'pets:read pets:write health:read health:write microchips:read microchips:write finance:read finance:write' \
  --no-probe
openclaw mcp login meo-mai-moi
```

That initial pet-management grant covers profile, health, microchip, and
finance reads and writes. It is intentionally broader than a read-only smoke
test and the consent screen remains the final approval boundary. For a named
narrower task, replace it with only the relevant read/write pair.

OpenClaw's headless OAuth flow prints an authorization URL and then accepts the
short-lived code from the final browser redirect with
`openclaw mcp login meo-mai-moi --code <code>`. A remote browser may fail to
load the loopback `localhost:8989` page; copy only the `code` value from its
address bar. Treat the URL and code as temporary credentials: use them only in
the same private one-to-one session, exchange the code immediately, and never
put either in groups, issues, screenshots, or logs. Use a local shell instead
when the conversation is not private.

Verify and activate the connection:

```bash
openclaw mcp status --verbose
openclaw mcp doctor meo-mai-moi --probe
openclaw mcp reload
```

The complete Meo tool catalog remains visible; each tool still enforces its
OAuth scope. A fresh agent message may be required after reload before the new
tools are projected into the model runtime. If a later call reports
`insufficient_scope`, add only the missing domain's read/write pair and repeat
OAuth. See OpenClaw's [native MCP documentation](https://docs.openclaw.ai/cli/mcp)
for current command details.

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

Never paste access tokens, refresh tokens, authorization URLs, callback query
strings, or full debug headers into issues or logs.
