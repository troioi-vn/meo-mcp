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
| `create_pet` | Live | Create a pet profile with an authoritative exact-name/species duplicate guard | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `create`) | `GET /api/pet-types`; `POST /api/pets`; `GET /api/pets/{pet_id}` | Create | Moderate; creates a durable personal profile |
| `update_pet` | Live | Correct selected profile fields for one explicit pet and version | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}`; `GET /api/pet-types` when species changes; `PUT /api/pets/{pet_id}`; verification `GET` | Update | Moderate; overwrites profile fields |
| `add_weight` | Live | Record one dated weight for an explicit pet | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/weights`; `GET /api/pets/{pet_id}/weights/{weight_id}` | Create | Moderate; creates pet health data |
| `update_weight` | Live | Correct one explicit weight record at a known version | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/weights/{weight_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites pet health data |
| `add_vaccination` | Live | Record one vaccination for an explicit pet | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/vaccinations`; `GET /api/pets/{pet_id}/vaccinations/{vaccination_id}` | Create | Moderate; creates pet medical data |
| `update_vaccination` | Live | Correct one explicit vaccination at a known version | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/vaccinations/{vaccination_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites pet medical data |
| `add_medical_record` | Live | Record one dated medical event for an explicit pet | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/medical-records`; `GET /api/pets/{pet_id}/medical-records/{record_id}` | Create | Moderate; creates sensitive medical data |
| `update_medical_record` | Live | Correct one explicit medical record at a known version | `health:read` + `health:write` | `health:read` + `health:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/medical-records/{record_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites sensitive medical data |
| `list_habits` | Proposed (Phase 2A) | List habit trackers visible to the user | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits` | Read | Moderate; pet routines and reminder settings |
| `get_habit` | Proposed (Phase 2A) | Retrieve one explicit habit and its editable version | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits/{habit_id}` | Read | Moderate; pet routines and reminder settings |
| `get_habit_heatmap` | Proposed (Phase 2A) | Summarize a bounded date range of habit completion/intensity | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits/{habit_id}/heatmap` | Read | Moderate; longitudinal care routine data |
| `get_habit_day_entries` | Proposed (Phase 2A) | Read per-pet values for one explicit habit date | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits/{habit_id}/entries/{date}` | Read | Moderate; per-pet routine data |
| `create_habit` | Proposed (Phase 2A) | Create a tracker for explicit owned pet IDs | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `create`) | `POST /api/habits`; verification `GET /api/habits/{habit_id}` | Create | Moderate; creates reminders and routine tracking |
| `update_habit` | Proposed (Phase 2A) | Update one explicit habit at a known version | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites tracker configuration |
| `save_habit_day_entries` | Proposed (Phase 2A) | Upsert or clear explicit per-pet values on one habit date | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}/entries/{date}`; `PUT` same path; verification `GET` | Upsert | Moderate; overwrites daily care tracking |
| `archive_habit` | Proposed (Phase 2A) | Hide one explicit habit without deleting its history | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}`; `POST /api/habits/{habit_id}/archive`; verification `GET` | Update | Moderate; disables an active tracker |
| `restore_habit` | Proposed (Phase 2A) | Restore one explicit archived habit | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}`; `POST /api/habits/{habit_id}/restore`; verification `GET` | Update | Moderate; re-enables a tracker |
| `delete_habit` | Proposed (Phase 2A) | Permanently delete one explicit habit after a versioned read | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `delete`) | `GET /api/habits/{habit_id}`; `DELETE` same path; absence verification `GET` | Delete | High; permanently removes habit history |
| `list_pet_photos` | Proposed (Phase 2A) | List stable photo IDs, renditions, primary status, and pet version | `pets:read` | `pets:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}` | Read | Moderate; personal images and metadata |
| `upload_pet_photo_from_url` | Proposed (Phase 2A) | Import one bounded public HTTPS image and make it primary | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | guarded source `GET`; `GET /api/pets/{pet_id}`; multipart `POST /api/pets/{pet_id}/photos`; verification `GET` | Create | High; gateway fetch plus durable personal image upload |
| `set_primary_pet_photo` | Proposed (Phase 2A) | Make one explicit existing photo the pet's primary image | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}`; `POST /api/pets/{pet_id}/photos/{photo_id}/set-primary`; verification `GET` | Update | Moderate; changes public/profile presentation |
| `delete_pet_photo` | Proposed (Phase 2A) | Permanently delete one explicit pet photo at a known pet version | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `delete`) | `GET /api/pets/{pet_id}`; `DELETE /api/pets/{pet_id}/photos/{photo_id}`; verification `GET` | Delete | High; permanently removes a personal image |
| `list_microchips` | Proposed (Phase 2A) | List a pet's microchip identity records | `microchips:read` | `microchips:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/microchips` | Read | High; stable animal identity data |
| `get_microchip` | Proposed (Phase 2A) | Retrieve one explicit microchip record and version | `microchips:read` | `microchips:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/microchips/{microchip_id}` | Read | High; stable animal identity data |
| `add_microchip` | Proposed (Phase 2A) | Add one microchip identity record without finance side effects | `microchips:read` + `microchips:write` | `microchips:read` + `microchips:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/microchips`; verification `GET` | Create | High; creates durable identity data |
| `update_microchip` | Proposed (Phase 2A) | Correct one explicit microchip record at a known version | `microchips:read` + `microchips:write` | `microchips:read` + `microchips:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/microchips/{microchip_id}`; `PUT` same path; verification `GET` | Update | High; overwrites durable identity data |
| `delete_microchip` | Proposed (Phase 2A) | Delete one explicit microchip record while preserving linked finance data | `microchips:read` + `microchips:write` | `microchips:read` + `microchips:write` (legacy PAT: `read` + `delete`) | `GET /api/pets/{pet_id}/microchips/{microchip_id}`; `DELETE` same path with linked transaction kept; absence verification `GET` | Delete | High; permanently removes identity data |

