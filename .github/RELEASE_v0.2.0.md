# obsidian-connector v0.2.0

**Release date:** 2026-03-16
**Classification:** GitHub Release (source archives + macOS .dmg)
**Branch:** `feature/uninstaller` -> `main` (PR #13)
**Commits since v0.1.1:** 38
**Files changed:** 59 (+11,796 / -135 lines)

---

## What's New

### Cross-Platform Support (macOS, Linux, Windows)

New `platform.py` module centralizes all OS-specific logic:
- **Path resolution**: Claude Desktop config, Obsidian app registry, index DB,
  scheduling config -- resolved per OS using XDG (Linux), %APPDATA% (Windows),
  ~/Library (macOS)
- **Scheduling**: launchd (macOS), systemd user timers (Linux), Task Scheduler
  via schtasks (Windows) -- unified `install_schedule()`/`uninstall_schedule()` API
- **Notifications**: osascript (macOS), notify-send (Linux), PowerShell toast
  (Windows) via `send_notification()`
- **Process detection**: `is_obsidian_running()` and `obsidian_binary_candidates()`
  per platform

### Uninstaller

`obsx uninstall` -- two-mode safe uninstaller:
- **Interactive**: Per-artifact confirmation prompts (defaults to keep)
- **Non-interactive**: `--force` with explicit `--remove-*` flags
- **Dry-run**: `--dry-run` shows what would be removed
- **MCP tool**: `obsidian_uninstall` (defaults to dry_run=True)
- Timestamped config backups before any modification
- Atomic writes via tempfile + os.replace

### Security Hardening (14-Expert Review Panel)

- PowerShell injection in `send_notification()` fixed (env var passing)
- osascript escaping expanded (single quotes, newlines, tabs, carriage returns)
- CWD config.json hijack fixed (package dir checked before CWD)
- Non-atomic config write fixed in uninstaller
- 7 bare `except Exception: pass` patterns narrowed to specific types
- Doctor false negatives for systemd/schtasks fixed
- install-linux.sh double-execution bug fixed
- Interactive prompt defaults inverted to non-destructive

### Test Coverage

| Metric | v0.1.1 | v0.2.0 |
|--------|--------|--------|
| Test files | 8 | 23 |
| Test LOC | ~1,200 | 6,024 |
| CI platforms | macOS | macOS + Ubuntu + Windows |
| Python versions | 3.11-3.13 | 3.11-3.13 |

New test suites: platform (57 tests), edge cases, uninstall, MCP tool contracts,
CLI parsing, import cycles, audit permissions, file backend (68 tests),
integration workflows.

---

## Release Artifacts

| Asset | Format | Platform |
|-------|--------|----------|
| `obsidian-connector-v0.2.0.tar.gz` | Source archive | All |
| `obsidian-connector-v0.2.0.zip` | Source archive | All |
| `obsidian-connector-v0.2.0.dmg` | macOS installer | macOS |
| `obsidian-connector-v0.2.0.sha256` | SHA256 checksums | All |

### Verification

```bash
# Download checksums
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.2.0/obsidian-connector-v0.2.0.sha256

# Verify
sha256sum -c obsidian-connector-v0.2.0.sha256
```

---

## Installation

### macOS (easiest)
1. Download `.dmg` from Releases
2. Open DMG, double-click `Install.command`
3. Restart Claude Desktop

### Linux
```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
bash scripts/install-linux.sh
```

### Windows (PowerShell)
```powershell
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
.\scripts\Install.ps1
```

### Manual (any platform)
```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
python3 -m venv .venv
.venv/bin/pip install -e .
./bin/obsx doctor
```

---

## Security Review

### Fixes in This Release

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

### Security Model

- **Local-only**: No network calls, no telemetry, no data collection
- **Vault safety**: Never modifies, deletes, or touches vault notes
- **Audit trail**: All mutations logged to `~/.obsidian-connector/logs/` (JSONL)
- **Path traversal protection**: `.resolve()` + `.relative_to()` on all file operations
- **Subprocess safety**: List-based args (no shell=True), binary path validation

### Known Gaps (Not Fixed)

- No security scanning in CI (CodeQL, pip-audit)
- No GPG/cosign signing on release assets
- No dependabot for automated dependency updates
- Frontmatter parser does not handle all YAML edge cases (flow sequences, multi-line)
- `%%comment%%` blocks not masked from tag/link extraction

---

## Testing Summary

**15 test files run in CI (no Obsidian required):**
audit_test, graph_test, index_test, graduate_test, thinking_deep_test,
delegation_test, import_cycle_test, platform_test, edge_case_test,
uninstall_test, mcp_tool_contract_test, cli_parse_test, audit_permissions_test,
escaping_test (unit portion), cache_test (unit portion)

**CI matrix:** macOS-latest + ubuntu-latest + windows-latest x Python 3.11, 3.12, 3.13

**What is NOT tested in CI:**
- Integration with running Obsidian desktop app (requires interactive session)
- End-to-end MCP tool execution via Claude Desktop
- systemd timer installation (requires systemd)
- PowerShell notification dispatch (requires Windows with WinRT)
- .dmg creation (tested only in release workflow)

**Pre-existing test failures (not regressions):**
- `graduate_test.py`: 2 of 26 tests fail (heading candidate detection heuristic)
- `cache_test.py`, `escaping_test.py`: Integration subtests timeout without Obsidian

---

## Compatibility

### Requirements

| Component | Minimum | Tested |
|-----------|---------|--------|
| Python | 3.11 | 3.11, 3.12, 3.13 |
| Obsidian | 1.12 (CLI support) | 1.12+ |
| macOS | 12+ | latest (CI) |
| Ubuntu | 22.04+ | latest (CI) |
| Windows | 10+ | latest (CI) |

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

---

## Known Limitations

1. **Obsidian CLI required**: Most tools need the Obsidian desktop app running.
   Graph tools, doctor, and uninstall work offline.
2. **Daily note format**: Assumes `YYYY-MM-DD.md` naming. Custom formats not yet
   supported (ROADMAP item #3).
3. **file_backend.py**: Built but not wired into MCP/CLI. Planned for v0.2.1.
4. **Skills not shipped**: `/morning`, `/evening`, `/idea`, `/weekly` skills
   referenced in docs but not included in this release. Planned for v0.2.1.
5. **CLI/workflows monoliths**: cli.py (1,599 LOC) and workflows.py (1,594 LOC)
   are large single files. Refactoring planned for v0.3.0.
6. **Open loop detection**: Custom `OL:` marker convention -- no Obsidian plugin
   support. Consider task-style `- [ ] OL:` in future.
7. **Drift analysis**: Regex-based intention extraction. Semantic matching planned.

---

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

---

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
