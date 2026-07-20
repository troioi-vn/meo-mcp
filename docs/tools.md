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
| `list_habits` | Live | List habit trackers visible to the user | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits` | Read | Moderate; pet routines and reminder settings |
| `get_habit` | Live | Retrieve one explicit habit and its editable version | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits/{habit_id}` | Read | Moderate; pet routines and reminder settings |
| `get_habit_heatmap` | Live | Summarize a bounded date range of habit completion/intensity | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits/{habit_id}/heatmap` | Read | Moderate; longitudinal care routine data |
| `get_habit_day_entries` | Live | Read per-pet values for one explicit habit date | `habits:read` | `habits:read` (legacy PAT: `read`) | `GET /api/habits/{habit_id}/entries/{date}` | Read | Moderate; per-pet routine data |
| `create_habit` | Live | Create a tracker for explicit owned pet IDs | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `create`) | `POST /api/habits`; verification `GET /api/habits/{habit_id}` | Create | Moderate; creates reminders and routine tracking |
| `update_habit` | Live | Update one explicit habit at a known version | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}`; `PUT` same path; verification `GET` | Update | Moderate; overwrites tracker configuration |
| `save_habit_day_entries` | Live | Upsert or clear explicit per-pet values on one habit date | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}/entries/{date}`; `PUT` same path; verification `GET` | Upsert | Moderate; overwrites daily care tracking |
| `archive_habit` | Live | Hide one explicit habit without deleting its history | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}`; `POST /api/habits/{habit_id}/archive`; verification `GET` | Update | Moderate; disables an active tracker |
| `restore_habit` | Live | Restore one explicit archived habit | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `update`) | `GET /api/habits/{habit_id}`; `POST /api/habits/{habit_id}/restore`; verification `GET` | Update | Moderate; re-enables a tracker |
| `delete_habit` | Live | Permanently delete one explicit habit after a versioned read | `habits:read` + `habits:write` | `habits:read` + `habits:write` (legacy PAT: `read` + `delete`) | `GET /api/habits/{habit_id}`; `DELETE` same path; absence verification `GET` | Delete | High; permanently removes habit history |
| `list_pet_photos` | Live | List stable photo IDs, renditions, primary status, and pet version | `pets:read` | `pets:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}` | Read | Moderate; personal images and metadata |
| `upload_pet_photo_from_url` | Live | Import one bounded public HTTPS image and make it primary | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | guarded source `GET`; `GET /api/pets/{pet_id}`; multipart `POST /api/pets/{pet_id}/photos`; verification `GET` | Create | High; gateway fetch plus durable personal image upload |
| `set_primary_pet_photo` | Live | Make one explicit existing photo the pet's primary image | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}`; `POST /api/pets/{pet_id}/photos/{photo_id}/set-primary`; verification `GET` | Update | Moderate; changes public/profile presentation |
| `delete_pet_photo` | Live | Permanently delete one explicit pet photo at a known pet version | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `delete`) | `GET /api/pets/{pet_id}`; `DELETE /api/pets/{pet_id}/photos/{photo_id}`; verification `GET` | Delete | High; permanently removes a personal image |
| `list_microchips` | Live | List a pet's microchip identity records | `microchips:read` | `microchips:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/microchips` | Read | High; stable animal identity data |
| `get_microchip` | Live | Retrieve one explicit microchip record and version | `microchips:read` | `microchips:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/microchips/{microchip_id}` | Read | High; stable animal identity data |
| `add_microchip` | Live | Add one microchip identity record without finance side effects | `microchips:read` + `microchips:write` | `microchips:read` + `microchips:write` (legacy PAT: `read` + `create`) | `POST /api/pets/{pet_id}/microchips`; verification `GET` | Create | High; creates durable identity data |
| `update_microchip` | Live | Correct one explicit microchip record at a known version | `microchips:read` + `microchips:write` | `microchips:read` + `microchips:write` (legacy PAT: `read` + `update`) | `GET /api/pets/{pet_id}/microchips/{microchip_id}`; `PUT` same path; verification `GET` | Update | High; overwrites durable identity data |
| `delete_microchip` | Live | Delete one explicit microchip record while preserving linked finance data | `microchips:read` + `microchips:write` | `microchips:read` + `microchips:write` (legacy PAT: `read` + `delete`) | `GET /api/pets/{pet_id}/microchips/{microchip_id}`; `DELETE` same path with linked transaction kept; absence verification `GET` | Delete | High; permanently removes identity data |
| `get_pet_sharing` | Live | Read active collaborators, the caller's permissions, and pet sharing version | `sharing:read` | `sharing:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/sharing` | Read | High; exposes named collaborators and access roles |
| `list_pet_relationship_suggestions` | Live | List explicit known-user candidates eligible for direct sharing | `sharing:read` | `sharing:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/relationship-suggestions` | Read | High; exposes user IDs and names |
| `list_pet_invitations` | Live | List pending share links for one owned pet | `sharing:read` | `sharing:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/invitations` | Read | High; returns bearer invitation URLs |
| `preview_pet_invitation` | Live | Preview a supplied pet invitation without changing access | `sharing:read` | `sharing:read` (legacy PAT: `read`) | `POST /api/mcp/resource-invitations/preview` | Read | High; consumes a caller-supplied bearer link in the body |
| `add_pet_collaborator` | Live | Grant a selected suggested user an explicit pet role | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `create`) | sharing/suggestion reads; `POST /api/pets/{pet_id}/users`; verification sharing read | Create | High; grants pet access, including ownership |
| `change_pet_collaborator_role` | Live | Change one explicit collaborator role at a known relationship version | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `update`) | sharing read; `PUT /api/pets/{pet_id}/users/{user_id}`; verification read | Update | High; changes access or ownership |
| `remove_pet_collaborator` | Live | End one explicit collaborator's access at a known relationship version | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `delete`) | sharing read; `DELETE /api/pets/{pet_id}/users/{user_id}`; verification read | Delete | High; revokes access or ownership |
| `create_pet_invitation` | Live | Create a role-specific bearer share link for an explicit owned pet/version | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `create`) | sharing read; `POST /api/pets/{pet_id}/invitations`; verification list | Create | High; anyone holding the link may gain access |
| `revoke_pet_invitation` | Live | Revoke one explicit pending pet invitation at its known version | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `delete`) | invitation list; `DELETE /api/pets/{pet_id}/invitations/{invitation_id}`; verification list | Delete | High; invalidates a distributed bearer link |
| `accept_pet_invitation` | Live | Accept a freshly previewed pet invitation whose expected pet/role match | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `create`) | body-token preview; `POST /api/mcp/resource-invitations/accept`; verification sharing read | Create | High; grants the caller durable pet access |
| `decline_pet_invitation` | Live | Decline a freshly previewed pet invitation whose expected pet/role match | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `update`) | body-token preview; `POST /api/mcp/resource-invitations/decline`; verification preview | Update | High; permanently consumes the invitation |
| `leave_shared_pet` | Live | End all caller relationships with an explicit pet after a versioned read | `sharing:read` + `sharing:write` | `sharing:read` + `sharing:write` (legacy PAT: `read` + `delete`) | sharing read; `POST /api/pets/{pet_id}/leave`; post-write permission verification | Delete | High; removes the caller's own access and may revoke issued invites |
| `list_placement_opportunities` | Live | Browse open placement requests through narrowed pet/request summaries | `placement:read` | `placement:read` (legacy PAT: `read`) | `GET /api/pets/placement-requests` | Read | High; public rehoming/foster intent and approximate location |
| `get_placement_request` | Live | Read one placement request plus the caller's role and currently allowed actions | `placement:read` | `placement:read` (legacy PAT: `read`) | `GET /api/placement-requests/{placement_request_id}`; authenticated `GET .../me` | Read/aggregate | High; role-shaped placement and handover context |
| `list_placement_responses` | Live | Let the request owner review the latest response from each helper profile | `placement:read` | `placement:read` (legacy PAT: `read`) | request/detail preflight; `GET /api/placement-requests/{placement_request_id}/responses` | Read | High; helper identity, offer text, and lifecycle state |
| `search_helper_profiles` | Live | Browse approved public helpers using explicit country/city/service/pet filters | `helpers:read` | `helpers:read` (legacy PAT: `read`) | `GET /api/helpers` | Read | High; public helper identity, experience, location, and home context |
| `get_public_helper_profile` | Live | Read one approved public helper profile without private contact fields | `helpers:read` | `helpers:read` (legacy PAT: `read`) | `GET /api/helpers/{helper_profile_id}` | Read | High; public helper profile and photos |
| `list_my_helper_profiles` | Live | List the caller's profiles and profiles visible through placement responses | `helpers:read` | `helpers:read` (legacy PAT: `read`) | `GET /api/helper-profiles` | Read | High; may include private contact and address data |
| `get_helper_profile` | Live | Read one explicitly visible full helper profile for management/review | `helpers:read` | `helpers:read` (legacy PAT: `read`) | `GET /api/helper-profiles/{helper_profile_id}` | Read | High; private contact, address, placement, and photo data |
| `list_helper_location_options` | Live | Resolve stable country codes and city IDs before helper-profile writes | `helpers:read` | `helpers:read` (legacy PAT: `read`) | `GET /api/countries`; optional `GET /api/cities?country=...&search=...` | Read | Low; reference data |
| `list_chats` | Live | List the caller's active direct chats with last-message and unread summaries | `messages:read` | `messages:read` (legacy PAT: `read`) | `GET /api/msg/chats` | Read | High; private correspondence metadata and preview text |
| `get_chat` | Live | Read participants and placement context for one explicit chat | `messages:read` | `messages:read` (legacy PAT: `read`) | `GET /api/msg/chats/{chat_id}` | Read | High; private participant and context metadata |
| `list_chat_messages` | Live | Page through one explicit chat without changing read receipts | `messages:read` | `messages:read` (legacy PAT: `read`) | side-effect-free `GET /api/msg/chats/{chat_id}/messages` | Read | Critical; private message bodies and image URLs |
| `get_unread_message_count` | Live | Count unread messages without marking any chat read | `messages:read` | `messages:read` (legacy PAT: `read`) | `GET /api/msg/unread-count` | Read | Moderate; private activity metadata |
| `create_placement_request` | Proposed (Phase 3B) | Create one explicit pet placement request | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `create`) | `POST /api/placement-requests`; verification reads | Create | High; publishes placement intent |
| `delete_placement_request` | Proposed (Phase 3B) | Delete an exact owned request after pet/name/version preview | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `delete`) | request read; `DELETE /api/placement-requests/{id}`; absence verification | Delete | High; removes request context |
| `respond_to_placement_request` | Proposed (Phase 3B) | Offer an exact helper profile for an exact placement | `placement:read` + `placement:write` + `helpers:read` | `placement:read` + `placement:write` + `helpers:read` (legacy PAT: `read` + `create`) | request/profile reads; `POST .../responses`; verification | Create | High; shares helper identity and offer |
| `accept_placement_response` | Proposed (Phase 3B) | Accept an exact owner-reviewed response and start handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | response read; `POST .../{id}/accept`; verification | Update | Critical; selects custodian |
| `reject_placement_response` | Proposed (Phase 3B) | Reject an exact owner-reviewed response | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | response read; `POST .../{id}/reject`; verification | Update | High; blocks helper response |
| `cancel_placement_response` | Proposed (Phase 3B) | Cancel the caller's exact current response | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | context read; `POST .../{id}/cancel`; verification | Update | High; withdraws offer |
| `confirm_pet_transfer` | Proposed (Phase 3B) | Confirm receipt for an exact handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | context read; `POST /api/transfer-requests/{id}/confirm`; verification | Update | Critical; changes custody |
| `reject_pet_transfer` | Proposed (Phase 3B) | Reject an exact pending handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | context read; `POST .../{id}/reject`; verification | Update | Critical; aborts transfer |
| `cancel_pet_transfer` | Proposed (Phase 3B) | Cancel an exact initiated handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `delete`) | context read; `DELETE /api/transfer-requests/{id}`; verification | Delete | Critical; resets flow |
| `finalize_temporary_placement` | Proposed (Phase 3B) | End an exact active foster/sitting placement | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | request read; `POST .../{id}/finalize`; verification | Update | Critical; ends care relationship |
| `create_helper_profile` | Proposed (Phase 3B) | Create one private helper profile with stable locations | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `create`) | location reads; `POST /api/helper-profiles`; verification | Create | High; stores contact data |
| `update_helper_profile` | Proposed (Phase 3B) | Update selected fields on an exact profile/version | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `PUT /api/helper-profiles/{id}`; verification | Update | High; private/public data |
| `archive_helper_profile` | Proposed (Phase 3B) | Archive an exact unused helper profile | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `POST .../{id}/archive`; verification | Update | High; disables profile |
| `restore_helper_profile` | Proposed (Phase 3B) | Restore an exact archived profile as private | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `POST .../{id}/restore`; verification | Update | High; reactivates profile |
| `delete_helper_profile` | Proposed (Phase 3B) | Delete an exact unused profile and photos | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `delete`) | detail read; `DELETE /api/helper-profiles/{id}`; absence verification | Delete | Critical; destroys data |
| `upload_helper_profile_photo_from_url` | Proposed (Phase 3B) | Import one bounded public HTTPS image | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | guarded GET; multipart profile update; verification | Create | High; personal image |
| `set_primary_helper_profile_photo` | Proposed (Phase 3B) | Make one exact profile photo primary | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `POST .../set-primary`; verification | Update | High; public presentation |
| `delete_helper_profile_photo` | Proposed (Phase 3B) | Delete one exact profile photo | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `delete`) | detail read; `DELETE .../photos/{id}`; verification | Delete | Critical; destroys image |
| `open_placement_chat` | Proposed (Phase 3B) | Open/find a direct chat with an exact placement counterparty | `placement:read` + `messages:read` + `messages:write` | `placement:read` + `messages:read` + `messages:write` (legacy PAT: `read` + `create`) | placement read; `POST /api/msg/chats`; verification | Create | Critical; private channel |
| `send_chat_message` | Proposed (Phase 3B) | Send replay-safe text to an exact counterparty | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `create`) | chat read; `POST .../messages`; verification | Create | Critical; correspondence |
| `send_chat_image_from_url` | Proposed (Phase 3B) | Send a bounded HTTPS image to an exact chat | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `create`) | guarded GET; multipart message POST; verification | Create | Critical; private image |
| `mark_chat_read` | Proposed (Phase 3B) | Explicitly advance one chat read receipt | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `update`) | chat read; `POST .../read`; verification | Update | Moderate; activity signal |
| `delete_own_message` | Proposed (Phase 3B) | Soft-delete one exact own message/content/version | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `delete`) | message read; `DELETE /api/msg/messages/{id}`; verification | Delete | Critical; correspondence |
| `leave_chat` | Proposed (Phase 3B) | Leave one exact direct chat after participant preview | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `delete`) | chat read; `DELETE /api/msg/chats/{id}`; verification | Delete | Critical; ends access |

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
| `sharing:read` | View pet collaborators, roles, suggestions, and invitation previews/links | `sharing:read` | Pet sharing reads |
| `sharing:write` | Grant, change, revoke, accept, decline, or leave pet access | `sharing:write` | Pet sharing mutations; always paired with `sharing:read` by these tools |
| `placement:read` | View open placement opportunities and role-shaped request/response/handover state | `placement:read` | Placement request, response, and viewer-context reads |
| `placement:write` | Create and manage placement requests, responses, transfers, and finalization | `placement:write` | Placement mutations; paired with `placement:read` |
| `helpers:read` | Browse public helper profiles and view profiles the caller may manage or review | `helpers:read` | Public/private helper reads and location options |
| `helpers:write` | Create and manage the caller's helper profiles and photos | `helpers:write` | Helper mutations; paired with `helpers:read` |
| `messages:read` | View the caller's chats, private messages, and unread counts | `messages:read` | Messaging reads without changing read receipts |
| `messages:write` | Open placement chats, send/remove messages, mark read, and leave chats | `messages:write` | Messaging mutations; paired with `messages:read` |

