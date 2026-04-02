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

## Repository structure

- `src/` -- human-authored plugin content (skills, hooks, manifest, MCP config, bin wrappers)
- `obsidian_connector/` -- Python package (stays at top level for PyPI)
- `config/` -- target profiles and skill portability classification
- `tools/` -- TypeScript build pipeline (build, validate, diff, doctor, package)
- `builds/` -- generated build output (gitignored)
- `tests/` -- pytest suite including build system tests

Edit skills and hooks in `src/`. Edit the Python package in `obsidian_connector/`. Never edit files in `builds/` -- they are regenerated on each build.

## Development workflow

1. Create a branch from `main`: `git checkout -b feature/your-feature`
2. Make your changes
3. Build: `npx tsx tools/build.ts --target all`
4. Validate: `npx tsx tools/validate.ts --target all`
5. Test: `python3 -m pytest tests/test_build_system.py -v`
6. Open a pull request against `main`

## Testing

```bash
# Build system tests (requires builds/ to exist)
npx tsx tools/build.ts --target claude-code
npx tsx tools/build.ts --target claude-desktop
npx tsx tools/build.ts --target portable
python3 -m pytest tests/test_build_system.py -v

# Python unit tests (no Obsidian required)
python3 scripts/cache_test.py
python3 scripts/audit_test.py
python3 scripts/escaping_test.py
python3 scripts/graph_test.py
python3 scripts/index_test.py
python3 scripts/graduate_test.py
python3 scripts/thinking_deep_test.py
python3 scripts/delegation_test.py

# Integration tests (Obsidian must be running)
python3 scripts/smoke_test.py
python3 scripts/workflow_test.py
python3 scripts/checkin_test.py

# MCP server launch
bash scripts/mcp_launch_smoke.sh

# Build health check
npx tsx tools/doctor.ts
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
