# Task 38 -- Delegation and waiting-on workflows (connector side)

Status: accepted, shipped 2026-04-15.

Companion to the capture-service ADR at
`../../obsidian-capture-service/docs/architecture/task_38_delegation.md`
(service PR #24, merge `67cc26b`).

## Context

The service side added three nullable columns on `actions`
(`delegated_to_entity_id`, `delegated_at`, `delegation_note`), four
endpoints (`POST /delegate`, `POST /reclaim`, `GET /delegated-to/{person}`,
`GET /patterns/stale-delegations`), and widened the
`acknowledgements.kind` CHECK constraint to admit `delegate` and
`reclaim`. The sync bridge forwards the new kwargs to
`connector_write_commitment_note`.

This ADR covers the connector-side surface that completes the round
trip: how delegated actions are represented in the vault, how the MCP
and CLI expose the new verbs, and where the review dashboard lives.

## Decisions

### 1. Three nullable fields on `ActionInput`

`ActionInput` gains:

- `delegated_to: str | None` -- resolved canonical name of the person
  entity.
- `delegated_at: str | None` -- ISO-8601 timestamp of the most recent
  delegate event.
- `delegation_note: str | None` -- optional free-form context.

All three default to `None`. Pre-Task-38 payloads construct
`ActionInput` unchanged; the service's kwarg filter drops unknown
fields when the connector is older, so the reverse direction is also
safe.

### 2. Frontmatter slot between `postponed_until` and `requires_ack`

The three keys render in that order in the YAML frontmatter between
`postponed_until` and `requires_ack`. Two reasons:

- They are lifecycle-related and belong near the other lifecycle
  markers, not next to the capture-era metadata at the bottom.
- Inserting in the middle of an already-stable block minimises noise
  on first-touch upgrade -- existing notes diff with three new lines
  plus three `null`s, nothing else moves.

Field order is preserved across writes so re-sync is byte-identical
when nothing changed.

### 3. Body row renders only when delegated

`_render_body` emits `- Delegated to: <name> (YYYY-MM-DD)` (and, when
present, `- Delegation note: <text>`) only when `delegated_to` is
truthy. Non-delegated notes diff cleanly; delegated notes carry a
prose-friendly row that Obsidian readers pick up without looking at
the frontmatter.

`delegated_at` is condensed to a date-only string when it parses; a
non-ISO value falls back to the raw timestamp so we never silently
drop the signal.

### 4. Four new `commitment_ops` HTTP wrappers

`delegate_commitment(action_id, *, to_person, note=None, ...)` ->
`POST /api/v1/actions/{id}/delegate`.

`reclaim_commitment(action_id, *, note=None, ...)` ->
`POST /api/v1/actions/{id}/reclaim`. Empty body when no note.

`list_delegated_to(person, *, limit=50, cursor=None, include_terminal=False, ...)` ->
`GET /api/v1/actions/delegated-to/{person}`.

`list_stale_delegations(*, threshold_days=14, limit=50, ...)` ->
`GET /api/v1/patterns/stale-delegations`.

All four reuse `_service_get_json` / `_service_post_json` so the
Task 35 timeout, scheme-allowlist, and auth behavior is shared with
every other service wrapper. They never raise; failures surface inside
the standard envelope (`{ok: False, status_code?: N, error: "..."}`).
Alias-safety on `list_delegated_to` is delegated to the service.

### 5. MCP + CLI surface

MCP tools (`mcp_server.py`): `obsidian_delegate_commitment`,
`obsidian_reclaim_commitment`, `obsidian_delegated_to`,
`obsidian_stale_delegations`. Each is a thin wrapper around the
`commitment_ops` helper, matching the shape every other Task 38-era
MCP tool uses (JSON dump, catch-all exception envelope, lazy import).

CLI subcommands: `obsx delegate-commitment`, `obsx reclaim-commitment`,
`obsx delegated-to`, `obsx stale-delegations`. Each supports human
and `--json` output and honours `--service-url` for override.

### 6. Delegation review dashboard

`commitment_dashboards.generate_delegation_dashboard(vault, *, service_url, token, threshold_days=14, now_iso=None)`
writes `Dashboards/Review/Delegations.md` with two sections:

- **Stale delegations (> N days)**: per-person buckets sourced from
  `list_stale_delegations(threshold_days=N)`. Each row shows count,
  oldest `delegated_at`, and up to three sample titles.
- **Open delegations**: per-person counts across every person who
  currently has at least one open delegated action. Sourced from
  `list_stale_delegations(threshold_days=1)` so the service returns
  every active bucket, sorted alphabetically (case-insensitive).

Service-unreachable and service-unconfigured render the page with a
banner and empty sections -- never silent skip. Always writes via
`atomic_write` so the user-visible surface lands atomically.

`update_all_review_dashboards(..., include_delegations=True)` is the
new opt-out flag; default-on because delegations is the primary
surface for the Task 38 workflow. Operators who want local-only
review runs pass `include_delegations=False`. Backwards-compatible:
existing callers without the kwarg get the new page by default.

## Not included

- No write-back on the vault side. Deleting the body row or frontmatter
  key does not reclaim the action; operators must call the reclaim
  endpoint through MCP / CLI so the SQLite row stays authoritative.
- No LLM-assisted nudge for stale delegations. The review dashboard
  surfaces the bucket; the operator decides whether to ping or
  reclaim.
- No analytics projection. Delegation counts ride on the existing
  Task 39 weekly report via `acknowledgements.kind IN ('delegate',
  'reclaim')` on the service side; no connector-side aggregation.

## Tests

`tests/test_delegation_connector.py` covers:

- `ActionInput` constructs with delegation kwargs and frontmatter
  renders the three new slots in stable order.
- Body row only emits when `delegated_to` is set; no stray line on
  non-delegated notes.
- `delegate_commitment` posts the right body and path, returns the
  service envelope.
- `reclaim_commitment` posts an empty body when no note is supplied.
- `list_delegated_to` and `list_stale_delegations` build the right
  query string and URL-encode the person segment (alias-safe).
- `generate_delegation_dashboard` renders both sections when the
  service is reachable, writes a banner when unreachable / not
  configured.

The existing `tests/test_admin_helpers.py` and
`tests/test_approval_ux.py` HTTP-mock patterns are reused verbatim.

## References

- Service ADR: `../../obsidian-capture-service/docs/architecture/task_38_delegation.md`
- Service PR #24, merge commit `67cc26b`.
- Connector helpers: `obsidian_connector/commitment_ops.py`
  (`_service_get_json`, `_service_post_json`, `_service_timeout`).
- Dashboard module: `obsidian_connector/commitment_dashboards.py`
  (`generate_delegation_dashboard`, `update_all_review_dashboards`).
