---
title: "Security Review: Uninstaller Module"
status: draft
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Security Review: Uninstaller Module

**Scope**: `obsidian_connector/uninstall.py`, MCP tool `uninstall` in `mcp_server.py`, CLI subcommand `uninstall` in `cli.py`

**Review date**: 2026-03-16

---

## 1. Threat Model

The uninstaller removes locally installed artifacts: virtual environments, skill files, launchd plists, Claude Desktop config entries, audit logs, and cache databases. It runs entirely on the local machine under the invoking user's privileges. The primary threat categories are:

| Threat | Description |
|--------|-------------|
| **Unintended data loss** | User accidentally removes artifacts they wanted to keep. |
| **Config corruption** | A failed or partial write to `claude_desktop_config.json` leaves the file in an unparseable state, breaking Claude Desktop. |
| **Scope escape** | The uninstaller deletes files outside its intended artifact set (path traversal, symlink following). |
| **Unauthorized invocation** | A malicious MCP client or prompt-injection attack triggers destructive removal without user consent. |
| **Race condition (TOCTOU)** | File state changes between detection and removal, causing unexpected behavior. |
| **Denial of service** | Removing audit logs or cache erases operational history or forces expensive rebuilds. |

---

## 2. Attack Surface Analysis

### 2.1 MCP Tool Exposure

The `uninstall` MCP tool is exposed to any MCP client connected to the server. Key properties:

- **ToolAnnotations**: `destructiveHint=True`, `readOnlyHint=False`, `idempotentHint=False`. Correctly signals destructive intent to MCP hosts.
- **Default dry-run**: `dry_run=True` is the default. An MCP client must explicitly set `dry_run=False` to execute removal. This is the correct safe default.
- **Per-artifact flags**: Even with `dry_run=False`, each artifact type (`remove_venv`, `remove_skills`, etc.) defaults to `False`. The caller must opt in to each category individually. This limits blast radius.
- **No authentication layer**: MCP stdio transport has no auth. Any process that can connect to the MCP server can invoke the tool. This is standard for local MCP servers and is mitigated by the dry-run default plus per-artifact opt-in.

**Risk**: Low. Double-gate design (dry_run + per-artifact flags) makes accidental destructive invocation unlikely.

### 2.2 CLI Exposure

- **Interactive mode** (default): Prompts the user per-artifact, then requires a final `y/N` confirmation before executing. Safe.
- **`--force` mode**: Bypasses interactive prompts. Requires explicit `--remove-*` flags for each artifact type. Designed for scripted/CI contexts.
- **`--dry-run` mode**: Preview only, no mutations.

**Risk**: Low. Interactive confirmation is the default. Force mode still requires explicit per-artifact flags.

### 2.3 File Deletion Scope

Files the uninstaller can delete:

| Artifact | Path Pattern | Scope |
|----------|-------------|-------|
| Virtual environment | `{repo_root}/.venv/` | Single directory tree via `shutil.rmtree` |
| Skill files | `{repo_root}/.claude/commands/{morning,evening,idea,weekly}.md` | 4 hardcoded filenames only |
| Launchd plist | `~/Library/LaunchAgents/com.obsidian-connector.daily.plist` | Single hardcoded path |
| Claude Desktop config | `~/Library/Application Support/Claude/claude_desktop_config.json` | Key removal only (not file deletion) |
| Audit logs | `~/.obsidian-connector/logs/` | Not directly in uninstall.py (would need plan.files_to_remove population) |
| Cache/index | `~/.obsidian-connector/index.sqlite` | Not directly in uninstall.py (would need plan.files_to_remove population) |

All paths are constructed from `Path(__file__).parent.parent` (repo root), `Path.home()`, or hardcoded constants. No user-supplied path components are interpolated into deletion targets.

**Risk**: Low. Deletion scope is bounded by hardcoded paths and a fixed filename allowlist for skills.

---

## 3. Safety Mechanism Review

### 3.1 Timestamped Config Backups

**Implementation**: `backup_config_file()` copies the config file to `{config_path}.backup-{YYYY-MM-DD-HH-MM-SS}` before any modification.

**Assessment**: Effective. The backup is created before the config is modified, so even if the process crashes mid-write, the backup exists. The timestamp format is second-granularity, which is sufficient for interactive use. Multiple rapid invocations within the same second could overwrite a backup, but this is an edge case with negligible real-world risk.

