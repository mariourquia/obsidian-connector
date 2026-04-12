---
title: Commitment Dashboards
status: stable
owner: obsidian-connector
last_reviewed: 2026-04-12
---

# Commitment Dashboards

Dashboard notes that aggregate the state of all commitment notes inside a
vault into four human-navigable Markdown files under ``Dashboards/``.  They
are generated (or updated) by ``obsidian_connector.commitment_dashboards`` and
are the read-only, aggregate counterpart to the individual commitment notes
produced by ``commitment_notes.py``.

## Purpose

Commitment notes live at ``Commitments/Open/YYYY/MM/*.md`` and
``Commitments/Done/YYYY/MM/*.md``.  These are great for individual note
context but require Dataview or folder-level inspection to answer
questions like "what is overdue right now?" or "what needs my explicit sign-off?".
The four dashboards answer those questions at a glance.

## Dashboards

| File | Content |
|------|---------|
| ``Dashboards/Commitments.md`` | All commitments: open grouped by project, done as a table |
| ``Dashboards/Due Soon.md`` | Open commitments due within N days (default 7), split overdue vs upcoming |
| ``Dashboards/Waiting On Me.md`` | Open commitments with ``requires_ack: true`` |
| ``Dashboards/Postponed.md`` | Open commitments with ``postponed_until`` set |

## Wikilinks

Every entry in every dashboard links back to its source commitment note via an
Obsidian wikilink:

```
[[Commitments/Open/2026/04/deploy-ops-module-0000001|Deploy the ops module]]
```

- The target is the vault-relative path **without** the ``.md`` extension (Obsidian convention).
- The display text is the commitment ``title``.
- Inside Markdown table cells, the pipe separator is escaped as ``\|``:
  ```
  [[Commitments/Done/2026/04/old-task-0000002\|Old task]]
  ```

## Frontmatter

Every dashboard note has a short YAML frontmatter block:

```yaml
---
type: dashboard
dashboard: commitments   # one of: commitments, due-soon, waiting-on-me, postponed
generated_at: 2026-04-12T10:00:00+00:00
---
```

This allows Obsidian Dataview to query dashboards by type or by which dashboard
they are.

## Determinism and idempotency

Given fixed vault state and a fixed ``now_iso`` argument, every renderer
produces byte-for-byte identical output:

- Project groups are sorted alphabetically (case-insensitive), with ``None``
  project always last.
- Within each group, items are sorted by ``due_at`` ascending (``None`` last),
  then by ``title``.
- Overdue items sort earliest-due first; upcoming items sort earliest-due first.
- Postponed items sort by ``postponed_until`` ascending, then ``title``.
- Done items in ``Commitments.md`` sort by vault path.

Only the ``generated_at`` frontmatter field changes between live runs.

## Public API

```python
from obsidian_connector import (
    DashboardResult,
    generate_commitments_dashboard,
    generate_due_soon_dashboard,
    generate_waiting_on_me_dashboard,
    generate_postponed_dashboard,
    update_all_dashboards,
    DASHBOARDS_DIR,
)
```

### ``update_all_dashboards(vault_root, within_days=7, now_iso=None)``

Generate or update all four dashboards in a single call.

```python
results = update_all_dashboards(vault_root="/path/to/vault")
# returns [DashboardResult, DashboardResult, DashboardResult, DashboardResult]
# one per dashboard, in order: Commitments, Due Soon, Waiting On Me, Postponed
```

### ``generate_commitments_dashboard(vault_root, now_iso=None)``

Write ``Dashboards/Commitments.md``.  ``DashboardResult.written`` is the total
number of commitment entries (open + done) rendered.

### ``generate_due_soon_dashboard(vault_root, within_days=7, now_iso=None)``

Write ``Dashboards/Due Soon.md``.  ``DashboardResult.written`` is the number of
open commitments due on or before ``now + within_days``.

### ``generate_waiting_on_me_dashboard(vault_root, now_iso=None)``

Write ``Dashboards/Waiting On Me.md``.  ``DashboardResult.written`` is the
number of open commitments with ``requires_ack=True``.

### ``generate_postponed_dashboard(vault_root, now_iso=None)``

Write ``Dashboards/Postponed.md``.  ``DashboardResult.written`` is the number
of open commitments with ``postponed_until`` set.

### ``DashboardResult``

```python
@dataclass
class DashboardResult:
    path: Path   # absolute path of the written file
    written: int # number of commitment entries rendered
```

## now_iso injection (for deterministic tests)

All public functions accept an optional ``now_iso`` ISO 8601 string.  When
supplied, it is used as the reference timestamp for ``generated_at``, overdue
detection, and the "due within N days" window.  In production, omit it; the
functions default to ``datetime.now(timezone.utc).isoformat()``.

```python
# deterministic test
result = generate_due_soon_dashboard(
    vault_root=vault,
    within_days=7,
    now_iso="2026-04-12T10:00:00+00:00",
)
```

## Tests

```bash
python3 scripts/commitment_dashboards_test.py     # 36 test cases
```

The suite covers:

- Empty vault (all four dashboards created without error)
- Wikilink format: no ``.md`` extension, vault-relative path
- Link validity: every wikilink target file exists on disk
- Project grouping and sort order
- Open vs done item routing in ``Commitments.md``
- Due Soon: overdue vs upcoming split; window exclusion; done items excluded
- Waiting On Me: ``requires_ack`` filter; done excluded
- Postponed: ``postponed_until`` filter; done excluded; date display in table
- No duplicate entries (same ``action_id`` written twice)
- Idempotency (same vault + same ``now_iso`` -> identical content)
- All four files created by ``update_all_dashboards``
- ``Dashboards/`` directory auto-created
- Table pipe escaping (``\|``) in Done and Postponed tables
- Frontmatter: ``type: dashboard``, ``generated_at`` field

## Related modules

- ``obsidian_connector.commitment_notes`` -- individual note rendering and writing
- ``obsidian_connector.commitment_ops`` -- ``CommitmentSummary`` and ``_scan_commitments``
  (the scan function is an intentional package-internal dependency used directly to avoid
  dict round-tripping)
- ``obsidian_connector.write_manager`` -- ``atomic_write`` used for all file writes
