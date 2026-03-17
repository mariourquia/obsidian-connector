```
 ___  _         _    _ _               ___
/ _ \| |__  ___(_) _| (_) __ _ _ __   / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

                  v0.2.0 -- Cross-Platform + Security Hardening
                    Turn Claude into your second brain.
```

## Highlights

- **Now runs on macOS, Linux, and Windows.** New `platform.py` centralizes
  path resolution, scheduling, and notifications per OS.
- **8 security fixes.** PowerShell injection, osascript escaping, 
  CWD config hijack, non-atomic writes, exception
  swallowing, and more.
- **Safe uninstaller.** `obsx uninstall` with interactive prompts, `--force`
  mode, `--dry-run`, and MCP tool (`obsidian_uninstall`). Defaults to keep
  everything.
- **4 skills and SessionStart hook.** `/morning`, `/evening`, `/idea`,
  `/weekly` skills for Claude Code. SessionStart hook calls `check_in`
  automatically at every session start.
- **23 test files, 6,024 lines.** CI now runs on macOS + Ubuntu + Windows
  across Python 3.11-3.13.

## What's New

### Cross-Platform Support

| Feature | Description | Environment |
|---------|-------------|-------------|
| Path resolution | Claude Desktop config, Obsidian registry, index DB, scheduling config resolved per OS (XDG, %APPDATA%, ~/Library) | All |
| Scheduling | launchd (macOS), systemd user timers (Linux), Task Scheduler via schtasks (Windows) -- unified `install_schedule()`/`uninstall_schedule()` API | All |
| Notifications | osascript (macOS), notify-send (Linux), PowerShell toast (Windows) via `send_notification()` | All |
| Process detection | `is_obsidian_running()` and `obsidian_binary_candidates()` per platform | All |

### Uninstaller

| Feature | Description | Environment |
|---------|-------------|-------------|
| Interactive mode | Per-artifact confirmation prompts (defaults to keep) | CLI |
| Non-interactive mode | `--force` with explicit `--remove-*` flags | CLI |
| Dry-run | `--dry-run` shows what would be removed without touching anything | CLI + MCP |
| MCP tool | `obsidian_uninstall` (defaults to `dry_run=True`) | Desktop |
| Config backups | Timestamped backup before any config modification | CLI + MCP |
| Atomic writes | tempfile + os.replace for all config changes | CLI + MCP |

### Security Hardening

| Issue | Severity | File | Fix |
|-------|----------|------|-----|
| PowerShell injection in notifications | CRITICAL | platform.py | Values passed via env vars |
| Incomplete osascript escaping | CRITICAL | platform.py | Full metacharacter escaping |
| CWD config.json hijack | HIGH | config.py | Package dir checked first |
| Non-atomic config write | HIGH | uninstall.py | tempfile + os.replace |
| Silent exception swallowing (7x) | HIGH | workflows.py, thinking.py | Narrowed to specific types |
| Doctor false negatives | HIGH | doctor.py | Returns True for all backends |
| Inverted destructive defaults | HIGH | cli.py | Defaults to keep (non-destructive) |
| Duplicate systemd timer install | MEDIUM | install-linux.sh | Removed duplicate call |

## Installation

```
+---------------------------------------------------+
|               Install Methods                     |
+---------------------------------------------------+
|                                                   |
|  macOS (easiest):                                 |
|    Download .dmg from Releases                    |
|    Open DMG, double-click Install.command         |
|    Restart Claude Desktop                         |
|                                                   |
|  Linux:                                           |
|    git clone ...obsidian-connector.git            |
|    cd obsidian-connector                          |
|    bash scripts/install-linux.sh                  |
|                                                   |
|  Windows (PowerShell):                            |
|    git clone ...obsidian-connector.git            |
|    cd obsidian-connector                          |
|    .\scripts\Install.ps1                          |
|                                                   |
|  Manual (any platform):                           |
|    git clone ...obsidian-connector.git            |
|    cd obsidian-connector                          |
|    python3 -m venv .venv                          |
|    .venv/bin/pip install -e .                     |
|    ./bin/obsx doctor                              |
|                                                   |
+---------------------------------------------------+
```

See the [Setup Guide](docs/setup-guide.md) for detailed instructions
for Desktop-only, CLI-only, or combined setups.

## Requirements

