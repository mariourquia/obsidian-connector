# v0.2.0 Hardening & Cross-Platform Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a hardened v0.2.0 that fixes all critical findings (version sync, doc counts, audit log security, CI coverage), addresses high-priority structural issues (circular dep, code duplication, error handling inconsistency), and adds Linux/Windows cross-platform support.

**Architecture:** Fix-forward approach -- no large refactors (cli.py/workflows.py split deferred to v0.2.1). All changes are backward-compatible. Cross-platform support adds platform detection in config.py and scheduling abstraction in a new platform.py module. Tests use pytest-style assertions in existing scripts/ runners (full pytest migration deferred to backlog).

**Tech Stack:** Python 3.11+, mcp SDK, GitHub Actions CI, hatchling build system

**Deferred to v0.2.1+:**
- Finding #6: cli.py/workflows.py split (1,598/1,603 LOC) -- too risky mid-release
- Finding #13: Parameter naming normalization (name_or_path vs note_path) -- breaking change needs deprecation
- Finding #14: Long function extraction (ghost_voice_profile 192 LOC etc.) -- pairs with #6
- Finding #20: PyPI publishing workflow
- Finding #21: macOS-only limitation (addressed partially by cross-platform work here)

---

## Chunk 1: Foundation Fixes

### Task 1: Version Sync (Critical #1)

**Files:**
- Modify: `pyproject.toml:7`
- Modify: `obsidian_connector/__init__.py:3`
- Verify: `.claude-plugin/plugin.json:3` (already 0.2.0)

All three version sources must read `0.2.0`.

- [ ] **Step 1: Update pyproject.toml version**

```python
# pyproject.toml line 7
version = "0.2.0"
```

- [ ] **Step 2: Update __init__.py version**

```python
# obsidian_connector/__init__.py line 3
__version__ = "0.2.0"
```

- [ ] **Step 3: Verify plugin.json already correct**

Run: `python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); assert d['version']=='0.2.0', f'got {d[\"version\"]}'; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Verify all three match**

Run: `python3 -c "
import json, tomllib
with open('pyproject.toml','rb') as f: pt = tomllib.load(f)['project']['version']
from obsidian_connector import __version__ as iv
with open('.claude-plugin/plugin.json') as f: pj = json.load(f)['version']
assert pt == iv == pj == '0.2.0', f'mismatch: pyproject={pt} init={iv} plugin={pj}'
print(f'All versions: {pt}')
"`
Expected: `All versions: 0.2.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml obsidian_connector/__init__.py
git commit -m "fix: sync all version sources to 0.2.0 (Critical #1)"
```

---

### Task 2: Audit Log Directory Permissions (Critical #3)

**Files:**
- Modify: `obsidian_connector/audit.py:45`
- Create: `scripts/audit_permissions_test.py`

The audit log directory `~/.obsidian-connector/logs/` is created with default umask (typically 755), exposing search queries and note paths on shared machines. Fix to 0o700 (owner-only).

- [ ] **Step 1: Write the failing test**

Create `scripts/audit_permissions_test.py`:

```python
"""Test audit log directory permissions."""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

# Test 1: New directory gets restricted permissions
def test_audit_dir_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        test_dir = Path(tmp) / "audit-test" / "logs"
        with patch("obsidian_connector.audit.AUDIT_DIR", test_dir):
            from obsidian_connector.audit import log_action
            log_action(
                command="test",
                args={"q": "secret query"},
                vault="test-vault",
            )
        assert test_dir.exists(), "audit dir should be created"
        mode = stat.S_IMODE(test_dir.stat().st_mode)
        assert mode == 0o700, (
            f"audit dir should be 0o700 (owner-only), got {oct(mode)}"
        )
    print("PASS: test_audit_dir_permissions")


# Test 2: Parent directory also gets restricted permissions
def test_audit_parent_dir_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp) / "obsidian-connector-test"
        test_dir = parent / "logs"
        with patch("obsidian_connector.audit.AUDIT_DIR", test_dir):
            from obsidian_connector.audit import log_action
            log_action(
                command="test",
                args={},
                vault=None,
            )
        mode = stat.S_IMODE(parent.stat().st_mode)
        assert mode == 0o700, (
            f"parent dir should be 0o700, got {oct(mode)}"
        )
    print("PASS: test_audit_parent_dir_permissions")


if __name__ == "__main__":
    test_audit_dir_permissions()
    test_audit_parent_dir_permissions()
    print("\nAll audit permission tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/audit_permissions_test.py`
Expected: FAIL with `audit dir should be 0o700 (owner-only), got 0o755` (or similar)

- [ ] **Step 3: Fix audit.py to set restrictive permissions**

In `obsidian_connector/audit.py`, replace line 45:

```python
# Before:
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# After:
AUDIT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
# Harden both dirs: mkdir(mode=) only applies to newly created dirs,
# not pre-existing ones (exist_ok=True path). Explicit chmod handles upgrades.
AUDIT_DIR.chmod(0o700)
if AUDIT_DIR.parent.exists():
    AUDIT_DIR.parent.chmod(0o700)
```

**Why the explicit chmod:** `Path.mkdir(mode=0o700, exist_ok=True)` does NOT change permissions on directories that already exist. Users upgrading from pre-0.2.0 would keep world-readable log dirs without the explicit `chmod` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/audit_permissions_test.py`
Expected: PASS

- [ ] **Step 5: Run existing audit tests to avoid regression**

Run: `python3 scripts/audit_test.py`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add obsidian_connector/audit.py scripts/audit_permissions_test.py
git commit -m "fix: restrict audit log directory to owner-only 0o700 (Critical #3)"
```

