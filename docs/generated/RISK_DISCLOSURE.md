---
title: "Risk Disclosure: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Risk Disclosure: obsidian-connector v0.2.0

> Date: 2026-03-16

## Security Risks

| Risk                                          | Severity | Status    | Mitigation                                                   |
|-----------------------------------------------|----------|-----------|--------------------------------------------------------------|
| Runs shell commands (Obsidian CLI, launchctl)  | M        | Mitigated | List-based subprocess args, no shell=True. Binary path rejects metacharacters. |
| Reads/writes local filesystem                  | M        | Mitigated | Path traversal protection via `.resolve()` + `.relative_to()`. Vault path confined to vault root. |
| Modifies Claude Desktop config JSON            | M        | Mitigated | Atomic writes (tempfile + os.replace), timestamped backups, JSON validation before write. |
| osascript string interpolation (macOS)         | M        | Mitigated | Full metacharacter escaping (backslash, quotes, newline, CR, tab). |
| PowerShell notification dispatch (Windows)     | M        | Mitigated | Values passed via environment variables, no string interpolation. `-NoProfile` flag. |
| `file_backend.py` wired via `client_fallback.py` adapter | M | Mitigated | Fallback reads vault files directly when Obsidian CLI unavailable. Path traversal protection via `.resolve()` + `.relative_to()`. |
| `mcp` dependency includes httpx/uvicorn (HTTP stack) | M | Accepted | `--http` mode binds to a network port. Default is stdio (no network). Users must opt in to HTTP transport. |
| Audit log is not tamper-resistant               | M        | Accepted  | Audit JSONL files are owned by the same user who runs the tool. A local attacker with same-user access can modify or delete audit entries. |
| No authentication on MCP stdio transport       | L        | Accepted  | Standard for local MCP servers. Only local processes can connect. |
| No dependency scanning in CI                   | L        | Accepted  | Manual pip-audit (0 vulns). CodeQL planned for v0.3.0.       |
| Release assets signed via Sigstore cosign      | L        | Mitigated | Keyless OIDC signing in CI. `.sig` and `.cert` files attached to each release artifact. |

## Operational Risks

| Risk                                          | Likelihood | Impact | Mitigation                                                  |
|-----------------------------------------------|------------|--------|-------------------------------------------------------------|
| Obsidian CLI not available (app not running)   | M          | L      | `obsx doctor` health check. Graph/uninstall/doctor work offline. Error messages guide user. |
| Config file corruption during uninstall        | L          | M      | Timestamped backup created before modification. JSON validation before write. Atomic os.replace. |
| SQLite index corruption                        | L          | L      | `rebuild-index` tool rebuilds from scratch. Index is a cache, not authoritative data. |
| launchd/systemd schedule misconfiguration      | L          | L      | `obsx doctor` detects missing/broken schedules. Manual install/uninstall commands available. |

## Compatibility Risks

| Risk                                          | Affected Users                | Mitigation                                                  |
|-----------------------------------------------|-------------------------------|-------------------------------------------------------------|
| `uninstall` MCP tool renamed to `obsidian_uninstall` | MCP callers using old tool name | Update tool name in prompts. Old name no longer exists.     |
| Config search order reversed (CWD no longer priority) | Users with `config.json` in CWD | Move config.json to package directory.                      |
| Exception types narrowed in workflows/thinking | Code catching `Exception` from these modules | Catch specific types listed in CHANGELOG.                   |
| `mcp` package range `>=1.0.0,<2.0.0`          | Users with mcp 2.x (when released) | Pin maintained in pyproject.toml. Test with mcp 2.x before bumping. |

## Maintenance Risks

- Maintainer count: 1
- Bus factor: 1
- Last commit: 2026-03-16 (today)
- Open issues: check repository
- Open security issues: 0 known
- Dependency freshness: current (mcp 1.x, pyyaml 6.x)

## Tradeoffs Accepted

- **Obsidian CLI dependency over direct file access**: Chose to use the Obsidian desktop CLI for vault operations rather than reading markdown files directly. This requires Obsidian to be running but ensures compatibility with Obsidian's internal data model, plugins, and sync. `file_backend.py` (direct file access) is wired in via `client_fallback.py` adapter.
- **No PyPI publication**: Distributed via GitHub Release + git clone. This avoids PyPI supply chain risk but means users cannot `pip install obsidian-connector` from the registry. Users install from source.
- **Custom test runner over pytest**: Tests use Python's `unittest` via custom scripts in `scripts/`. This avoids a pytest dependency but means no coverage measurement, no parallel test execution, and non-standard test discovery.
- **Regex over semantic analysis**: Thinking tools (drift, ghost, trace) use regex patterns for text extraction. This is fast and dependency-free but produces heuristic results that depend on note structure.
## Blast Radius

If this release fails in production, the expected impact is:

- **Data**: Cannot corrupt or lose vault data. The tool reads vault notes via Obsidian CLI and never writes to vault files directly. The only writable data is audit logs (JSONL), SQLite index cache (rebuildable), and Claude Desktop config (backed up before modification).
- **Availability**: A crash in the MCP server disconnects Claude Desktop from Obsidian tools. Restarting Claude Desktop reconnects. A crash in the CLI exits the process. No persistent daemons other than the optional launchd/systemd schedule.
- **Security**: Failure cannot expose secrets (none stored). Failure cannot expose vault data over the network (no network calls). The worst case is a malformed osascript/PowerShell string that fails to display a notification.
- **Downstream**: No known downstream consumers. This is an end-user tool, not a library.
