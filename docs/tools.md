# MCP tool catalog

This is the canonical capability matrix for `meo-mcp`. Update it in the same
change that adds or changes a tool, scope, delegated ability, upstream endpoint,
schema, annotation, error behavior, or risk classification.

The gateway exposes semantic workflow tools, not a one-to-one mirror of Meo's
REST API. Admin/Filament endpoints and internal connector endpoints are never
part of the end-user tool surface.

## Lifecycle

- **Live** means implemented and accepted on the development MCP endpoint.
- **Proposed** means the contract is cataloged for the active milestone but is
  not available until its implementation, deployment, and acceptance finish.

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
| `create_placement_request` | Live | Create one explicit pet placement request | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `create`) | `POST /api/placement-requests`; verification reads | Create | High; publishes placement intent |
| `delete_placement_request` | Live | Delete an exact owned request after pet/name/version preview | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `delete`) | request read; `DELETE /api/placement-requests/{id}`; absence verification | Delete | High; removes request context |
| `respond_to_placement_request` | Live | Offer an exact helper profile for an exact placement | `placement:read` + `placement:write` + `helpers:read` | `placement:read` + `placement:write` + `helpers:read` (legacy PAT: `read` + `create`) | request/profile reads; `POST .../responses`; verification | Create | High; shares helper identity and offer |
| `accept_placement_response` | Live | Accept an exact owner-reviewed response and start handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | response read; `POST .../{id}/accept`; verification | Update | Critical; selects custodian |
| `reject_placement_response` | Live | Reject an exact owner-reviewed response | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | response read; `POST .../{id}/reject`; verification | Update | High; blocks helper response |
| `cancel_placement_response` | Live | Cancel the caller's exact current response | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | context read; `POST .../{id}/cancel`; verification | Update | High; withdraws offer |
| `confirm_pet_transfer` | Live | Confirm receipt for an exact handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | context read; `POST /api/transfer-requests/{id}/confirm`; verification | Update | Critical; changes custody |
| `reject_pet_transfer` | Live | Reject an exact pending handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | context read; `POST .../{id}/reject`; verification | Update | Critical; aborts transfer |
| `cancel_pet_transfer` | Live | Cancel an exact initiated handover | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `delete`) | context read; `DELETE /api/transfer-requests/{id}`; verification | Delete | Critical; resets flow |
| `finalize_temporary_placement` | Live | End an exact active foster/sitting placement | `placement:read` + `placement:write` | `placement:read` + `placement:write` (legacy PAT: `read` + `update`) | request read; `POST .../{id}/finalize`; verification | Update | Critical; ends care relationship |
| `create_helper_profile` | Live | Create one private helper profile with stable locations | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `create`) | location reads; `POST /api/helper-profiles`; verification | Create | High; stores contact data |
| `update_helper_profile` | Live | Update selected fields on an exact profile/version | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `PUT /api/helper-profiles/{id}`; verification | Update | High; private/public data |
| `archive_helper_profile` | Live | Archive an exact unused helper profile | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `POST .../{id}/archive`; verification | Update | High; disables profile |
| `restore_helper_profile` | Live | Restore an exact archived profile as private | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `POST .../{id}/restore`; verification | Update | High; reactivates profile |
| `delete_helper_profile` | Live | Delete an exact unused profile and photos | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `delete`) | detail read; `DELETE /api/helper-profiles/{id}`; absence verification | Delete | Critical; destroys data |
| `upload_helper_profile_photo_from_url` | Live | Import one bounded public HTTPS image | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | guarded GET; multipart profile update; verification | Create | High; personal image |
| `set_primary_helper_profile_photo` | Live | Make one exact profile photo primary | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `update`) | detail read; `POST .../set-primary`; verification | Update | High; public presentation |
| `delete_helper_profile_photo` | Live | Delete one exact profile photo | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `delete`) | detail read; `DELETE .../photos/{id}`; verification | Delete | Critical; destroys image |
| `open_placement_chat` | Live | Open/find a direct chat with an exact placement counterparty | `placement:read` + `messages:read` + `messages:write` | `placement:read` + `messages:read` + `messages:write` (legacy PAT: `read` + `create`) | placement read; `POST /api/msg/chats`; verification | Create | Critical; private channel |
| `send_chat_message` | Live | Send replay-safe text to an exact counterparty | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `create`) | chat read; `POST .../messages`; verification | Create | Critical; correspondence |
| `send_chat_image_from_url` | Live | Send a bounded HTTPS image to an exact chat | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `create`) | guarded GET; multipart message POST; verification | Create | Critical; private image |
| `mark_chat_read` | Live | Explicitly advance one chat read receipt | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `update`) | chat read; `POST .../read`; verification | Update | Moderate; activity signal |
| `delete_own_message` | Live | Soft-delete one exact own message/content/version | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `delete`) | message read; `DELETE /api/msg/messages/{id}`; verification | Delete | Critical; correspondence |
| `leave_chat` | Live | Leave one exact direct chat after participant preview | `messages:read` + `messages:write` | `messages:read` + `messages:write` (legacy PAT: `read` + `delete`) | chat read; `DELETE /api/msg/chats/{id}`; verification | Delete | Critical; ends access |
| `list_groups` | Live | List groups the caller belongs to with role and size summaries | `groups:read` | `groups:read` (legacy PAT: `read`) | `GET /api/groups` | Read | High; membership metadata |
| `get_group_overview` | Live | Read one explicit group with members, roles, pets, and version | `groups:read` | `groups:read` (legacy PAT: `read`) | `GET /api/groups/{group_id}` | Read | High; named people and animal membership |
| `list_group_member_suggestions` | Live | Resolve known-user candidates before a group membership write | `groups:read` | `groups:read` (legacy PAT: `read`) | `GET /api/groups/{group_id}/member-suggestions` | Read | High; user identity suggestions |
| `list_group_invitations` | Live | List pending bearer invitations for one managed group | `groups:read` | `groups:read` (legacy PAT: `read`) | `GET /api/groups/{group_id}/invitations` | Read | High; invitation URLs grant access |
| `list_currencies` | Live | Resolve supported currency codes and minor-unit precision | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/currencies` | Read | Low; reference data |
| `list_ledgers` | Live | List accessible active or archived ledgers | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/ledgers` | Read | High; shared-finance membership and totals context |
| `get_ledger_overview` | Live | Aggregate one ledger's identity, members, pets, configuration, and dashboard | `finance:read` | `finance:read` (legacy PAT: `read`) | ledger detail, dashboard, accounts, categories, members, pets `GET`s | Read/aggregate | Critical; financial totals and named participants |
| `list_ledger_member_suggestions` | Live | Resolve known-user candidates before a ledger membership write | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/ledgers/{ledger_id}/member-suggestions` | Read | High; user identity suggestions |
| `list_ledger_invitations` | Live | List pending bearer invitations for one managed ledger | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/ledgers/{ledger_id}/invitations` | Read | Critical; finance invitation URLs grant access |
| `list_ledger_transactions` | Live | Page and filter transactions in one explicit ledger | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/ledgers/{ledger_id}/transactions` | Read | Critical; amounts, descriptions, people, and pet links |
| `get_ledger_transaction` | Live | Read one exact transaction and receipt-presence flag | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/ledgers/{ledger_id}/transactions/{transaction_id}` | Read | Critical; detailed financial record |
| `list_pet_finance_transactions` | Live | Page finance entries linked to one pet across accessible ledgers | `finance:read` | `finance:read` (legacy PAT: `read`) | `GET /api/pets/{pet_id}/finance-transactions` | Read | Critical; cross-ledger pet spending/income |
| `preview_ledger_invitation` | Live | Preview a ledger bearer invitation without putting its token in a URL | `finance:read` | `finance:read` (legacy PAT: `read`) | `POST /api/mcp/ledger-invitations/preview` | Read | Critical; invitation bearer material |
| `create_ledger` | Live | Create a titled ledger with an explicit currency | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | duplicate preview; `POST /api/ledgers`; overview verification | Create | Critical; creates shared finance boundary |
| `update_ledger` | Live | Rename one exact ledger from its current version | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | overview preview; `PUT /api/ledgers/{ledger_id}`; overview verification | Update | Critical; shared identity change |
| `archive_ledger` | Live | Archive one exact versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | overview preview; `POST .../archive`; overview verification | Update | Critical; disables finance mutations |
| `restore_ledger` | Live | Restore one exact archived ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | archived list preview; `POST .../restore`; overview verification | Update | Critical; re-enables finance access |
| `delete_ledger` | Live | Permanently delete one unused exact ledger after title preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `delete`) | overview preview; `DELETE /api/ledgers/{ledger_id}`; absence verification | Delete | Critical; destroys unused ledger |
| `add_ledger_member` | Live | Add one exact suggested user as an equal member | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | overview/suggestion preview; `POST .../members`; overview verification | Create | Critical; grants finance access |
| `remove_ledger_member` | Live | Remove one exact member after name preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `delete`) | overview preview; `DELETE .../members/{user_id}`; overview verification | Delete | Critical; revokes finance access |
| `leave_ledger` | Live | Leave one exact ledger after overview preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `delete`) | overview preview; `POST .../leave`; absence verification | Delete | Critical; ends caller access |
| `add_ledger_pet` | Live | Assign one exact manageable pet to a versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | overview/pet preview; `POST .../pets/{pet_id}`; overview verification | Create | Critical; links pet spending |
| `remove_ledger_pet` | Live | Remove one exact manual pet assignment after name preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `delete`) | overview preview; `DELETE .../pets/{pet_id}`; overview verification | Delete | Critical; changes pet finance linkage |
| `link_ledger_group` | Live | Link one exact group to a versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | overview preview; `POST .../group-link`; overview verification | Update | Critical; cross-boundary group sync |
| `unlink_ledger_group` | Live | Unlink the group from one exact versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | overview preview; `DELETE .../group-link`; overview verification | Update | Critical; ends group sync |
| `create_ledger_invitation` | Live | Create a bearer invitation for one exact ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | overview preview; `POST .../invitations`; list verification | Create | Critical; emits bearer access material |
| `revoke_ledger_invitation` | Live | Revoke one exact pending ledger invitation | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `delete`) | invitation preview; `DELETE .../invitations/{invitation_id}`; absence verification | Delete | Critical; invalidates bearer material |
| `accept_ledger_invitation` | Live | Accept an exact previewed ledger invitation | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | body-token preview; `POST /api/mcp/ledger-invitations/accept`; overview verification | Create | Critical; grants caller ledger access |
| `decline_ledger_invitation` | Live | Decline an exact previewed ledger invitation | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | body-token preview; `POST /api/mcp/ledger-invitations/decline`; inactive verification | Update | Critical; permanently consumes invitation |
| `create_ledger_account` | Live | Create one account on an exact versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | overview preview; `POST .../accounts`; overview verification | Create | High; changes configuration |
| `update_ledger_account` | Live | Rename one exact account from its current version | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | account preview; `PUT .../accounts/{account_id}` | Update | High; configuration change |
| `archive_ledger_account` | Live | Toggle archive on one exact account after state preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | account preview; `POST .../accounts/{account_id}/archive` | Update | High; configuration change |
| `create_ledger_category` | Live | Create one category on an exact versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | overview preview; `POST .../categories`; overview verification | Create | High; changes configuration |
| `update_ledger_category` | Live | Update one exact category from its current version | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | category preview; `PUT .../categories/{category_id}` | Update | High; configuration change |
| `archive_ledger_category` | Live | Toggle archive on one exact category after state preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | category preview; `POST .../categories/{category_id}/archive` | Update | High; configuration change |
| `create_ledger_transaction` | Live | Record one income or expense on an exact versioned ledger | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `create`) | overview preview; `POST .../transactions`; detail verification | Create | Critical; creates financial audit data |
| `update_ledger_transaction` | Live | Correct one exact transaction at a known version | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `update`) | detail preview; `PUT .../transactions/{transaction_id}`; detail verification | Update | Critical; overwrites financial audit data |
| `delete_ledger_transaction` | Live | Delete one exact transaction after type/amount/date preview | `finance:read` + `finance:write` | `finance:read` + `finance:write` (legacy PAT: `read` + `delete`) | detail preview; `DELETE .../transactions/{transaction_id}`; absence verification | Delete | Critical; removes financial audit data |
| `get_notification_inbox` | Live | Read bounded bell notifications plus unread bell/message counts | `notifications:read` | `notifications:read` (legacy PAT: `read`) | `GET /api/notifications/unified` | Read | High; private event and action metadata |
| `get_notification_preferences` | Live | Read per-event delivery preferences | `notifications:read` | `notifications:read` (legacy PAT: `read`) | `GET /api/notification-preferences` | Read | Moderate; communication settings |
| `get_my_profile` | Live | Read a narrowed self profile, locale, avatar, storage, and account state | `profile:read` | `profile:read` (legacy PAT: `read`) | `GET /api/users/me` | Read | Critical; personal identity and account metadata |
| `list_owner_weights` | Live | Page the caller's own body-weight history | `profile:read` | `profile:read` (legacy PAT: `read`) | `GET /api/users/me/owner-weights` | Read | Critical; personal health data |
| `get_owner_weight` | Live | Read one exact owner-weight record and its editable version | `profile:read` | `profile:read` (legacy PAT: `read`) | `GET /api/users/me/owner-weights/{owner_weight_id}` | Read | Critical; personal health data |
| `get_account_invitation_summary` | Live | Read sent onboarding invitations and lifecycle totals | `invitations:read` | `invitations:read` (legacy PAT: `read`) | `GET /api/invitations`; `GET /api/invitations/stats` | Read/aggregate | High; bearer codes and recipient identity |
| `mark_notification_read` | Live | Mark one exact notification read without executing its actions | `notifications:read` + `notifications:write` | `notifications:read` + `notifications:write` (legacy PAT: `read` + `update`) | inbox preview; `PATCH /api/notifications/{notification_id}/read`; inbox verification | Update | Moderate; changes private activity state |
| `mark_all_notifications_read` | Live | Mark the previewed unread set read only if its count is still current | `notifications:read` + `notifications:write` | `notifications:read` + `notifications:write` (legacy PAT: `read` + `update`) | inbox preview; `POST /api/notifications/mark-all-read`; count verification | Update | High; bulk activity-state change |
| `update_notification_preference` | Live | Change one exact event type's delivery channels from an expected current state | `notifications:read` + `notifications:write` | `notifications:read` + `notifications:write` (legacy PAT: `read` + `update`) | preference preview; `PUT /api/notification-preferences`; preference verification | Update | High; changes whether communications are delivered |
| `update_my_profile_name` | Live | Change only the caller's display name from a versioned profile preview | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `update`) | profile preview; `PUT /api/users/me`; profile verification | Update | High; changes personal identity presentation |
| `upload_my_avatar_from_url` | Live | Replace the caller's avatar with one bounded public HTTPS image | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `update`) | guarded source `GET`; profile preview; multipart `POST /api/users/me/avatar`; profile verification | Update | High; replaces a personal image |
| `delete_my_avatar` | Live | Permanently remove the exact previewed avatar | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `delete`) | profile preview; `DELETE /api/users/me/avatar`; profile verification | Delete | High; permanently removes a personal image |
| `create_owner_weight` | Live | Record one dated body-weight measurement for the caller | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `create`) | duplicate-date guard; `POST /api/users/me/owner-weights`; detail verification | Create | Critical; creates personal health data |
| `update_owner_weight` | Live | Correct one exact owner-weight record at a known version | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `update`) | detail preview; `PUT /api/users/me/owner-weights/{owner_weight_id}`; detail verification | Update | Critical; overwrites personal health data |
| `delete_owner_weight` | Live | Delete one exact owner-weight record after date/value preview | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `delete`) | detail preview; `DELETE /api/users/me/owner-weights/{owner_weight_id}`; absence verification | Delete | Critical; permanently removes personal health data |
| `create_account_invitation` | Live | Create a generic or email-targeted onboarding invitation with explicit expiry | `invitations:read` + `invitations:write` | `invitations:read` + `invitations:write` (legacy PAT: `read` + `create`) | invitation preview; `POST /api/invitations`; summary verification | Create | Critical; emits bearer account-registration material and may send email |
| `revoke_account_invitation` | Live | Revoke one exact pending onboarding invitation at a known version | `invitations:read` + `invitations:write` | `invitations:read` + `invitations:write` (legacy PAT: `read` + `delete`) | summary preview; `DELETE /api/invitations/{invitation_id}`; summary verification | Delete | Critical; invalidates distributed bearer material |
| `list_pet_categories` | Proposed | Resolve visible breed/category options for one exact species | `pets:read` | `pets:read` (legacy PAT: `read`) | pet-type lookup; `GET /api/categories` | Read | Low; reference data plus caller-created pending options |
| `create_pet_category` | Proposed | Create one caller-visible category option for an exact species after duplicate preview | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `create`) | category preview; `POST /api/categories`; category verification | Create | Moderate; creates moderated shared reference data |
| `update_pet_status` | Proposed | Change one exact pet between active, lost, and deceased states from a versioned preview | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `update`) | pet preview; `PUT /api/pets/{pet_id}/status`; pet verification | Update | High; changes visibility and lifecycle presentation |
| `delete_pet` | Proposed | Soft-delete one exact pet after name/status/version preview | `pets:read` + `pets:write` | `pets:read` + `pet:write` (legacy PAT: `read` + `delete`) | pet preview; `DELETE /api/pets/{pet_id}`; absence verification | Delete | Critical; removes the pet from normal user workflows |
| `create_helper_city_option` | Proposed | Create one visible city option for helper/location workflows after duplicate preview | `helpers:read` + `helpers:write` | `helpers:read` + `helpers:write` (legacy PAT: `read` + `create`) | country/city preview; `POST /api/cities`; city verification | Create | Moderate; creates shared location reference data |
| `update_my_locale` | Proposed | Change the caller's locale to one advertised supported value from a versioned profile read | `profile:read` + `profile:write` | `profile:read` + `profile:write` (legacy PAT: `read` + `update`) | profile/locale preview; `PUT /api/user/locale`; profile verification | Update | Moderate; changes language preference |
| `create_group` | Live | Create a named group with an explicit initial pet set | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `create`) | duplicate preview; `POST /api/groups`; detail verification | Create | High; creates shared access boundary |
| `update_group` | Live | Rename one exact group from its current version | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `update`) | detail preview; `PUT /api/groups/{group_id}`; detail verification | Update | High; shared identity change |
| `delete_group` | Live | Permanently delete one exact group after membership/pet preview | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `delete`) | detail preview; `DELETE /api/groups/{group_id}`; absence verification | Delete | Critical; destroys group and sharing state |
| `add_group_member` | Live | Add one exact suggested user with an explicit role | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `create`) | detail/suggestion preview; `POST /api/groups/{group_id}/members`; detail verification | Create | Critical; grants access |
| `update_group_member_role` | Live | Change one exact member's role from a versioned group preview | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `update`) | detail preview; `PUT /api/groups/{group_id}/members/{user_id}`; detail verification | Update | Critical; changes administrative authority |
| `remove_group_member` | Live | Remove one exact member after role preview | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `delete`) | detail preview; `DELETE /api/groups/{group_id}/members/{user_id}`; detail verification | Delete | Critical; revokes access |
| `leave_group` | Live | Leave one exact group after caller-role and last-admin preview | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `delete`) | detail preview; `POST /api/groups/{group_id}/leave`; absence verification | Delete | Critical; ends caller access |
| `add_group_pets` | Live | Add an explicit non-empty set of manageable pet IDs | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `create`) | detail/pet preview; `POST /api/groups/{group_id}/pets`; detail verification | Create | Critical; shares pet visibility with group |
| `remove_group_pet` | Live | Remove one exact pet from a versioned group | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `delete`) | detail preview; `DELETE /api/groups/{group_id}/pets/{pet_id}`; detail verification | Delete | Critical; changes shared pet access |
| `create_group_invitation` | Live | Create a bearer invitation for one exact group and role | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `create`) | group/invitation preview; `POST /api/groups/{group_id}/invitations`; list verification | Create | Critical; emits bearer access material |
| `revoke_group_invitation` | Live | Revoke one exact pending group invitation | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `delete`) | invitation preview; `DELETE /api/groups/{group_id}/invitations/{invitation_id}`; absence verification | Delete | Critical; invalidates bearer material |
| `preview_group_invitation` | Live | Resolve bearer material in a request body before accept/decline | `groups:read` | `groups:read` (legacy PAT: `read`) | `POST /api/mcp/group-invitations/preview` | Read | Critical; consumes bearer material without URL leakage |
| `accept_group_invitation` | Live | Accept an exact previewed group invitation | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `create`) | body-token preview; `POST /api/mcp/group-invitations/accept`; group verification | Create | Critical; grants caller group access |
| `decline_group_invitation` | Live | Decline an exact previewed group invitation | `groups:read` + `groups:write` | `groups:read` + `groups:write` (legacy PAT: `read` + `update`) | body-token preview; `POST /api/mcp/group-invitations/decline`; inactive verification | Update | Critical; permanently consumes invitation |

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
| `groups:read` | View groups, members, assigned pets, suggestions, and pending invitations available to the caller | `groups:read` | Group reads only |
| `groups:write` | Create and manage groups, memberships, assigned pets, and group invitations | `groups:write` | Group mutations only; tools pair it with `groups:read` |
| `finance:read` | View accessible ledgers, transactions, totals, configuration, pets, members, suggestions, and pending invitations | `finance:read` | Finance reads only |
| `finance:write` | Create and manage ledgers, transactions, accounts, categories, members, pets, and ledger invitations | `finance:write` | Finance mutations only; tools pair it with `finance:read` |
| `notifications:read` | View the caller's notification inbox, unread counts, available actions, and delivery preferences | `notifications:read` | Notification reads only |
| `notifications:write` | Mark notifications read and change the caller's delivery preferences | `notifications:write` | Notification mutations only; tools pair it with `notifications:read` |
| `profile:read` | View a narrowed self profile and the caller's own weight history | `profile:read` | Self-profile reads only |
| `profile:write` | Change the caller's display name/avatar and manage their own weight history | `profile:write` | Safe self-profile mutations only; tools pair it with `profile:read` |
| `invitations:read` | View onboarding invitations sent by the caller and their lifecycle totals | `invitations:read` | Account-invitation reads only |
| `invitations:write` | Create and revoke onboarding invitations sent by the caller | `invitations:write` | Account-invitation mutations only; tools pair it with `invitations:read` |

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

