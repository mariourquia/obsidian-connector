# Task 30 -- First-pass entity wiki body (connector side)

Status: accepted, shipped 2026-04-14

## Context

The service side (Task 30 ADR in `obsidian-capture-service`) now
exposes `related_entities_by_kind`, `first_seen_at`, and
`last_activity_at` on `GET /api/v1/entities/{id}` and forwards them
through `sync_entity_to_vault()` to the connector. The connector side
uses that projection to render a deterministic Markdown body inside
the `service:entity-wiki:begin/end` fence.

Task 15.A introduced the fence and left it empty pending Task 15.C
(LLM overview). Task 30 fills that gap without introducing an LLM
dependency.

## Decisions

### 1. Pure function, deterministic output

`render_first_pass_wiki_body(entity, related_entities_by_kind=None)`
is a pure function on `(EntityInput, projection map)`. Given the same
inputs it returns byte-identical Markdown. A test pins this invariant.

Determinism matters because:

- Re-running the writer with no state change should not perturb
  snapshots or hashed audit trails.
- The scaffold is rendered at every push; avoiding noise in the diff
  is a usability property.

### 2. Fence contract is the only API

The fence contract between the connector and any future LLM pipeline
(Task 15.C) is:

    <!-- service:entity-wiki:begin -->
    <body>
    <!-- service:entity-wiki:end -->

`<body>` comes from `EntityInput.wiki_content` when the caller sets it,
otherwise from `render_first_pass_wiki_body(entity)`. The connector
never parses `<body>`; it only writes the envelope. Task 15.C therefore
does not need to change any connector code: it just populates
`wiki_content`.

Legacy behaviour is preserved for pre-Task-30 EntityInputs (no
projection, no actions, no timestamps): existing fence contents are
preserved on re-render. This keeps early 15.A vaults untouched.

### 3. `EntityInput` gains three frozen fields

- `related_entities_by_kind: dict[str, list[dict]]` -- maps kind to a
  list of `{entity_id, canonical_name, kind, slug, co_occurrence_count}`
  dicts. Every kind the service knows about appears as a key (empty
  list when no peers exist).
- `first_seen_at: str | None` -- `entities.created_at` upstream.
- `last_activity_at: str | None` -- most recent linked action's
  `created_at`.

Defaults are empty / None so older callers (capture-service < Task 30)
still construct `EntityInput` without friction.

### 4. Layout is kind-conditioned, subsections degrade gracefully

Each entity kind has a fixed set of peer subsections:

- `person` -> "Projects this person appears in", "Areas".
- `project` -> "People involved", "Areas".
- `area` -> "Projects in this area", "People".
- `topic` -> "Related projects", "People".
- `tool` / `org` / `place` -> "Related projects", "People".

Plus activity subsections ("Open commitments on this project" etc.)
that reuse `EntityInput.open_actions` / `done_actions`. Empty peer
lists render `_No linked data yet._` so the fence has a consistent
shape regardless of data volume.

### 5. Wikilinks use the canonical entity path

Peer bullets render as `[[Entities/<Kind>/<slug>|name]] (count)` so
Obsidian can navigate directly without a separate alias index. When
a peer dict lacks `slug` (defence against partial service payloads),
the bullet falls back to `- name`.

### 6. Service-first trigger

The canonical trigger for rendering remains
`sync_entity_to_vault()` in the capture service. No polling from the
connector, no re-fetches. The service computes the projection once,
forwards it via the kwarg-filtered bridge, and the connector writes.

## Files

- `obsidian_connector/entity_notes.py` -- new `EntityInput` fields,
  `render_first_pass_wiki_body`, fence substitution logic, kind-
  conditioned layout tables.
- `obsidian_connector/__init__.py` -- surfaces `render_first_pass_wiki_body`.
- `tests/test_entity_wiki_foundations.py` -- +22 tests covering
  body shape, peer kinds, placeholders, determinism, fence
  preservation, user-notes preservation, long aliases, and re-render
  idempotency.

## Upgrade path to Task 15.C

The LLM pipeline will:

1. Pull `GET /api/v1/entities/{id}` for aliases, actions, and the
   Task 30 projection payload.
2. Generate an LLM body using those facts as prompt context.
3. Set `EntityInput.wiki_content` on the push and call through the
   existing `connector_write_entity_note` surface.

No connector changes required. The scaffold becomes the fallback path
when the LLM call errors or is disabled.

## TODO: commitment_ops entry point

`obsidian_connector/commitment_ops.py` does not currently fetch
entity data from the service — entity notes are populated exclusively
by the capture-service bridge (`sync_entity_to_vault()`). If a future
direct-fetch entry point is added to `commitment_ops`, it will need to
thread the same projection payload through `EntityInput`. Until then
the bridge remains the only producer.
