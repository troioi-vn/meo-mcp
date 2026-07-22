# Authoritative overdue vaccination semantics

Status: not started

## Goal

Let agents answer questions about overdue vaccination renewals without deriving
medical-record state independently. Meo Mai Moi remains the authority; the MCP
gateway passes through and normalizes the authoritative filter and boolean.

Use **overdue** rather than “expired vaccination” in schemas and documentation.
This describes an incomplete renewal whose due date has passed, not a claim that
an administered vaccine is medically invalid.

## Public contract

- Extend vaccination list status from `active | completed | all` to
  `active | overdue | completed | all`.
- Preserve `active` as the backward-compatible set of all incomplete records;
  overdue records remain a subset of active records.
- Add required boolean `is_overdue` to every serialized vaccination record.
- The authoritative predicate is: `completed_at` is null, `due_at` is non-null,
  and the calendar due date is strictly earlier than today in the Meo
  application's configured timezone.
- A record due today is not overdue. Completed records and records without a due
  date are never overdue. Historical completed/renewed records remain completed,
  even when their old due date is in the past.
- Reuse existing `health:read`; do not add a scope or a new MCP tool.

## Work items

### Meo Mai Moi authority

- [ ] Re-read repository and release instructions, vaccination model/resource,
      controller, policies, API tests, and date/time configuration
- [ ] Implement the overdue predicate once in the domain/query layer and reuse it
      for both the `status=overdue` query and `is_overdue` serialization
- [ ] Validate the new status value alongside the existing values and retain
      existing pagination and authorization behavior
- [ ] Update the API contract/docs and any generated schema consumed by clients
- [ ] Use no database migration unless inspection proves one is necessary; the
      existing dates contain all required state

### MCP gateway parity

- [ ] Extend `list_vaccinations` input validation and tool description with
      `overdue`
- [ ] Pass the filter to the upstream API and normalize the authoritative
      `is_overdue` boolean without recomputing it in Python
- [ ] Update the vaccination schema, structured examples, errors, and canonical
      `docs/tools.md` capability matrix
- [ ] Update relevant public skill guidance so agents prefer `status=overdue`
      and never infer overdue state from prose or local time
- [ ] Preserve all existing response fields and active/completed/all behavior

### Delivery

- [ ] Run documented unit, feature, lint, formatting, and schema checks in both
      repositories
- [ ] Inspect changed public files for private infrastructure or credentials
- [ ] Deploy/release Meo Mai Moi development first, then the gateway development
      branch, following each repository's normal workflow
- [ ] Monitor both pipelines and logs, verify local/public health, and perform a
      real authenticated MCP call before production promotion
- [ ] Promote each repository through its documented release process only after
      development acceptance; verify rollback remains non-destructive

## Test cases

- Incomplete due yesterday: returned by `overdue`, included in `active`, and
  `is_overdue=true`.
- Incomplete due today or tomorrow: absent from `overdue` and
  `is_overdue=false`.
- Incomplete with `due_at=null`: absent from `overdue` and false.
- Completed with a past due date: absent from `overdue` and false.
- `all` returns every record with an authoritative boolean; pagination metadata
  remains unchanged.
- Boundary tests freeze time in a non-UTC application timezone and prove that
  comparison uses the application calendar date, not the gateway host clock.
- Invalid status retains the stable validation/error contract.
- Existing active/completed/all API and MCP tests remain green.

## Definition of done

- Main-app API tests and MCP tests cover all boundary cases and pass with lint
  and formatting checks.
- Development and production expose matching authoritative semantics without a
  new scope or tool.
- A real MCP `list_vaccinations` call with `status=overdue` returns only the
  authoritative subset and the same records carry `is_overdue=true`.
- Durable API/tool/skill documentation is updated and this plan is archived.