```
+---------------------+-------------------------------+
| Requirement         | Version                       |
+---------------------+-------------------------------+
| Python              | 3.11+                         |
| Obsidian            | 1.12+                         |
| macOS               | 12+                           |
| Ubuntu              | 22.04+                        |
| Windows             | 10+                           |
| Claude Desktop      | latest                        |
| Claude Code (opt.)  | latest                        |
+---------------------+-------------------------------+
```

## Security Review

### Fixes in This Release

```
+--------------------------------------+----------+--------+
| Issue                                | Severity | Status |
+--------------------------------------+----------+--------+
| PowerShell injection (notifications) | CRITICAL | FIXED  |
| Incomplete osascript escaping        | CRITICAL | FIXED  |
| CWD config.json hijack               | HIGH     | FIXED  |
| Non-atomic config write              | HIGH     | FIXED  |
| Silent exception swallowing (7x)     | HIGH     | FIXED  |
| Doctor false negatives               | HIGH     | FIXED  |
| Inverted destructive defaults        | HIGH     | FIXED  |
| Duplicate systemd timer install      | MEDIUM   | FIXED  |
+--------------------------------------+----------+--------+
```

**Security model:**

- **Local-only**: No network calls, no telemetry, no data collection.
- **Vault safety**: Never modifies, deletes, or touches vault notes
  (uninstaller only removes connector artifacts).
- **Audit trail**: All mutations logged to `~/.obsidian-connector/logs/`
  (append-only JSONL).
- **Path traversal protection**: `.resolve()` + `.relative_to()` on all
  file operations.
- **Subprocess safety**: List-based args (no `shell=True`), binary path
  validation.

### Known Gaps (Not Fixed)

- No dependabot for automated dependency updates.
- Frontmatter parser does not handle all YAML edge cases (flow sequences,
  multi-line).
- `%%comment%%` blocks not masked from tag/link extraction.

## Testing

```
+-------------------------------+-------------+--------+
| Test Suite (CI)               | Assertions  | Status |
+-------------------------------+-------------+--------+
| scripts/audit_test.py         | varies      | PASS   |
| scripts/graph_test.py         | varies      | PASS   |
| scripts/index_test.py         | varies      | PASS   |
| scripts/graduate_test.py      | varies      | PASS   |
| scripts/thinking_deep_test.py | 56          | PASS   |
| scripts/delegation_test.py    | varies      | PASS   |
| scripts/import_cycle_test.py  | varies      | PASS   |
| scripts/platform_test.py      | 57          | PASS   |
| scripts/edge_case_test.py     | varies      | PASS   |
| scripts/uninstall_test.py     | varies      | PASS   |
| scripts/mcp_tool_contract_test.py | varies  | PASS   |
| scripts/cli_parse_test.py     | varies      | PASS   |
| scripts/audit_permissions_test.py | varies  | PASS   |
| scripts/escaping_test.py      | varies      | PASS   |
| scripts/cache_test.py         | varies      | PASS   |
+-------------------------------+-------------+--------+
| CI matrix: macOS + Ubuntu + Windows         |        |
| Python versions: 3.11, 3.12, 3.13           |        |
+-------------------------------+-------------+--------+
```

**What is NOT tested in CI:**

- Integration with running Obsidian desktop app (requires interactive session)
- End-to-end MCP tool execution via Claude Desktop
- systemd timer installation (requires systemd)
- PowerShell notification dispatch (requires Windows with WinRT)
- .dmg creation (tested only in release workflow)

**Pre-existing test failures (not regressions):**

- `graduate_test.py`: 2 of 26 tests fail (heading candidate detection
  heuristic)
- `cache_test.py`, `escaping_test.py`: Integration subtests timeout
  without Obsidian

## Compatibility

```
+-------------------+-----------+-----------------------------------+
| Environment       | Status    | Notes                             |
+-------------------+-----------+-----------------------------------+
| macOS 12+         | Supported | Primary platform                  |
| macOS 14+         | Supported | Tested (CI)                       |
| macOS 15          | Supported | Tested (development machine)      |
| Ubuntu 22.04+     | Supported | Tested (CI)                       |
| Windows 10+       | Supported | Tested (CI)                       |
+-------------------+-----------+-----------------------------------+
```

### Runtime Dependencies

| Package | Version | License |
|---------|---------|---------|
| mcp | >=1.0.0,<2.0.0 | MIT |
| pyyaml (optional) | >=6.0,<7.0 | MIT |