Scopes are independently requestable non-empty subsets. Dynamic registration
defaults to the full advertised set, while authorization can request a narrow
subset. Every tool checks its own requirement. Meo endpoints accept the
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

Phase 2B read tools use the shared read annotations. Every sharing mutation is
open-world, destructive, and idempotent: even a grant is destructive because
it changes another person's durable access. The hint is backed by the stable
idempotency key and authoritative Meo checks, not confirmation wording.

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

## Phase 2B pet sharing tools

Sharing uses dedicated `sharing:read` and `sharing:write` scopes. The narrowed
sharing endpoint—not the general pet profile endpoint—is the authority for
collaborators and caller permissions. Outputs omit email addresses, historic
relationships, creator IDs, and arbitrary upstream fields.

- `PetSharing` contains `pet_id`, `pet_name`, nullable `version`, caller
  permission booleans, caller `relationship_types`, and active relationships
  narrowed to `relationship_id`, `user_id`, `user_name`, `relationship_type`,
  and nullable `version`.
- `Invitation` contains `invitation_id`, `relationship_type`, `status`,
  `expires_at`, nullable `version`, and `share_url`. The URL is a bearer
  credential and appears only in owner-manager results.
- `InvitationPreview` contains only `status`, `expires_at`, `is_valid`,
  `is_authenticated`, `is_self_invitation`, `inviter_name`, `pet_name`,
  `relationship_type`, and nullable `version`. It never echoes the supplied
  token or link.
