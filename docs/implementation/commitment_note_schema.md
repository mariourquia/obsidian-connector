---
title: Commitment note schema
status: stable
owner: obsidian-connector
last_reviewed: 2026-04-12
---

# Commitment note schema

This document specifies how `obsidian-capture-service` action objects are
represented as notes inside an Obsidian vault. The representation is
produced by `obsidian_connector.commitment_notes` and is the vault-side
counterpart to the `actions` table in the capture service.

The capture service remains the system of record. Commitment notes are a
projection of that state into the vault -- human-navigable, backlinkable,
and safe to edit in the designated user region.

## Goals

- One action on the service side = exactly one commitment note in the
  vault, at a deterministic path.
- Repeated syncs update the same note in place. No duplicates, no
  orphans.
- Status transitions (`open` -> `done`) move the file between the
  `Open/` and `Done/` buckets so folder-level queries stay cheap.
- Follow-up activity (status changes, due-date changes, priority
  changes) is appended to a log section so the note has a readable
  history without consulting the service.
- A clearly marked "user notes" region is preserved verbatim across
  syncs so humans can edit the note without losing their work.

## Non-goals (for this milestone)

This module deliberately does not:

- expose MCP tools
- build dashboards or aggregate views
- subscribe to events or poll the service
- read or write the SQLite database

Those concerns belong to later tasks (Task 6+).

## Path layout

```
Commitments/
  Open/
    YYYY/
      MM/
        <slug>-<id7>.md
  Done/
    YYYY/
      MM/
        <slug>-<id7>.md
```

- `YYYY/MM` is derived from the action's `created_at` field, not from
  the current clock. This keeps the file's month partition stable even
  if the note is completed months later.
- `<slug>` is a lowercased, hyphen-collapsed version of the action
  title, clamped to 60 characters.
- `<id7>` is the last 7 characters of `action_id` (lowercased), used as
  a stable, unique suffix so identical titles never collide.

The bucket (`Open` or `Done`) is determined by the action's `status`
field, not the filename. Moving between `open` and `done` relocates the
file and records the transition in the follow-up log.

## Frontmatter schema

Every commitment note begins with a YAML frontmatter block containing
the following fields, in this order:

| Field                    | Type                 | Notes                                                                    |
| ------------------------ | -------------------- | ------------------------------------------------------------------------ |
| `type`                   | constant             | Always `commitment`. Lets graph queries filter by note type.             |
| `action_id`              | string (required)    | ULID-style id minted by the capture service. Used for idempotent lookup. |
| `capture_id`             | string (required)    | Id of the source capture the action was extracted from.                  |
| `title`                  | string (required)    | Quoted when it contains YAML-special characters.                         |
| `project`                | string or `null`     | Project slug the action belongs to, if any.                              |
| `status`                 | enum                 | `open` or `done`.                                                        |
| `priority`               | string               | Free-form (e.g. `low`, `normal`, `high`). Defaults to `normal`.          |
| `due_at`                 | ISO 8601 or `null`   | Target completion time with offset.                                      |
| `postponed_until`        | ISO 8601 or `null`   | Snooze fence; mirrors `actions.not_before`.                              |
| `requires_ack`           | boolean              | Whether the user must explicitly acknowledge completion.                 |
| `escalation_policy`      | string or `null`     | Human label (policy name), not the policy id.                            |
| `channels`               | YAML flow list       | Notification channels, e.g. `[push, sms]`. Empty list when unset.        |
| `source_note`            | vault path or `null` | Relative path of the originating capture note.                           |
| `service_last_synced_at` | ISO 8601             | UTC timestamp written by the renderer every sync.                        |

Unknown additional keys are ignored by the reader but are permitted --
the parser only touches the fields it cares about.

## Body structure

The body is a fixed set of sections. Section ordering is stable so
tooling can locate sections by heading.

```
# <title>

<description or "_No description provided._">

## Metadata
- Created: <created_at>
- Status: <status>
- Priority: <priority>
- Due: <due_at | "null">
- Postponed until: <postponed_until | "null">
- Requires acknowledgement: <yes|no>
- Escalation policy: <escalation_policy | "null">
- Channels: <comma list | "none">
- Completed: <completed_at>           # only when status == "done"

## Source Capture
- [[<source_note without .md>|Source capture]]

## Follow-up Log
<!-- service:follow-up-log:begin -->
- <iso> -- note created (status=open)
- <iso> -- status change: open -> done
- <iso> -- priority change: normal -> high
- <iso> -- due_at change: 2026-04-15T17:00:00+00:00 -> null
- <iso> -- postponed_until change: null -> 2026-04-20T09:00:00+00:00
<!-- service:follow-up-log:end -->

## Notes
<!-- service:user-notes:begin -->
_User-editable area below. Content here is preserved across syncs._
<!-- service:user-notes:end -->
```

### Follow-up log rules

- The log is bounded by HTML comment fences:
  `<!-- service:follow-up-log:begin -->` and `:end`.
- On first write, the log is seeded with a single `note created` entry.
- On each subsequent write, the renderer diffs the incoming
  `ActionInput` against the frontmatter currently on disk. Only fields
  the module tracks produce log lines: `status`, `priority`, `due_at`,
  `postponed_until`.
- Identical resyncs (no diff) do **not** append a log entry. The
  `service_last_synced_at` frontmatter field is updated regardless.