### Breaking Changes from v0.1.x

| Change | Impact | Migration |
|--------|--------|-----------|
| `uninstall` MCP tool renamed to `obsidian_uninstall` | MCP callers using tool name | Update tool name in prompts |
| Config search order reversed | CWD config.json no longer takes priority | Move config.json to package dir if using CWD |
| Exception types narrowed | Code catching `Exception` from workflows may miss | Catch specific types listed in CHANGELOG |

## Known Limitations

```
+------------------------------------+-----------------------------------+-----------------------------+
| Limitation                         | Impact                            | Workaround                  |
+------------------------------------+-----------------------------------+-----------------------------+
| Obsidian CLI required              | Most tools need the Obsidian      | Graph tools, doctor, and    |
|                                    | desktop app running               | uninstall work offline      |
+------------------------------------+-----------------------------------+-----------------------------+
| Daily note format assumed          | Expects YYYY-MM-DD.md in daily/   | Configure daily note path   |
|                                    | or root                           | in config.json              |
+------------------------------------+-----------------------------------+-----------------------------+
| CLI/workflows monoliths            | cli.py (1,599 LOC) and            | Refactoring planned for     |
|                                    | workflows.py (1,594 LOC)          | v0.3.0                      |
+------------------------------------+-----------------------------------+-----------------------------+
| Open loop detection                | Custom OL: marker convention      | Consider task-style         |
|                                    | with no Obsidian plugin support   | - [ ] OL: in future         |
+------------------------------------+-----------------------------------+-----------------------------+
| Drift analysis regex-based         | Intention extraction uses regex   | Semantic matching planned   |
|                                    | not semantic matching             |                             |
+------------------------------------+-----------------------------------+-----------------------------+
```

## Release Artifacts

| Asset | Format | Platform |
|-------|--------|----------|
| `obsidian-connector-v0.2.0.tar.gz` | Source archive | All |
| `obsidian-connector-v0.2.0.zip` | Source archive | All |
| `obsidian-connector-v0.2.0.dmg` | macOS installer | macOS |
| `obsidian-connector-v0.2.0.sha256` | SHA256 checksums | All |
| `*.sig` | Cosign signatures (Sigstore) | All |
| `*.cert` | Signing certificates (Sigstore) | All |

### Verification

```bash
# 1. Verify checksums
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.2.0/obsidian-connector-v0.2.0.sha256
sha256sum -c obsidian-connector-v0.2.0.sha256

# 2. Verify Sigstore signature (requires cosign: brew install cosign)
cosign verify-blob \
  --signature obsidian-connector-v0.2.0.tar.gz.sig \
  --certificate obsidian-connector-v0.2.0.tar.gz.cert \
  --certificate-identity-regexp "github.com/mariourquia/obsidian-connector" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  obsidian-connector-v0.2.0.tar.gz
```

## Rollback

```bash
# If v0.2.0 causes issues, roll back to v0.1.1:
cd /path/to/obsidian-connector
git fetch --tags
git checkout v0.1.1
rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -e .
# Restart Claude Desktop
```

Full rollback guide: `docs/generated/ROLLBACK_OR_UNINSTALL.md`

## Maintainer Release Checklist

- [ ] PR #13 merged to main
- [ ] All CI checks green on main
- [ ] `git tag v0.2.0` on the merge commit
- [ ] `git push origin v0.2.0` (triggers release workflow)
- [ ] Release workflow completes (builds tar.gz, zip, dmg, sha256)
- [ ] Review draft release on GitHub
- [ ] Copy release notes from this file to the GitHub Release body
- [ ] Publish the release (undraft)
- [ ] Verify download links work
- [ ] Verify checksums match: `sha256sum -c obsidian-connector-v0.2.0.sha256`
- [ ] Update any external documentation or marketplace listings

## Full Changelog

**Compare:** [`v0.1.1...v0.2.0`](https://github.com/mariourquia/obsidian-connector/compare/v0.1.1...v0.2.0)

---

```
+----------------------------------------------------------+
|                                                          |
|  Built with care in New York.                            |
|  100% local. Your vault never leaves your machine.       |
|                                                          |
|  github.com/mariourquia/obsidian-connector               |
|                                                          |
+----------------------------------------------------------+
```