## Scope model

| MCP scope | Consent meaning | MCP-issued Sanctum ability | Tools |
|-----------|-----------------|-----------------------------|-------|
| `pets:read` | View the user's pet profiles and public pet-type reference data | `pets:read` | Pet list/find/detail; pet types; overview |
| `health:read` | View weights, vaccinations, and medical records for pets the user may access | `health:read` | Health lists/details; overview |
| `pets:write` | Create and edit pet profiles the user may manage | `pet:write` | Pet create/update; always paired with `pets:read` by these tools |
| `health:write` | Add and edit weight, vaccination, and medical records for pets the user may manage | `health:write` | Health create/update; always paired with `health:read` by these tools |
| `habits:read` | View habit trackers, day entries, and heatmaps visible to the user | `habits:read` | Habit list/detail/day/heatmap |
| `habits:write` | Create, edit, archive, restore, delete, and record entries for habits the user may manage | `habits:write` | Habit mutations; always paired with `habits:read` by these tools |
| `microchips:read` | View microchip identity records for pets the user may access | `microchips:read` | Microchip list/detail |
| `microchips:write` | Add, correct, and delete microchip records for pets the user may manage | `microchips:write` | Microchip mutations; always paired with `microchips:read` by these tools |

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

Phase 2A creates use the same create annotations. Configuration changes,
day-entry upserts, archive/restore, primary-photo selection, and all deletes use
the update annotations. Deletes remain `idempotentHint: true` because the
stable key replays the first terminal response; they are also
`destructiveHint: true`. Photo source fetching is open-world and does not make
the other write scopes interchangeable.

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

## Phase 2A ordinary pet-care tools

All Phase 2A writes use the same idempotency-key contract as Phase 1B. An
update, archive, restore, or delete also requires the exact `base_version` from
its read tool. Meo performs the authoritative version check before mutation.
The gateway then reads the target back, or verifies absence after a delete.

### Habits

- `Habit` contains `id`, `name`, IANA `timezone`, `value_type` (`yes_no |
  integer_scale`), nullable `scale_min`/`scale_max`, `day_summary_mode`
  (`average_scored_pets | average_all_pets | sum`), sharing/reminder settings,
  nullable `archived_at`, a narrowed pet list (`id`, `name`, `photo_url`),
  capability booleans, and nullable `version`. Creator IDs are omitted.
- `list_habits` input is `{}` and returns `{ "habits": Habit[] }`.
  `get_habit` takes positive `habit_id` and returns `{ "habit": Habit }`.
