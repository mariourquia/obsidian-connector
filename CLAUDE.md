# Agent Instructions -- obsidian-connector

## Quick orientation

Python wrapper for the Obsidian desktop app CLI. Five distribution surfaces:
- **Python API** -- `from obsidian_connector import search_notes, read_note, ...`
- **CLI** -- `obsx search "query"` or `./bin/obsx search "query"`
- **MCP server** -- 62 tools for Claude Desktop via stdio or HTTP
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
- `mcp_server.py` -- FastMCP tool definitions (62 tools)
- `cli.py` -- argparse CLI (65 commands)
- `workflows.py` -- composed multi-step operations
- `config.py` -- vault/index configuration, vault path resolution
- `commitment_notes.py` -- renderer + idempotent writer for capture-service actions (see `docs/implementation/commitment_note_schema.md`). Task 27 extends `ActionInput` and the frontmatter schema with `urgency` (derived by the service), `lifecycle_stage` (enum, separate from `status`), `source_app`, `source_entrypoint`, `people`, `areas`. Field slots are stable; pre-Task-27 notes hydrate with defaults (`urgency='normal'`, `lifecycle_stage='inbox'`, empty lists). **Task 29** adds a pure `format_source_label(source_app, source_entrypoint) -> str` that maps the Task 27 tuples to a human-readable provenance label (`"Captured via Wispr Flow (Action Button)"`, `"Captured from Apple Notes (#capture)"`, `"(via cloud queue)"` suffix for `queue_poller` entrypoint, `"Unknown source"` fallback). Rendered alongside the raw `- Source:` line as a new `- Captured:` body row. Reused by `commitment_dashboards.py` for the By-source subsection on the Daily and Weekly review surfaces. Single source of truth for provenance vocabulary. ADR: `docs/architecture/task_29_provenance_ux.md`. **Task 32** adds an optional `why_open_summary: str | None` field on `ActionInput`. When supplied, `_render_body` writes a `## Why still open` section inside the `service:why-open:begin/end` fence. The summary is truncated at 1500 chars, idempotent, and preserved across routine re-syncs (the renderer reads the existing fence from disk when `why_open_summary is None`). Only an explicit refresh (`obsx explain-commitment` + re-sync) replaces the block. No auto-fetch on every sync.
- `commitment_ops.py` -- list, inspect, mutate, and sync operations for commitment notes (see `docs/implementation/commitment_commands.md`). `_dict_to_action_input` and `_action_from_content` tolerate missing Task 27 keys from older service payloads / legacy on-disk notes. Task 28 adds three thin wrappers over the capture service's retrieval endpoints: `list_service_actions(...)` (filters + cursor), `get_service_action(action_id)`, and `get_service_action_stats()`. All share the same `http.client` pattern, honor `OBSIDIAN_CAPTURE_SERVICE_URL` / `_TOKEN`, and never raise — errors surface inside a dict envelope. CLI: `obsx find-commitments`, `obsx commitment-detail --action-id ...`, `obsx commitment-stats`. MCP: `obsidian_find_commitments`, `obsidian_commitment_detail`, `obsidian_commitment_stats`. **Task 21.B** adds two more wrappers for cross-input dedup: `list_duplicate_candidates(action_id, *, limit, within_days, min_score, service_url, token)` over `GET /api/v1/actions/{id}/duplicate-candidates`, and `merge_commitments(loser_id, winner_id, *, service_url, token)` over `POST /api/v1/actions/{id}/merge`. Both follow the same no-raise envelope contract. CLI: `obsx duplicate-candidates --action-id ... [--limit N]`, `obsx merge-commitment --loser ... --winner ...`. MCP: `obsidian_duplicate_candidates`, `obsidian_merge_commitment`. **Task 31** adds three pattern-intelligence wrappers: `list_repeated_postponements(*, since_days, limit, ...)`, `list_blocker_clusters(*, since_days, limit, ...)`, `list_recurring_unfinished(*, by, since_days, limit, ...)` over `GET /api/v1/patterns/{repeated-postponements,blocker-clusters,recurring-unfinished}`. Same no-raise envelope contract. CLI: `obsx repeated-postponements`, `obsx blocker-clusters`, `obsx recurring-unfinished --by project|person|area`. MCP: `obsidian_repeated_postponements`, `obsidian_blocker_clusters`, `obsidian_recurring_unfinished`. **Task 32** adds `explain_commitment(action_id, *, service_url, token)` over `GET /api/v1/actions/{id}/why-still-open`. Returns an envelope with `{ok, data: {action_id, status, lifecycle_stage, urgency, reasons[{code, label, data}], inputs}}`. 404/409 surface via `status_code`. CLI: `obsx explain-commitment --action-id ...`. MCP: `obsidian_explain_commitment`.
- `commitment_dashboards.py` -- generate/update four commitment dashboards in `Dashboards/` plus four review surfaces in `Dashboards/Review/` (Daily, Weekly, Stale, Merge Candidates) from current commitment state. `update_all_dashboards` refreshes all eight in one call; `update_all_review_dashboards` refreshes only the review surfaces. CLI: `obsx review-dashboards`. MCP: `obsidian_review_dashboards`. See `docs/implementation/commitment_dashboards.md` and ADR `docs/architecture/task_26_review_dashboards.md`. **Task 29** adds a `## By source (N)` subsection at the bottom of Daily.md and Weekly.md — a small Markdown `| Source | Count |` table over the current day's / week's captures, grouped by the label `commitment_notes.format_source_label()` returns. Backwards compatible: existing sections untouched, new subsection added below the existing ones. **Task 31** adds a fifth review surface — `Dashboards/Review/Patterns.md` — via `generate_patterns_dashboard(vault, *, service_url, token)`. Opt-in from `update_all_review_dashboards(..., include_patterns=True)` because it contacts the capture service. Renders three sections (postponement loops, blocker clusters, recurring unfinished by project/person/area); writes a "Capture service unreachable" banner when the service is down, with empty-section placeholders below so the shape is stable.
- `entity_notes.py` -- idempotent writer for semantic-memory entity notes under `Entities/<Kind>/<slug>.md` with preserved user-notes fence (Task 15.A). Task 30 adds a deterministic `render_first_pass_wiki_body(entity)` that fills the `service:entity-wiki:begin/end` fence with kind-conditioned peer subsections (projects / people / areas / topics) plus an "At a glance" header. Triggers when `EntityInput.wiki_content is None` and the caller has supplied projection data; an explicit `wiki_content` always wins so Task 15.C can override the scaffold. See ADR `docs/architecture/task_30_wiki_foundations.md`.
- `admin_ops.py` -- **Task 44** HTTP wrappers for the capture service's `/api/v1/admin/*` endpoints: `get_queue_health`, `list_delivery_failures`, `list_pending_approvals`, `list_stale_sync_devices`, `get_system_health`. Reuse `commitment_ops._service_get_json` so the Task 35 timeout / scheme / auth behavior is shared. Never raises; returns envelopes. CLI: `obsx queue-health`, `obsx delivery-failures`, `obsx pending-approvals`, `obsx stale-sync-devices`, `obsx system-health` (each with `--json`). MCP: `obsidian_queue_health`, `obsidian_delivery_failures`, `obsidian_pending_approvals`, `obsidian_stale_sync_devices`, `obsidian_system_health`. `commitment_dashboards.generate_admin_dashboard(vault, *, service_url, token)` writes `Dashboards/Admin.md` with five sections (system health summary, queue health, recent delivery failures, pending approvals, stale sync devices). When `OBSIDIAN_CAPTURE_SERVICE_URL` isn't configured the dashboard renders with a "service not configured" banner and empty sections (doesn't silently skip). `update_all_dashboards(..., include_admin=True)` (default) appends the admin dashboard plus the Task 36 approvals dashboard to the standard 8 surfaces for a total of 10.
- `approval_ops.py` -- **Task 36** HTTP wrappers for the capture service's Task 36 approval UX endpoints: `get_delivery_detail`, `bulk_approve_deliveries`, `bulk_reject_deliveries`, `get_approval_digest`. Reuse `commitment_ops._service_get_json` / `_service_post_json` so the Task 35 timeout / scheme / auth behavior is shared. Never raises; returns envelopes. CLI: `obsx delivery-detail --delivery-id ...`, `obsx bulk-approve --delivery-ids a,b,c [--note "..."]`, `obsx bulk-reject ...`, `obsx approval-digest [--since-hours N]` (each with `--json`). MCP: `obsidian_delivery_detail`, `obsidian_bulk_approve`, `obsidian_bulk_reject`, `obsidian_approval_digest`. `commitment_dashboards.generate_approval_dashboard(vault, *, service_url, token, now_iso, since_hours)` writes `Dashboards/Admin/Approvals.md` with three sections: "Approval digest" (top stats), "Pending approvals with risk factors" (ordered by urgency then age), "Recent decisions (last 24h)". Service-unreachable and service-unconfigured both render the page with a banner — never silent skip. Rides on `include_admin=True` so the new page lands next to `Dashboards/Admin.md`.

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py` (composed)
2. Export from `__init__.py`
3. Add an argparse subcommand in `cli.py` with both human and `--json` output
4. Add a `@mcp.tool()` function in `mcp_server.py`
5. If mutating, add `--dry-run` and call `log_action()` from `audit.py`
6. Add a smoke test in `scripts/`
7. Update `TOOLS_CONTRACT.md`
