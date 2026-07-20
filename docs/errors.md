# Error contracts

Errors are structured at three different boundaries. Callers should branch on
the stable code, not on human-readable text.

## Request-guard errors

Gateway middleware rejects malformed or unsafe HTTP requests with this shape:

```json
{
  "error": {
    "code": "invalid_origin",
    "message": "The request Origin is not allowed.",
    "request_id": "<request-id>"
  }
}
```

Every response also carries `X-Request-ID`.

| HTTP status | Code | Meaning |
|-------------|------|---------|
| `400` | `invalid_content_length` | `Content-Length` is not an integer |
| `403` | `invalid_origin` | Browser `Origin` is not allowlisted |
| `413` | `request_too_large` | Declared or actual body exceeds 1 MiB |
| `421` | `invalid_host` | Request host does not match the configured public host |

## OAuth and bearer errors

OAuth protocol endpoints use standard top-level fields:

```json
{
  "error": "invalid_target",
  "error_description": "The resource parameter must name this MCP endpoint."
}
```

Representative codes include `invalid_request`, `invalid_redirect_uri`,
`invalid_scope`, `invalid_target`, `invalid_grant`, `access_denied`, and
`server_error`. Token endpoint errors include `Cache-Control: no-store` and
`Pragma: no-cache` where the gateway handles the response directly.

An MCP request without a usable bearer token receives `401` with an
`invalid_token` response and a `WWW-Authenticate` header pointing to protected
resource metadata. Clients should follow discovery and OAuth rather than ask a
user to paste tokens.

The browser callback deliberately returns only:

```json
{"error":"authorization_failed"}
```

when completion fails. Detailed exception values are not exposed.

## MCP tool errors

A tool-level failure is still a successful JSON-RPC/HTTP exchange. The MCP
result has `isError: true`; its text content is a JSON serialization of the
error, and `structuredContent.error` contains the same object:

```json
{
  "code": "upstream_rate_limited",
  "message": "Meo Mai Moi is rate-limiting requests. Try again shortly.",
  "retryable": true,
  "upstream_status": 429
}
```

Stable fields:

| Field | Type | Meaning |
|-------|------|---------|
| `code` | string | Machine-readable gateway code |
| `message` | string | Safe user-facing explanation; wording may improve over time |
| `retryable` | boolean | Whether retrying later may succeed without reconnecting or changing input |
| `upstream_status` | integer, optional | Meo HTTP status when one was received |

Current tool error codes:

| Code | Retryable | Upstream status | Client behavior |
|------|-----------|-----------------|-----------------|
| `scope_required` | no | — | Reauthorize with the tool's required scope |
| `authorization_inactive` | no | — | Reconnect the Meo account |
| `validation_error` | no | — | Correct the tool input before retrying |
| `duplicate_candidate` | no | `409` | Inspect the existing stable pet IDs; create only if this is a distinct pet intent |
| `idempotency_conflict` | no | `409` | Use the original payload or a new key for a genuinely new intent |
| `idempotency_in_progress` | yes | `425` | Retry later with the same key and payload |
| `concurrency_conflict` | no | `409` or — | Re-read the explicit target and reconcile before updating |
| `post_write_verification_failed` | yes | — | The write may have succeeded; read the stable target before any retry |
| `upstream_unavailable` | yes | — | Retry later; no HTTP response was received |
| `upstream_unauthorized` | no | `401` | Reconnect; delegated authorization was rejected |
| `upstream_forbidden` | no | `403` | Stop or change the request; Meo denied access |
| `upstream_not_found` | no | `404` | Refresh/read targets before retrying |
| `upstream_validation_failed` | no | `422` | Correct the normalized request; upstream field text is withheld |
| `upstream_rate_limited` | yes | `429` | Back off before retrying |
| `upstream_server_error` | yes | `5xx` | Retry later |
| `upstream_unexpected` | no | other non-`200` | Do not blind-retry; report with request context |
| `upstream_malformed` | yes | `200` | Retry later or report a contract mismatch |

Upstream response bodies are not forwarded. New tools should reuse a code when
the recovery action is identical and add a documented code when callers need a
different branch.
