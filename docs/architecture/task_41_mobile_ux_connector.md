# Task 41 -- Mobile bulk actions (connector side)

Status: accepted, shipped 2026-04-15.

Companion to the capture-service ADR at
`../../obsidian-capture-service/docs/architecture/task_41_mobile_ux.md`
(service PR #26, merge commit `6989d26`).

## Context

The service side added five new endpoints under `/api/v1/actions`:

- `POST /api/v1/actions/bulk-ack`
- `POST /api/v1/actions/bulk-done`
- `POST /api/v1/actions/bulk-postpone`
- `POST /api/v1/actions/bulk-cancel`
- `GET  /api/v1/actions/postpone-presets`

They clone Task 36's atomic bulk-approval pattern for lifecycle verbs
and introduce a named-preset vocabulary for postpone. No new DB
tables; every mutation lands in the existing `acknowledgements`
audit trail.

This ADR covers the connector-side surface that wraps those endpoints
for the Python API, MCP, and CLI layers. There is **no** vault-side
dashboard for this task: bulk actions are triggered interactively
(iOS Reminders, CLI, MCP), not reviewed in a dashboard. The existing
Task 40 coaching dashboard is the review surface that surfaces
actions ripe for bulk operations; Task 41 only provides the rails.

## Decisions

### 1. Five thin HTTP wrappers in `commitment_ops.py`

All five wrappers reuse `_service_get_json` / `_service_post_json`
so Task 35 timeout / scheme / auth behavior is shared. None raise;
failures surface inside the standard envelope
(`{ok: False, status_code?: N, error: "..."}`).

- `bulk_ack_commitments(action_ids, *, note=None, ...)` ->
  `POST /api/v1/actions/bulk-ack`.
- `bulk_done_commitments(action_ids, *, note=None, ...)` ->
  `POST /api/v1/actions/bulk-done`.
- `bulk_postpone_commitments(action_ids, *, preset=None, postponed_until=None, note=None, ...)` ->
  `POST /api/v1/actions/bulk-postpone`. **Client-side validates
  exactly one of `preset` or `postponed_until` is supplied** so the
  caller never wastes a network round-trip on a 422. Blank strings
  (`""`, `"   "`) count as unset. Both empty or both set surfaces
  as `{ok: False, error: "exactly one of preset or postponed_until
  must be supplied"}`.
- `bulk_cancel_commitments(action_ids, *, reason=None, ...)` ->
  `POST /api/v1/actions/bulk-cancel`.
- `list_postpone_presets(*, ...)` ->
  `GET /api/v1/actions/postpone-presets`.

All four POST wrappers share a private `_bulk_action_call(path, *,
action_ids, extra_body, ...)` helper that validates `action_ids` is a
non-empty list of non-empty strings before touching the network.
Mirrors the Task 36 `_bulk_call` contract so the connector's two bulk
paths share identical preflight semantics.

### 2. Five MCP tools + five CLI subcommands

MCP tools in `mcp_server.py`:

- `obsidian_bulk_ack(action_ids, note=None, service_url=None)`
- `obsidian_bulk_done(action_ids, note=None, service_url=None)`
- `obsidian_bulk_postpone(action_ids, preset=None, postponed_until=None, note=None, service_url=None)`
- `obsidian_bulk_cancel(action_ids, reason=None, service_url=None)`
- `obsidian_postpone_presets(service_url=None)`

Each is a thin wrapper around the `commitment_ops` helper with the
standard JSON dump + catch-all exception envelope + lazy import
pattern.

CLI subcommands in `cli.py` (each supports human and `--json` output,
honours `--service-url`):

- `obsx bulk-ack --action-ids a,b,c [--note ...]`
- `obsx bulk-done --action-ids ... [--note ...]`
- `obsx bulk-postpone --action-ids ... [--preset NAME | --postponed-until ISO] [--note ...]`
- `obsx bulk-cancel --action-ids ... [--reason ...]`
- `obsx postpone-presets`

The `_fmt_bulk_action(result, verb)` helper formats the
`processed`/`skipped` envelope for ack/done/cancel; `_fmt_bulk_postpone`
adds the `resolved_postponed_until` echo line; `_fmt_postpone_presets`
renders the preset catalog with name + label + description.

### 3. Client-side preset/explicit exclusivity (key design call)

The service's `/bulk-postpone` endpoint returns 422 when both
`preset` and `postponed_until` are set (or neither). The connector
validates this client-side for two reasons:

1. **Saves a round-trip** when the CLI or MCP caller passes both.
   The CLI `--preset` and `--postponed-until` flags are independent
   argparse args; argparse doesn't enforce mutual exclusion for
   value-carrying options, so we would otherwise learn about the
   mistake via HTTP.
2. **Matches the Task 36 ergonomic contract** where empty lists
   short-circuit before `_service_post_json`. Consistent preflight
   across both bulk paths keeps the connector's behavior legible.

Blank strings are treated as unset via `.strip() != ""` so a
Shortcut that emits `preset=""` to mean "use postponed_until" still
routes cleanly.

## Not included

- **No write-back on the vault side.** Lifecycle mutations feed
  through the existing sync bridge on the service side; the
  connector's commitment-note writer already picks up the new
  statuses on the next sync pass. No dashboard writer for bulk ops
  -- they are fire-and-forget.
- **No built-in `Choose from Menu` generator.** The two new Shortcut
  docs on the service side walk the user through building the iOS
  Shortcuts UI by hand; we did not add a CLI `obsx print-shortcut`
  helper because Shortcuts' on-device editor is the canonical build
  surface.
- **No bulk-reschedule semantics.** The verb vocabulary matches the
  service side exactly (`ack | done | postpone | cancel`). Other
  verbs (`reason`, `delegate`, `reclaim`, `merge`) are deliberately
  not bulk-friendly: each carries row-specific inputs that don't
  generalise to a batch.

## Tests

`tests/test_bulk_actions_connector.py` covers:

- Wrapper path + body + auth shape for each POST wrapper.
- Envelope behavior on missing URL, HTTP 400 (cap exceeded).
- Empty `action_ids` list shorts before the network call.
- List of blank strings shorts before the network call.
- Preset vs explicit `postponed_until` mutual exclusivity (both set,
  neither set, both blank, both with only whitespace).
- `bulk_postpone_commitments` note forwarding.
- `list_postpone_presets` path + missing-url envelope.
- MCP tool passthrough for all five tools (plus client-side
  exclusivity in `obsidian_bulk_postpone`).
- CLI human + `--json` output for each subcommand, including the
  HTTP 400 failure message and per-row `skip: ...  wrong_status`
  rendering.

36 new test cases. Baseline 575 -> 611.

## References

- Service ADR: `../../obsidian-capture-service/docs/architecture/task_41_mobile_ux.md`
- Service PR #26, merge commit `6989d26`.
- Transport helpers: `obsidian_connector/commitment_ops.py`
  (`_service_get_json`, `_service_post_json`, `_service_timeout`).
- Shortcut docs (service repo):
  `../../obsidian-capture-service/docs/shortcuts/BULK_ACK_FROM_REMINDERS.md`,
  `../../obsidian-capture-service/docs/shortcuts/QUICK_POSTPONE_PRESETS.md`.
- Related: Task 36 approval bulk pattern
  (`obsidian_connector/approval_ops.py`).