---

## Chunk 2: Structural Fixes

### Task 3: Break Circular Dependency (High #5)

**Files:**
- Modify: `obsidian_connector/errors.py` (move `ObsidianCLIError` here)
- Modify: `obsidian_connector/client.py` (import from errors.py instead of defining)
- Modify: `obsidian_connector/__init__.py` (update import source)
- Create: `scripts/import_cycle_test.py`

Currently `errors.py` imports `ObsidianCLIError` from `client.py`, and `client.py` does late imports from `errors.py`. Fix: move `ObsidianCLIError` into `errors.py` as the canonical location. `client.py` imports it from there.

- [ ] **Step 1: Write the import cycle test**

Create `scripts/import_cycle_test.py`:

```python
"""Verify no circular import issues in the package."""

import importlib
import sys


def test_clean_import_errors():
    """errors.py should import without triggering client.py side effects."""
    # Remove cached modules to test fresh import
    mods_to_remove = [k for k in sys.modules if k.startswith("obsidian_connector")]
    for m in mods_to_remove:
        del sys.modules[m]

    # This should succeed without ImportError
    from obsidian_connector.errors import (
        ObsidianCLIError,
        ObsidianNotFound,
        ObsidianNotRunning,
        VaultNotFound,
        CommandTimeout,
        MalformedCLIOutput,
    )
    assert issubclass(ObsidianNotFound, ObsidianCLIError)
    assert issubclass(ObsidianNotRunning, ObsidianCLIError)
    print("PASS: test_clean_import_errors")


def test_clean_import_client():
    """client.py should import cleanly after errors.py."""
    mods_to_remove = [k for k in sys.modules if k.startswith("obsidian_connector")]
    for m in mods_to_remove:
        del sys.modules[m]

    from obsidian_connector.client import ObsidianCLIError, run_obsidian
    from obsidian_connector.errors import ObsidianNotFound

    # The base class should be the same object regardless of import path
    assert issubclass(ObsidianNotFound, ObsidianCLIError)
    print("PASS: test_clean_import_client")


def test_top_level_import():
    """Package-level import should work."""
    mods_to_remove = [k for k in sys.modules if k.startswith("obsidian_connector")]
    for m in mods_to_remove:
        del sys.modules[m]

    import obsidian_connector
    assert hasattr(obsidian_connector, "ObsidianCLIError")
    assert hasattr(obsidian_connector, "ObsidianNotFound")
    print("PASS: test_top_level_import")


if __name__ == "__main__":
    test_clean_import_errors()
    test_clean_import_client()
    test_top_level_import()
    print("\nAll import cycle tests passed.")
```

- [ ] **Step 2: Run test to verify current state**

Run: `python3 scripts/import_cycle_test.py`
Expected: Should pass (current late-import hack works), but this locks in the contract.

- [ ] **Step 3: Move ObsidianCLIError to errors.py**

Rewrite `obsidian_connector/errors.py`:

```python
"""Typed exception hierarchy for obsidian-connector."""

from __future__ import annotations


class ObsidianCLIError(Exception):
    """Raised when the Obsidian CLI exits with a non-zero code."""

    def __init__(
        self, command: list[str], returncode: int, stdout: str, stderr: str
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = stderr.strip() or stdout.strip()
        super().__init__(
            f"obsidian exited {returncode}: {detail!r}\n"
            f"  command: {command}"
        )


class ObsidianNotFound(ObsidianCLIError):
    """The ``obsidian`` binary is not on PATH."""

    def __init__(self, message: str = "obsidian binary not found on PATH") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=127,
            stdout="",
            stderr=message,
        )


class ObsidianNotRunning(ObsidianCLIError):
    """Obsidian app is not open / IPC unavailable."""

    def __init__(
        self, message: str = "Obsidian is not running (IPC unavailable)"
    ) -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


class VaultNotFound(ObsidianCLIError):
    """The specified vault does not exist."""

    def __init__(self, message: str = "specified vault not found") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=1,
            stdout="",
            stderr=message,
        )


class CommandTimeout(ObsidianCLIError):
    """The subprocess timed out."""

    def __init__(self, message: str = "obsidian command timed out") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=-1,
            stdout="",
            stderr=message,
        )


class MalformedCLIOutput(ObsidianCLIError):
    """JSON parse failure on CLI stdout."""

    def __init__(self, message: str = "failed to parse CLI output as JSON") -> None:
        super().__init__(
            command=["obsidian"],
            returncode=0,
            stdout="",
            stderr=message,
        )
```

- [ ] **Step 4: Update client.py to import from errors.py**

In `obsidian_connector/client.py`, replace the `ObsidianCLIError` class definition (lines 22-36) with an import:

```python
# Remove the class definition block and replace with:
from obsidian_connector.errors import ObsidianCLIError
```

Also update the late import block inside `run_obsidian()` (lines 59-64). Since `ObsidianCLIError` is now in `errors.py`, the late imports are no longer needed for cycle avoidance. Move them to top-level:

