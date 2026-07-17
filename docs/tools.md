# MCP tool catalog

This is the canonical capability matrix for `meo-mcp`. Update it in the same
change that adds or changes a tool, scope, delegated ability, upstream endpoint,
schema, annotation, error behavior, or risk classification.

The gateway exposes semantic workflow tools, not a one-to-one mirror of Meo's
REST API. Admin/Filament endpoints and internal connector endpoints are never
part of the end-user tool surface.

## Capability matrix

| Tool | Semantic intent | MCP scope | Sanctum ability | Upstream Meo endpoint | Mode | Risk |
|------|-----------------|-----------|------------------|-----------------------|------|------|
| `list_pets` | List the authenticated user's pets with basic profiles and photo URLs | `pets:read` | `read` | `GET /api/my-pets` | Read | Low; returns personal pet profile data |

No write scope or write tool is currently available.

## `list_pets`

Use when the user explicitly needs their pet list or when a later workflow must
resolve a stable pet ID. The gateway calls Meo once and returns only the fields
below; additive upstream fields do not cross the MCP contract automatically.

### Input

An empty object. There are no arguments.

```json
{}
```

### Success output

```json
{
  "pets": [
    {
      "id": 7,
      "name": "Dirty Nostril",
      "species": "Cat",
      "sex": "female",
      "age": 6,
      "photo_url": "https://example.test/miso.jpg"
    }
  ]
}
```

| Field | Type | Source/normalization |
|-------|------|----------------------|
| `pets` | array | Pets owned by the authenticated Meo user |
| `pets[].id` | integer or null | Stable Meo pet identifier |
| `pets[].name` | string or null | Meo pet name |
| `pets[].species` | string or null | `pet_type.name`, falling back to upstream `species` |
| `pets[].sex` | string or null | Upstream sex value |
| `pets[].age` | integer or null | Upstream age, or derived from an ISO birthday when age is absent |
| `pets[].photo_url` | string or null | Upstream primary photo URL |

The same object is returned in MCP `structuredContent`; JSON text content is
also included for compatible older clients.

### Annotation and enforcement

| Annotation | Value |
|------------|-------|
| `readOnlyHint` | `true` |

The annotation helps clients classify the tool. It does not enforce access.
Enforcement is the `pets:read` MCP scope, the delegated `read` Sanctum ability,
and Meo's ownership query.

### Errors

The tool can return `scope_required`, `authorization_inactive`, or any of the
documented `upstream_*` codes. See [errors.md](errors.md) for fields and recovery
behavior. It never forwards an upstream error body.

## Required catalog entry for future tools

Every new tool row and detail section must state:

1. semantic intent and when an agent should use it;
2. MCP scope and exact delegated Sanctum ability;
3. every upstream endpoint it calls;
4. stable input and output schemas, including nullability;
5. MCP annotations and whether the operation reads or writes;
6. structured error codes and recovery behavior;
7. risk level and personal/sensitive data returned;
8. for writes, explicit target identity, idempotency or duplicate handling,
   concurrency behavior, preview/read-before-write requirements, and post-write
   verification.

Confirmation language in a tool description is guidance only. High-impact
write safety must be implemented in scopes, upstream authorization, schemas,
idempotency/concurrency controls, and the tool workflow itself.
