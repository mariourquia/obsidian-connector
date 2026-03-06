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
4. Run docs lint: `make docs-lint`
5. Open a pull request against `main`

## Testing

Tests live in `scripts/` and run without pytest. Most tests work without
Obsidian running -- they test pure Python logic with temp directories.

```bash
# All unit tests (no Obsidian required)
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

# Docs structure
make docs-lint
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

## Documentation

Every file in `docs/` requires frontmatter:

```yaml
---
title: "Title"
status: draft | verified | deprecated
owner: "team-slug"
last_reviewed: "YYYY-MM-DD"
---
```

Run `make docs-lint` before submitting docs changes.

## Code style

- Python: snake_case, type hints on new/modified functions
- No `shell=True` in subprocess calls
- Parameterized SQL only (no string interpolation)
- All mutations must support `--dry-run` and write to the audit log

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.
