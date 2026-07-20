# Connect an MCP client

## What you need

- The environment's public base URL, written below as `<MCP_BASE_URL>`.
- A Meo account that satisfies that environment's consent policy. Development
  currently requires a verified, non-banned, eligible account.
- An MCP client supporting remote Streamable HTTP and OAuth.

Do not configure a bearer token manually. Point the client at
`<MCP_BASE_URL>/mcp`; OAuth discovery supplies the authorization server and the
currently advertised `pets:read` and `health:read` scopes.

## Generic flow

1. Add a remote **Streamable HTTP** server named `meo-mai-moi` with URL
   `<MCP_BASE_URL>/mcp`.
2. Choose **Authenticate**, **Connect**, or the client's equivalent OAuth action.
3. Sign in to Meo, review the client name and scopes, and approve or deny.
4. Return to the client. It should initialize the `Meo Mai Moi` server and
   discover the read tools in [tools.md](tools.md).
5. Call a tool covered by the approved scopes. For example, `list_pets` with
   an empty input returns a top-level `pets` array.

Clients may display a local authentication helper or connection control next to
the server's tools. Such helpers belong to the client; they are not MCP tools
defined by this repository. The gateway's canonical tool list is
[tools.md](tools.md).

## Agent instruction layers

These neighboring instruction surfaces have different jobs:

- [`AGENTS.md`](../AGENTS.md) contains always-on engineering rules for this
  gateway repository: authority boundaries, branch policy, validation, and
  documentation hygiene.
- [`.agents/skills/meo-mcp/SKILL.md`](../.agents/skills/meo-mcp/SKILL.md) is the
  reusable, opt-in workflow for connecting, operating, and extending the
  gateway across supported agent clients.
- The sibling `meo-mai-moi-skill` teaches agents Meo product-domain workflows.
  Product knowledge stays there instead of being copied into this gateway's
  engineering skill or documentation.

## Codex CLI, app, and IDE extension

Codex clients on the same host share MCP configuration. Add and authenticate the
remote server from the CLI:

```bash
codex mcp add meo-mai-moi --url <MCP_BASE_URL>/mcp
codex mcp login meo-mai-moi --scopes pets:read
codex mcp list
```

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
