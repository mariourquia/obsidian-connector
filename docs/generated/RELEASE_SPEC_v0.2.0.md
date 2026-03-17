---
title: "Release Specification: v0.2.0"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-16"
---

# Release Specification: obsidian-connector v0.2.0

> Generated: 2026-03-16
> Branch: `feature/uninstaller`
> Commits since v0.1.1: 38
> Files changed: 59 (+11,796 / -135 lines)

---

## 1. Classification and Verdict

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| Classification   | RELEASE ONLY (GitHub Release with assets, no PyPI)     |
| Verdict          | **READY WITH WARNINGS**                                |
| Blockers         | 0                                                      |
| Warnings         | 8 (non-blocking, documented in section 11)             |
| Target           | GitHub Release (draft, then publish)                   |
| Tag              | `v0.2.0`                                               |
| Previous release | `v0.1.1` (2026-03-06, tagged)                          |

**Note:** CHANGELOG references v0.1.2 and v0.1.3 as intermediate versions. Neither has a corresponding git tag. Compare links for those versions will 404.

---

## 2. Version Sync Verification

All four version sources must match exactly.

| Source                             | Value   | Status |
|------------------------------------|---------|--------|
| `pyproject.toml` (`version`)       | `0.2.0` | PASS   |
| `obsidian_connector/__init__.py`   | `0.2.0` | PASS   |
| `mcpb.json` (`version`)           | `0.2.0` | PASS   |
| `CHANGELOG.md` (`## [0.2.0]`)     | `0.2.0` | PASS   |

---

## 3. Build and CI Evidence

### Build System

| Field               | Value                         |
|----------------------|-------------------------------|
| Build backend        | hatchling                     |
| Config file          | `pyproject.toml`              |
| Python requirement   | `>=3.11`                      |
| Classifiers          | 3.11, 3.12, 3.13             |
| License              | MIT                           |

### CI Workflows

| Workflow     | File                              | Trigger                         | Jobs                                     |
|-------------|-----------------------------------|---------------------------------|------------------------------------------|
| CI          | `.github/workflows/ci.yml`        | PR to main, push to main        | lint, test (3x3 matrix), mcp-launch (2 OS), lockfile-check |
| Release     | `.github/workflows/release.yml`   | Tag push (`v*`)                 | build-artifacts, build-macos-dmg, create-release |
| Security    | `.github/workflows/security.yml`  | PR to main, push to main, weekly cron | codeql, pip-audit                   |

### CI Test Matrix

| OS               | Python 3.11 | Python 3.12 | Python 3.13 |
|------------------|-------------|-------------|-------------|
| macOS-latest     | 16 files    | 16 files    | 16 files    |
| ubuntu-latest    | 16 files    | 16 files    | 16 files    |
| windows-latest   | 16 files    | 16 files    | 16 files    |

**Total CI configurations:** 9 (3 OS x 3 Python).

### MCP Launch Smoke

| OS               | Status    |
|------------------|-----------|
| macOS-latest     | Tested    |
| ubuntu-latest    | Tested    |
| windows-latest   | **Excluded** (see Warning W5) |

### Lockfile Verification

CI includes a `lockfile-check` job that runs `pip-compile --generate-hashes --check` to ensure `requirements-lock.txt` stays in sync with `pyproject.toml`.

---

## 4. Test Evidence

### Test Inventory

| Category         | Files | LOC   | Runs in CI | Notes                                                 |
|------------------|-------|-------|------------|-------------------------------------------------------|
| Unit             | 15    | --    | Yes        | No Obsidian required                                  |
| Integration      | 3     | --    | No         | Requires Obsidian desktop (`integration_test`, `workflow_test`, `workflow_os_test`) |
| Smoke            | 1     | --    | No         | `smoke_test.py` (requires Obsidian)                   |
| MCP launch       | 1     | --    | Partial    | Bash script, macOS + Ubuntu only                      |
| Performance      | 1     | --    | No         | `perf_test.py` (local only)                           |
| Edge case        | 1     | --    | Yes        | `edge_case_test.py`                                   |
| Contract         | 1     | --    | Yes        | `mcp_tool_contract_test.py`                           |
| **Total**        | **23**| **6,024** | **16 in CI** |                                                  |

### 16 Tests Run in CI