**Risk**: Low.

### 3.2 JSON Validation After Config Edits

**Implementation**: `remove_from_json_config()` serializes the modified config to a string, validates it with `json.loads()`, and only writes back if validation passes.

**Assessment**: Effective. The validate-then-write pattern prevents writing corrupted JSON. However, there is a subtle TOCTOU gap: between reading and writing the config file, another process could modify it, and the write would silently overwrite those changes. See Section 6 for analysis.

**Risk**: Low (see TOCTOU section for nuance).

### 3.3 Launchd Plist Unload Before Removal

**Implementation**: `unload_launchd_plist()` calls `launchctl unload` before `plist_path.unlink()`.

**Assessment**: Correct ordering. The subprocess call uses list-based arguments (no `shell=True`), `check=False` (tolerates already-unloaded plists), and `capture_output=True` (suppresses stderr noise). If unload fails (e.g., plist already unloaded), the file is still removed. This is the right behavior for idempotent cleanup.

**Risk**: Low.

### 3.4 Audit Logging

**Implementation**: The CLI interactive path calls `log_action("uninstall", ...)` before executing removal.

**Assessment**: Partially effective. The CLI interactive mode logs the intent before execution, which is correct. However, the MCP tool path in `mcp_server.py` does not call `log_action()` -- it invokes `execute_uninstall()` directly. This means MCP-initiated uninstalls are not audit-logged. See Recommendations.

**Risk**: Medium. MCP-initiated uninstalls lack audit trail.

### 3.5 Idempotent Operation

**Implementation**: `remove_file_safely()` checks `exists()` and `is_symlink()` before removal. Returns `True` if the file is already gone.

**Assessment**: Effective. Re-running the uninstaller after a successful run is safe. No errors are raised for already-removed artifacts.

**Risk**: Low.

### 3.6 Symlink Handling

**Implementation**: `remove_file_safely()` checks `is_symlink()` before `is_dir()` and calls `unlink()` for symlinks rather than `rmtree()`.

**Assessment**: Correct. This prevents following a symlink from `.venv` to an arbitrary directory and deleting its contents. If `.venv` is a symlink pointing elsewhere, only the symlink itself is removed, not the target.

**Risk**: Low.

### 3.7 Subprocess Safety

**Implementation**: All `subprocess.run()` calls use list-based arguments. No `shell=True` anywhere in the codebase.

**Assessment**: Effective. Command injection via argument values is not possible with list-based subprocess invocation.

**Risk**: Low.

---

## 4. Risk Summary

| Risk | Rating | Justification |
|------|--------|---------------|
| Unintended data loss | **Low** | Double-gate (dry_run default + per-artifact flags), interactive confirmation, backups |
| Config corruption | **Low** | JSON validation before write, timestamped backup |
| Scope escape / path traversal | **Low** | All paths hardcoded or derived from known roots; symlinks handled correctly |
| Unauthorized MCP invocation | **Low** | dry_run=True default, per-artifact opt-in, destructiveHint annotation |
| TOCTOU race on config file | **Low** | Theoretically possible but requires concurrent config modification (see Section 6) |
| Missing MCP audit trail | **Medium** | MCP tool does not call log_action(); uninstalls via MCP leave no audit record |
| Audit log / cache deletion | **Low** | Requires explicit opt-in; these are recoverable (logs are informational, cache is rebuilt) |
| Command injection | **Low** | List-based subprocess, no shell=True, binary path sanitized in config.py |

---

## 5. TOCTOU Analysis

Three file operations in the uninstaller have a time-of-check-time-of-use gap:

### 5.1 Config File Read-Modify-Write

```
detect_installed_artifacts() reads config  -->  time passes  -->  execute_uninstall() reads again, modifies, writes
```

**Gap**: Between detection and execution, another process could modify `claude_desktop_config.json`. The uninstaller would read the newer version during execution (it re-reads in `remove_from_json_config`), so it would not clobber concurrent changes -- unless the concurrent change adds back the `obsidian-connector` key, in which case it would be removed. This is semantically correct behavior for an uninstaller.

**Mitigation**: `remove_from_json_config()` reads the file fresh each time, so stale detection data does not cause data loss. The backup is created from the current state at execution time.

**Residual risk**: Negligible. The config file is human-edited or tool-edited at low frequency.