## Phase 4A groups, finance, notifications, profile, and invitation reads

Phase 4A is a read-only deployment checkpoint. Its five scopes are independent:
financial access does not grant group membership, notification, self-profile,
or onboarding-invitation access. Every tool uses the shared read annotations.

- Group summaries expose stable group ID/name, the caller's role, and member/pet
  counts. `get_group_overview` requires a positive group ID and narrows members
  to stable user ID, display name, role, and membership start time; pets to ID,
  name, species, and public photo; and `version` to the authority `updated_at`.
  Suggestions contain only user ID and display name. Invitation lists preserve
  only pending invitation ID, target summary, expiry/version, and bearer URL.
- Currency options expose code, localized name, symbol, and non-negative minor
  units. Ledger summaries expose stable ledger ID/title, currency, optional
  linked group, archive state, member/pet counts, caller capabilities, and
  nullable version. `get_ledger_overview` requires a positive ledger ID and
  aggregates its detail, current/previous-month totals, six-month trend,
  account/category activity, members, pets, and newest five transactions.
- Transaction lists accept positive `ledger_id`, page and per-page bounds,
  optional ISO date range, exact `income | expense`, positive account/category/
  pet/creator IDs, and bounded search text. Results preserve integer minor-unit
  amounts plus the formatted major amount, exact date, description, narrowed
  creator/pet references, receipt presence, and authority version. Detail
  requires both ledger and transaction IDs; pet finance additionally requires
  a positive pet ID and never crosses ledgers unavailable to the caller.
