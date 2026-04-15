---
title: Task 26 - Review Dashboards
status: frozen
owner: obsidian-connector
last_reviewed: 2026-04-14
---

# ADR: Task 26 -- Review dashboards and inbox review flows

## Context

After Task 27 (rich metadata) landed, commitment notes carry
``lifecycle_stage``, ``urgency``, ``source_app``, ``source_entrypoint``,
``people``, and ``areas`` alongside the existing ``status``, ``priority``,
``project``, ``due_at``, and ``postponed_until`` fields.  Task 12 already
built four baseline dashboards under ``Dashboards/`` but those surfaces
answer "what is out there?" -- they do not help with the *review* loop:
"what came in today?", "what is stuck?", "what should I be merging?".

The product needs Daily and Weekly review surfaces plus a Stale view for
grooming and a Merge Candidates view for safe deduplication review.

## Decision

Extend ``obsidian_connector/commitment_dashboards.py`` with four new
Markdown dashboards under ``Dashboards/Review/``:

- ``Daily.md`` -- today's slice (captured / due / overdue / completed /
  blocked-waiting).
- ``Weekly.md`` -- captured-this-ISO-week, completed-this-ISO-week,
  still-open-from-last-week, stale (> *stale_days* with no movement), top
  projects by open volume.
- ``Stale.md`` -- any open commitment with ``updated_at`` older than
  *stale_days* (default 14) OR stuck in ``lifecycle_stage in (inbox,
  triaged)`` for more than 3 days, sorted by staleness descending.
- ``Merge Candidates.md`` -- heuristic-only pair suggestions: same
  project + title token-Jaccard >= 0.6 + both open + ``created_at``
  within 14 days of each other.  Review-only; the actual merge is a
  human decision (the real dedup intelligence is Task 21.B).

The existing ``generate_postponed_dashboard`` is extended with a
"Stale postponements" section at the top for postponements whose
``postponed_until`` has elapsed without a status change.

## Key design choices

### Reuse, do not rewrite

The new surfaces plug into the existing substrate:

- ``_scan_commitments(vault_root)`` is the single source of truth for
  vault state; each renderer consumes the list it returns directly.
- Sorting keys (``_key_due``, ``_key_postponed``) and rendering helpers
  (``_wikilink``, ``_wikilink_table``, ``_fmt_date``, ``_frontmatter``)
  are reused so the review dashboards feel identical to the originals
  and diffs stay minimal.
- Writes go through ``atomic_write`` (see ``write_manager.py``) with
  ``inject_generated_by=False`` so the frontmatter stays clean.

### CommitmentSummary gained four new fields

``CommitmentSummary`` grew backward-compatible slots for
``created_at``, ``updated_at``, ``lifecycle_stage``, ``urgency``,
``source_app``, ``source_entrypoint``, ``people``, and ``areas``.
``created_at`` comes from the body ``- Created:`` line (the renderer
puts it there, not in frontmatter); ``updated_at`` reads the
frontmatter ``service_last_synced_at`` slot.  Existing callers do not
need to pass anything new: pre-Task-26 notes hydrate with safe defaults
(``lifecycle_stage='inbox'``, ``urgency='normal'``, empty tuples).

### Determinism

Every review renderer accepts a ``now_iso`` argument (default
``datetime.now(timezone.utc).isoformat()``) that is threaded through
every time-relative calculation (today's date, ISO week bounds,
staleness age, merge created_at window).  Given a fixed vault and a
fixed ``now_iso`` the rendered bytes are identical across runs -- the
only delta between production calls is the ``generated_at`` field.

### Merge heuristic is pure + testable

``title_jaccard(a, b)`` and ``_compute_merge_candidates`` are exported
as pure functions.  Tokens are lowercase, alphanumeric only, with a
short English stop-word list.  No embeddings.  The output is
deterministic because pairs are canonicalised by sorted path before
sorting, and results are ordered by ``(-score, path_a, path_b)``.

### Orchestrator + single-refresh

- ``update_all_review_dashboards(vault_root, now_iso=None,
  stale_days=14, merge_window_days=14, merge_jaccard=0.6)`` writes the
  four review surfaces in one call.
- ``update_all_dashboards(...)`` was extended to call
  ``update_all_review_dashboards`` after the four commitment dashboards
  so a single refresh keeps the eight dashboards in sync.  The return
  list grew from 4 to 8 items; the prefix order is stable for any
  caller that indexes by position.

### CLI + MCP

- CLI: ``obsx review-dashboards [--stale-days N] [--merge-window-days N]
  [--merge-jaccard X] [--now ISO] [--json]`` -- on-demand refresh.
- MCP: ``obsidian_review_dashboards(stale_days, merge_window_days,
  merge_jaccard, now, vault)`` -- same semantics, JSON envelope.

Both surface ``[path, written]`` tuples so callers can verify which
files were written and how many items made it into each surface.

## Alternatives considered

- **Dataview queries inside Markdown**: ruled out because not all users
  have Dataview installed, and the deterministic-bytes contract matters
  for Git-backed vaults.
- **Server-side rendering**: ruled out because dashboards are a vault
  projection in the connector's scope (capture-service remains the
  system of record).
- **Embedding-based merge detection**: deferred to Task 21.B; Jaccard
  keeps the substrate dependency-free and deterministic.
- **Separate orchestrator per review surface**: we could have kept the
  four review surfaces entirely out of ``update_all_dashboards`` to
  preserve the 4-item return tuple, but then callers wiring a cron
  refresh would have to call two orchestrators.  A single refresh
  matches the product spec.

## Consequences

- ``update_all_dashboards`` return length went from 4 to 8.  Two
  legacy tests in ``scripts/commitment_dashboards_test.py`` were
  updated to assert the new expected set.  The ordering of the first
  four entries is unchanged.
- Vaults gain a new directory ``Dashboards/Review/`` on first refresh.
- Pre-Task-26 commitment notes work unchanged; the new
  ``CommitmentSummary`` fields default to safe values.
- Test count grew from 141 + 1 skipped to 179 + 1 skipped in the
  connector pytest suite (38 new tests in
  ``tests/test_review_dashboards.py``).

## References

- Implementation doc: ``docs/implementation/commitment_dashboards.md``
- Pure heuristics: ``obsidian_connector.commitment_dashboards.title_jaccard``,
  ``_compute_merge_candidates``
- Rich-metadata ADR (upstream): ``obsidian-capture-service/docs/architecture/task_27_rich_metadata.md``