- `get_pet_sharing` takes positive `pet_id` and returns
  `{ "sharing": PetSharing }`.
- `list_pet_relationship_suggestions` takes positive `pet_id` and returns
  candidates narrowed to stable `user_id` and `user_name`.
- `list_pet_invitations` takes positive `pet_id` and returns pending
  `{ "invitations": Invitation[] }`.
- `preview_pet_invitation` takes `invitation`, either the exact configured Meo
  invitation URL or its 64-character alphanumeric token, and returns
  `{ "invitation": InvitationPreview }`. The gateway validates the value and
  redacts it from logs and errors.

Every mutation requires an `idempotency_key` under the shared write contract.
Grant roles are limited to `owner | editor | viewer`; Meo remains authoritative
for ownership, self-sharing, duplicate, and last-owner rules.

- `add_pet_collaborator` requires explicit `pet_id`, a `user_id` present in a
  fresh suggestion read, `relationship_type`, the `sharing_base_version`,
  and the key. It verifies the exact active relationship afterward.
- `change_pet_collaborator_role` requires explicit pet/user IDs,
  `relationship_type`, `sharing_base_version`, and the key. It first
  resolves that exact active relationship and verifies its new role afterward.
- `remove_pet_collaborator` requires explicit pet/user IDs,
  `sharing_base_version`, and the key. It verifies that relationship is
  absent afterward. An exact retry may replay the prior terminal result.
