---
title: Shared vault support (Task 37)
status: verified
owner: mariourquia
last_reviewed: 2026-04-16
---

# Shared vault support

A first-pass treatment of running the obsidian-connector against a vault
that lives on iCloud Drive, Dropbox, OneDrive, or Obsidian Sync and is
written to from more than one device by the same user. "Shared" here is
strictly single-user multi-device. Multi-user collaboration is out of
scope per the product spec.

## What already works

The connector's write path was designed for this from day one:

- `write_manager.atomic_write` writes every note via `tmp + rename`. On
  POSIX and NTFS the rename is atomic at the filesystem level, so a
  partial file is never visible to the sync daemon picking up changes.
- Every commitment note, entity wiki note, and dashboard has a
  `service:<name>:begin` / `service:<name>:end` fence inside which the
  renderer is idempotent. Text the user types outside the fence is
  preserved across every re-render.
- The service-side sync ops use a deterministic idempotency key (Task 3)
  and the capture service's `sync_operations` table has
  `UNIQUE(idempotency_key)`, so two devices pulling the same op list
  can race safely.
- Task 42 scopes every sync cursor to a `device_id`, so a phone and a
  laptop running the connector against the same vault pull independent
  op streams and never fight for cursor position.

## What the user has to set up

- Put the Obsidian vault inside the synced folder root (e.g.
  `~/iCloud Drive/Obsidian/<vault-name>`). Do NOT put a sub-folder of
  the vault under sync and the rest outside. The connector assumes the
  whole vault moves together.
- Configure `OBSIDIAN_VAULT` or the `--vault` flag to point at that
  path on every device.
- The capture service still runs on one Mac (system of record). Other
  devices reach it via Tailscale or LAN as usual. Task 42 gives each
  device its own `device_id` automatically the first time it calls
  `/sync`.
- Every device needs its own `OBSIDIAN_CAPTURE_SERVICE_TOKEN` value
  (same token is fine for a single user; Task 46 will split these when
  role-based tokens land).

## Conflict files

iCloud, Dropbox, and OneDrive produce their own flavor of conflict file
when they cannot reconcile two simultaneous writes. The connector does
NOT write these; only the sync daemon does. Common patterns:

| Sync provider | Conflict filename pattern |
|---------------|---------------------------|
| iCloud Drive | `Note 2.md` or `Note (Mario's iPhone).md` |
| Dropbox | `Note (Mario's conflicted copy 2026-04-15).md` |
| OneDrive | `Note-DESKTOP-ABC.md` |
| Obsidian Sync | `Note (vault-id).md` |

Recommended operator workflow when you spot one:

1. Open both files side by side in Obsidian.
2. Reconcile manually (the user-notes fence is outside the
   service-rendered block, so any user edit is definitely in the
   non-fence portion of at least one of the two files).
3. Delete the conflict copy.

A future pass can add a `obsx vault-conflicts` helper that scans for
these patterns and surfaces them in `Dashboards/Admin.md`. Not shipped
in Task 37; tracked in the follow-up thread.

## What you should NOT do

- Do not run two connectors (Mac and laptop) with the same vault
  pointed at the same shared folder and expect them to BOTH write
  commitment notes for the same action without conflict files. Pick
  one machine as the "connector host" per user-session. The other
  devices read via Obsidian but let the host write.
- Do not put the capture-service SQLite DB inside the synced folder.
  The DB is the system of record and must stay on one machine. If you
  need it accessible from another machine, expose the service over
  Tailscale instead of syncing the DB file.
- Do not commit conflict files to git if the vault is also a git
  repo. They are not useful history.

## Test posture

This is a docs-first pass. No new code, no new tests. The atomic-write
contract is already covered by `tests/test_hardening.py` (the AST audit
that every writer uses `atomic_write`), and per-device cursor isolation
is covered by `tests/test_devices_ops.py` + the capture-service
`tests/test_mobile_sync_multi_device.py`.

A follow-up task can add:

- `obsx vault-conflicts` CLI detector (deterministic scan, returns
  `{ok, items[{path, provider, detected_pattern}]}`).
- `Dashboards/Admin.md` "Vault conflicts" section.
- `obsidian_vault_conflicts` MCP tool.

## Related

- Task 42: per-device sync state + `forget device` endpoint.
- Task 43: vault import (same atomic-write substrate; safe to run on
  a shared vault because the idempotency-key prefix
  `vault-import-<sha>` collapses re-runs from any device).
- Capture service ADR: `docs/architecture/task_42_cross_device_sync.md`.