- `get_notification_inbox` bounds `limit` to 1–50 and can omit notification
  bodies while still returning non-negative unread bell/message counts. Items
  contain stable ID, level, title/body, safe application-relative URL, available
  action keys, created/read timestamps, and version when supplied. Reading does
  not mark anything read or execute an action. Notification preferences expose
  only type/label/group and the three delivery booleans.
- `get_my_profile` returns an allowlist of self fields needed by agents: stable
  user ID, name, email, locale/timezone where present, avatar URL, password and
  verification state, premium/banned state, storage usage/limit, latest owner
  weight summary, and profile version. It excludes roles, admin capability,
  authentication provider internals, and hidden model attributes.
  `list_owner_weights` accepts a positive page and returns record ID, weight in
  kilograms, date, notes if present, version, and bounded pagination metadata.
- `get_account_invitation_summary` combines the caller's sent onboarding
  invitations with total/pending/accepted/expired/revoked counts. It narrows a
  recipient to stable ID, display name, and email. Invitation codes and URLs are
  bearer material: they are returned only to the authorized caller and must
  never appear in gateway logs or structured errors.

Receipt binaries are not returned in Phase 4A: transaction reads expose the
authoritative `has_receipt` flag. A future receipt tool requires a separately
designed bounded MCP content contract rather than leaking an authenticated API
URL or embedding an unbounded 10 MiB file.