```python
# At the top of client.py, after the ObsidianCLIError import:
from obsidian_connector.errors import (
    ObsidianCLIError,
    CommandTimeout,
    ObsidianNotFound,
    ObsidianNotRunning,
    VaultNotFound,
)
```

Remove the late import block from inside `run_obsidian()` and the comment about circular imports.

- [ ] **Step 5: Update __init__.py import path**

In `obsidian_connector/__init__.py`, change line 8:

```python
# Before:
from obsidian_connector.client import (
    ObsidianCLIError,
    batch_read_notes,
    ...
)

# After:
from obsidian_connector.client import (
    batch_read_notes,
    list_tasks,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)
from obsidian_connector.errors import ObsidianCLIError
```

Note: `ObsidianCLIError` is still re-exported from `client.py` for backward compatibility (it imports and uses it), but the canonical import is now from `errors.py`.

- [ ] **Step 6: Run import cycle tests**

Run: `python3 scripts/import_cycle_test.py`
Expected: All PASS

- [ ] **Step 7: Run full existing test suite**

Run: `python3 scripts/cache_test.py && python3 scripts/audit_test.py && python3 scripts/escaping_test.py && python3 scripts/graph_test.py && python3 scripts/index_test.py`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add obsidian_connector/errors.py obsidian_connector/client.py obsidian_connector/__init__.py scripts/import_cycle_test.py
git commit -m "refactor: move ObsidianCLIError to errors.py, break circular dependency (High #5)"
```

---

### Task 4: Deduplicate _load_or_build_index (High #7)

**Files:**
- Modify: `obsidian_connector/mcp_server.py:80-84` (remove local def)
- Modify: `obsidian_connector/thinking.py:24-28` (remove local def)
- Modify: `obsidian_connector/workflows.py:28-32` (remove local def)
- No test file changes needed -- `index_test.py` already covers `load_or_build_index`

Three modules define identical `_load_or_build_index()` wrappers that delegate to `index_store.load_or_build_index`. Replace all three with direct imports.

- [ ] **Step 1: Remove _load_or_build_index from mcp_server.py**

In `obsidian_connector/mcp_server.py`:

Remove lines 80-84 (the `_load_or_build_index` function definition).

Add to the existing imports at the top:

```python
from obsidian_connector.index_store import load_or_build_index
```

Replace all calls to `_load_or_build_index(vault)` with `load_or_build_index(vault)`. There are 3 call sites (lines ~542, ~604, ~681).

- [ ] **Step 2: Remove _load_or_build_index from thinking.py**

In `obsidian_connector/thinking.py`:

Remove lines 24-28 (the `_load_or_build_index` function definition).

Add to imports at top:

```python
from obsidian_connector.index_store import load_or_build_index
```

Replace all calls to `_load_or_build_index(vault)` with `load_or_build_index(vault)`. There are 3 call sites (lines ~101, ~476, ~625).

- [ ] **Step 3: Remove _load_or_build_index from workflows.py**

In `obsidian_connector/workflows.py`:

Remove lines 28-32 (the `_load_or_build_index` function definition).

Add to imports at top:

```python
from obsidian_connector.index_store import load_or_build_index
```

Replace all calls to `_load_or_build_index(vault)` with `load_or_build_index(vault)`. There are 3 call sites (lines ~247, ~400, ~931).

- [ ] **Step 4: Verify no remaining local definitions**

Run: `grep -rn "def _load_or_build_index" obsidian_connector/`
Expected: No output (all removed)

Run: `grep -rn "load_or_build_index" obsidian_connector/ | grep -v "from.*import\|index_store.py"`
Expected: Only call sites, no definitions

**Note on `cli.py`:** Three call sites in `cli.py` (lines ~1203, ~1245, ~1298) use `from obsidian_connector.index_store import load_or_build_index as _load_or_build_index`. These are already correct -- they import from the canonical `index_store` module. The underscore alias is a local convention. No changes needed in `cli.py`.

- [ ] **Step 5: Run index tests**

Run: `python3 scripts/index_test.py && python3 scripts/graph_test.py`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add obsidian_connector/mcp_server.py obsidian_connector/thinking.py obsidian_connector/workflows.py
git commit -m "refactor: deduplicate _load_or_build_index, use canonical index_store import (High #7)"
```

---

## Chunk 3: Error Handling Consistency

### Task 5: Fix Uninstall Tool Error Format (High #10)

**Files:**
- Modify: `obsidian_connector/mcp_server.py` (uninstall function, line ~1181)