1. `audit_test.py`
2. `audit_permissions_test.py`
3. `cache_test.py` (unit subtests only; integration subtests timeout without Obsidian)
4. `cli_parse_test.py`
5. `delegation_test.py`
6. `edge_case_test.py`
7. `escaping_test.py` (unit subtests only; integration subtests timeout without Obsidian)
8. `file_backend_test.py`
9. `graduate_test.py` (2 pre-existing failures, not regressions)
10. `graph_test.py`
11. `import_cycle_test.py`
12. `index_test.py`
13. `mcp_tool_contract_test.py`
14. `platform_test.py` (57 tests)
15. `thinking_deep_test.py`
16. `uninstall_test.py` (52 tests)

### 7 Tests Excluded from CI

| Test File             | Reason                                    |
|-----------------------|-------------------------------------------|
| `smoke_test.py`       | Requires running Obsidian desktop         |
| `integration_test.py` | Requires running Obsidian desktop         |
| `workflow_test.py`    | Requires running Obsidian desktop         |
| `workflow_os_test.py` | Requires running Obsidian desktop         |
| `checkin_test.py`     | Requires running Obsidian desktop         |
| `thinking_tools_test.py` | Requires running Obsidian desktop      |
| `perf_test.py`        | Performance benchmark, local only         |

### Pre-Existing Failures

| Test File          | Failures | Root Cause                                   | Severity |
|--------------------|----------|----------------------------------------------|----------|
| `graduate_test.py` | 2 of 26  | Heading candidate detection heuristic misses edge cases | Low |

These are not v0.2.0 regressions.

### Coverage

Coverage is collected in CI via `coverage run --append` but **not enforced**. The CI step runs `coverage report --fail-under=0`, meaning any coverage percentage passes. Actual line/branch coverage numbers are not persisted as artifacts.

---

## 5. Security Evidence

### Static Analysis

| Tool      | Scope              | Trigger             | Status    |
|-----------|--------------------|----------------------|-----------|
| CodeQL    | Python             | PR, push, weekly     | Configured |
| pip-audit | Dependencies       | PR, push, weekly     | Configured |

### Security Model

| Control                        | Status    | Evidence                                      |
|--------------------------------|-----------|-----------------------------------------------|
| No `shell=True` in subprocess  | PASS      | All subprocess calls use list-based arguments  |
| Parameterized SQL              | PASS      | SQLite queries use `?` placeholders            |
| Path traversal protection      | PASS      | `graduate_execute` validates title and folder  |
| osascript injection prevention | PASS      | Notification strings escaped before interpolation |
| No hardcoded secrets           | PASS      | Local-only tool, no credentials stored         |
| No network calls in core       | PASS      | All operations are filesystem-local            |
| Audit log directory permissions| PASS      | `0o700` (owner-only) on creation and upgrade   |
| Config backup before mutation  | PASS      | Timestamped backup of Claude Desktop config    |

### Out-of-Scope Threats

- Physical access to the machine
- Compromise of Obsidian desktop application
- Malicious Markdown content (tool reads as plain text)
- Denial-of-service via large vaults

---

## 6. Dependency Inventory

### Direct Dependencies

| Package | Version Constraint | License | Purpose           |
|---------|--------------------|---------|-------------------|
| mcp     | `>=1.0.0,<2.0.0`  | MIT     | MCP server protocol |

### Optional Dependencies

| Package | Version Constraint | License | Purpose                | Install Extra  |
|---------|--------------------|---------|------------------------|----------------|
| pyyaml  | `>=6.0,<7.0`      | MIT     | Schedule config parsing | `scheduling`   |

### Lockfile Summary

| Metric                     | Value |
|----------------------------|-------|
| Total packages in lockfile | 29    |
| Direct dependency          | 1 (mcp 1.26.0) |
| Transitive dependencies    | 28    |
| All hashes present         | Yes (SHA256, via `pip-compile --generate-hashes`) |
| Lockfile CI check          | Yes (`pip-compile --check` in `lockfile-check` job) |
| pip-audit result           | 0 known vulnerabilities (as of 2026-03-16) |

### Transitive Dependency Tree (via mcp 1.26.0)

