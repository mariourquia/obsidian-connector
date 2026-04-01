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

## Available local commands

```bash
python3 scripts/smoke_test.py           # Core function smoke tests
python3 scripts/cache_test.py           # Cache module tests
python3 scripts/import_cycle_test.py    # Import cycle regression
python3 scripts/platform_test.py        # Cross-platform path tests
python3 scripts/mcp_tool_contract_test.py # MCP tool contract tests
python3 scripts/cli_parse_test.py       # CLI argument parsing tests
python3 scripts/audit_permissions_test.py # Audit dir permissions
bash scripts/mcp_launch_smoke.sh        # MCP server launch test
python3 scripts/project_sync_test.py   # Project sync + vault init tests (56 assertions)
./bin/obsx doctor                       # Health check (Obsidian connectivity)
```

## Rules

1. **When code behavior changes** -- update TOOLS_CONTRACT.md and relevant docs
2. **If docs conflict with code** -- code wins; fix docs immediately

## Key modules

- `client.py` -- low-level Obsidian CLI wrapper
- `platform.py` -- cross-platform path resolution, scheduling, notifications (macOS/Linux/Windows)
- `errors.py` -- canonical exception hierarchy (ObsidianCLIError base class)
- `mcp_server.py` -- FastMCP tool definitions (62 tools)
- `cli.py` -- argparse CLI (65 commands)
- `project_sync.py` -- project sync engine (git state, dashboard, TODO, sessions)
- `vault_init.py` -- vault initialization wizard
- `workflows.py` -- composed multi-step operations
- `config.py` -- vault/index configuration (uses platform.py for OS paths)
- `audit.py` -- mutation audit logging (0o700 directory permissions)

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py` (composed)
2. Export from `__init__.py`
3. Add an argparse subcommand in `cli.py` with both human and `--json` output
4. Add a `@mcp.tool()` function in `mcp_server.py`
5. If mutating, add `--dry-run` and call `log_action()` from `audit.py`
6. Add a smoke test in `scripts/`
7. Update `TOOLS_CONTRACT.md`