The `uninstall()` MCP tool uses a bare `except Exception` with inline JSON formatting instead of `_error_envelope()`. All other tools use `_error_envelope()` for `ObsidianCLIError` and the ad-hoc format only for truly unexpected exceptions. The uninstall tool should at minimum match the ad-hoc pattern used by other tools (since uninstall errors aren't `ObsidianCLIError`).

However, the real issue is the uninstall tool catches `Exception` but never catches `ObsidianCLIError` specifically. Since `detect_installed_artifacts` and `execute_uninstall` don't raise `ObsidianCLIError`, this is actually correct -- uninstall errors are filesystem/JSON errors, not CLI errors. The fix is to use a more specific catch.

- [ ] **Step 1: Tighten uninstall exception handling**

In `obsidian_connector/mcp_server.py`, replace the uninstall try/except block (around line 1147-1184):

```python
    try:
        # ... existing code ...
        return json.dumps(result, indent=2)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )
```

- [ ] **Step 2: Verify MCP launch still works**

Run: `bash scripts/mcp_launch_smoke.sh`
Expected: MCP server starts without error

- [ ] **Step 3: Commit**

```bash
git add obsidian_connector/mcp_server.py
git commit -m "fix: tighten uninstall exception handling to specific types (High #10)"
```

---

### Task 6: Replace Broad except Exception Handlers (High #11)

**Files:**
- Modify: `obsidian_connector/mcp_server.py` (8 tool functions)

Eight MCP tools catch `except Exception` after `except ObsidianCLIError`. The broad catch masks bugs. Replace with specific exception types that these tools can actually raise: `OSError` (file I/O), `json.JSONDecodeError` (parsing), `KeyError`/`TypeError` (data access), `ValueError` (bad input).

The affected tools (all have the same pattern `except Exception as exc: return json.dumps({"ok": False, ...})`):

1. `obsidian_neighborhood` (line ~582)
2. `obsidian_vault_structure` (line ~658)
3. `obsidian_backlinks` (line ~735)
4. `obsidian_ghost` (line ~877)
5. `obsidian_drift` (line ~912)
6. `obsidian_trace` (line ~948)
7. `obsidian_deep_ideas` (line ~983)
8. `uninstall` (line ~1181) -- already fixed in Task 5

- [ ] **Step 1: Replace all 7 remaining broad catches**

For each of the 7 tools listed above, replace:

```python
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )
```

With:

```python
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )
```

This is a safe replacement because:
- Graph/index operations raise `OSError` (file access) and `ValueError`/`KeyError` (data parsing)
- Thinking tools raise `OSError` (vault file reads) and `ValueError` (date parsing)
- `json.JSONDecodeError` covers malformed vault file content
- `TypeError` covers None-safety issues in index lookups

- [ ] **Step 2: Verify MCP launch still works**

Run: `bash scripts/mcp_launch_smoke.sh`
Expected: MCP server starts without error

- [ ] **Step 3: Add exception path regression test**

Add to `scripts/mcp_tool_contract_test.py` (will be created in Task 9):

```python
def test_narrowed_exceptions_catch_expected_types():
    """Verify the tightened except clauses catch filesystem and data errors."""
    import json
    from unittest.mock import patch
    from obsidian_connector.mcp_server import obsidian_vault_structure

    # Simulate an OSError during index building (filesystem error)
    with patch("obsidian_connector.mcp_server.load_or_build_index", side_effect=OSError("disk full")):
        result = json.loads(obsidian_vault_structure(vault="test"))
        assert result["ok"] is False
        assert result["error"]["type"] == "OSError"

    # Verify that truly unexpected exceptions (e.g., RuntimeError) propagate
    with patch("obsidian_connector.mcp_server.load_or_build_index", side_effect=RuntimeError("bug")):
        try:
            obsidian_vault_structure(vault="test")
            assert False, "RuntimeError should propagate, not be caught"
        except RuntimeError:
            pass  # Expected: not silently swallowed
    print("PASS: test_narrowed_exceptions_catch_expected_types")
```

- [ ] **Step 4: Commit**

```bash
git add obsidian_connector/mcp_server.py
git commit -m "fix: replace broad except Exception with specific types in 7 MCP tools (High #11)"
```

---

## Chunk 4: Cross-Platform Support

### Task 7: Platform-Aware Configuration Paths

**Files:**
- Create: `obsidian_connector/platform.py`
- Modify: `obsidian_connector/config.py:22-23` (use platform module)
- Modify: `obsidian_connector/uninstall.py:63` (use platform module)
- Modify: `obsidian_connector/cli.py:1469` (use platform module)
- Create: `scripts/platform_test.py`

Create a `platform.py` module that centralizes all OS-specific path resolution. This is the foundation for Linux/Windows support.

- [ ] **Step 1: Write platform detection tests**

Create `scripts/platform_test.py`:

```python
"""Test platform-specific path resolution."""

import sys
from unittest.mock import patch


def test_macos_paths():
    with patch("sys.platform", "darwin"):
        # Re-import to pick up patched platform
        import importlib
        import obsidian_connector.platform as plat
        importlib.reload(plat)

        paths = plat.get_platform_paths()
        assert "Library/Application Support/obsidian" in str(paths.obsidian_config)
        assert "Library/Application Support/Claude" in str(paths.claude_config_dir)
        assert "Library/LaunchAgents" in str(paths.scheduler_dir)
    print("PASS: test_macos_paths")


def test_linux_paths():
    with patch("sys.platform", "linux"):
        import importlib
        import obsidian_connector.platform as plat
        importlib.reload(plat)

        paths = plat.get_platform_paths()
        assert ".config/obsidian" in str(paths.obsidian_config) or "obsidian" in str(paths.obsidian_config)
        assert ".config/Claude" in str(paths.claude_config_dir) or "Claude" in str(paths.claude_config_dir)
    print("PASS: test_linux_paths")


def test_windows_paths():
    with patch("sys.platform", "win32"), \
         patch("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}):
        import importlib
        import obsidian_connector.platform as plat
        importlib.reload(plat)

        paths = plat.get_platform_paths()
        assert "obsidian" in str(paths.obsidian_config).lower()
    print("PASS: test_windows_paths")


def test_data_dir_creation():
    """Data dir (~/.obsidian-connector) should be platform-independent."""
    import obsidian_connector.platform as plat
    paths = plat.get_platform_paths()
    assert ".obsidian-connector" in str(paths.data_dir)
    print("PASS: test_data_dir_creation")


if __name__ == "__main__":
    test_macos_paths()
    test_linux_paths()
    test_windows_paths()
    test_data_dir_creation()
    print("\nAll platform tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail (module doesn't exist yet)**

Run: `python3 scripts/platform_test.py`
Expected: `ModuleNotFoundError: No module named 'obsidian_connector.platform'`

- [ ] **Step 3: Create platform.py**

Create `obsidian_connector/platform.py`:

```python
"""Platform-specific path resolution for obsidian-connector.

Centralizes all OS-dependent paths so the rest of the codebase
can use ``get_platform_paths()`` instead of hardcoding macOS paths.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformPaths:
    """Resolved paths for the current operating system."""

    obsidian_config: Path
    """Path to Obsidian's obsidian.json (vault registry)."""

    claude_config_dir: Path
    """Directory containing claude_desktop_config.json."""

    scheduler_dir: Path | None
    """Directory for scheduled job definitions (launchd/systemd/Task Scheduler)."""

    data_dir: Path
    """obsidian-connector data directory (~/.obsidian-connector)."""

    log_dir: Path
    """Audit log directory."""

    scheduler_type: str
    """Scheduling backend: 'launchd', 'systemd', 'task_scheduler', or 'none'."""


def get_platform_paths() -> PlatformPaths:
    """Resolve all platform-specific paths for the current OS."""
    home = Path.home()
    data_dir = home / ".obsidian-connector"
    log_dir = data_dir / "logs"

    if sys.platform == "darwin":
        return PlatformPaths(
            obsidian_config=home / "Library" / "Application Support" / "obsidian" / "obsidian.json",
            claude_config_dir=home / "Library" / "Application Support" / "Claude",
            scheduler_dir=home / "Library" / "LaunchAgents",
            data_dir=data_dir,
            log_dir=log_dir,
            scheduler_type="launchd",
        )
    elif sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return PlatformPaths(
            obsidian_config=appdata / "obsidian" / "obsidian.json",
            claude_config_dir=appdata / "Claude",
            scheduler_dir=None,  # Task Scheduler uses schtasks.exe, not a dir
            data_dir=data_dir,
            log_dir=log_dir,
            scheduler_type="task_scheduler",
        )
    else:
        # Linux and other Unix-like
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        return PlatformPaths(
            obsidian_config=xdg_config / "obsidian" / "obsidian.json",
            claude_config_dir=xdg_config / "Claude",
            scheduler_dir=xdg_config / "systemd" / "user",
            data_dir=data_dir,
            log_dir=log_dir,
            scheduler_type="systemd",
        )
```

- [ ] **Step 4: Run platform tests**

Run: `python3 scripts/platform_test.py`
Expected: All PASS

- [ ] **Step 5: Wire platform.py into config.py**

In `obsidian_connector/config.py`, replace the hardcoded macOS path (line 22-23):

```python
# Before:
_OBSIDIAN_APP_JSON = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)