| Package                    | Pinned Version | License       |
|----------------------------|----------------|---------------|
| annotated-types            | 0.7.0          | MIT           |
| anyio                      | 4.12.1         | MIT           |
| attrs                      | 25.4.0         | MIT           |
| certifi                    | 2026.2.25      | MPL-2.0       |
| cffi                       | 2.0.0          | MIT           |
| click                      | 8.3.1          | BSD-3-Clause  |
| cryptography               | 46.0.5         | Apache-2.0/BSD |
| h11                        | 0.16.0         | MIT           |
| httpcore                   | 1.0.9          | BSD-3-Clause  |
| httpx                      | 0.28.1         | BSD-3-Clause  |
| httpx-sse                  | 0.4.3          | MIT           |
| idna                       | 3.11           | BSD-3-Clause  |
| jsonschema                 | 4.26.0         | MIT           |
| jsonschema-specifications  | 2025.9.1       | MIT           |
| pycparser                  | 3.0            | BSD-3-Clause  |
| pydantic                   | 2.12.5         | MIT           |
| pydantic-core              | 2.41.5         | MIT           |
| pydantic-settings          | 2.13.1         | MIT           |
| pyjwt[crypto]              | 2.12.1         | MIT           |
| python-dotenv              | 1.2.2          | BSD-3-Clause  |
| python-multipart           | 0.0.22         | Apache-2.0    |
| referencing                | 0.37.0         | MIT           |
| rpds-py                    | 0.30.0         | MIT           |
| sse-starlette              | 3.3.2          | BSD-3-Clause  |
| starlette                  | 0.52.1         | BSD-3-Clause  |
| typing-extensions          | 4.15.0         | PSF-2.0       |
| typing-inspection          | 0.4.2          | MIT           |
| uvicorn                    | 0.42.0         | BSD-3-Clause  |

### Stdlib-Only Modules (No External Dependencies)

These modules import only from the Python standard library:

- `client.py` (subprocess, json, os)
- `graph.py` (os, re, pathlib)
- `index_store.py` (sqlite3, json)
- `audit.py` (json, datetime, pathlib)
- `config.py` (os, json, pathlib)
- `thinking.py` (re, collections, datetime)
- `workflows.py` (os, re, datetime, pathlib)
- `platform.py` (os, subprocess, pathlib, platform)
- `file_backend.py` (os, re, pathlib, tempfile)
- `uninstall.py` (json, os, shutil, tempfile, pathlib)

Only `mcp_server.py` imports the `mcp` package.

---

## 7. Release Assets and Signing

### Release Workflow Output

The release workflow is triggered by pushing a `v*` tag. It creates a **draft** GitHub Release.

| Asset                                      | Type        | Source Job         |
|--------------------------------------------|-------------|--------------------|
| `obsidian-connector-v0.2.0.tar.gz`         | Source archive | build-artifacts  |
| `obsidian-connector-v0.2.0.zip`            | Source archive | build-artifacts  |
| `obsidian-connector-v0.2.0.dmg`            | macOS installer | build-macos-dmg |
| `obsidian-connector-v0.2.0.sha256`         | Checksum file  | create-release   |
| `obsidian-connector-v0.2.0.tar.gz.sig`     | Cosign signature | create-release |
| `obsidian-connector-v0.2.0.tar.gz.cert`    | Cosign certificate | create-release |
| `obsidian-connector-v0.2.0.zip.sig`        | Cosign signature | create-release |
| `obsidian-connector-v0.2.0.zip.cert`       | Cosign certificate | create-release |
| `obsidian-connector-v0.2.0.dmg.sig`        | Cosign signature | create-release |
| `obsidian-connector-v0.2.0.dmg.cert`       | Cosign certificate | create-release |
| `obsidian-connector-v0.2.0.sha256.sig`     | Cosign signature | create-release |
| `obsidian-connector-v0.2.0.sha256.cert`    | Cosign certificate | create-release |

**Total assets:** 12 (3 distributable + 1 checksum + 4 signatures + 4 certificates).

### Signing

| Method         | Tool                        | Identity              |
|----------------|-----------------------------|-----------------------|
| Asset signing  | Sigstore cosign (keyless)   | GitHub OIDC token     |
| Tag signing    | 1Password SSH (`op-ssh-sign`) | Maintainer GPG key  |

### User Verification Command

```bash
cosign verify-blob \
  --signature obsidian-connector-v0.2.0.tar.gz.sig \
  --certificate obsidian-connector-v0.2.0.tar.gz.cert \
  --certificate-identity-regexp ".*github.com/mariourquia/obsidian-connector.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  obsidian-connector-v0.2.0.tar.gz
```

---

## 8. Installation Verification Matrix

### Entry Points

| Entry Point            | Target                         |
|------------------------|--------------------------------|
| `obsidian-connector`   | `obsidian_connector.cli:main`  |
| `obsx`                 | `obsidian_connector.cli:main`  |

### Install Methods

