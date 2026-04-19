# Agent Instructions -- obsidian-connector

## Quick orientation

Python wrapper for the Obsidian desktop app CLI. Five distribution surfaces:
- **Python API** -- `from obsidian_connector import search_notes, read_note, ...`
- **CLI** -- `obsx search "query"` or `./bin/obsx search "query"`
- **MCP server** -- 100+ tools for Claude Desktop via stdio or HTTP
- **Claude Code plugin** -- `claude --plugin-dir .` or `claude plugin install obsidian-connector`
- **macOS DMG** -- Double-click installer for non-technical users

## Golden rule

**Never call the `obsidian` CLI directly.** Use the MCP tools, Python API,
or CLI wrapper. They handle vault resolution, argument escaping, error
detection, audit logging, and output parsing.

## Navigation hierarchy

Read files in this order (progressive disclosure):
1. `ARCHITECTURE.md` -- module/package layering
2. `TOOLS_CONTRACT.md` -- JSON envelope schema, typed errors, command reference
3. `docs/index.md` -> leaf docs (only as needed)

## Install (Task 33)

Editable install from the repo root exposes the three console scripts the
package ships:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

| Command | Module | Purpose |
|---------|--------|---------|
| `obsidian-connector` | `obsidian_connector.cli:main` | Primary CLI dispatcher |
| `obsx` | `obsidian_connector.cli:main` | Short alias for the CLI |
| `obsidian-connector-mcp` | `obsidian_connector.mcp_server:main` | MCP server (stdio) |

## Update

```bash
git pull --ff-only
pip install -e . --upgrade
obsx doctor                       # sanity check after upgrade
```

See `CHANGELOG.md` for release notes.

## CI / release

Five release surfaces ship from one tag:

| Surface | Manifest | Version source |
|---------|----------|----------------|
| PyPI (`obsx`) | `pyproject.toml` | `[project].version` -- single source of truth |
| Claude Code plugin | `src/plugin/plugin.json`, `builds/claude-code/.claude-plugin/plugin.json` | must match `pyproject.toml` |
| Claude Desktop MCP bundle | `mcpb.json` | must match `pyproject.toml` |
| Runtime (`obsidian_connector.__version__`) | `obsidian_connector/__init__.py` | must match `pyproject.toml` |
| macOS DMG / Windows EXE | installer workflows read `github.ref_name` | must match `pyproject.toml` |

**PyPI distribution.** Published as `obsx` via OIDC Trusted Publishing from `.github/workflows/publish-pypi.yml`; the import name is still `obsidian_connector`. `[tool.hatch.build.targets.wheel] packages = ["obsidian_connector"]` keeps hatchling happy. `[tool.hatch.build] exclude` drops `node_modules`, build caches, and `__pycache__` so broken symlinks under `obsidian_connector/ix_engine/` never crash the wheel.

