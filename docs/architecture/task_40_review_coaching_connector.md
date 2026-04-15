# Task 40 -- Review coaching (connector side)

Status: accepted, shipped 2026-04-15.

Companion to the capture-service ADR at
`../../obsidian-capture-service/docs/architecture/task_40_review_coaching.md`
(service PR #25, merge commit `19003f0`).

## Context

The service side added a deterministic coaching engine
(`app/coaching.py`) that composes the existing reasoning, dedup, and
delegation surfaces into six recommendation codes
(`CONSIDER_{CANCEL,DELEGATE,MERGE,RECLAIM,RESCHEDULE,UNBLOCK}`), plus
two Bearer-authed read-only endpoints:
`GET /api/v1/coaching/action/{id}` and `GET /api/v1/coaching/review`.

This ADR covers the connector-side surface that wraps those endpoints
for the Python API, MCP, CLI, and review dashboard layers.

## Decisions

### 1. Two thin HTTP wrappers in `coaching_ops.py`

`get_action_recommendations(action_id, *, service_url, token)` wraps
`GET /api/v1/coaching/action/{id}`. URL-encodes `action_id` with
`urllib.parse.quote(..., safe="")` so slashes and other reserved
characters don't break the path split on the service side.

`list_review_recommendations(*, since_days=7, limit=50, service_url, token)`
wraps `GET /api/v1/coaching/review`. Defaults mirror the server-side
defaults exactly; the server clamps out-of-bounds values to the
`[1, 365]` and `[1, 200]` windows so the wrapper can stay naive.

Both functions reuse `commitment_ops._service_get_json` so the Task 35
timeout, scheme-allowlist, and auth behavior is shared with every
other service wrapper. They never raise; failures surface inside the
standard envelope (`{ok: False, status_code?: N, error: "..."}`).

### 2. MCP tools + CLI subcommands

MCP tools in `mcp_server.py`: `obsidian_action_recommendations` and
`obsidian_review_recommendations`. Each is a thin wrapper around the
`coaching_ops` helper, matching the shape every other service-backed
MCP tool uses (JSON dump, catch-all exception envelope, lazy import).

CLI subcommands in `cli.py`: `obsx action-recommendations --action-id ...`
and `obsx review-recommendations [--since-days N] [--limit N]`. Each
supports human and `--json` output and honours `--service-url` for
override. Human formatting uses a two-line-per-rec summary that makes
the action verb + confidence obvious at a glance.

### 3. Review coaching dashboard

`commitment_dashboards.generate_coaching_dashboard(vault_root, *, service_url, token, since_days=7, limit=100, now_iso=None)`
writes `Dashboards/Review/Coaching.md` with one section per
recommendation code:

- **Consider cancel** (N)
- **Consider delegate** (N)
- **Consider merge** (N)
- **Consider reclaim** (N)
- **Consider reschedule** (N)
- **Consider unblock** (N)

Each section shows every action bucketed under that code with title,
action verb, mini "why" line (the rec label), and the action id so
operators can pivot to MCP / CLI to apply the recommendation.
Sections iterate in the fixed alphabetical order of the
`_COACHING_CODE_LABELS` dict so the rendered document is stable.

Service-unreachable and service-unconfigured render the page with a
banner and empty sections -- never silent skip. Always writes via
`atomic_write` so the user-visible surface lands atomically.

### 4. Default-on in `update_all_review_dashboards`

`update_all_review_dashboards(..., include_coaching=True, coaching_since_days=7)`
is the new opt-out flag; default-on because coaching is the primary
review surface Task 40 introduces. Operators who want local-only
review runs pass `include_coaching=False`. Backwards-compatible:
existing callers without the kwarg get the new page by default.

Orchestrator test counts updated accordingly:

- Default review set: 4 -> 5 (Task 38: Delegations) -> **6 (Task 40: Coaching)**.
- Default full stack (`update_all_dashboards`): 12 -> **13**.
- Opt-out shape (`include_coaching=False, include_delegations=False`)
  remains 4 review surfaces.

When the coaching generator itself raises (pathological case), the
orchestrator swallows the exception and lets the rest of the set
complete, matching the Task 38 graceful-degradation pattern.

## Not included

- **No write-back on the vault side.** The dashboard renders nudges;
  operators apply them via MCP / CLI (`obsx delegate-commitment ...`,
  `obsx merge-commitment ...`, the action lifecycle verbs). A future
  task can add click-through automation once the dashboard schema
  stabilises.
- **No nudge deduplication across waves.** If an action has a rec
  this week and the operator declines to act, the rec resurfaces in
  next week's dashboard. Fine for now -- the nudges are stable by
  design, not suppressed after-the-fact.
- **No LLM paraphrasing.** The dashboard uses the server-side
  English labels verbatim; a future task can layer an LLM over the
  `rationale` block to produce per-action prose.

## Tests

`tests/test_coaching_ops.py` covers:

- Wrapper path / query / auth shape for both endpoints.
- Envelope behavior on missing URL, malformed JSON, 404 / 409 / 500
  status codes.
- MCP tool passthrough + JSON envelope.
- CLI human + `--json` output paths, including the 404 friendly
  message.
- Dashboard render (pure): banner on unconfigured, banner on service
  error, section-per-code grouping, alphabetical section order,
  empty-window note, determinism on identical inputs.
- `generate_coaching_dashboard` integration with the fake HTTP
  sequence + atomic write.
- `update_all_review_dashboards` orchestrator: default-on Coaching,
  opt-out via `include_coaching=False`, non-fatal coaching failure.

The existing `tests/test_review_dashboards.py` orchestrator regressions
are updated to reflect the new default review-surface count (6) and
the new full-stack count (13).

## References

- Service ADR: `../../obsidian-capture-service/docs/architecture/task_40_review_coaching.md`
- Service PR #25, merge commit `19003f0`.
- Connector helpers: `obsidian_connector/commitment_ops.py`
  (`_service_get_json`, `_service_timeout`).
- Dashboard module: `obsidian_connector/commitment_dashboards.py`
  (`generate_coaching_dashboard`, `update_all_review_dashboards`).