| Method                 | Platform       | Script / Path                                |
|------------------------|----------------|----------------------------------------------|
| macOS .dmg installer   | macOS          | `scripts/create-dmg.sh` -> `.dmg` release asset |
| macOS terminal install | macOS          | `scripts/install.sh`                         |
| Linux terminal install | Linux          | `scripts/install-linux.sh`                   |
| Windows PowerShell     | Windows        | Manual setup per README                      |
| pip editable install   | All            | `pip install -e .`                           |
| ZIP/tar.gz manual      | All            | Download from GitHub Release                 |

### Installer Artifacts Created

| Artifact                          | macOS                              | Linux                                    | Windows                                  |
|-----------------------------------|------------------------------------|------------------------------------------|------------------------------------------|
| CLI symlink                       | `/usr/local/bin/obsx`              | `~/.local/bin/obsx`                      | N/A (pip entry point)                    |
| Scheduled automation              | `~/Library/LaunchAgents/*.plist`   | `~/.config/systemd/user/*.timer`         | N/A                                      |
| Claude Desktop MCP config         | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.config/claude-desktop/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code skills                | `.claude/commands/{morning,evening,idea,weekly}.md` | Same | Same |
| SessionStart hook                 | `.claude/settings.json`            | Same                                     | Same                                     |

### Surface Area

| Category       | Count |
|----------------|-------|
| MCP tools      | 29    |
| CLI commands   | 29 (27 top-level + 2 graduate subcommands) |
| Skills         | 4 (`/morning`, `/evening`, `/idea`, `/weekly`) |
| Hooks          | 1 (SessionStart auto check-in) |
| Python modules | 20    |
| Code LOC       | 8,722 |

---

## 9. Breaking Changes

### API Breaking Changes

None. v0.2.0 is additive relative to v0.1.1.

### Behavioral Changes

| Change                               | Impact                                           |
|--------------------------------------|--------------------------------------------------|
| Daily note date uses local time      | Previously used UTC. Notes now match the user's local date. |
| `ObsidianNotRunning` fires independently | Previously gated behind other error checks. Now detected and raised on its own. |
| `batch_read_notes` fallback returns `""` | For missing notes. Previously could raise or return inconsistent values. |

### Vault Data

No vault data is modified, migrated, or deleted. The tool never writes to vault notes directly (only to daily notes via append, and to standalone draft notes via `graduate_execute`).

---

## 10. Known Limitations and Risks

### Platform Limitations

| Platform | Status    | Gaps                                                     |
|----------|-----------|----------------------------------------------------------|
| macOS    | Supported | ARM64 tested (CI runners). Intel via Rosetta untested.   |
| Linux    | Supported | x86_64 tested in CI. ARM64 untested.                    |
| Windows  | Supported | x86_64 tested in CI. MCP launch smoke test excluded.    |
| ARM64    | Partial   | macOS ARM tested. Linux ARM not tested.                  |

### Runtime Dependencies

| Dependency      | Required For                                      |
|-----------------|---------------------------------------------------|
| Obsidian desktop v1.12+ | 22 of 29 MCP tools (CLI-based operations)  |
| Python >=3.11   | All functionality                                 |
| mcp >=1.0.0     | MCP server mode only                              |

7 of 29 MCP tools work without Obsidian running: `neighborhood`, `vault_structure`, `backlinks`, `rebuild_index`, `doctor`, `obsidian_uninstall`, and `check_in` (partial: vault reads still need Obsidian).

### Architecture Risks

- `cli.py` (1,599 LOC) and `workflows.py` (1,594 LOC) are monolithic. Refactoring planned for v0.3.0.
- Single maintainer. Bus factor of 1.
- No plugin system for third-party extensions.

---

## 11. Warnings (Non-Blocking)

| ID  | Warning                                              | Severity | Mitigation                                                |
|-----|------------------------------------------------------|----------|-----------------------------------------------------------|
| W1  | No `dependabot.yml` configured                       | Low      | Dependency updates are manual. Lockfile CI check catches drift. |
| W2  | Coverage collected but not enforced (`--fail-under=0`) | Medium  | Coverage is reported in CI logs but no regression gate exists. |
| W3  | No pre-commit hooks configured                       | Low      | Docs lint and tests run in CI. Local dev relies on manual `make docs-lint`. |
| W4  | CHANGELOG references v0.1.2 and v0.1.3 tags that do not exist | Low | Compare links for those versions will 404. Only v0.1.0 and v0.1.1 tags exist. |
| W5  | MCP launch smoke test excludes Windows               | Medium   | `mcp_launch_smoke.sh` is a Bash script. Windows MCP launch is untested in CI. |
| W6  | 7 of 23 test files excluded from CI                  | Medium   | These require Obsidian desktop. Documented as local-only validation. |
| W7  | Audit log is not tamper-resistant                     | Low      | Same-user can modify/delete audit JSONL files. Acceptable for single-user local tool. |
| W8  | `--http` MCP mode binds to network                   | Medium   | Not documented in SECURITY.md. The `--http` flag starts a network-accessible server. Users invoking it should understand the exposure. |

