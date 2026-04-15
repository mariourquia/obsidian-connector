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
- `commitment_notes.py` -- renderer + idempotent writer for capture-service actions (see `docs/implementation/commitment_note_schema.md`). Task 27 extends `ActionInput` and the frontmatter schema with `urgency` (derived by the service), `lifecycle_stage` (enum, separate from `status`), `source_app`, `source_entrypoint`, `people`, `areas`. Field slots are stable; pre-Task-27 notes hydrate with defaults (`urgency='normal'`, `lifecycle_stage='inbox'`, empty lists).
- `commitment_ops.py` -- list, inspect, mutate, and sync operations for commitment notes (see `docs/implementation/commitment_commands.md`). `_dict_to_action_input` and `_action_from_content` tolerate missing Task 27 keys from older service payloads / legacy on-disk notes. Task 28 adds three thin wrappers over the capture service's retrieval endpoints: `list_service_actions(...)` (filters + cursor), `get_service_action(action_id)`, and `get_service_action_stats()`. All share the same `http.client` pattern, honor `OBSIDIAN_CAPTURE_SERVICE_URL` / `_TOKEN`, and never raise — errors surface inside a dict envelope. CLI: `obsx find-commitments`, `obsx commitment-detail --action-id ...`, `obsx commitment-stats`. MCP: `obsidian_find_commitments`, `obsidian_commitment_detail`, `obsidian_commitment_stats`.
- `commitment_dashboards.py` -- generate/update four commitment dashboards in `Dashboards/` plus four review surfaces in `Dashboards/Review/` (Daily, Weekly, Stale, Merge Candidates) from current commitment state. `update_all_dashboards` refreshes all eight in one call; `update_all_review_dashboards` refreshes only the review surfaces. CLI: `obsx review-dashboards`. MCP: `obsidian_review_dashboards`. See `docs/implementation/commitment_dashboards.md` and ADR `docs/architecture/task_26_review_dashboards.md`.
- `entity_notes.py` -- idempotent writer for semantic-memory entity notes under `Entities/<Kind>/<slug>.md` with preserved user-notes fence (Task 15.A). Task 30 adds a deterministic `render_first_pass_wiki_body(entity)` that fills the `service:entity-wiki:begin/end` fence with kind-conditioned peer subsections (projects / people / areas / topics) plus an "At a glance" header. Triggers when `EntityInput.wiki_content is None` and the caller has supplied projection data; an explicit `wiki_content` always wins so Task 15.C can override the scaffold. See ADR `docs/architecture/task_30_wiki_foundations.md`.

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py` (composed)
2. Export from `__init__.py`
3. Add an argparse subcommand in `cli.py` with both human and `--json` output
4. Add a `@mcp.tool()` function in `mcp_server.py`
5. If mutating, add `--dry-run` and call `log_action()` from `audit.py`
6. Add a smoke test in `scripts/`
7. Update `TOOLS_CONTRACT.md`