## Phase 4B1 group write contract

Phase 4B1 introduces only `groups:write`, always paired with `groups:read` by
mutation tools. Every mutation carries an idempotency key. Every operation
against an existing group also carries the exact group `base_version` returned
by `get_group_overview`; Meo rejects stale versions before changing membership,
pet assignment, group identity, or invitation state.

- `create_group(name, pet_ids, idempotency_key)` normalizes a required name and
  distinct positive pet IDs. Meo serializes MCP creates per user and returns
  stable visible-group IDs instead of guessing whether an equal normalized
  name is intentional; `allow_duplicate` is required for a deliberately
  distinct equal-name group. Idempotency resolves before this duplicate guard,
  so exact retries return the original group.
- `update_group(group_id, base_version, name, idempotency_key)` and
  `delete_group(group_id, base_version, expected_group_name, idempotency_key)`
  read the complete target first. Delete additionally compares the expected
  name and returns the member/pet counts in the previewed result; confirmation
  prose is not used as an enforcement mechanism.
- Membership tools require explicit `group_id` and `user_id`.
  `add_group_member` also requires an exact `admin | member` role and proves the
  user is still in the authority's suggestion set. Role update and removal
  require `expected_current_role`; last-admin rules remain authoritative in
  Meo. `leave_group` compares `expected_caller_role` before ending access.