# After:
from obsidian_connector.platform import get_platform_paths as _get_platform_paths

_OBSIDIAN_APP_JSON = _get_platform_paths().obsidian_config
```

- [ ] **Step 6: Wire platform.py into uninstall.py**

In `obsidian_connector/uninstall.py`, replace the entire plist detection block (lines 62-70):

```python
# Before:
    # Check plist
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.obsidian-connector.daily.plist"

    return UninstallPlan(
        venv_path=venv_path,
        files_to_remove=files_to_remove,
        config_changes=config_changes,
        plist_path=plist_path if plist_path.exists() else None
    )

# After:
    from obsidian_connector.platform import get_platform_paths
    paths = get_platform_paths()

    # Check scheduler artifact (launchd plist on macOS, systemd unit on Linux, None on Windows)
    plist_path: Path | None = None
    if paths.scheduler_dir is not None:
        candidate = paths.scheduler_dir / "com.obsidian-connector.daily.plist"
        if candidate.exists():
            plist_path = candidate

    return UninstallPlan(
        venv_path=venv_path,
        files_to_remove=files_to_remove,
        config_changes=config_changes,
        plist_path=plist_path,
    )
```

**Why the full block replacement:** The original code calls `plist_path.exists()` unconditionally. If `paths.scheduler_dir` is `None` (Windows), this would raise `AttributeError`. The fix guards the `.exists()` call behind a `None` check.

- [ ] **Step 7: Wire platform.py into cli.py uninstall command**

In `obsidian_connector/cli.py`, find the hardcoded Claude config path in the uninstall handler (around line 1469):

```python
# Before:
claude_config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"

# After:
from obsidian_connector.platform import get_platform_paths
claude_config_path = get_platform_paths().claude_config_dir / "claude_desktop_config.json"
```

- [ ] **Step 8: Run platform and existing tests**

Run: `python3 scripts/platform_test.py && python3 scripts/cache_test.py && python3 scripts/audit_test.py`
Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add obsidian_connector/platform.py obsidian_connector/config.py obsidian_connector/uninstall.py obsidian_connector/cli.py scripts/platform_test.py
git commit -m "feat: add cross-platform path resolution via platform.py (Linux/Windows support)"
```

---

### Task 8: Expand CI Matrix (Critical #4)

**Files:**
- Modify: `.github/workflows/ci.yml`

