---
title: Vault import / migration walkthrough
status: verified
owner: obsidian-connector
last_reviewed: 2026-04-14
---

# Vault import / migration walkthrough (Task 43)

This page describes the connector half of Task 43 -- bringing a
pre-existing Markdown vault (or a folder of legacy notes) into the
zero-touch capture pipeline without corrupting state and without
introducing a new write path. The service half lives in
``obsidian-capture-service`` (PR #23, merge ``496bb35``) and only adds
two tiny contracts: a deterministic idempotency key convention and an
``import_metadata`` echo on ``/api/v1/ingest/text`` responses.

All scanning / classification / planning / execution / report logic
runs in this repo, in
[``obsidian_connector/import_tools.py``](../../obsidian_connector/import_tools.py).

## Five-phase model

1. **Scan** -- walk a directory and yield ``FileCandidate`` rows in
   deterministic (sorted) path order.
2. **Classify** -- decide whether each candidate is a live capture
   (``ready_capture``), an already-system-managed note
   (``already_managed``), or unknown (``unknown``).
3. **Plan** -- group the classified candidates into actionable buckets
   plus a warnings list. This is the safe, no-HTTP step.
4. **Execute** -- POST the ``ready_capture`` bucket to
   ``/api/v1/ingest/text`` with a deterministic
   ``X-Idempotency-Key: vault-import-<sha256[:16]>`` so re-runs collapse
   on the service-side dedup substrate.
5. **Report** -- write a Markdown summary under
   ``Analytics/Import/<timestamp>.md``.

## Safety rails (read this before --execute)

The pipeline is deliberately paranoid because importing is the only
zero-touch path that can fan out a single misconfigured invocation
into thousands of POSTs. The defaults all bias toward *no mutation*:

| Rail | Default | How to opt out |
|------|---------|----------------|
| ``execute_import(dry_run=True)`` | dry-run | pass ``dry_run=False`` AND ``confirm=True`` |
| CLI ``--dry-run`` flag | on | use ``--execute`` |
| CLI confirmation | required | pass ``--yes`` (or answer ``yes`` at the prompt) |
| ``max_files`` cap | 1000 | pass ``--max-files N`` (and accept the risk) |
| Per-file failure | non-fatal | the loop continues; failure is recorded in the report |
| Throttle between POSTs | 0.1s | pass ``--throttle 0`` to disable |

``execute_import`` also refuses to mutate when only one of the two
opt-ins is supplied -- ``confirm=True`` alone or ``dry_run=False``
alone both yield a no-op result with ``dry_run=true``. Both flags
must be present for a real POST to occur.

## Classifier rules (deterministic, no LLM)

Order of evaluation (first match wins):

1. Frontmatter ``type: commitment`` -> ``already_managed``.
2. Frontmatter ``type: entity`` -> ``already_managed``.
3. Path under ``Commitments/``, ``Entities/``, ``Dashboards/``,
   ``Analytics/``, or ``Archive/`` -> ``already_managed``.
4. ``#capture`` tag (in body or frontmatter ``tags``) -> ``ready_capture``
   (high confidence).
5. ``#idea`` / ``#todo`` / ``#action`` tag -> ``ready_capture``
   (low confidence).
6. Small file (< 300 bytes) without any tags -> ``unknown``.
7. Otherwise -> ``unknown``.

Tags inside fenced code blocks (``\`\`\````) are ignored to avoid
false positives from things like ``#include`` in C snippets.

## Idempotency key convention

The connector builds keys as:

```
vault-import-<sha256_hex[:16]>
```

The hash is computed over the full file body (including frontmatter).
The service already dedupes on ``X-Idempotency-Key`` (repeat key with
identical body -> replay the same ``capture_id``) and on content hash
(different key with same content -> same ``capture_id`` with
``duplicate: true``). Either path produces the same end state: re-running
``obsx execute-import`` against the same vault collapses to the prior
``capture_ids`` and does not mutate any rows.

## End-to-end walkthrough

```bash
# 1. Scan + plan -- safe, no HTTP. Inspect the buckets.
obsx plan-import --root ~/vaults/old-notes
obsx plan-import --root ~/vaults/old-notes --json | jq '.data | keys'

# Narrow the scope with globs (repeatable; --exclude wins over --include).
obsx plan-import --root ~/vaults/old-notes \
    --include 'Inbox/**/*.md' \
    --include 'Notes/**/*.md' \
    --exclude 'Archive/**' \
    --exclude '.obsidian/**'

# 2. Dry-run execute -- still no HTTP. Same call surface as the real run.
obsx execute-import --root ~/vaults/old-notes --service-url http://localhost:8787

# 3. Real execute. Both --execute AND --yes (or interactive prompt) required.
obsx execute-import --root ~/vaults/old-notes \
    --service-url http://localhost:8787 \
    --execute --yes \
    --throttle 0.2 \
    --report

# 4. Verify in the vault.
cat ~/vaults/old-notes/Analytics/Import/*.md | head -60

# 5. Re-run the exact same command -- the service collapses on dedup,
#    every posted result reports duplicate=true and the vault state is
#    unchanged. This is the round-trip integrity check.
obsx execute-import --root ~/vaults/old-notes \
    --service-url http://localhost:8787 \
    --execute --yes
```

## MCP tools

| Tool | Mutates? | Safety |
|------|---------|--------|
| ``obsidian_plan_import`` | No | Pure planning. No HTTP. |
| ``obsidian_execute_import`` | Optional | ``dry_run=true`` default. Requires ``dry_run=false`` AND ``confirm=true`` to POST. |

Both tools accept the same scoping arguments as the CLI (``include_globs``,
``exclude_globs``, ``min_size``, ``max_size``, ``max_files``).

## Report shape

The Markdown report under ``Analytics/Import/<ts>.md`` carries:

- frontmatter (``type: import-report``, started_at / finished_at,
  dry_run flag, root, all bucket counts);
- a Summary section;
- a Warnings section (only when warnings exist; e.g., duplicate
  content hashes within the planned set);
- Planned imports table (path / confidence / bytes / idempotency key);
- Post results table (only when ``executed``: status / capture_id /
  duplicate / import_metadata echoed / error);
- Skipped sections (already managed, size out of range, unknown kind).

The report is rendered through ``write_manager.atomic_write`` so it is
crash-safe and lands inside the vault's allowed write roots.

## Round-trip integrity check

When the request body sets ``context.entrypoint = "vault_import"`` and
``context.extra.source_path`` / ``source_modified_at``, the service
response carries an ``import_metadata`` block echoing those values
back. The connector verifies this on success and reports the result in
``ImportFileResult.import_metadata_echoed``. If the echo does not match,
the result is still ``ok=True`` but the report column reads ``no``,
which is a strong signal the service or the connector is rolling out a
mismatch -- worth investigating before scaling the import.

## What this module does NOT do

- It does not write anything into the source vault other than the
  optional report.
- It does not modify or move source files.
- It does not generate commitments or entity notes -- that is the
  service's job, downstream of the ingest.
- It does not call any LLM. Classification is rule-based; the body
  text is passed verbatim to the service.
- It does not embed or vectorize anything.

## Related

- Service-side ADR: ``../../../obsidian-capture-service/docs/architecture/task_43_import.md``.
- Hardening (timeout, scheme allowlist, no-raise envelope) inherited from Task 35.
- Dedup substrate: ``../../../obsidian-capture-service/docs/architecture/task_21b_dedup_intelligence.md``.
