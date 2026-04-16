# Task 42 -- Cross-device sync (connector side)

**Status**: shipped
**Owner**: obsidian-connector
**Companion**: `../obsidian-capture-service/docs/architecture/task_42_cross_device_sync.md`

## Context

Task 42 ships two new `/api/v1/mobile` endpoints on the capture service:
`GET /devices` (list registered devices) and
`POST /devices/{device_id}/forget` (drop a device + cancel its pending
ops). This ADR records how the connector mirrors those endpoints as
Python wrappers, MCP tools, CLI subcommands, and an admin-dashboard
section.

## What shipped

### `admin_ops.py`

Two new HTTP wrappers, reusing
`commitment_ops._service_get_json` / `_service_post_json` so the
Task 35 timeout / scheme / auth / retry behavior is shared:

- `list_mobile_devices(*, service_url=None, token=None) -> dict` over
  `GET /api/v1/mobile/devices`.
- `forget_mobile_device(device_id, *, service_url=None, token=None) -> dict`
  over `POST /api/v1/mobile/devices/{device_id}/forget`. URL-encodes
  `device_id`. Blank / non-string `device_id` short-circuits to
  `{"ok": False, "error": "..."}` before any HTTP call.

Both functions never raise; failures surface in the standard envelope.

### MCP tools

Two new `@mcp.tool` entries in `mcp_server.py`:

- `obsidian_mobile_devices(service_url=None) -> str` -- read-only,
  idempotent, openWorld.
- `obsidian_forget_mobile_device(device_id, service_url=None) -> str`
  -- destructive on the service side; idempotent on a missing device
  id.

Both follow the standard pattern (lazy-import the admin_ops helper,
JSON-dump the result, catch-all exception envelope).

### CLI subcommands

Two new subcommands in `cli.py`:

- `obsx mobile-devices [--service-url URL] [--json]` -- read-only list.
- `obsx forget-mobile-device --device-id ID [--yes] [--service-url URL] [--json]`.

Human formatters `_fmt_mobile_devices` + `_fmt_forget_mobile_device`
echo the label, platform/version, last sync, pending ops count, and the
forget outcome (row removed vs. not registered, op cancellation count).

Confirmation flow on `forget-mobile-device`:

- Default: interactive prompt that requires typing `y` / `yes` to
  proceed. `n` / EOF cancels (prints `Cancelled.`, no HTTP issued).
- `--yes` / `-y`: skip the prompt.
- `--json`: skip the prompt (output must stay parseable for scripts).

### Admin dashboard extension

`commitment_dashboards._render_admin_md` gains an optional
`mobile_devices_items` parameter. The render appends a new
"## Mobile devices" section after the existing "Stale sync devices"
section with columns `Device | Label | Platform | App | Last sync |
Pending ops | First seen`. When the service is unreachable the table
collapses to a single `service not configured` / `service unreachable`
line (reuses the existing banner pattern; never silent skip).

`generate_admin_dashboard` now issues six service calls (system-health,
queue-health, delivery-failures, pending-approvals, stale-sync-devices,
**mobile-devices**) and passes all six payloads into the renderer. The
`DashboardResult.written` count now includes the mobile device count.

The existing "Stale sync devices" section also now renders
`label (device_id)` when a `device_label` is present on the row, so
operators no longer have to guess which stale row is which device.

### Tests

- `tests/test_devices_ops.py` (22 cases): admin_ops wrappers (9),
  MCP passthrough (2), CLI human/JSON/confirm paths (6), dashboard
  renderer + integration (5).
- `tests/test_admin_helpers.py` extended for the new sixth response in
  the happy-path dashboard test (`res.written` 3 -> 4).

Baseline was 611; post-Task-42 is 633 (+22).

## Service contract compatibility

- The wrappers tolerate missing keys in the returned `data` shape -- a
  pre-Task-42 service that did not implement `/devices` returns 404
  which propagates as `{ok: False, status_code: 404}` in the envelope.
  The dashboard shows the error banner rather than crashing.
- Response Pydantic models on the service side strictly extend; older
  connectors ignore unknown keys.

## Followups

- If the dashboard ever needs a destructive control surface (a
  "Forget" button next to each device), factor the confirmation prompt
  out of the CLI subcommand into a shared helper so the button can
  reuse the same text.
- When Task 46 lands (per-token device scoping), the list endpoint
  starts returning a scoped subset rather than the full fleet. No
  connector change needed -- the wrapper just passes through.