- `get_habit_heatmap` takes `habit_id`, `weeks` from 1 through 104 (default
  52), and optional ISO `end_date`. It returns daily rows containing only
  `date`, nullable `average_value`, nullable `display_value`, `entry_count`,
  `visible_pet_count`, and nullable `normalized_intensity`.
- `get_habit_day_entries` takes `habit_id` and a non-future ISO `entry_date`.
  It returns the narrowed habit plus rows containing `entry_id`, `pet_id`,
  `pet_name`, `pet_photo_url`, nullable `value_int`, `is_current_pet`, and
  `has_entry`.
- `create_habit` requires `name`, `value_type`, one or more explicit unique
  `pet_ids`, and `idempotency_key`. It accepts the optional configuration fields
  represented by `Habit`; integer scales require both bounds, and enabled
  reminders require a time. Output is the verified `habit`.
- `update_habit` requires `habit_id`, `base_version`, `idempotency_key`, and at
  least one mutable configuration field. Meo keeps value-type and pet ownership
  rules authoritative. Output is the verified `habit`.
- `save_habit_day_entries` requires `habit_id`, `entry_date`,
  `idempotency_key`, and one or more unique `{ "pet_id", "value_int" }` rows.
  A null value explicitly clears that pet/date entry. It reads the day first
  and verifies the returned day after the upsert.
- `archive_habit`, `restore_habit`, and `delete_habit` each require explicit
  `habit_id`, `base_version`, and `idempotency_key`. Archive/restore return the
  verified habit. Delete returns `{ "habit_id", "deleted": true,
  "verified": true }` only after a detail read returns not-found.

### Pet photos

- `list_pet_photos` takes positive `pet_id` and returns `pet_version` plus
  photos narrowed to `id`, `url`, nullable `thumb_url`/`medium_url`, nullable
  `width`/`height`, `is_primary`, and `processing`.
- `upload_pet_photo_from_url` requires `pet_id`, its `base_version`, a public
  HTTPS `source_url`, and `idempotency_key`. The gateway rejects credentials,
  fragments, non-443 ports, private/reserved/loopback DNS answers, unsafe
  redirects, unsupported image MIME types, and bodies over 10 MiB. Each hop is
  connected through a validated pinned address while preserving TLS SNI and
  the HTTP host. Meo receives a multipart file; arbitrary source response text
  is never returned or logged.
- `set_primary_pet_photo` and `delete_pet_photo` require positive `pet_id` and
  `photo_id`, the pet's `base_version`, and `idempotency_key`. Both read the
  current photo list first; setting primary verifies the selected ID is primary,
  while deletion verifies that ID is absent. The special upstream `current`
  deletion alias is never exposed.

### Microchips

- `Microchip` contains `id`, `chip_number`, nullable `issuer`, nullable ISO
  `implanted_at`, nullable `version`, and `has_linked_transaction`; it omits
  pet/user and finance identifiers.
- `list_microchips` takes `pet_id` and `page`; `get_microchip` additionally
  takes explicit `microchip_id`. Outputs use the shared pagination shape.
- `add_microchip` requires `pet_id`, a 10–20 character `chip_number`, and
  `idempotency_key`; optional fields are `issuer` and `implanted_at`. It does
  not accept finance-expense input under the microchip scope.
- `update_microchip` requires `pet_id`, `microchip_id`, `base_version`,
  `idempotency_key`, and at least one mutable field.
- `delete_microchip` requires the explicit IDs, version, and key. If a finance
  transaction is linked, Meo removes only the link and preserves the finance
  record. The tool never receives authority to delete finance data.
- Microchip creates/updates return the verified record. Delete returns
  `{ "microchip_id", "deleted": true, "verified": true }` after absence is
  confirmed.

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
| `source_url_rejected` | no | A photo source URL or redirect is not public HTTPS on the permitted port |
| `source_image_invalid` | no | A photo source has an unsupported MIME type, invalid declared size, or no usable body |
| `source_image_too_large` | no | A streamed photo source exceeded the 10 MiB gateway limit |
| `source_fetch_failed` | yes | A validated public photo source could not be fetched safely |

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