- `create_pet_invitation` requires explicit `pet_id`, `relationship_type`,
  `sharing_base_version`, and the key. It returns the verified pending invitation
  including its share URL.
- `revoke_pet_invitation` requires explicit pet/invitation IDs,
  `invitation_base_version`, and the key. It verifies the invitation is absent
  from the pending list; an exact retry may replay the prior result.
- `accept_pet_invitation` and `decline_pet_invitation` require `invitation`,
  exact `expected_pet_name`, exact `expected_relationship_type`,
  `invitation_base_version`, and the key. Immediately before mutation the
  gateway previews the invitation and rejects unless the expected pet and role
  match. It passes the version to Meo, which atomically distinguishes an exact
  idempotency replay from a stale request. Accept verifies the caller's new relationship; decline
  verifies that a subsequent preview is inactive.
- `leave_shared_pet` requires explicit `pet_id`, `sharing_base_version`, a non-empty
  exact `expected_relationship_types` set from the sharing read, and the key.
  The gateway rejects a mismatch before mutation. Meo enforces last-owner
  protection; success is verified by loss of the caller's active relationship
  or access.

Fresh-read version mismatches are also resolved by Meo rather than rejected
before the write request, because the first successful attempt changes the
version and an exact retry must still reach Meo's idempotency middleware.