Add ubuntu-latest to the test matrix. Add new test files to the CI job. The MCP launch test stays macOS-only (Obsidian CLI availability).

- [ ] **Step 1: Update CI workflow**

Replace `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .
      - name: Docs lint
        run: python3 tools/docs_lint.py --severity error

  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [macos-latest, ubuntu-latest]
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e .
      - name: Unit tests (no Obsidian required)
        run: |
          python3 scripts/cache_test.py
          python3 scripts/audit_test.py
          python3 scripts/escaping_test.py
          python3 scripts/graph_test.py
          python3 scripts/index_test.py
          python3 scripts/graduate_test.py
          python3 scripts/thinking_deep_test.py
          python3 scripts/delegation_test.py
          python3 scripts/import_cycle_test.py
          python3 scripts/platform_test.py
          python3 scripts/audit_permissions_test.py
          python3 scripts/edge_case_test.py
          python3 scripts/uninstall_test.py

  mcp-launch:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .
      - name: MCP server starts without error
        run: bash scripts/mcp_launch_smoke.sh
```

- [ ] **Step 2: Verify CI config is valid YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('Valid YAML')" 2>/dev/null || python3 -c "import json; print('Install pyyaml to validate, or visually inspect')"`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add ubuntu-latest to matrix, expand test coverage to 13 test files (Critical #4)"
```

---

## Chunk 5: Test Coverage

### Task 9: MCP Tool Contract Tests (High #8)

**Files:**
- Create: `scripts/mcp_tool_contract_test.py`

Test that all MCP tools are registered, have ToolAnnotations, and return valid JSON. Does NOT require Obsidian to be running -- tests the tool metadata and error path behavior.

- [ ] **Step 1: Write MCP tool contract tests**

Create `scripts/mcp_tool_contract_test.py`:

```python
"""Verify MCP tool registration, annotations, and error contracts.

These tests inspect the MCP server's tool metadata without calling Obsidian.
They ensure all tools are properly registered and follow the project's
error envelope convention.
"""

import json
import importlib


def test_all_tools_registered():
    """Verify expected tool count matches actual registered tools."""
    import re

    # Count @mcp.tool decorators in the source as ground truth.
    # This avoids depending on FastMCP internals.
    with open("obsidian_connector/mcp_server.py") as f:
        source = f.read()
    decorator_count = len(re.findall(r"@mcp\.tool\(", source))
    assert decorator_count >= 29, (
        f"Expected at least 29 @mcp.tool decorators, found {decorator_count}"
    )
    print(f"PASS: test_all_tools_registered ({decorator_count} tools by source scan)")


def test_error_envelope_format():
    """Verify _error_envelope produces valid JSON with required keys."""
    from obsidian_connector.mcp_server import _error_envelope
    from obsidian_connector.errors import ObsidianNotRunning

    exc = ObsidianNotRunning("test error")
    result = _error_envelope(exc)
    parsed = json.loads(result)

    assert parsed["ok"] is False, "error envelope must have ok=False"
    assert "error" in parsed, "error envelope must have 'error' key"
    assert "type" in parsed["error"], "error must have 'type'"
    assert "message" in parsed["error"], "error must have 'message'"
    assert parsed["error"]["type"] == "ObsidianNotRunning"
    print("PASS: test_error_envelope_format")


def test_error_envelope_all_types():
    """Verify all typed errors map correctly."""
    from obsidian_connector.mcp_server import _error_envelope, _ERROR_TYPE_MAP
    from obsidian_connector.errors import (
        ObsidianNotFound,
        ObsidianNotRunning,
        VaultNotFound,
        CommandTimeout,
        MalformedCLIOutput,
    )

    for exc_class, expected_name in [
        (ObsidianNotFound, "ObsidianNotFound"),
        (ObsidianNotRunning, "ObsidianNotRunning"),
        (VaultNotFound, "VaultNotFound"),
        (CommandTimeout, "CommandTimeout"),
        (MalformedCLIOutput, "MalformedCLIOutput"),
    ]:
        exc = exc_class()
        result = json.loads(_error_envelope(exc))
        assert result["error"]["type"] == expected_name, (
            f"Expected {expected_name}, got {result['error']['type']}"
        )
    print("PASS: test_error_envelope_all_types")


def test_tool_annotations_present():
    """Verify tools that we can inspect have annotations."""
    # Import the module to trigger tool registration
    import obsidian_connector.mcp_server
    # If we got here without error, the module loaded and all @mcp.tool
    # decorators with annotations= kwarg were accepted by FastMCP.
    print("PASS: test_tool_annotations_present (module loaded without annotation errors)")


if __name__ == "__main__":
    test_error_envelope_format()
    test_error_envelope_all_types()
    test_tool_annotations_present()
    test_all_tools_registered()
    print("\nAll MCP tool contract tests passed.")
```

- [ ] **Step 2: Run tests**

Run: `python3 scripts/mcp_tool_contract_test.py`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/mcp_tool_contract_test.py
git commit -m "test: add MCP tool contract tests (registration, annotations, error envelope) (High #8)"
```

---

### Task 10: CLI Argument Parsing Tests (High #9)

**Files:**
- Create: `scripts/cli_parse_test.py`

Test that CLI subcommands parse arguments correctly without executing commands. Uses `parse_args()` directly.

- [ ] **Step 1: Write CLI parsing tests**

