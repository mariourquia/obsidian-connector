---
title: Commitment Commands
status: verified
owner: mariourquia
last_reviewed: 2026-04-12
---

# Commitment Commands

Seven MCP tools and CLI subcommands for inspecting and updating commitment
note state.  These commands operate on the `Commitments/` tree in the vault
and optionally sync status back to `obsidian-capture-service` when the
service integration is configured.

## Overview

| Command | MCP Tool | CLI Subcommand | Mutates vault | Service sync |
|---|---|---|---|---|
| List commitments | `obsidian_commitments` | `commitments` | No | No |
| Get single commitment | `obsidian_commitment_status` | `commitment-status` | No | No |
| Mark done | `obsidian_mark_done` | `mark-done` | Yes | PATCH (optional) |
| Postpone | `obsidian_postpone` | `postpone` | Yes | PATCH (optional) |
| Add reason | `obsidian_add_reason` | `add-reason` | Yes | No |
| Due soon | `obsidian_due_soon` | `due-soon` | No | No |
| Sync from service | `obsidian_sync_commitments` | `sync-commitments` | Yes | GET (required) |

All commands operate on commitment notes at `Commitments/Open/` and
`Commitments/Done/` within the vault.  See
[`commitment_note_schema.md`](commitment_note_schema.md) for the note
format specification.

## Implementation

Business logic lives in `obsidian_connector/commitment_ops.py`.  MCP
registrations are in `mcp_server.py`; CLI subcommands and formatters are
in `cli.py`.

```
obsidian_connector/
  commitment_notes.py   ← renderer, writer, find (existing)
  commitment_ops.py     ← list, inspect, mutate, sync (new)

obsidian_connector/mcp_server.py   ← 7 new @mcp.tool() registrations
obsidian_connector/cli.py          ← 7 new subcommands + formatters
scripts/commitment_ops_test.py     ← test suite (35 cases)
```

## Service integration

Set these environment variables to enable service sync:

```bash
export OBSIDIAN_CAPTURE_SERVICE_URL="https://your-capture-service.example.com"
export OBSIDIAN_CAPTURE_SERVICE_TOKEN="your-api-token"   # optional, Bearer auth
```

When these are not set, `mark-done` and `postpone` write locally only and
return no `service_sync` key.  `sync-commitments` returns
`{"ok": false, "error": "service not configured"}` and does not touch the
vault.

Service calls use `http.client` with `ssl.create_default_context()` for
HTTPS.  Non-http/https schemes are rejected before any connection attempt.
Failures are non-fatal for mutating commands (the local write always
completes first).

## Commands

### `obsidian_commitments` / `commitments`

List commitment notes with optional filtering.

**MCP:**
```json
{
  "status": "open",
  "project": "obsidian-connector",
  "priority": "high"
}
```

**CLI:**
```bash
obsx commitments --status open --project obsidian-connector --priority high
obsx commitments --json   # canonical JSON envelope
```

**Returns:** array of commitment summaries with `action_id`, `title`,
`status`, `priority`, `project`, `due_at`, `postponed_until`,
`requires_ack`, `path`.

---

### `obsidian_commitment_status` / `commitment-status`

Return the current state of one commitment.

**MCP:**
```json
{ "action_id": "ACT-OPS-TEST-0000001" }
```

**CLI:**
```bash
obsx commitment-status ACT-OPS-TEST-0000001
obsx commitment-status ACT-OPS-TEST-0000001 --json
```

**Returns:** single commitment dict, or error envelope with
`type: "NotFound"` when the action_id is not in the vault.

---

### `obsidian_mark_done` / `mark-done`

Mark a commitment as done and move it to the Done bucket.

**MCP:**
```json
{
  "action_id": "ACT-OPS-TEST-0000001",
  "completed_at": "2026-04-13T10:00:00+00:00"
}
```

**CLI:**
```bash
obsx mark-done ACT-OPS-TEST-0000001
obsx mark-done ACT-OPS-TEST-0000001 --completed-at 2026-04-13T10:00:00+00:00
obsx mark-done ACT-OPS-TEST-0000001 --dry-run
```

**Returns:**
```json
{
  "ok": true,
  "action_id": "ACT-OPS-TEST-0000001",
  "previous_status": "open",
  "status": "done",
  "completed_at": "2026-04-13T10:00:00+00:00",
  "path": "Commitments/Done/2026/04/deploy-the-ops-module-0000001.md",
  "moved_from": "Commitments/Open/2026/04/deploy-the-ops-module-0000001.md",
  "service_sync": { "ok": true, "status_code": 200 }
}
```