- Pet assignment tools accept only explicit positive pet IDs. Addition checks
  every target through the caller's pet read boundary, uses one atomic request,
  and treats already-assigned pets as an exact replay only when the full intent
  matches. Removal requires `expected_pet_name` from the versioned group read.
- Manager invitation create/revoke uses explicit group, role, invitation ID,
  and group version. Create retries return the same invitation; revoke retries
  verify absence. Invitation tokens and URLs are bearer material and may appear
  only in successful authorized tool content, never logs or errors.
- Recipient preview/accept/decline sends the 64-character bearer token in the
  request body to type-specific MCP authority endpoints. Accept/decline require
  the invitation `base_version` from preview. The group endpoints reject pet or
  ledger invitations so `groups:write` cannot cross domains.

Successful mutations perform a post-write detail/list/absence read. Stable
errors include the shared validation, idempotency, concurrency, authorization,
inactive-invitation, and post-write-verification codes. Deletion and access
changes use destructive annotations; create/update operations do not.


## Phase 4B2 finance write contract

Phase 4B2 introduces only `finance:write`, always paired with `finance:read` by
mutation tools. Every mutation carries an idempotency key. Operations against an
existing ledger, account, category, transaction, or invitation also carry the
exact `base_version` from the matching read/preview.

- `create_ledger(title, currency_code, idempotency_key)` normalizes a required
  title and 3-letter currency. Meo serializes MCP creates per user and returns
  stable visible-ledger IDs instead of guessing whether an equal normalized
  title is intentional; `allow_duplicate` is required for a deliberately
  distinct equal-title ledger. Idempotency resolves before this duplicate guard.