**Release tag format: `vX.Y.Z` only.** `build-macos-dmg.yml:37` and `build-windows-installer.yml:39` reject anything else (`CFBundleShortVersionString` and Inno Setup's `AppVersion` require numeric X.Y.Z). Post-releases (`vX.Y.Z.postN`), pre-releases (`vX.Y.Z-rc.N`), and PEP 440 epochs all fail the regex and Apple notarization. Use a fresh patch bump (`v0.11.0.post1` -> `v0.11.1`) when a release needs re-running.

**Pre-tag checklist (must all pass):**

```bash
python3 scripts/integrity_check.py    # version consistency, tool contract, legacy files
python3 scripts/manifest_check.py     # counts + versions across docs
npx tsx tools/validate.ts --target claude-code
```

**Bumping the version.** Edit all of: `pyproject.toml`, `obsidian_connector/__init__.py`, `mcpb.json`, `src/plugin/plugin.json`, `builds/claude-code/.claude-plugin/plugin.json`, `builds/claude-code/pyproject.toml`, `builds/claude-desktop/pyproject.toml`. Add a `## [X.Y.Z]` heading to `CHANGELOG.md`. Merge -> tag `vX.Y.Z` -> push tag; the `Release`, `Build macOS DMG Installer`, `Build Windows Installer`, and `Publish to PyPI` workflows fire in parallel.

## Hardening (Task 35)

- **HTTP client timeout**: every service wrapper in `commitment_ops.py`
  honors `SERVICE_REQUEST_TIMEOUT_SECONDS` (default 10s). Set via env;
  bad or non-positive values fall back to the default. The helper
  `_service_timeout()` is the single knob — `_service_get_json`,
  `_service_post_json`, and the Task 15.A `sync_service_commitments_to_vault`
  fetch all route through it.
- **Atomic writes**: `commitment_notes.py`, `entity_notes.py`, and
  `commitment_dashboards.py` write exclusively through
  `write_manager.atomic_write`. `tests/test_hardening.py` asserts this
  at the AST level (any raw `write_text` call fails the audit) plus at
  runtime (monkeypatched `atomic_write` must record the call).
- Companion to obsidian-capture-service Task 35 (PR #19).

## Review coaching (Task 40)

Companion to the capture-service ADR in
`../obsidian-capture-service/docs/architecture/task_40_review_coaching.md`
(service PR #25, merge `19003f0`). Connector-side ADR:
`docs/architecture/task_40_review_coaching_connector.md`.

- New module `obsidian_connector/coaching_ops.py` with two HTTP
  wrappers:
  - `get_action_recommendations(action_id, *, service_url, token)` ->
    `GET /api/v1/coaching/action/{id}`. URL-encodes the action_id so
    reserved characters don't break the path split.
  - `list_review_recommendations(*, since_days=7, limit=50, service_url, token)` ->
    `GET /api/v1/coaching/review`. Defaults mirror the server-side
    defaults; the server clamps out-of-bounds values.
  Both reuse `commitment_ops._service_get_json` so Task 35 timeout /
  scheme / auth behavior is shared; never raises.
- Two MCP tools in `mcp_server.py`: `obsidian_action_recommendations`,
  `obsidian_review_recommendations`. Thin wrappers with the standard
  JSON dump + catch-all exception envelope + lazy import pattern.
- Two CLI subcommands in `cli.py`:
  `obsx action-recommendations --action-id ...`,
  `obsx review-recommendations [--since-days N] [--limit N]`. Each
  supports human + `--json` output and honours `--service-url` for
  override. Human formatters show the verb, confidence, and
  suggested-inputs block per rec.
- Review dashboard:
  `commitment_dashboards.generate_coaching_dashboard(vault, *, service_url, token, since_days=7, limit=100, now_iso=None)`
  writes `Dashboards/Review/Coaching.md` with one section per
  recommendation code (`CONSIDER_CANCEL`, `CONSIDER_DELEGATE`,
  `CONSIDER_MERGE`, `CONSIDER_RECLAIM`, `CONSIDER_RESCHEDULE`,
  `CONSIDER_UNBLOCK`). Each row shows the action title + verb + mini
  "why" label + action id. Service-unreachable and service-
  unconfigured render with a banner, never silent skip.
- `update_all_review_dashboards(..., include_coaching=True, coaching_since_days=7)`
  is the new default-on opt-out flag. Default review set goes 5 -> 6
  surfaces (Daily, Weekly, Stale, Merge Candidates, Delegations,
  Coaching); default full stack via `update_all_dashboards(...)` goes
  12 -> 13. Orchestrator-count regressions in
  `tests/test_review_dashboards.py` updated accordingly.
- Tests: `tests/test_coaching_ops.py` (34 cases -- wrapper path /
  query / auth, envelope error surfaces incl. 404 / 409, MCP
  passthrough, dashboard render / alphabetical grouping /
  determinism, orchestrator wiring, CLI human + JSON). 541 -> 575.

## Cross-device sync (Task 42)

Companion to the capture-service ADR in
`../obsidian-capture-service/docs/architecture/task_42_cross_device_sync.md`.
Connector-side ADR:
`docs/architecture/task_42_cross_device_sync_connector.md`.

- Two new HTTP wrappers in `obsidian_connector/admin_ops.py` on top of
  `commitment_ops._service_get_json` / `_service_post_json` so Task 35
  timeout / scheme / auth behavior is shared. Never raises; failures
  surface inside the standard envelope.
  - `list_mobile_devices(*, service_url=None, token=None)` ->
    `GET /api/v1/mobile/devices`.
  - `forget_mobile_device(device_id, *, service_url=None, token=None)` ->
    `POST /api/v1/mobile/devices/{device_id}/forget`. URL-encodes
    the path id; blank / non-string id short-circuits before HTTP.
- Two MCP tools in `mcp_server.py`: `obsidian_mobile_devices`
  (read-only, idempotent), `obsidian_forget_mobile_device`
  (destructive hint on the tool annotations; still idempotent on a
  missing id). Same lazy-import + try/except envelope pattern as the
  Task 44 admin tools.
- Two CLI subcommands in `cli.py`:
  `obsx mobile-devices [--service-url ...] [--json]`,
  `obsx forget-mobile-device --device-id ID [--yes] [--service-url ...] [--json]`.
  The forget subcommand interactively prompts for confirmation unless
  `--yes` is set; `--json` also short-circuits the prompt so scripts
  stay parseable. Human formatters `_fmt_mobile_devices` +
  `_fmt_forget_mobile_device`.
- `commitment_dashboards.generate_admin_dashboard()` now fetches the
  new `/devices` payload alongside the Task 44 surfaces and renders a
  "## Mobile devices" section after "## Stale sync devices" with
  columns `Device | Label | Platform | App | Last sync | Pending ops |
  First seen`. The existing "Stale sync devices" section now prefixes
  the `device_label` when available so operators can disambiguate
  iPhone from Watch at a glance. Service-unreachable and
  service-unconfigured both fall into the existing banner pattern
  (never silent skip). `DashboardResult.written` now includes the
  mobile devices count.
- Tests: `tests/test_devices_ops.py` (22 cases -- wrapper path / body
  / auth, blank-id preflight, HTTP error surfaces, MCP passthrough,
  CLI human + `--json` + confirm / `--yes` / cancellation paths,
  dashboard renderer + integration). `tests/test_admin_helpers.py`
  updated for the new sixth service call in `generate_admin_dashboard`
  (written 3 -> 4). 611 -> 633.

## Mobile bulk actions (Task 41)

Companion to the capture-service ADR in
`../obsidian-capture-service/docs/architecture/task_41_mobile_ux.md`
(service PR #26, merge `6989d26`). Connector-side ADR:
`docs/architecture/task_41_mobile_ux_connector.md`.

- Five new HTTP wrappers on top of `commitment_ops._service_get_json`
  / `_service_post_json`, so Task 35 timeout / scheme / auth behavior
  is shared. Never raises; failures surface inside the standard
  envelope.
  - `bulk_ack_commitments(action_ids, *, note=None, ...)` ->
    `POST /api/v1/actions/bulk-ack`.
  - `bulk_done_commitments(action_ids, *, note=None, ...)` ->
    `POST /api/v1/actions/bulk-done`.
  - `bulk_postpone_commitments(action_ids, *, preset=None, postponed_until=None, note=None, ...)` ->
    `POST /api/v1/actions/bulk-postpone`. **Client-side validates
    exactly one of `preset` or `postponed_until` is set** so the
    caller never wastes a round-trip on a 422. Blank strings count as
    unset.
  - `bulk_cancel_commitments(action_ids, *, reason=None, ...)` ->
    `POST /api/v1/actions/bulk-cancel`.
  - `list_postpone_presets(*, ...)` ->
    `GET /api/v1/actions/postpone-presets`.
- Shared preflight via private `_bulk_action_call(...)` helper:
  empty `action_ids` or lists of blank strings short-circuit before
  the network call (mirrors Task 36's `_bulk_call`).
- Five MCP tools in `mcp_server.py`: `obsidian_bulk_ack`,
  `obsidian_bulk_done`, `obsidian_bulk_postpone`,
  `obsidian_bulk_cancel`, `obsidian_postpone_presets`. Thin wrappers
  with the standard JSON dump + catch-all exception envelope + lazy
  import pattern.
- Five CLI subcommands in `cli.py` (each supports human + `--json`,
  honours `--service-url`):
  `obsx bulk-ack --action-ids a,b,c [--note ...]`,
  `obsx bulk-done ...`,
  `obsx bulk-postpone --action-ids ... [--preset NAME | --postponed-until ISO] [--note ...]`,
  `obsx bulk-cancel --action-ids ... [--reason ...]`,
  `obsx postpone-presets`.
- Human formatters: `_fmt_bulk_action(result, verb)` for
  ack/done/cancel, `_fmt_bulk_postpone(result)` adds the
  `resolved_postponed_until` echo line, `_fmt_postpone_presets(result)`
  renders the catalog.
- No vault dashboard for Task 41 -- bulk actions are fire-and-forget
  and the Task 40 coaching dashboard is the review surface that
  surfaces candidates. Shortcut docs on the service side walk users
  through iOS Shortcuts build guides.
- Tests: `tests/test_bulk_actions_connector.py` (36 cases --
  wrapper path + body + auth, mutual exclusivity for bulk-postpone,
  empty-ids / blank-ids preflight, HTTP 400 surfaces, MCP
  passthrough for all five tools, CLI human + `--json` output,
  per-row `skip: ... wrong_status` rendering). 575 -> 611.

## Delegation (Task 38)

Companion to the capture-service ADR in
`../obsidian-capture-service/docs/architecture/task_38_delegation.md`
(service PR #24). Connector-side ADR:
`docs/architecture/task_38_delegation_connector.md`.

- `ActionInput` (`commitment_notes.py`) gains three optional frozen
  fields: `delegated_to: str | None`, `delegated_at: str | None`,
  `delegation_note: str | None`. All default to `None`. Frontmatter
  slot sits between `postponed_until` and `requires_ack` so
  pre-Task-38 notes diff cleanly on first-touch upgrade.
- Body line `- Delegated to: <name> (YYYY-MM-DD)` (plus optional
  `- Delegation note: <text>`) renders only when `delegated_to` is
  truthy; non-delegated notes are unchanged.
- Four HTTP wrappers in `commitment_ops.py`:
  `delegate_commitment(action_id, *, to_person, note=None, ...)` ->
  `POST /api/v1/actions/{id}/delegate`;
  `reclaim_commitment(action_id, *, note=None, ...)` ->
  `POST /api/v1/actions/{id}/reclaim`;
  `list_delegated_to(person, *, limit, cursor, include_terminal, ...)` ->
  `GET /api/v1/actions/delegated-to/{person}`;
  `list_stale_delegations(*, threshold_days=14, limit=50, ...)` ->
  `GET /api/v1/patterns/stale-delegations`. All four reuse
  `_service_get_json` / `_service_post_json`; never raise.
- CLI subcommands: `obsx delegate-commitment --action-id ... --to-person ... [--note ...]`,
  `obsx reclaim-commitment --action-id ... [--note ...]`,
  `obsx delegated-to --person ... [--limit N] [--cursor ...] [--include-terminal]`,
  `obsx stale-delegations [--threshold-days N] [--limit N]` (each with
  human + `--json` output).
- MCP tools: `obsidian_delegate_commitment`,
  `obsidian_reclaim_commitment`, `obsidian_delegated_to`,
  `obsidian_stale_delegations`.
- Review dashboard: `commitment_dashboards.generate_delegation_dashboard(vault, *, service_url, token, threshold_days=14, now_iso=None)`
  writes `Dashboards/Review/Delegations.md` with two sections --
  stale delegations (per-person buckets past the threshold) and open
  delegations (per-person counts, alphabetical). Service-unreachable
  and service-unconfigured render the page with a banner (never
  silent skip).
- `update_all_review_dashboards(..., include_delegations=True)` is
  the new opt-out flag; default-on so the Delegations surface lands
  in every review run. Pass `include_delegations=False` for
  local-only review runs that should not touch the network.
- Tests: `tests/test_delegation_connector.py` (39 cases covering
  `ActionInput` kwargs, frontmatter order, body-row conditional,
  HTTP wrappers, MCP passthrough, CLI human/JSON output, dashboard
  render + integration, orchestrator opt-out).

## Onboarding (Task 34)

New-install walkthrough lives at `docs/ONBOARDING.md` and is also
available via the CLI:

```bash
obsx onboarding          # prints the 6-step walkthrough
obsx onboarding --json   # stable payload for scripts / MCP clients
```

The step catalog lives in `obsidian_connector/onboarding.py`
(`ONBOARDING_STEPS`, `get_onboarding_payload`, `format_onboarding`).
Pure Python, no I/O, no network — kept deliberately side-effect-free so
tests, MCP callers, and the Markdown doc render from the same data.
The sequence cross-references `../obsidian-capture-service/docs/onboarding/ONBOARDING.md`
for the service-side steps that precede the connector setup.

## Build system

Plugin artifacts live in `src/` (skills, hooks, manifest, MCP config, bin). Python package stays at `obsidian_connector/`. Build pipeline in `tools/` (TypeScript, tsx).

```bash
npx tsx tools/build.ts --target all          # Build all targets to builds/
npx tsx tools/build.ts --target claude-code   # Build specific target
npx tsx tools/validate.ts --target all        # Validate build output
npx tsx tools/diff.ts --target portable       # Show source-to-build diff
npx tsx tools/doctor.ts                       # Environment health check
npx tsx tools/package.ts --target all         # Create dist/ archives
```

Targets: `claude-code`, `claude-desktop`, `portable`, `pypi`. Config in `config/targets/`. Skill portability in `config/defaults/skill-portability.yaml`.

Symlinks (`skills/`, `hooks/`, `bin/`, `.mcp.json`, `.claude-plugin/plugin.json`) point into `src/` so `claude --plugin-dir .` works during development.

## Available local commands

```bash
# Build system
npx tsx tools/build.ts --target all          # Build all targets
npx tsx tools/validate.ts --target all       # Validate builds
npx tsx tools/doctor.ts                      # Build environment check

# Quick health check
./bin/obsx doctor                            # Obsidian connectivity + env
```

Full test catalog in `CONTRIBUTING.md`.

## Rules

1. **When code behavior changes** -- update TOOLS_CONTRACT.md and relevant docs
2. **If docs conflict with code** -- code wins; fix docs immediately

## Key modules

See `ARCHITECTURE.md` for the full module table (39 modules). Key entry points:

- `client.py` -- low-level Obsidian CLI wrapper (+ `client_fallback.py` for direct file I/O)
- `mcp_server.py` -- FastMCP tool definitions (100+ tools)
- `cli.py` -- argparse CLI (100+ commands)
- `workflows.py` -- composed multi-step operations
- `config.py` -- vault/index configuration, vault path resolution
- `commitment_notes.py` -- renderer + idempotent writer for capture-service actions (see `docs/implementation/commitment_note_schema.md`). Task 27 extends `ActionInput` and the frontmatter schema with `urgency` (derived by the service), `lifecycle_stage` (enum, separate from `status`), `source_app`, `source_entrypoint`, `people`, `areas`. Field slots are stable; pre-Task-27 notes hydrate with defaults (`urgency='normal'`, `lifecycle_stage='inbox'`, empty lists). **Task 29** adds a pure `format_source_label(source_app, source_entrypoint) -> str` that maps the Task 27 tuples to a human-readable provenance label (`"Captured via Wispr Flow (Action Button)"`, `"Captured from Apple Notes (#capture)"`, `"(via cloud queue)"` suffix for `queue_poller` entrypoint, `"Unknown source"` fallback). Rendered alongside the raw `- Source:` line as a new `- Captured:` body row. Reused by `commitment_dashboards.py` for the By-source subsection on the Daily and Weekly review surfaces. Single source of truth for provenance vocabulary. ADR: `docs/architecture/task_29_provenance_ux.md`. **Task 32** adds an optional `why_open_summary: str | None` field on `ActionInput`. When supplied, `_render_body` writes a `## Why still open` section inside the `service:why-open:begin/end` fence. The summary is truncated at 1500 chars, idempotent, and preserved across routine re-syncs (the renderer reads the existing fence from disk when `why_open_summary is None`). Only an explicit refresh (`obsx explain-commitment` + re-sync) replaces the block. No auto-fetch on every sync.
- `commitment_ops.py` -- list, inspect, mutate, and sync operations for commitment notes (see `docs/implementation/commitment_commands.md`). `_dict_to_action_input` and `_action_from_content` tolerate missing Task 27 keys from older service payloads / legacy on-disk notes. Task 28 adds three thin wrappers over the capture service's retrieval endpoints: `list_service_actions(...)` (filters + cursor), `get_service_action(action_id)`, and `get_service_action_stats()`. All share the same `http.client` pattern, honor `OBSIDIAN_CAPTURE_SERVICE_URL` / `_TOKEN`, and never raise — errors surface inside a dict envelope. CLI: `obsx find-commitments`, `obsx commitment-detail --action-id ...`, `obsx commitment-stats`. MCP: `obsidian_find_commitments`, `obsidian_commitment_detail`, `obsidian_commitment_stats`. **Task 21.B** adds two more wrappers for cross-input dedup: `list_duplicate_candidates(action_id, *, limit, within_days, min_score, service_url, token)` over `GET /api/v1/actions/{id}/duplicate-candidates`, and `merge_commitments(loser_id, winner_id, *, service_url, token)` over `POST /api/v1/actions/{id}/merge`. Both follow the same no-raise envelope contract. CLI: `obsx duplicate-candidates --action-id ... [--limit N]`, `obsx merge-commitment --loser ... --winner ...`. MCP: `obsidian_duplicate_candidates`, `obsidian_merge_commitment`. **Task 31** adds three pattern-intelligence wrappers: `list_repeated_postponements(*, since_days, limit, ...)`, `list_blocker_clusters(*, since_days, limit, ...)`, `list_recurring_unfinished(*, by, since_days, limit, ...)` over `GET /api/v1/patterns/{repeated-postponements,blocker-clusters,recurring-unfinished}`. Same no-raise envelope contract. CLI: `obsx repeated-postponements`, `obsx blocker-clusters`, `obsx recurring-unfinished --by project|person|area`. MCP: `obsidian_repeated_postponements`, `obsidian_blocker_clusters`, `obsidian_recurring_unfinished`. **Task 32** adds `explain_commitment(action_id, *, service_url, token)` over `GET /api/v1/actions/{id}/why-still-open`. Returns an envelope with `{ok, data: {action_id, status, lifecycle_stage, urgency, reasons[{code, label, data}], inputs}}`. 404/409 surface via `status_code`. CLI: `obsx explain-commitment --action-id ...`. MCP: `obsidian_explain_commitment`. **Task 41** adds five bulk lifecycle wrappers: `bulk_ack_commitments(action_ids, *, note=None, ...)`, `bulk_done_commitments(action_ids, *, note=None, ...)`, `bulk_postpone_commitments(action_ids, *, preset=None, postponed_until=None, note=None, ...)` (client-side enforces exactly one of preset/postponed_until), `bulk_cancel_commitments(action_ids, *, reason=None, ...)`, and `list_postpone_presets(*, ...)`. Shared preflight via private `_bulk_action_call(...)` helper. CLI: `obsx bulk-ack`, `obsx bulk-done`, `obsx bulk-postpone`, `obsx bulk-cancel`, `obsx postpone-presets`. MCP: `obsidian_bulk_ack`, `obsidian_bulk_done`, `obsidian_bulk_postpone`, `obsidian_bulk_cancel`, `obsidian_postpone_presets`.
- `commitment_dashboards.py` -- generate/update four commitment dashboards in `Dashboards/` plus four review surfaces in `Dashboards/Review/` (Daily, Weekly, Stale, Merge Candidates) from current commitment state. `update_all_dashboards` refreshes all eight in one call; `update_all_review_dashboards` refreshes only the review surfaces. CLI: `obsx review-dashboards`. MCP: `obsidian_review_dashboards`. See `docs/implementation/commitment_dashboards.md` and ADR `docs/architecture/task_26_review_dashboards.md`. **Task 29** adds a `## By source (N)` subsection at the bottom of Daily.md and Weekly.md — a small Markdown `| Source | Count |` table over the current day's / week's captures, grouped by the label `commitment_notes.format_source_label()` returns. Backwards compatible: existing sections untouched, new subsection added below the existing ones. **Task 31** adds a fifth review surface — `Dashboards/Review/Patterns.md` — via `generate_patterns_dashboard(vault, *, service_url, token)`. Opt-in from `update_all_review_dashboards(..., include_patterns=True)` because it contacts the capture service. Renders three sections (postponement loops, blocker clusters, recurring unfinished by project/person/area); writes a "Capture service unreachable" banner when the service is down, with empty-section placeholders below so the shape is stable.
- `entity_notes.py` -- idempotent writer for semantic-memory entity notes under `Entities/<Kind>/<slug>.md` with preserved user-notes fence (Task 15.A). Task 30 adds a deterministic `render_first_pass_wiki_body(entity)` that fills the `service:entity-wiki:begin/end` fence with kind-conditioned peer subsections (projects / people / areas / topics) plus an "At a glance" header. Triggers when `EntityInput.wiki_content is None` and the caller has supplied projection data; an explicit `wiki_content` always wins so Task 15.C can override the scaffold. See ADR `docs/architecture/task_30_wiki_foundations.md`.
- `coaching_ops.py` -- **Task 40** HTTP wrappers for the capture service's `/api/v1/coaching/*` endpoints: `get_action_recommendations(action_id, ...)` over `GET /api/v1/coaching/action/{id}`, and `list_review_recommendations(since_days=7, limit=50, ...)` over `GET /api/v1/coaching/review`. Reuse `commitment_ops._service_get_json` so the Task 35 timeout / scheme / auth behavior is shared. Never raises; returns envelopes. CLI: `obsx action-recommendations --action-id ...`, `obsx review-recommendations [--since-days N] [--limit N]` (each with `--json`). MCP: `obsidian_action_recommendations`, `obsidian_review_recommendations`. `commitment_dashboards.generate_coaching_dashboard(vault, *, service_url, token, since_days=7, limit=100, now_iso=None)` writes `Dashboards/Review/Coaching.md` with one section per recommendation code (`CONSIDER_CANCEL`, `CONSIDER_DELEGATE`, `CONSIDER_MERGE`, `CONSIDER_RECLAIM`, `CONSIDER_RESCHEDULE`, `CONSIDER_UNBLOCK`), each grouping actions sharing that verb. `update_all_review_dashboards(..., include_coaching=True)` (default) adds the page to the review set; `include_coaching=False` opts out. Service-unreachable and service-unconfigured render with a banner, never silent skip.
- `admin_ops.py` -- **Task 44** HTTP wrappers for the capture service's `/api/v1/admin/*` endpoints: `get_queue_health`, `list_delivery_failures`, `list_pending_approvals`, `list_stale_sync_devices`, `get_system_health`. **Task 42** adds two more wrappers over `/api/v1/mobile/*`: `list_mobile_devices` and `forget_mobile_device(device_id, ...)`. All seven reuse `commitment_ops._service_get_json` / `_service_post_json` so the Task 35 timeout / scheme / auth behavior is shared. Never raises; returns envelopes. CLI: `obsx queue-health`, `obsx delivery-failures`, `obsx pending-approvals`, `obsx stale-sync-devices`, `obsx system-health`, plus `obsx mobile-devices` and `obsx forget-mobile-device --device-id ID [--yes]` (each with `--json`; the forget subcommand prompts for confirmation unless `--yes` or `--json`). MCP: `obsidian_queue_health`, `obsidian_delivery_failures`, `obsidian_pending_approvals`, `obsidian_stale_sync_devices`, `obsidian_system_health`, `obsidian_mobile_devices`, `obsidian_forget_mobile_device`. `commitment_dashboards.generate_admin_dashboard(vault, *, service_url, token)` writes `Dashboards/Admin.md` with six sections (system health summary, queue health, recent delivery failures, pending approvals, stale sync devices, mobile devices). When `OBSIDIAN_CAPTURE_SERVICE_URL` isn't configured the dashboard renders with a "service not configured" banner and empty sections (doesn't silently skip). `update_all_dashboards(..., include_admin=True)` (default) appends the admin dashboard plus the Task 36 approvals dashboard to the standard 8 surfaces for a total of 10.
- `approval_ops.py` -- **Task 36** HTTP wrappers for the capture service's Task 36 approval UX endpoints: `get_delivery_detail`, `bulk_approve_deliveries`, `bulk_reject_deliveries`, `get_approval_digest`. Reuse `commitment_ops._service_get_json` / `_service_post_json` so the Task 35 timeout / scheme / auth behavior is shared. Never raises; returns envelopes. CLI: `obsx delivery-detail --delivery-id ...`, `obsx bulk-approve --delivery-ids a,b,c [--note "..."]`, `obsx bulk-reject ...`, `obsx approval-digest [--since-hours N]` (each with `--json`). MCP: `obsidian_delivery_detail`, `obsidian_bulk_approve`, `obsidian_bulk_reject`, `obsidian_approval_digest`. `commitment_dashboards.generate_approval_dashboard(vault, *, service_url, token, now_iso, since_hours)` writes `Dashboards/Admin/Approvals.md` with three sections: "Approval digest" (top stats), "Pending approvals with risk factors" (ordered by urgency then age), "Recent decisions (last 24h)". Service-unreachable and service-unconfigured both render the page with a banner — never silent skip. Rides on `include_admin=True` so the new page lands next to `Dashboards/Admin.md`.
- `analytics_ops.py` -- **Task 39** HTTP wrappers + vault projection for the capture service's Task 39 weekly-analytics endpoints. Wrappers: `get_weekly_report(week_offset=0, ...)`, `get_weekly_report_markdown(week_offset=0, ...)` (returns `data.markdown` as a string), `list_weeks_available(weeks_back=12, ...)`. Projection: `write_weekly_report_note(vault_root, report_markdown, week_label, ...)` writes `Analytics/Weekly/<year>/<week_label>.md` with deterministic frontmatter (`type: analytics`, `week_label`, `generated_at`) and a preserved `service:analytics-user-notes:{begin,end}` fence for operator commentary. `fetch_and_write_weekly_report_note(...)` is the one-shot service call + write helper. CLI: `obsx weekly-report [--week-offset N]`, `obsx weekly-report-markdown [--week-offset N]`, `obsx weeks-available [--weeks-back N]`, `obsx write-weekly-report [--week-offset N] [--vault-root path]` (each with `--json`). MCP: `obsidian_weekly_report`, `obsidian_weekly_report_markdown`, `obsidian_weeks_available`, `obsidian_write_weekly_report`. `commitment_dashboards.generate_analytics_index_dashboard(vault, *, service_url, token, now_iso, weeks_back)` writes `Dashboards/Analytics.md` with two sections: "This week so far" (live from the service) and "Past weeks" (list of the past N ISO windows with links to whichever weekly notes are already present in `Analytics/Weekly/`). `update_all_dashboards(..., include_analytics=True)` (default) appends the analytics dashboard alongside the admin / approvals ones; operators can pass `include_analytics=False` to opt out. Gracefully no-ops without a service URL (renders "service not configured" banner, never silent skip).
- `import_tools.py` -- **Task 43** vault import / migration tools (connector half of service-side PR #23, merge `496bb35`). Five pure phases: `scan_markdown_files(root, *, include_globs, exclude_globs, max_files)` walks a directory and yields deterministic `FileCandidate` rows in sorted-path order; `classify_candidate(fc) -> dict` is a rule-based classifier (`already_managed | ready_capture | unknown`) keyed off frontmatter `type: commitment | entity`, managed-folder paths (`Commitments/**`, `Entities/**`, `Dashboards/**`, `Analytics/**`, `Archive/**`), and `#capture` / `#idea` / `#todo` / `#action` tags (with code-fence stripping); `plan_import(root, ...) -> ImportPlan` (frozen dataclass) groups into actionable buckets (`to_import_as_capture`, `to_skip_already_managed`, `to_skip_size_out_of_range`, `to_skip_unknown_kind`) and refuses cleanly on `max_files` overflow (default 1000); `execute_import(plan, *, dry_run=True, confirm=False, throttle_seconds=0.1, ...)` POSTs each ready candidate to `/api/v1/ingest/text` with deterministic `X-Idempotency-Key: vault-import-<sha256[:16]>` so re-runs collapse on the service-side dedup substrate. **Defaults to dry-run; requires both `dry_run=False` AND `confirm=True` to actually POST.** Per-file failures non-fatal. `write_import_report(result, path)` writes a Markdown report under `Analytics/Import/<ts>.md` via `atomic_write`. CLI: `obsx plan-import --root <dir> [--include / --exclude globs] [--min-size / --max-size / --max-files] [--json]` (read-only; no HTTP), `obsx execute-import --root <dir> --service-url ... [--dry-run | --execute] [--yes] [--token ...] [--throttle 0.1] [--report] [--vault-root ...]` (default `--dry-run`; interactive prompt requires typing `yes` when running with `--execute` without `--yes`). MCP: `obsidian_plan_import`, `obsidian_execute_import` (schema has explicit `dry_run` and `confirm` bools). Reuses `commitment_ops._service_timeout` for Task 35 hardening. No LLM, no embeddings, no schema changes. Walkthrough: `docs/import/IMPORT.md`.

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py` (composed)
2. Export from `__init__.py`
3. Add an argparse subcommand in `cli.py` with both human and `--json` output
4. Add a `@mcp.tool()` function in `mcp_server.py`
5. If mutating, add `--dry-run` and call `log_action()` from `audit.py`
6. Add a smoke test in `scripts/`
7. Update `TOOLS_CONTRACT.md`