- Log entries are append-only. Historical entries are never rewritten.

### User notes rules

- The notes region is bounded by `<!-- service:user-notes:begin -->`
  and `:end`.
- On first write, the region contains a placeholder line describing
  its purpose.
- On subsequent writes, the entire region (including the placeholder
  or whatever the user has replaced it with) is copied forward
  verbatim. The writer never edits content inside the fences.
- Users may remove the placeholder, add arbitrary Markdown, or drop
  backlinks into the region. All of it survives syncs.

## Idempotency contract

Given an `ActionInput` with `action_id = X`, repeated calls to
`write_commitment_note(vault_root, action)` MUST produce the same file
on disk (same path, same inode churn aside). The contract:

1. **Lookup by action_id**, not by path. `find_commitment_note` scans
   `Commitments/**` for a frontmatter match. This means the renderer
   can correctly locate a note even if the user manually renamed or
   moved the file inside the Commitments tree.
2. **Relocation on bucket change.** When the incoming `status` differs
   from the file's current bucket, the writer creates the new file in
   the correct bucket and deletes the old one. The move is recorded
   in the follow-up log.
3. **No duplicates.** After any number of `write_commitment_note`
   calls for the same `action_id`, exactly one file exists under
   `Commitments/**`.
4. **Failure-safe.** The underlying `atomic_write` writes to a
   temp file and renames, so partial writes cannot corrupt an
   existing note. If the new-location write fails, the old note
   remains in place.

## Validation

`write_commitment_note` refuses to proceed if:

- `action_id` is missing or blank (`ValueError`).
- `status` is not one of `{"open", "done"}` (`ValueError`).

All other fields are treated as advisory -- rendering is lossy where
the source data is messy (e.g., an unparseable `created_at` falls back
to the current UTC date for YYYY/MM bucketing).

## Public API (for Task 6 and beyond)

```python
from obsidian_connector import (
    ActionInput,
    CommitmentWriteResult,
    find_commitment_note,
    render_commitment_note,
    resolve_commitment_path,
    write_commitment_note,
)
```

### `ActionInput`

Frozen dataclass capturing the inputs the renderer needs. Field names
mirror the capture-service `Action` row model where possible. Required
fields: `action_id`, `capture_id`, `title`, `created_at`. All others
are optional with sensible defaults.

### `resolve_commitment_path(vault_root, action) -> Path`

Pure function. Returns the absolute path where the note would live
given the supplied `vault_root` and `ActionInput`. Does not touch the
filesystem.

### `render_commitment_note(action, existing_content=None, now_iso=None) -> str`

Pure function. Returns the full note text (frontmatter + body). When
`existing_content` is supplied, follow-up log entries and the
user-notes region are preserved. `now_iso` is injectable for
deterministic tests.

### `find_commitment_note(vault_root, action_id) -> Path | None`

Linear scan of `Commitments/**/*.md` for a matching `action_id`
frontmatter entry. Returns the first match or `None`.

### `write_commitment_note(vault_root, action, now_iso=None) -> CommitmentWriteResult`

End-to-end entry point. Resolves the target path, looks up any
existing note by `action_id`, preserves log + user-notes blocks,
writes atomically, and relocates-then-deletes the old file if the
bucket changed. Returns a `CommitmentWriteResult` with:

- `path`: the final location of the note
- `created`: `True` when no prior note existed for this `action_id`
- `moved_from`: the previous path if the bucket changed, else `None`

## What Task 6 can call / use

Task 6 (capture-service / connector bridge for action sync) can rely on
the following without further changes in this repo:

1. **Import surface.** The symbols above are exported from
   `obsidian_connector`'s top-level package; there is no need to reach
   into `obsidian_connector.commitment_notes` directly.
2. **Idempotent `write_commitment_note`.** Task 6 can call it once per
   action on every sync tick without risk of duplicate files or lost
   user edits. If the action's status moved to `done`, the writer
   relocates the file and returns `moved_from` so the caller can
   audit-log the move if desired.
3. **`resolve_commitment_path` for dry-run / diff.** Task 6 can
   compute the target path ahead of writing to show the user a plan.
4. **`find_commitment_note` for backfill.** Task 6 can check whether
   an action already has a vault representation before deciding to
   write, useful for one-shot backfills.
5. **Plain-string frontmatter parser.** `parse_frontmatter` (imported
   from `obsidian_connector.commitment_notes`) handles the flat
   key/value format used here without adding a YAML dependency.
6. **Audit trail.** `write_commitment_note` already funnels through
   `atomic_write`, which logs to `obsidian-connector`'s audit trail
   under the tool name `obsidian-connector/commitment-notes`. Task 6
   does not need to log again.

Things Task 6 will need to provide that this module does not:

- Mapping from `EscalationPolicy.policy_id` to a human label for the
  `escalation_policy` field.
- Mapping from `Delivery.channel` rows (or the policy steps JSON) to
  the `channels` list.
- Resolution of `Capture.note_path` to the relative vault path used
  for `source_note`.
- The trigger for when to call `write_commitment_note` (poll, webhook,
  scheduled tick).

## Related modules

- `obsidian_connector.write_manager` -- atomic write primitive and
  audit logging.
- `obsidian_connector.draft_manager` -- precedent for fenced,
  service-managed regions inside a vault note.
- `obsidian-capture-service/app/models_actions.py` -- upstream
  `Action` row model.