- `update_ledger`, `archive_ledger`, `restore_ledger`, and `delete_ledger` read
  the target first. Delete compares `expected_title` and only succeeds when Meo
  reports `can_delete`.
- Membership tools require explicit `ledger_id` and `user_id`. Members are equal;
  there is no role field. Addition proves the user remains in the suggestion set.
  Removal requires `expected_user_name`. `leave_ledger` ends caller access.
- Pet assignment tools accept only explicit positive pet IDs. Removal requires
  `expected_pet_name` and fails for group-synced pets in Meo.
- Group link/unlink are finance mutations that Meo additionally authorizes
  against the target group. Receipt binary upload/download remains out of MCP.
- Account and category create/update/archive use ledger or record versions.
  Archive tools require `expected_archived` so a stale toggle cannot invert the
  wrong way.
- Transaction create/update/delete require explicit account, type, major-unit
  amount string, and date. Delete compares expected type/amount/date before
  mutation and verifies absence afterward.
- Manager invitation create/revoke uses explicit ledger and invitation IDs plus
  ledger version. Recipient preview/accept/decline sends the 64-character bearer
  token in the request body to type-specific MCP authority endpoints. Accept and
  decline require the invitation `base_version` from preview and
  `expected_ledger_title`. The ledger endpoints reject pet or group invitations
  so `finance:write` cannot cross domains.