Invitation tokens and URLs are never placed in application, HTTP-client, or
structured-error logs. Do not pass them in query strings or return them from
preview, accept, or decline. The gateway permits exact idempotency replay after
a target becomes inaccessible or disappears by allowing Meo's idempotency
middleware to resolve the stable key before a fresh-target read is required.

## Phase 3A placement, helper, and messaging reads

Phase 3 ships read parity as a separately deployed checkpoint before any new
write grant. Its three read scopes are independent; placement access does not
grant helper-profile or correspondence access.

- `PlacementOpportunity` contains a narrowed pet snapshot (`pet_id`, name,
  species, public photo, city/country) and its open requests as
  `placement_request_id`, `request_type`, `status`, notes/translation,
  start/end/expiry dates, and response count. `list_placement_opportunities`
  accepts optional `request_type`, two-letter `country`, `city`, and positive
  `pet_type_id` filters and returns matching summaries only.
- `get_placement_request` requires positive `placement_request_id`. It returns
  the narrowed request plus caller `viewer_role`, `my_response`, `my_transfer`,
  server-derived `available_actions`, and nullable `chat_id`. Public-only
  fields never gain private response or transfer data through gateway merging.
- `list_placement_responses` requires positive `placement_request_id`, verifies
  fresh owner context, and returns only the latest response per helper profile.
  Each response is narrowed to stable response/profile/user IDs, display name,
  status, message, timestamps, public helper summary, and nullable transfer ID,
  status, and version. Contact details are excluded from this tool.
