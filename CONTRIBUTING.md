# Contributing to obsidian-connector

Thanks for your interest in contributing.

## Getting started

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Development workflow

1. Create a branch from `main`: `git checkout -b feature/your-feature`
2. Make your changes
3. Run tests: see [Testing](#testing)
4. Open a pull request against `main`

## Testing

Tests live in `scripts/` and run without pytest. Most tests work without
Obsidian running -- they test pure Python logic with temp directories.

### Unit tests (no Obsidian required)

```bash
python3 scripts/audit_test.py               # Audit logging
python3 scripts/audit_permissions_test.py    # Audit directory permissions
python3 scripts/automation_test.py           # Event-triggered automation
python3 scripts/cache_test.py               # TTL cache
python3 scripts/cli_parse_test.py           # CLI argument parsing
python3 scripts/delegation_test.py          # Delegation detection
python3 scripts/draft_manager_test.py       # Draft lifecycle
python3 scripts/edge_case_test.py           # Edge case handling
python3 scripts/escaping_test.py            # Argument escaping
python3 scripts/file_backend_test.py        # CLI-less file backend
python3 scripts/graduate_test.py            # Graduate pipeline
python3 scripts/graph_test.py               # Graph indexing
python3 scripts/import_cycle_test.py        # Import cycle regression
python3 scripts/index_test.py               # SQLite index store
python3 scripts/installer_smoke_test.py     # Installer validation
python3 scripts/mcp_tool_contract_test.py   # MCP tool contract
python3 scripts/new_modules_test.py         # New module validation
python3 scripts/perf_test.py                # Performance benchmarks
python3 scripts/platform_test.py            # Cross-platform paths
python3 scripts/project_intelligence_test.py # Project health scores
python3 scripts/project_sync_test.py        # Project sync + vault init
python3 scripts/reports_test.py             # Report generation
python3 scripts/retrieval_test.py           # Hybrid search
python3 scripts/scheduler_test.py           # Scheduler config
python3 scripts/template_test.py            # Template engine
python3 scripts/thinking_deep_test.py       # Thinking tools
python3 scripts/thinking_tools_test.py      # Thinking tools (extended)
python3 scripts/uninstall_test.py           # Uninstall artifact removal
python3 scripts/vault_registry_test.py      # Vault registry
python3 scripts/watcher_test.py             # Filesystem watcher
python3 scripts/workflow_os_test.py         # Workflow OS operations
python3 scripts/write_manager_test.py       # Atomic writes
```

### Integration tests (Obsidian must be running)

```bash
python3 scripts/smoke_test.py               # Core function smoke tests
python3 scripts/integration_test.py          # End-to-end integration
python3 scripts/workflow_test.py             # Workflow operations
python3 scripts/checkin_test.py              # Check-in workflow
bash scripts/mcp_launch_smoke.sh             # MCP server launch
```

### Build system tests

```bash
npx tsx tools/build.ts --target all          # Build all targets
npx tsx tools/validate.ts --target all       # Validate build output
npx tsx tools/doctor.ts                      # Build environment check
```

## Adding a new tool

Follow the checklist in `CLAUDE.md` under "Adding new commands":

1. Add the core function in `client.py` or `workflows.py`
2. Export from `__init__.py`
3. Add CLI subcommand in `cli.py`
4. Add MCP tool in `mcp_server.py`
5. If mutating: add `--dry-run` and audit logging
6. Add a test in `scripts/`
7. Update `TOOLS_CONTRACT.md`

## Code style

- Python: snake_case, type hints on new/modified functions
- No `shell=True` in subprocess calls
- Parameterized SQL only (no string interpolation)
- All mutations must support `--dry-run` and write to the audit log

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.