Successful mutations perform a post-write overview/detail/list/absence read.
Stable errors include the shared validation, idempotency, concurrency,
authorization, inactive-invitation, and post-write-verification codes. Deletion
and access changes use destructive annotations; create operations do not.

## Phase 4B3 notification, profile, owner-weight, and account-invitation contract

Phase 4B3 adds three independent write scopes. Mutation tools pair each write
scope with its matching read scope so they can enforce a fresh preview and a
post-write read. Every mutation requires an idempotency key; existing records
also require exact expected state or the authority's current `updated_at`
version.

- `mark_notification_read` accepts only a stable notification ID returned by a
  bounded inbox read and never executes an advertised notification action.
  `mark_all_notifications_read` requires the caller's previewed unread bell
  count; Meo rejects the write if a notification arrived or changed before the
  atomic bulk update. The admin-only city-unapproval handler is the sole
  registered notification action, so Phase 4B3 exposes no action-execution
  tool.
- `update_notification_preference` changes one explicit notification type. It
  carries all three expected channel booleans and all three desired booleans;
  Meo locks and compares the current row before updating it. This avoids a
  stale agent overwriting a concurrent browser preference change.
- `update_my_profile_name` changes only the display name. Email change,
  password change, and account deletion remain outside MCP because they affect
  authentication, verification, or account recovery. Avatar replacement uses
  the same pinned-DNS, redirect-limited, public-HTTPS image fetch boundary as
  other image-import tools and is limited further by Meo's avatar validator.
  Avatar deletion compares the previewed URL before removing media.