- `PublicHelperProfile` contains stable profile/user IDs, display name,
  country/state/cities, experience/translation, offer, household flags,
  supported placement types/pet types, and public photos. It excludes address,
  postal code, phone number, contact methods, moderation fields, and placement
  history. Search inputs map exactly to Meo's public filters.
- `PrivateHelperProfile` adds owner-visible address, postal code, phone,
  normalized contact methods, approval/status values, lifecycle timestamps,
  and nullable version. `list_my_helper_profiles` and `get_helper_profile`
  preserve Meo visibility checks and never pass arbitrary related records.
- `list_helper_location_options` takes optional uppercase two-letter `country`
  and optional search (only with a country). Without a country it returns
  narrowed country code/name/phone-prefix options; with one it returns stable
  city IDs and localized names.
- `Chat` contains stable chat/context IDs, type, participants narrowed to ID,
  display name and avatar, last-message ID/type/safe content preview/timestamp,
  unread count, and nullable version. Email addresses and role internals are
  excluded. Only currently active participant chats are returned.
- `ChatMessage` contains stable message/chat/sender IDs, sender display name and
  avatar, type, content, `is_mine`, created timestamp, and the authority version
  required for deletion concurrency checks.
  `list_chat_messages` requires positive `chat_id`, optional ISO cursor, and
  limit 1–100; it returns `has_more`, nullable next cursor, and counterparty
  read timestamp. Listing never updates `last_read_at`; that mutation belongs
  to the explicit Phase 3B mark-read tool.