### 5.2 File Existence Check Before Removal

```
detect_installed_artifacts() checks exists()  -->  time passes  -->  remove_file_safely() attempts removal
```

**Gap**: A file could be removed between detection and the removal attempt. `remove_file_safely()` handles this gracefully: if the file no longer exists, it returns `True` (success). No exception is raised.

**Residual risk**: None. Idempotent design eliminates this class of bug.

### 5.3 Plist Existence Check Before Unload

```
detect_installed_artifacts() checks plist exists  -->  time passes  -->  unload_launchd_plist() checks again, unloads, removes
```

**Gap**: The plist could be removed between detection and unload. `unload_launchd_plist()` re-checks `exists()` before acting and catches OSError. `launchctl unload` on a stale path is a no-op (returns non-zero, ignored via `check=False`).

**Residual risk**: None.

---

## 6. Permission Model

The uninstaller operates under the invoking user's filesystem permissions. It does not require elevated privileges.

| Operation | Required Permission |
|-----------|-------------------|
| Remove `.venv/` | Write to repo directory |
| Remove skill `.md` files | Write to `{repo}/.claude/commands/` |
| Modify `claude_desktop_config.json` | Write to `~/Library/Application Support/Claude/` |
| `launchctl unload` | User-level LaunchAgents (no root) |
| Remove plist | Write to `~/Library/LaunchAgents/` |
| Remove audit logs | Write to `~/.obsidian-connector/logs/` |
| Remove cache | Write to `~/.obsidian-connector/` |

All paths are within the user's home directory or the repo clone directory. No root/sudo is needed. No capabilities or entitlements are required.

**Risk**: Low. The permission model is minimal and does not require privilege escalation.

---

## 7. Recommendations

### 7.1 Add Audit Logging to MCP Tool (Medium Priority)

The MCP `uninstall` tool in `mcp_server.py` should call `log_action()` before invoking `execute_uninstall()`, mirroring the CLI's behavior. Currently, MCP-initiated uninstalls produce no audit record.

Suggested addition in `mcp_server.py` `uninstall()` function, before the `execute_uninstall()` call:

```python
from obsidian_connector.audit import log_action
log_action(
    "uninstall",
    {"mode": "mcp", "dry_run": dry_run, "remove_venv": remove_venv, ...},
    vault=None,
    dry_run=dry_run,
    affected_path="system-config",
)
```

### 7.2 Consider File Locking for Config Writes (Low Priority)

The read-modify-write on `claude_desktop_config.json` is not atomic. For defense-in-depth, an advisory file lock (e.g., `fcntl.flock`) could be acquired during the config modification window. This is low priority because concurrent config edits are rare in practice.

### 7.3 Verify Logs and Cache Removal Coverage (Low Priority)

The `detect_installed_artifacts()` function does not populate `files_to_remove` for audit logs (`~/.obsidian-connector/logs/`) or cache (`~/.obsidian-connector/index.sqlite`). If `remove_logs` or `remove_cache` flags are set but the corresponding paths are not in `files_to_remove`, `execute_uninstall()` will not remove them. Verify that these artifact types are handled elsewhere in the execution flow or add them to detection.

---

## 8. Verdict

**Overall security posture: Strong (Low risk)**

The uninstaller demonstrates defense-in-depth with multiple layers of protection against accidental data loss:

1. **Safe defaults** -- MCP defaults to dry-run; each artifact type defaults to keep.
2. **Explicit opt-in** -- Both CLI (interactive prompts) and MCP (per-artifact flags) require deliberate action for each artifact category.
3. **Backup before modify** -- Config files are backed up with timestamps before any edit.
4. **Validation after modify** -- JSON validity is confirmed before writing config changes.
5. **Correct subprocess hygiene** -- List-based arguments, no shell injection vectors.
6. **Bounded scope** -- Hardcoded paths and filename allowlists prevent scope escape.
7. **Symlink awareness** -- Symlinks are unlinked rather than followed, preventing collateral damage.
8. **Idempotent design** -- Re-running is safe; already-removed artifacts do not cause errors.
9. **Proper ToolAnnotations** -- MCP hosts can surface the destructive nature of the tool to users.

The single medium-risk finding (missing MCP audit trail) is a logging gap, not a data safety issue. The core deletion logic is well-protected. No critical or high-risk findings.