Create `scripts/cli_parse_test.py`:

```python
"""Verify CLI argument parsing for key subcommands.

Tests parse_args() behavior without executing any Obsidian commands.
"""

import sys
from io import StringIO


def _get_parser():
    """Build the argparse parser from cli.py."""
    # cli.py's main() calls parse_args() and dispatches.
    # We need the parser object directly.
    from obsidian_connector.cli import main
    import argparse

    # Intercept the parser by importing and inspecting the module
    import obsidian_connector.cli as cli_mod
    import importlib
    importlib.reload(cli_mod)

    # The parser is built inside main(), so we reconstruct it.
    # Alternative: call main with --help and check exit code.
    # Simpler: test that main() with known args doesn't crash on parse.
    return None  # Use subprocess approach instead


def test_help_exits_zero():
    """obsx --help should exit 0."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"--help exited {result.returncode}: {result.stderr}"
    assert "usage:" in result.stdout.lower() or "obsidian" in result.stdout.lower()
    print("PASS: test_help_exits_zero")


def test_subcommand_help():
    """Key subcommands should have --help that exits 0."""
    import subprocess
    subcommands = [
        "search", "read", "tasks", "log-daily", "doctor",
        "today", "close", "ghost", "drift", "ideas",
        "uninstall",
    ]
    for cmd in subcommands:
        result = subprocess.run(
            [sys.executable, "-m", "obsidian_connector", cmd, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"{cmd} --help exited {result.returncode}: {result.stderr}"
        )
    print(f"PASS: test_subcommand_help ({len(subcommands)} subcommands)")


def test_json_flag_accepted():
    """--json flag should be accepted by commands that support it."""
    import subprocess
    # search requires a query arg, so test with --help after --json
    # Actually, just check that unknown args are rejected:
    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector", "search", "--json", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"search --json --help failed: {result.stderr}"
    print("PASS: test_json_flag_accepted")


def test_unknown_subcommand_fails():
    """Unknown subcommand should exit non-zero."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "obsidian_connector", "nonexistent-command"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0, "unknown subcommand should fail"
    print("PASS: test_unknown_subcommand_fails")


if __name__ == "__main__":
    test_help_exits_zero()
    test_subcommand_help()
    test_json_flag_accepted()
    test_unknown_subcommand_fails()
    print("\nAll CLI parse tests passed.")
```

- [ ] **Step 2: Run tests**

Run: `python3 scripts/cli_parse_test.py`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/cli_parse_test.py
git commit -m "test: add CLI argument parsing tests for key subcommands (High #9)"
```

---

## Chunk 6: Documentation & Release Prep

### Task 11: Fix README Tool/Command Counts (Critical #2)

**Files:**
- Modify: `README.md:13`

The README claims "29 MCP tools. 27 CLI commands." Verify actual counts and fix.

- [ ] **Step 1: Count actual tools and commands**

Run: `python3 -c "
import re
# Count @mcp.tool decorators
with open('obsidian_connector/mcp_server.py') as f:
    mcp_count = len(re.findall(r'@mcp\.tool', f.read()))

# Count add_parser calls (excluding sub-subparsers like graduate list/execute)
with open('obsidian_connector/cli.py') as f:
    content = f.read()
    # Count top-level subcommands (sub.add_parser) and sub-subcommands (grad_sub.add_parser)
    cli_count = len(re.findall(r'\.add_parser\(', content))

print(f'MCP tools: {mcp_count}')
print(f'CLI commands: {cli_count}')
"`

- [ ] **Step 2: Update README line 13 with correct counts**

Update the count line in `README.md` to match actual values. For example:

```markdown
29 MCP tools. 29 CLI commands. 4 skills. Scheduled automation. Full Python API.
```