`service_sync` is omitted when service integration is not configured.
`moved_from` is `null` when the file was already in Done.

---

### `obsidian_postpone` / `postpone`

Set or update `postponed_until` on an open commitment.

**MCP:**
```json
{
  "action_id": "ACT-OPS-TEST-0000001",
  "until": "2026-05-01T00:00:00+00:00"
}
```

**CLI:**
```bash
obsx postpone ACT-OPS-TEST-0000001 --until 2026-05-01T00:00:00+00:00
obsx postpone ACT-OPS-TEST-0000001 --until 2026-05-01T00:00:00+00:00 --dry-run
```

**Returns:**
```json
{
  "ok": true,
  "action_id": "ACT-OPS-TEST-0000001",
  "status": "open",
  "postponed_until": "2026-05-01T00:00:00+00:00",
  "path": "Commitments/Open/2026/04/deploy-the-ops-module-0000001.md"
}
```

---

### `obsidian_add_reason` / `add-reason`

Append a timestamped reason or note to a commitment's user-editable section.
Content is preserved across future service syncs.

**MCP:**
```json
{
  "action_id": "ACT-OPS-TEST-0000001",
  "reason": "Blocked by external review; revisit after 2026-05-01"
}
```

**CLI:**
```bash
obsx add-reason ACT-OPS-TEST-0000001 "Blocked by external review; revisit after 2026-05-01"
obsx add-reason ACT-OPS-TEST-0000001 "..." --dry-run
```

**Returns:**
```json
{
  "ok": true,
  "action_id": "ACT-OPS-TEST-0000001",
  "reason_added": "Blocked by external review; revisit after 2026-05-01",
  "timestamp": "2026-04-12T17:45:00+00:00",
  "path": "Commitments/Open/2026/04/deploy-the-ops-module-0000001.md",
  "status": "open"
}
```

---

### `obsidian_due_soon` / `due-soon`

List open commitments due within the next N days.

**MCP:**
```json
{ "within_days": 7 }
```

**CLI:**
```bash
obsx due-soon
obsx due-soon --within-days 7
obsx due-soon --json
```

**Returns:** array of commitment summaries with an added `overdue: bool`
field, sorted earliest-due first.

---

### `obsidian_sync_commitments` / `sync-commitments`

Fetch all open actions from the capture service and write them as vault
notes.  Idempotent: existing notes are updated, new ones are created.

**MCP:**
```json
{ "service_url": "https://capture.example.com" }
```

**CLI:**
```bash
obsx sync-commitments
obsx sync-commitments --service-url https://capture.example.com
obsx sync-commitments --dry-run
```

**Returns on success:**
```json
{
  "ok": true,
  "synced": 12,
  "errors": [],
  "source_url": "https://capture.example.com/actions?status=open&limit=200"
}
```

**Returns on failure (service not configured or unreachable):**
```json
{
  "ok": false,
  "error": "service not configured (set OBSIDIAN_CAPTURE_SERVICE_URL)"
}
```

## Example agent usage

```
# Check what commitments are due this week
obsidian_due_soon(within_days=7)

# Mark a commitment done after completing the work
obsidian_mark_done(action_id="ACT-OPS-TEST-0000001")

# Postpone a commitment that is blocked
obsidian_postpone(action_id="ACT-OPS-TEST-0000001", until="2026-05-01T00:00:00+00:00")
obsidian_add_reason(action_id="ACT-OPS-TEST-0000001", reason="Blocked on external review")

# Pull latest open actions from the capture service into the vault
obsidian_sync_commitments()

# Audit all commitments for a specific project
obsidian_commitments(project="obsidian-connector", status="open")
```

## Error handling

All commands return a canonical JSON envelope with `"ok": false` on error:

```json
{
  "ok": false,
  "error": {
    "type": "NotFound",
    "message": "commitment not found: 'ACT-DOES-NOT-EXIST'"
  }
}
```

Common error types:

| type | cause |
|---|---|
| `NotFound` | `action_id` not in vault |
| `ValueError` | empty `reason`, invalid status, malformed input |
| `VaultNotFound` | vault cannot be resolved |
| `OSError` | file I/O failure |

## Tests

```bash
python3 scripts/commitment_ops_test.py     # 35 test cases
python3 scripts/commitment_notes_test.py   # 28 cases (underlying module)
```

The test suite covers local-only paths (no service configured), service
unavailable (unreachable host), non-http scheme rejection, mock service
responses, and partial-failure tolerance during sync.
