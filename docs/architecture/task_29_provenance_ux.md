---
title: Task 29 - Source-aware provenance UX polish
status: frozen
owner: obsidian-connector
last_reviewed: 2026-04-14
---

# ADR: Task 29 -- Source-aware provenance UX polish

## Context

Task 27 denormalised ``source_app`` and ``source_entrypoint`` onto every
action row. The capture-service ingest endpoints and sync bridge pass those
values through to the connector's commitment-note writer, and the
frontmatter schema carries them in stable slots. That was enough for
machine consumers (MCP tools, dedup scorer, query filters), but it did
not help the human skimming a commitment note or a daily review
dashboard:

- The existing body rendered ``- Source: wispr_flow via action_button`` --
  accurate, but an opaque pair for anyone not already fluent in the
  capture pipeline vocabulary.
- The Task 26 review surfaces broke captures down by project, lifecycle
  stage, and staleness. Nothing surfaced the *entry point* distribution,
  so a user could not see at a glance "today I captured 5 via Wispr Flow
  and 2 via Apple Notes".

Task 29 closes that gap without introducing new tables, new API fields,
or new sync trips. Everything needed is already on each commitment note.

## Decision

1. **Introduce a single pure function** ``format_source_label(source_app,
   source_entrypoint) -> str`` in ``obsidian_connector.commitment_notes``.
   It maps the Task 27 tuples to a human-readable sentence. Both the
   commitment-note renderer and the review dashboards call this function
   so the label vocabulary stays consistent across surfaces.
2. **Add a "Captured:" row** in the commitment-note body Metadata section,
   alongside (not instead of) the existing ``Source:`` row. Agents keep
   the machine-readable raw tuple; humans see the prose label. Backward
   compatible -- legacy notes without the fields render
   ``- Captured: Unknown source``.
3. **Append a "By source" subsection** to Daily and Weekly review
   dashboards. Each renders a small Markdown table
   ``| Source | Count |`` over the same slice the list section above
   already shows (today's captures for Daily, this-week's captures for
   Weekly). Empty slices render an italic fallback line.

## Label table

| ``source_app``    | ``source_entrypoint`` | Label                                       |
|-------------------|-----------------------|----------------------------------------------|
| ``wispr_flow``    | ``action_button``     | Captured via Wispr Flow (Action Button)      |
| ``wispr_flow``    | ``share_sheet``       | Captured via Wispr Flow (Share Sheet)        |
| ``wispr_flow``    | anything else         | Captured via Wispr Flow                      |
| ``ios_share_sheet`` | any                 | Captured via iOS Share Sheet                 |
| ``apple_notes``   | ``apple_notes_tag``   | Captured from Apple Notes (#capture)         |
| ``apple_notes``   | anything else         | Captured from Apple Notes                    |
| any               | ``queue_poller``      | ``{base label} (via cloud queue)`` (suffix)  |
| ``queue_poller``  | any                   | Captured via cloud queue                     |
| any unrecognised  | any                   | ``Captured from {source_app}``               |
| ``None`` / empty  | ``None`` / empty      | Unknown source                               |

Notes:

- **Queue-poller is a transport marker.** When a cloud-queued capture is
  drained on the Mac side, the poller preserves the original
  ``source_app`` (e.g. ``wispr_flow``) and *overrides* only the
  ``source_entrypoint`` to ``queue_poller``. The label function therefore
  computes the base label from ``source_app`` first, then appends
  ``(via cloud queue)`` so the upstream signal is never lost.
- **The function degrades gracefully.** Whitespace-only and empty inputs
  are coerced to ``None`` so callers need not sanitise frontmatter-parsed
  values before calling.

## Why a pure function

- **One source of truth.** The commitment-note writer, the Daily
  dashboard, and the Weekly dashboard all call the same function so the
  label string never drifts between surfaces. Tests assert exact
  matches, not regex prefixes.
- **No state, no I/O, no mutation.** The function is trivially testable
  (14 dedicated test cases) and trivially reusable from future surfaces
  (CLI listings, MCP result shaping, import/migration tooling).
- **No new keys on the wire.** The service payload is unchanged. The
  frontmatter schema is unchanged. Upgrading only the connector (or
  regenerating dashboards) is enough to get the new UX on existing
  notes.

## Tests

- ``tests/test_provenance_ux.py`` adds 28 tests across three classes:
  ``TestFormatSourceLabel`` (14 cases for every known tuple, suffix,
  fallback, and whitespace handling), ``TestCommitmentCapturedRow`` (7
  rendering cases including legacy notes), and
  ``TestDailyBySource``/``TestWeeklyBySource`` (7 dashboard cases over
  synthetic vaults with fixed ``now_iso`` for determinism).
- The existing Task 27 rich-metadata assertions on the machine-readable
  ``- Source:`` row remain green -- this change is strictly additive.

## Alternatives considered and rejected

- **Replace the ``- Source:`` row with the human label.** Rejected: the
  raw tuple is useful to agents and debug tooling. Keeping both is
  cheap and backward compatible.
- **Render the label inline in the frontmatter.** Rejected: the label is
  a presentation layer, not a schema field. Derived, not stored.
- **Add a dedicated per-source dashboard.** Rejected: the Daily and
  Weekly surfaces already carry the relevant slice context; a separate
  dashboard would duplicate filters and drift.

## Follow-ups

- **Service-side docs.** Shortcut build guides in
  ``obsidian-capture-service/docs/shortcuts/`` cross-link to this label
  table so the iPhone side documents the provenance values the Mac side
  renders. Tracked in the Task 29 service-side PR.
- **Future CLI/MCP surfaces** that return commitment summaries can call
  ``format_source_label`` directly to enrich their output without
  re-deriving.

## References

- Commitment-note schema: ``docs/implementation/commitment_note_schema.md``
- Review dashboards: ``docs/implementation/commitment_dashboards.md``
- Rich-metadata ADR (Task 27):
  ``obsidian-capture-service/docs/architecture/task_27_rich_metadata.md``
- Review-dashboards ADR (Task 26):
  ``docs/architecture/task_26_review_dashboards.md``
