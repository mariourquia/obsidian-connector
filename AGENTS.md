# AGENTS.md (Repository Map)

> This file is your entry point. Read it first, follow links for detail.
> **Hard limit: <= 120 lines.** Do not add implementation details here.

## Start here (routing)

- Architecture map: [./ARCHITECTURE.md](./ARCHITECTURE.md)
- Tools contract (AI agents): [./TOOLS_CONTRACT.md](./TOOLS_CONTRACT.md)
- Docs catalog: [./docs/index.md](./docs/index.md)
- Design docs: [./docs/design-docs/index.md](./docs/design-docs/index.md)
- Active execution plans: [./docs/exec-plans/active/](./docs/exec-plans/active/)
- Quality scores: [./docs/quality/QUALITY_SCORE.md](./docs/quality/QUALITY_SCORE.md)
- Tech debt: [./docs/tech-debt-tracker.md](./docs/tech-debt-tracker.md)

## What this repo does

Python wrapper for the Obsidian desktop app. Exposes vault operations
(search, read, write, graph analysis, thinking tools, workflow management)
as a Python API, CLI (`obsx` -- 62 commands), and MCP server (62 tools)
for Claude Desktop. Includes skills, hooks, and scheduled automation that
turn Claude into a proactive second brain assistant.

## Module map

| Module | Purpose |
|--------|---------|
| `obsidian_connector/client.py` | Core CLI wrapper, batch reads |
| `obsidian_connector/cli.py` | 65 CLI subcommands |
| `obsidian_connector/mcp_server.py` | 62 MCP tools (FastMCP) |
| `obsidian_connector/workflows.py` | Daily ops, loops, graduate, delegations, context |
| `obsidian_connector/thinking.py` | Ghost, drift, trace, ideas |
| `obsidian_connector/graph.py` | Vault graph indexing (links, tags, backlinks) |
| `obsidian_connector/index_store.py` | SQLite persistent index |
| `src/skills/` | 17 Claude Code plugin skills in `<name>/SKILL.md` format |
| `src/hooks/` | hooks.json + session_start.sh, session_stop.sh, idea_detect.md |
| `src/plugin/` | Plugin manifest (plugin.json) and MCP config (.mcp.json) |
| `src/bin/` | Shell wrappers (obsx, obsx-mcp) |
| `config/targets/` | Build target profiles (claude-code, claude-desktop, portable, pypi) |
| `config/defaults/` | Skill portability classification |
| `tools/` | TypeScript build pipeline (build, validate, diff, doctor, package) |
| `builds/` | Generated build output (gitignored) |
| `marketplace.json` | Self-hosted marketplace metadata (at repo root) |
| `scheduling/` | launchd automation + headless runner |
| `templates/` | Claude Desktop system prompt, exec-plan templates |

Symlinks at root (`.mcp.json`, `.claude-plugin/plugin.json`) point into `src/plugin/`.
Root `skills/`, `hooks/`, `bin/` share content with `src/` counterparts.

## Operating rules

- **Never call the `obsidian` CLI directly.** Use MCP tools, Python API, or `obsx`.
- Treat `docs/` as source-of-truth; do not invent behavior not backed by code or docs.
- For complex changes: create/extend an execution plan under `docs/exec-plans/active/`.
- When code behavior changes, update TOOLS_CONTRACT.md, docs, and bump `last_reviewed`.
- If docs conflict with code, **code wins**; open a doc-fix PR immediately.

## How to navigate fast

- Use ripgrep: `rg "keyword" obsidian_connector/ docs/`
- Start with indexes; do not read long docs unless routed by an index.
- Prefer docs with `status: verified`. Treat `draft` as partial.

## Required artifacts by change type

- **New command:** client.py or workflows.py + cli.py subcommand + mcp_server.py tool + TOOLS_CONTRACT.md + smoke test
- **Behavior change:** update doc(s) + add/adjust tests
- **Cross-cutting change:** update ARCHITECTURE.md and relevant QUALITY_SCORE.md

## Escalation

- If docs conflict with code, code wins; open a doc-fix PR immediately.

## Available local commands

```
# Build system
npx tsx tools/build.ts --target all           # Build all targets to builds/
npx tsx tools/build.ts --target claude-code    # Build specific target
npx tsx tools/validate.ts --target all         # Validate build output
npx tsx tools/diff.ts --target portable        # Show source-to-build diff
npx tsx tools/doctor.ts                        # Environment health check
npx tsx tools/package.ts --target all          # Create dist/ archives
python3 -m pytest tests/test_build_system.py -v  # Build system tests (23 tests)

# Setup and health
./scripts/install.sh          # One-command setup (venv + Claude Desktop config)
make docs-lint                # Validate docs structure
make docs-lint-strict         # Errors only (CI equivalent)
make docs-staleness           # Check git-based staleness
./bin/obsx doctor             # Health check (Obsidian connectivity)

# Python tests
python3 scripts/smoke_test.py       # Core function smoke tests
python3 scripts/graph_test.py       # Graph module tests
python3 scripts/index_test.py       # Index store tests
python3 scripts/graduate_test.py    # Graduate pipeline tests
python3 scripts/thinking_deep_test.py  # Thinking tools tests (56 assertions)
bash scripts/mcp_launch_smoke.sh    # MCP server launch test
python3 scripts/checkin_test.py       # Check-in workflow tests
bash src/hooks/session_start.sh       # SessionStart hook test
python3 scheduling/run_scheduled.py morning  # Scheduled runner test
```

## Tools & skills reference

- Installer: `scripts/install.sh`
- Docs linter: `tools/docs_lint.py`
- Build pipeline: `tools/build.ts` (TypeScript, run via `npx tsx`)
- CLI wrapper: `bin/obsx` (no venv needed)
- MCP server: `python3 -m obsidian_connector.mcp_server`
- Templates: `templates/` (exec-plan, design-doc, frontmatter)
- Skills: `src/skills/` (17 skills in `<name>/SKILL.md` format)
- Hooks: `src/hooks/` (hooks.json + session_start.sh, session_stop.sh, idea_detect.md)
- Plugin manifest: `src/plugin/plugin.json`
- Scheduling: `scheduling/run_scheduled.py`
