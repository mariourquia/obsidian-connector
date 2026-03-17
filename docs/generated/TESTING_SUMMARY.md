---
title: "Testing Summary: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Testing Summary: obsidian-connector v0.2.0

> Date: 2026-03-16
> Environment: macOS-latest + ubuntu-latest + windows-latest, Python 3.11-3.13, GitHub Actions

## Test Inventory

| Test Type        | Files | Runner          | Notes                                       |
|------------------|-------|-----------------|---------------------------------------------|
| Unit             | 15    | Python unittest | Run in CI (no Obsidian required)             |
| Integration      | 3     | Python unittest | `integration_test`, `workflow_test`, `workflow_os_test` |
| Smoke            | 1     | Python script   | `smoke_test.py` (requires Obsidian)          |
| MCP launch       | 1     | Bash script     | `mcp_launch_smoke.sh` (CI: macOS + Ubuntu)   |
| Performance      | 1     | Python script   | `perf_test.py` (local only)                  |
| Edge case        | 1     | Python unittest | `edge_case_test.py` (in CI)                  |
| Contract         | 1     | Python unittest | `mcp_tool_contract_test.py` (in CI)          |

**Total**: 23 test files, ~6,024 lines of test code.

## Coverage

- Line coverage: not measured
- Branch coverage: not measured
- Coverage tool: none configured
- Coverage report: not available

## CI Matrix

| OS             | Python 3.11 | Python 3.12 | Python 3.13 |
|----------------|-------------|-------------|-------------|
| macOS-latest   | 15 files    | 15 files    | 15 files    |
| ubuntu-latest  | 15 files    | 15 files    | 15 files    |
| windows-latest | 15 files    | 15 files    | 15 files    |

Total CI configurations: 9 (3 OS x 3 Python).

## 15 Tests Run in CI (No Obsidian Required)

1. `audit_test.py` -- Audit log JSONL format, directory creation, permissions
2. `audit_permissions_test.py` -- 0o700 directory mode for new and pre-existing log dirs
3. `cache_test.py` -- Cache module unit tests (integration subtests timeout without Obsidian)
4. `cli_parse_test.py` -- `--help` on all subcommands, `--json` flag, unknown command rejection
5. `delegation_test.py` -- Delegation tracking and extraction
6. `edge_case_test.py` -- Boundary conditions across modules
7. `escaping_test.py` -- osascript/shell escaping unit tests (integration subtests timeout)
8. `graduate_test.py` -- Graduate candidate detection and execution (2 pre-existing failures)
9. `graph_test.py` -- Graph index build, query, backlinks
10. `import_cycle_test.py` -- `errors.py` and `client.py` import without circular dependency
11. `index_test.py` -- SQLite index store operations
12. `mcp_tool_contract_test.py` -- Tool count (29), error envelope format, typed errors
13. `platform_test.py` -- macOS/Linux/Windows path resolution, scheduling, binary candidates (57 tests)
14. `thinking_deep_test.py` -- Thinking tools (ghost, drift, trace, ideas)
15. `uninstall_test.py` -- Uninstall plan detection, execution, dry-run, atomic writes (52 tests)

## What Was NOT Tested

- **Obsidian CLI integration**: Most MCP tools invoke the Obsidian desktop CLI. Tests that require a running Obsidian instance are not run in CI. These include: `smoke_test.py`, integration portions of `cache_test.py` and `escaping_test.py`.
- **End-to-end MCP execution**: No test runs the MCP server with a real Claude Desktop client.
- **systemd timer installation**: Requires systemd (Linux-specific, not available in CI containers).
- **Windows notifications**: PowerShell toast notifications require WinRT (not available in CI).
- **macOS .dmg creation**: Tested only in the release workflow, not in CI.
- **Large vault performance**: No stress tests with >10,000 notes.
- **Custom daily note formats**: Only `YYYY-MM-DD.md` is tested.
- **YAML edge cases**: Frontmatter parser does not handle flow sequences or multi-line values.
- **Coverage**: No line or branch coverage measurement.

## Pre-Existing Test Failures (Not Regressions)

| Test File | Failures | Cause | Impact |
|-----------|----------|-------|--------|
| `graduate_test.py` | 2 of 26 | Heading candidate detection heuristic misses edge cases | Low -- affects graduate candidate suggestions only |
| `cache_test.py` | Integration subtests | Timeout without Obsidian desktop running | None -- expected in CI |
| `escaping_test.py` | Integration subtests | Timeout without Obsidian desktop running | None -- expected in CI |

## Flaky Tests

No known flaky tests. All CI-safe tests are deterministic.

## Manual Testing Performed

- MCP server launch verified on macOS (MCP launch smoke test)
- Uninstall interactive and force modes tested manually on macOS
- Claude Desktop integration tested manually (MCP tools visible and functional)
- osascript notification tested manually on macOS
- `obsx doctor` health check run manually