---

## 12. Deferred Items (v0.3.0+)

| Item                                         | Rationale for Deferral                           |
|----------------------------------------------|--------------------------------------------------|
| PyPI publication                             | Distribution is GitHub-only for now. Tracked in ROADMAP. |
| Dependabot automation                        | Low urgency with 1 direct dependency.            |
| Coverage enforcement threshold               | Need baseline measurement first.                 |
| Pre-commit hook configuration                | CI catches issues. Local DX improvement.         |
| Custom daily note format support             | Requires Periodic Notes plugin detection.        |
| `cli.py` / `workflows.py` decomposition      | Functional but monolithic. Refactor planned.     |
| Windows MCP launch smoke test                | Requires porting `mcp_launch_smoke.sh` to PowerShell or cross-platform runner. |
| Audit log tamper detection                   | Out of scope for single-user local tool.         |
| `--http` mode security documentation         | Requires threat model for network exposure.      |
| CHANGELOG tag gap (v0.1.2, v0.1.3)          | Retroactive tagging or CHANGELOG correction.     |

---

## 13. Maintainer Release Steps

Reference: `docs/generated/MAINTAINER_RELEASE_CHECKLIST.md` for the full checklist.

### Summary

```
1. Verify version sync (pyproject.toml, __init__.py, mcpb.json, CHANGELOG.md)
2. Run `make docs-lint` -- must pass
3. Run CI-safe tests locally
4. Push branch, open PR: feature/uninstaller -> main
5. Wait for CI (lint + 9 test matrix + 2 MCP launch + lockfile check)
6. Merge PR
7. Tag: git tag -s v0.2.0 -m "v0.2.0"
8. Push tag: git push origin v0.2.0
9. Release workflow runs automatically (builds artifacts, signs, creates draft release)
10. Review draft release on GitHub
11. Publish (undraft)
12. Delete feature/uninstaller branch
13. Verify rollback: git checkout v0.1.1, install, import
```

**Assumption:** The maintainer has GPG signing configured via 1Password SSH (`op-ssh-sign`). Tag signing will fail without this.

---

## 14. User Verification Steps

Reference: `docs/generated/USER_VERIFICATION_CHECKLIST.md` for the full checklist.

### Minimal Verification

```bash
# 1. Download and verify checksum
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.2.0/obsidian-connector-v0.2.0.sha256
curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.2.0/obsidian-connector-v0.2.0.tar.gz
sha256sum -c obsidian-connector-v0.2.0.sha256

# 2. Verify cosign signature
cosign verify-blob \
  --signature obsidian-connector-v0.2.0.tar.gz.sig \
  --certificate obsidian-connector-v0.2.0.tar.gz.cert \
  --certificate-identity-regexp ".*github.com/mariourquia/obsidian-connector.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  obsidian-connector-v0.2.0.tar.gz

# 3. Install and test
python3 -m venv /tmp/test-obsx
source /tmp/test-obsx/bin/activate
pip install -e .
python3 -c "import obsidian_connector; print(obsidian_connector.__version__)"
# Expected: 0.2.0

# 4. Run offline tests
python3 scripts/audit_test.py
python3 scripts/graph_test.py
python3 scripts/platform_test.py
python3 scripts/uninstall_test.py

# 5. Health check (requires Obsidian running)
./bin/obsx doctor

# 6. Clean up
deactivate && rm -rf /tmp/test-obsx
```

---

## Assumptions

1. CI status is inferred from workflow definitions, not from a specific run. The most recent CI run was not independently verified at document generation time.
2. The 2 pre-existing `graduate_test.py` failures are accepted and are not v0.2.0 regressions.
3. `cache_test.py` and `escaping_test.py` integration subtests timing out without Obsidian is expected and documented behavior.
4. Transitive dependency versions in `requirements-lock.txt` are current as of 2026-03-16. No CVEs found by `pip-audit` at that time.
5. The release workflow has not been run for v0.2.0 yet. Artifact names and signing behavior are inferred from the workflow YAML.
6. macOS CI runners use ARM64 (Apple Silicon). Intel compatibility is assumed via Rosetta but not independently tested.
7. The `--http` MCP mode network binding behavior is inferred from code, not from explicit testing in this review.