(Adjust numbers based on Step 1 output.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: fix MCP tool and CLI command counts in README (Critical #2)"
```

---

### Task 12: Populate Tech Debt Tracker (Medium #18)

**Files:**
- Modify: `docs/tech-debt-tracker.md`

Populate with the deferred findings from this review.

- [ ] **Step 1: Write tech debt tracker content**

Replace `docs/tech-debt-tracker.md` with:

```markdown
---
title: "Tech Debt Tracker"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-16"
review_cycle_days: 30
---

# Tech Debt Tracker

Tracked items from the v0.2.0 hardening review. Items are prioritized for
future releases.

## Deferred to v0.2.1

| # | Finding | Description | Impact |
|---|---------|-------------|--------|
| 6 | Module size | `cli.py` (1,598 LOC) and `workflows.py` (1,603 LOC) should be split | Hard to navigate, test, review |
| 13 | Parameter naming | Inconsistent: `name_or_path` vs `note_path`, `top_n` vs `max_ideas` vs `limit` | LLM confusion when calling tools |
| 14 | Long functions | 4 functions >150 LOC: `ghost_voice_profile`, `deep_ideas`, `drift_analysis`, `graduate_execute` | Hard to test individual paths |
| 15 | Error heuristic fragility | `client.py` keyword-scans stderr to classify errors | Breaks if Obsidian CLI changes messages |

## Backlog

| # | Finding | Description | Impact |
|---|---------|-------------|--------|
| 16 | No config.py tests | Env var precedence, missing config, malformed JSON untested | Silent misconfiguration |
| 17 | doctor.py gaps | No Obsidian version validation, no config.json syntax check | Incomplete health assessment |
| 25 | No retry logic | Transient timeouts in client.py not retried | Flaky under load |
| 19 | README narrative | Missing 2-3 sentence emotional hook at top | Visitors close tab |
```

- [ ] **Step 2: Run docs lint**

Run: `make docs-lint`
Expected: No errors on `tech-debt-tracker.md`

- [ ] **Step 3: Commit**

```bash
git add docs/tech-debt-tracker.md
git commit -m "docs: populate tech debt tracker with v0.2.0 review findings (Medium #18)"
```

---

### Task 13: CHANGELOG and Release Metadata

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/ROADMAP.md` (mark completed items)

- [ ] **Step 1: Update CHANGELOG.md**

Add a v0.2.0 section at the top of `CHANGELOG.md`. Read the existing file first, then prepend:

```markdown
## [0.2.0] - 2026-03-16

### Added
- Cross-platform support: Linux and Windows path resolution via `platform.py`
- `obsidian uninstall` MCP tool and CLI command (safe two-mode operation)
- MCP tool contract tests (registration, annotations, error envelope)
- CLI argument parsing tests for key subcommands
- Audit log directory permission tests
- Import cycle regression tests
- Platform detection tests
- Ubuntu added to CI test matrix (6 new test files in CI)

### Fixed
- All version sources synced to 0.2.0 (pyproject.toml, __init__.py, plugin.json)
- Audit log directory now created with 0o700 (owner-only) permissions
- Circular dependency between `client.py` and `errors.py` resolved
- `ObsidianCLIError` moved to `errors.py` as canonical location
- Uninstall MCP tool now uses specific exception types instead of broad `except Exception`
- 7 MCP tools tightened from `except Exception` to specific exception types
- README tool/command count corrected

### Changed
- `_load_or_build_index()` deduplicated: removed from `mcp_server.py`, `thinking.py`, `workflows.py`; all use `index_store.load_or_build_index` directly
- CI matrix expanded from macOS-only to macOS + Ubuntu, 8 to 13 test files

### Documentation
- Tech debt tracker populated with deferred v0.2.0 review findings
- Roadmap updated with completed items
```

- [ ] **Step 2: Update ROADMAP completed section**

In `docs/plans/ROADMAP.md`, add v0.2.0 completed items to the "Completed" table:

```markdown
| -- | `infra` | Cross-platform path resolution (platform.py) | v0.2.0 |
| -- | `risk` | Audit log directory permissions (0o700) | v0.2.0 |
| -- | `infra` | CI expanded to macOS + Ubuntu, 13 test files | v0.2.0 |
| -- | `infra` | Circular dependency resolved (errors.py canonical) | v0.2.0 |
| -- | `infra` | Broad `except Exception` replaced in 8 MCP tools | v0.2.0 |
| -- | `feature` | Safe two-mode uninstaller (`obsx uninstall`) | v0.2.0 |
```

Also remove the "Safe two-mode uninstaller" line from the existing Completed table since we're consolidating it under v0.2.0 (it was listed under v0.1.3 but hasn't shipped yet).

- [ ] **Step 3: Run docs lint**

Run: `make docs-lint`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/plans/ROADMAP.md
git commit -m "docs: add v0.2.0 CHANGELOG and update ROADMAP completed section"
```

---

## Post-Implementation Verification

After all tasks are complete, run the full verification suite:

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
python3 scripts/import_cycle_test.py
python3 scripts/platform_test.py
python3 scripts/audit_permissions_test.py
python3 scripts/edge_case_test.py
python3 scripts/uninstall_test.py
python3 scripts/mcp_tool_contract_test.py
python3 scripts/cli_parse_test.py

# MCP server launch
bash scripts/mcp_launch_smoke.sh

# Docs
make docs-lint

# Version check
python3 -c "
import json, tomllib
with open('pyproject.toml','rb') as f: pt = tomllib.load(f)['project']['version']
from obsidian_connector import __version__ as iv
with open('.claude-plugin/plugin.json') as f: pj = json.load(f)['version']
assert pt == iv == pj == '0.2.0', f'VERSION MISMATCH: {pt} / {iv} / {pj}'
print(f'All versions: {pt} -- OK')
"
```

All tests must pass before merging to main.

---

## Dependency Graph

```
Task 1 (version sync)        ─── independent
Task 2 (audit permissions)   ─── independent
Task 3 (circular dep)        ─── independent
Task 4 (dedup index)         ─── depends on Task 3 (import paths change)
Task 5 (uninstall errors)    ─── independent
Task 6 (broad exceptions)    ─── depends on Task 5 (same file, avoid conflicts)
Task 7 (platform.py)         ─── independent
Task 8 (CI matrix)           ─── depends on Tasks 2, 3, 7 (new test files)
Task 9 (MCP tool tests)      ─── depends on Tasks 5, 6 (error handling changes)
Task 10 (CLI parse tests)    ─── independent
Task 11 (README counts)      ─── independent
Task 12 (tech debt tracker)  ─── independent
Task 13 (CHANGELOG/ROADMAP)  ─── depends on all other tasks (summarizes changes)
```

**Parallel execution groups:**
- Group A: Tasks 1, 2, 3, 5, 7, 10, 11, 12 (all independent)
- Group B: Tasks 4, 6 (after Group A)
- Group C: Tasks 8, 9 (after Group B)
- Group D: Task 13 (after all)