- `get_unread_message_count` returns one non-negative integer and has no side
  effect.

The legacy `/api/placement-requests/{id}/confirm` and `/reject` controllers are
not tool dependencies because they contain no enforced state transition. The
actual user-facing acceptance, transfer confirmation/rejection/cancellation,
and temporary-placement finalization flows use the explicit versioned Phase 3B
tools below.

## Phase 3B guarded writes

All Phase 3B creates require a unique `idempotency_key`; exact retries replay
the first result and changed-payload reuse fails. Existing-resource operations
also require the `base_version` returned by the corresponding read. The gateway
freshly reads explicit IDs, compares expected pet/helper/counterparty names or
message content where relevant, lets Meo enforce ownership and state, and then
verifies the resulting stable state. Create/update tools are non-read-only and
all lifecycle/delete tools are additionally destructive.

- Placement writes accept only the four authority request types. Response and
  transfer transitions use the actual lifecycle endpoints; the legacy no-op
  request confirm/reject endpoints remain excluded.
- Helper-profile create/update accepts stable city and pet-type IDs, normalized
  contact items, care types, household flags, and optional private address and
  contact fields. Photo imports reuse the public-HTTPS, DNS-pinning, redirect,
  MIME, and byte-limit guard; chat images add the upstream 5 MiB limit.
- Messaging creation is limited by Meo to direct `PlacementRequest` context and
  an owner/helper pair with an existing response. Group chat is not exposed.
  Text/image send, explicit mark-read, own-message soft deletion, and leave are
  separate tools. Deleting a message requires its exact current content so a
  stale conversational reference cannot select a different message. Lookup and
  post-write verification follow at most ten 100-message pages; older targets
  fail with `target_not_in_bounded_history` instead of mutating blindly.

## Errors

Every tool can return `scope_required`, `authorization_inactive`, or the common
`upstream_*` codes in [errors.md](errors.md). Phase 1A also defines:

| Code | Retryable | Meaning |
|------|-----------|---------|
| `validation_error` | no | Locally validated input is missing, blank, out of range, or inconsistent |
| `upstream_validation_failed` | no | Meo rejected the normalized request with `422`; upstream field text is not forwarded |
| `duplicate_candidate` | no | Pet create found an exact existing name/species match; inspect stable IDs before deciding whether this is a distinct pet |
| `idempotency_conflict` | no | The idempotency key was reused for a different normalized write |
| `active_placement_conflict` | no | The pet already has an active placement request of the requested type |
| `upstream_conflict` | no | Meo rejected the write because the target's current domain state conflicts |
| `idempotency_in_progress` | yes | The same idempotent write is still being processed; retry later with the same key |
| `concurrency_conflict` | no | The supplied base version is stale; re-read and reconcile before another update |
| `post_write_verification_failed` | yes | Meo accepted the write but its stable target could not be read back safely |
| `source_url_rejected` | no | A photo source URL or redirect is not public HTTPS on the permitted port |
| `source_image_invalid` | no | A photo source has an unsupported MIME type, invalid declared size, or no usable body |
| `source_image_too_large` | no | A streamed photo source exceeded the 10 MiB gateway limit |
| `source_fetch_failed` | yes | A validated public photo source could not be fetched safely |
| `relationship_mismatch` | no | A fresh sharing read does not match the caller's exact expected role set |
| `invitation_mismatch` | no | A fresh preview does not match the caller's exact expected pet or role |
| `invitation_inactive` | no | The invitation is expired, revoked, declined, accepted, or otherwise unusable |
| `last_owner_conflict` | no | The requested relationship change would leave the pet without an owner |
| `target_mismatch` | no | A fresh read does not match the caller's explicit expected pet, helper, recipient, response, transfer, photo, or message target |
| `target_not_in_bounded_history` | no | A message target is older than the newest 1,000 messages inspected by the guarded write |

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
