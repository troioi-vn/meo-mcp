# MCP tool catalog

This is the canonical capability matrix for `meo-mcp`. Update it in the same
change that adds or changes a tool, scope, delegated ability, upstream endpoint,
schema, annotation, error behavior, or risk classification.

The gateway exposes semantic workflow tools, not a one-to-one mirror of Meo's
REST API. Admin/Filament endpoints and internal connector endpoints are never
part of the end-user tool surface.

## Lifecycle

- **Live** means implemented and accepted on the development MCP endpoint.

## Capability matrix

| Tool | Lifecycle | Semantic intent | MCP scope | Sanctum ability | Upstream Meo endpoint(s) | Mode | Risk |
|------|-----------|-----------------|-----------|------------------|--------------------------|------|------|
| `list_pets` | Live | List the authenticated user's pets with basic profiles and photo URLs | `pets:read` | `pets:read` (legacy PAT: `read`) | `GET /api/my-pets` | Read | Low; personal pet profiles |
| `find_pets` | Live | Resolve a partial name and/or species to stable pet IDs before targeted work | `pets:read` | `pets:read` (legacy PAT: `read`) | `GET /api/my-pets` | Read | Low; personal pet profiles |
| `get_pet` | Live | Retrieve a narrowed full profile for one explicit pet ID | `pets:read` | `pets:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}` | Read | Low; personal pet profile/location context |
| `get_pets_overview` | Live | Compare pets with birthday context, active vaccinations, and recent weights | `pets:read` + `health:read` | `pets:read` + `health:read` (legacy PAT: `read`) | `GET /api/my-pets`; per pet: `GET /api/pets/{pet_id}/vaccinations`, `GET /api/pets/{pet_id}/weights` | Read/aggregate | Moderate; combines personal and health data |
| `list_pet_types` | Live | List supported species and pet-care capability flags | `pets:read` | none; endpoint is public | `GET /api/pet-types` | Read | Low; public reference data |
| `list_weights` | Live | List one pet's paginated weight history | `health:read` | `health:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/weights` | Read | Moderate; pet health history |
| `get_weight` | Live | Retrieve one explicit weight record | `health:read` | `health:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/weights/{weight_id}` | Read | Moderate; pet health data |
| `list_vaccinations` | Live | List one pet's paginated vaccination records, optionally by lifecycle status | `health:read` | `health:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/vaccinations` | Read | Moderate; pet medical history |
| `get_vaccination` | Live | Retrieve one explicit vaccination record | `health:read` | `health:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/vaccinations/{vaccination_id}` | Read | Moderate; pet medical data |
| `list_medical_records` | Live | List one pet's paginated medical records, optionally by record type | `health:read` | `health:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/medical-records` | Read | Moderate; sensitive pet medical history |
| `get_medical_record` | Live | Retrieve one explicit medical record | `health:read` | `health:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/medical-records/{record_id}` | Read | Moderate; sensitive pet medical data |
| `create_pet` | Proposed (Phase 1B) | Create a pet profile with an authoritative exact-name/species duplicate guard | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `create`) | `GET /api/pet-types`; `POST /api/pets`; `GET /api/pets/{pet_id}` | Create | Moderate; creates a durable personal profile |
| `update_pet` | Proposed (Phase 1B) | Correct selected profile fields for one explicit pet and version | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}`; `GET /api/pet-types` when species changes; `PUT /api/pets/{pet_id}`; verification `GET` | Update | Moderate; overwrites profile fields |
| `add_weight` | Proposed (Phase 1B) | Record one dated weight for an explicit pet | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/weights`; `GET /api/pets/{pet_id}/weights/{weight_id}` | Create | Moderate; creates pet health data |
| `update_weight` | Proposed (Phase 1B) | Correct one explicit weight record at a known version | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/weights/{weight_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites pet health data |
| `add_vaccination` | Proposed (Phase 1B) | Record one vaccination for an explicit pet | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/vaccinations`; `GET /api/pets/{pet_id}/vaccinations/{vaccination_id}` | Create | Moderate; creates pet medical data |
| `update_vaccination` | Proposed (Phase 1B) | Correct one explicit vaccination at a known version | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/vaccinations/{vaccination_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites pet medical data |
| `add_medical_record` | Proposed (Phase 1B) | Record one dated medical event for an explicit pet | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/medical-records`; `GET /api/pets/{pet_id}/medical-records/{record_id}` | Create | Moderate; creates sensitive medical data |
| `update_medical_record` | Proposed (Phase 1B) | Correct one explicit medical record at a known version | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/medical-records/{record_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites sensitive medical data |

The Proposed rows define the Phase 1B contract before implementation. They do
not become discoverable until the coordinated Meo ability and consent changes,
gateway implementation, tests, deployment, and live acceptance are complete.

## Scope model

| MCP scope | Consent meaning | MCP-issued Sanctum ability | Tools |
|-----------|-----------------|-----------------------------|-------|
| `pets:read` | View the user's pet profiles and public pet-type reference data | `pets:read` | Pet list/find/detail; pet types; overview |
| `health:read` | View weights, vaccinations, and medical records for pets the user may access | `health:read` | Health lists/details; overview |
| `pets:write` | Create and edit pet profiles the user may manage | `pet:write` | Pet create/update; always paired with `pets:read` by these tools |
| `health:write` | Add and edit weight, vaccination, and medical records for pets the user may manage | `health:write` | Health create/update; always paired with `health:read` by these tools |

Scopes are independently requestable non-empty subsets. The default dynamic
registration scope set includes both so general clients can discover the whole
read surface. Every tool checks its own requirement. Meo endpoints accept the
domain ability on MCP-issued tokens while retaining the generic `read` ability
for existing user-created PATs.

## Shared annotations

All current read tools declare:

| Annotation | Value | Meaning |
|------------|-------|---------|
| `readOnlyHint` | `true` | The tool does not mutate Meo state |
| `destructiveHint` | `false` | The tool cannot delete or overwrite data |
| `idempotentHint` | `true` | Repeating the same read has no mutation side effect |
| `openWorldHint` | `true` | The result depends on the external Meo service and current user data |

Annotations help clients classify tools; enforcement comes from OAuth scope,
delegated Sanctum ability, explicit IDs, and Meo's resource authorization.

Phase 1B create tools declare `readOnlyHint: false`,
`destructiveHint: false`, `idempotentHint: true`, and `openWorldHint: true`.
Update tools differ only in `destructiveHint: true`, because they overwrite
existing fields. Their idempotency hint depends on the required stable
`idempotency_key`, not on a claim in the description.

## Shared schemas

### Pet summary

```json
{
  "id": 7,
  "name": "Miso",
  "species": "Cat",
  "sex": "female",
  "age": 6,
  "photo_url": "https://example.test/miso.jpg"
}
```

`id` is a positive integer. Other fields are nullable; `age` is a non-negative
integer derived from an ISO birthday only when Meo does not return an age.

### Pagination

Paginated health tools return:

```json
{
  "pagination": {
    "current_page": 1,
    "last_page": 1,
    "per_page": 25,
    "total": 1,
    "has_more": false
  }
}
```

The gateway omits upstream navigation URLs so internal/public routing details
do not become part of the MCP contract.

## Pet tools

### `list_pets`

- **Input:** `{}`.
- **Output:** `{ "pets": PetSummary[] }`.
- **Use:** only when the user asks for the whole list. Use `find_pets` to resolve
  a name for targeted work.

### `find_pets`

- **Input:** `name?: string`, `species?: string`; at least one non-blank filter
  is required. Name matching is case-insensitive partial matching with exact
  matches first; species is a case-insensitive exact match.
- **Output:** `{ "candidates": PetSummary[] }`.
- **Use:** resolve stable IDs. Never let fuzzy matching silently select a write
  target in a later phase.

### `get_pet`

- **Input:** `pet_id: integer >= 1`.
- **Output:** `{ "pet": PetDetail }`, where `PetDetail` contains only `id`,
  `name`, `species`, `sex`, `age`, `birthday`, `birthday_year`,
  `birthday_month`, `birthday_day`, `birthday_precision`, `country`, `state`,
  `city`, `description`, `status`, `photo_url`, and `version` (the upstream
  `updated_at` timestamp used for optimistic concurrency). It excludes relationships,
  placement responses, creator/user IDs, street address, and arbitrary
  additive upstream fields.

### `list_pet_types`

- **Input:** `{}`.
- **Output:** `{ "pet_types": [{ "id", "name", "slug",
  "placement_requests_allowed", "weight_tracking_allowed",
  "microchips_allowed" }] }`.
- **Use:** species lookup and capability-aware guidance; not an excuse to expose
  admin pet-type management.

### `get_pets_overview`

- **Input:** optional `name` and `species`; `only_with_upcoming_vaccination`
  boolean; `sort_by` enum `name | next_vaccination_due_at |
  next_birthday_at`; `sort_order` enum `asc | desc`.
- **Output:** `{ "pets": PetOverview[] }`. Each item extends `PetSummary` with
  `birthday_precision`, `birthday_year`, `birthday_month`, `birthday_day`,
  `next_birthday_at`, `days_until_next_birthday`, `active_vaccinations`, up to
  five `recent_weights`, `next_vaccination_due_at`,
  `next_vaccination_name`, `vaccination_data_status`, and
  `weights_data_status`.
- `active_vaccinations` contains only `id`, `vaccine_name`, `administered_at`,
  and `due_at`, ordered by due date. `recent_weights` contains the shared
  `Weight` shape, newest first. Birthday countdown fields are populated only
  for `birthday_precision: "day"`.
- **Partial failure:** a failed per-pet health subrequest produces an empty
  sublist plus `unavailable` for that domain; the overview remains useful. Pet
  list failure fails the whole call.

## Health tools

All health tools require explicit positive `pet_id`. Detail tools also require
the positive record ID, and Meo verifies that the record belongs to that pet.

### Weights

- `list_weights` input: `pet_id`, `page` (default `1`, minimum `1`).
- `list_weights` output: `{ "weights": Weight[], "pagination": Pagination }`.
- `get_weight` input: `pet_id`, `weight_id`.
- `get_weight` output: `{ "weight": Weight }`.
- `Weight`: `id`, `weight_kg` as a positive number, ISO `record_date`, and
  nullable ISO timestamp `version`.

### Vaccinations

- `list_vaccinations` input: `pet_id`, `page` (default `1`), and `status` enum
  `active | completed | all` (default `active`).
- `list_vaccinations` output:
  `{ "vaccinations": Vaccination[], "pagination": Pagination }`.
- `get_vaccination` input: `pet_id`, `vaccination_id`.
- `get_vaccination` output: `{ "vaccination": Vaccination }`.
- `Vaccination`: `id`, `vaccine_name`, ISO `administered_at`, nullable ISO
  `due_at`, nullable `notes`, nullable ISO timestamp `completed_at`, and
  nullable `photo_url`, and nullable ISO timestamp `version`.

### Medical records

- `list_medical_records` input: `pet_id`, `page` (default `1`), and optional
  non-blank `record_type`.
- `list_medical_records` output:
  `{ "medical_records": MedicalRecord[], "pagination": Pagination }`.
- `get_medical_record` input: `pet_id`, `record_id`.
- `get_medical_record` output: `{ "medical_record": MedicalRecord }`.
- `MedicalRecord`: `id`, `record_type`, nullable `description`, nullable ISO
  `record_date`, nullable `vet_name`, nullable ISO timestamp `version`, and
  `photos` narrowed to `id`, `url`, `thumb_url`, and `medium_url`.

## Phase 1B write tools

Every write requires an `idempotency_key` containing 1–128 ASCII letters,
digits, underscores, or hyphens. Repeating the same key with the same normalized
method, path, and payload replays Meo's stored successful response. Reusing it
for a different request returns `idempotency_conflict`; an in-flight duplicate
returns retryable `idempotency_in_progress`. Use a new key only for a genuinely
new user intent.

Every update also requires `base_version`, copied exactly from the target read
tool's `version`. The gateway reads the explicit target before writing, Meo
atomically rejects a stale version, and the gateway reads the resource back
after success. A stale version returns `concurrency_conflict`; callers must
re-read and reconcile rather than blind-retry. Creates are also read back by
the stable ID returned from Meo.

### Pet writes

- `create_pet` input: required `name`, exact supported `species`, two-letter
  `country`, and `idempotency_key`; optional `sex` (`male | female |
  not_specified | unknown`), exactly one of `birth_date`, `birth_month_year`,
  or `age_months`, optional `description`, and `allow_duplicate` defaulting to
  `false`.
- Before creating, the gateway resolves species through `list_pet_types`. Meo
  serializes MCP pet creates per user and performs the exact case-insensitive
  name/species check inside the create transaction. It returns
  `duplicate_candidate` with stable existing IDs unless `allow_duplicate` is
  explicitly true. Because Meo's idempotency middleware runs before that guard,
  an exact retry replays the original success instead of being mistaken for a
  new duplicate.
- `create_pet` output: `{ "pet": PetDetail, "verified": true }`.
- `update_pet` input: explicit positive `pet_id`, `base_version`,
  `idempotency_key`, and at least one of `name`, `species`, `sex`, one birth
  representation, or `description`. Fuzzy names are never accepted as targets.
- `update_pet` output: `{ "pet": PetDetail, "verified": true }`.

### Health writes

- `add_weight`: positive `pet_id`, positive `weight_kg` up to 1000, explicit
  ISO `record_date`, and `idempotency_key`. Meo permits one weight per pet/date;
  another key for the same date is a validation failure.
- `update_weight`: positive `pet_id` and `weight_id`, `base_version`,
  `idempotency_key`, and at least one of `weight_kg` or `record_date`.
- `add_vaccination`: positive `pet_id`, non-blank `vaccine_name`, ISO
  `administered_at`, optional ISO `due_at` and `notes`, plus `idempotency_key`.
  Meo rejects the same vaccine name/date for a pet.
- `update_vaccination`: positive `pet_id` and `vaccination_id`, `base_version`,
  `idempotency_key`, and at least one mutable vaccination field.
- `add_medical_record`: positive `pet_id`, `record_type` enum `checkup |
  deworming | flea_treatment | surgery | dental | other`, explicit ISO
  `record_date`, optional `description` and `vet_name`, plus
  `idempotency_key`. Different keys intentionally represent distinct events;
  there is no unsafe fuzzy deduplication of medical history.
- `update_medical_record`: positive `pet_id` and `record_id`, `base_version`,
  `idempotency_key`, and at least one mutable medical-record field.
- Health create/update outputs use the corresponding narrowed shared record
  under `weight`, `vaccination`, or `medical_record`, plus `verified: true`.

## Errors

Every tool can return `scope_required`, `authorization_inactive`, or the common
`upstream_*` codes in [errors.md](errors.md). Phase 1A also defines:

| Code | Retryable | Meaning |
|------|-----------|---------|
| `validation_error` | no | Locally validated input is missing, blank, out of range, or inconsistent |
| `upstream_validation_failed` | no | Meo rejected the normalized request with `422`; upstream field text is not forwarded |
| `duplicate_candidate` | no | Pet create found an exact existing name/species match; inspect stable IDs before deciding whether this is a distinct pet |
| `idempotency_conflict` | no | The idempotency key was reused for a different normalized write |
| `idempotency_in_progress` | yes | The same idempotent write is still being processed; retry later with the same key |
| `concurrency_conflict` | no | The supplied base version is stale; re-read and reconcile before another update |
| `post_write_verification_failed` | yes | Meo accepted the write but its stable target could not be read back safely |

Upstream `403` and `404` remain `upstream_forbidden` and
`upstream_not_found`. No upstream response body is forwarded.

## Required catalog entry for future tools

Every new tool row and detail section must state:

1. semantic intent and when an agent should use it;
2. lifecycle status, MCP scope, and exact delegated Sanctum ability;
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