- `get_owner_weight` supplies the stable-ID/version read required before owner-
  weight correction or deletion. Creates are unique per record date; an exact
  idempotency-key replay returns the original record, while a distinct key for
  the same date returns `duplicate_candidate`. Update/delete compare the exact
  record version, and delete additionally compares its date and weight.
- Account-invitation creation may be generic or target one normalized email and
  may set a future expiry. Email-targeted creates detect an existing pending
  target unless `allow_duplicate` explicitly records distinct intent. Generic
  invitations have no recipient identity and therefore rely on idempotency
  rather than a guessed duplicate match. Revocation requires a pending stable
  invitation ID/version. Codes and invitation URLs may appear only in
  successful authorized tool content, never logs or structured errors.

Successful mutations verify the exact field/state change, stable returned ID,
or target absence/revocation through the corresponding read scope. The three
write scopes never authorize password changes, account deletion, notification
actions, or another user's profile/weight/invitation data.

## Phase 5A pet, reference-data, and locale closeout contract

Phase 5A reuses the existing narrow pet, helper, and profile scope pairs. It
does not introduce a cross-domain reference-data scope: pet categories require
the pet pair, helper city creation requires the helper pair, and locale updates
require the profile pair.

- Pet category reads resolve species through the existing pet-type catalog and
  return only visible category ID, name, slug, description, approval state, and
  usage count. Category creation previews an exact normalized name within the
  species, serializes the caller's creates, uses idempotency, and returns
  `duplicate_candidate` for a distinct-key duplicate. Created categories remain
  subject to Meo moderation. Pet create/update accepts only distinct category
  IDs visible to the caller and belonging to the selected pet type; pet detail
  exposes the same narrowed category shape for read-before-write.
- Pet status changes require explicit pet ID, expected pet name/status, current
  pet version, and one of `active | lost | deceased`. The special `deleted`
  state is never accepted by the status tool. Pet deletion is separate and
  requires the same exact target preview before Meo performs its soft-delete.
  Both operations use authoritative idempotency and post-write verification.
- Helper city creation accepts an advertised two-letter country, normalized
  name, optional description, and unique idempotency key. It previews visible
  cities, serializes caller creates, and translates a distinct-key duplicate to
  `duplicate_candidate`; Meo remains authoritative for limits and moderation.
- Locale update first reads the public supported-locale list and the caller's
  profile version. It sends only one advertised locale, uses profile-write
  authority and idempotency, and verifies the narrowed self profile afterward.

## Errors

Every tool can return `scope_required`, `authorization_inactive`, or the common
`upstream_*` codes in [errors.md](errors.md). Phase 1A also defines:

| Code | Retryable | Meaning |
|------|-----------|---------|
| `validation_error` | no | Locally validated input is missing, blank, out of range, or inconsistent |
| `upstream_validation_failed` | no | Meo rejected the normalized request with `422`; upstream field text is not forwarded |
| `duplicate_candidate` | no | A create matched an existing pet, group, ledger, owner-weight date, or pending invitation target; inspect stable IDs before deciding whether this is distinct intent |
| `idempotency_conflict` | no | The idempotency key was reused for a different normalized write |
| `active_placement_conflict` | no | The pet already has an active placement request of the requested type |
| `upstream_conflict` | no | Meo rejected the write because the target's current domain state conflicts |
| `idempotency_in_progress` | yes | The same idempotent write is still being processed; retry later with the same key |
| `concurrency_conflict` | no | The supplied base version is stale; re-read and reconcile before another update |
| `post_write_verification_failed` | yes | Meo accepted the write but its stable target could not be read back safely |
| `source_url_rejected` | no | A photo source URL or redirect is not public HTTPS on the permitted port |
| `source_image_invalid` | no | A photo source has an unsupported MIME type, invalid declared size, or no usable body |
| `source_image_too_large` | no | A streamed image exceeded its tool limit (10 MiB photos, 5 MiB chat, or 2 MiB avatar) |
| `source_fetch_failed` | yes | A validated public photo source could not be fetched safely |
| `relationship_mismatch` | no | A fresh sharing read does not match the caller's exact expected role set |
| `invitation_mismatch` | no | A fresh preview does not match the caller's exact expected pet or role |
| `invitation_inactive` | no | The invitation is expired, revoked, declined, accepted, or otherwise unusable |
| `last_owner_conflict` | no | The requested relationship change would leave the pet without an owner |
| `target_mismatch` | no | A fresh read does not match the caller's explicit expected pet, helper, recipient, response, transfer, photo, message, notification, preference, weight, or invitation target |
| `target_not_in_bounded_history` | no | A notification is outside the newest 50 bell items or a message is older than the newest 1,000 messages inspected by the guarded write |

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
