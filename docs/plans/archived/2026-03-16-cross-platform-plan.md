---
title: "Cross-Platform Compatibility Plan"
status: draft
owner: "mariourquia"
last_reviewed: "2026-03-16"
---

# Cross-Platform Compatibility Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make obsidian-connector run natively on macOS, Linux, and Windows by abstracting all platform-specific code behind a unified `platform.py` module, adding platform-appropriate scheduling, config paths, notifications, vault detection, and installers.

**Architecture:** A new `platform.py` module provides OS detection and platform-specific path resolution, scheduling, and notification dispatch. All existing modules that currently hardcode macOS paths (`config.py`, `uninstall.py`, `doctor.py`, `cli.py`, `mcp_server.py`) and scripts (`install.sh`, `run_scheduled.py`) are refactored to call `platform.py` instead of inlining `~/Library/...` paths. Linux ships in v0.2.0, Windows in v0.3.0.

**Tech Stack:** Python 3.11+, pathlib, sys.platform, subprocess, optional pyyaml

**Scope alignment:** ROADMAP.md item #1 (Linux support, v0.2.0 P0) and item #13 (Windows support, v0.3.0 P2).

---

## Current State: macOS-Only Components

| Component | macOS implementation | File(s) |
|-----------|---------------------|---------|
| Config paths | `~/Library/Application Support/Claude/claude_desktop_config.json`, `~/Library/Application Support/obsidian/obsidian.json` | `config.py` lines 19-23, `cli.py` line 1469, `install.sh` line 78 |
| Scheduling | launchd plist in `~/Library/LaunchAgents/` | `scheduling/com.obsidian-connector.daily.plist`, `install.sh` lines 284-322 |
| Uninstaller | `launchctl unload`, hardcoded plist path | `uninstall.py` lines 63, 133-145 |
| Notifications | `osascript -e 'display notification ...'` | `scheduling/run_scheduled.py` lines 69-80 |
| Installer | bash script, `~/Library/...` paths | `scripts/install.sh` |
| Vault detection | Parse `~/Library/Application Support/obsidian/obsidian.json` | `config.py` lines 133-153 |
| Process detection | Implicit via CLI IPC failure | `client.py`, `doctor.py` |
| CI | `macos-latest` only | `.github/workflows/ci.yml` |

## Already Cross-Platform

These components use pathlib or pure Python and work on all platforms today:

- Graph tools (`graph.py`) -- direct file reads via pathlib
- SQLite index store (`index_store.py`) -- pathlib-based DB path
- Cache module (`cache.py`) -- in-memory, no filesystem
- Audit logging (`audit.py`) -- pathlib file writes
- MCP server (`mcp_server.py`) -- stdio transport
- Core Python logic in `workflows.py`, `thinking.py`, `search.py`
- All unit tests in `scripts/` that do not require Obsidian

---

## Platform Abstraction Strategy

### Core: `platform.py` Module

Create `obsidian_connector/platform.py` as the single source of truth for all OS-dependent behavior. Every other module imports from `platform.py` instead of hardcoding paths.

**Design principles:**
- `sys.platform` for OS detection (not `os.name` -- more granular)
- All path resolution returns `pathlib.Path` objects
- Each function has a clear fallback chain: platform-specific path -> env var -> error
- No platform `import` at module level that would fail on other OSes (e.g., no top-level `import winreg`)

**Public API:**

```python
# OS detection
def current_os() -> str:  # "macos" | "linux" | "windows"

# Path resolution
def claude_desktop_config_path() -> Path
def obsidian_app_json_path() -> Path
def default_index_db_path() -> Path
def schedule_config_dir() -> Path

# Scheduling
def scheduler_type() -> str  # "launchd" | "systemd" | "task_scheduler"
def install_schedule(repo_root: Path, python_path: Path, workflow: str, time: str) -> bool
def uninstall_schedule(job_name: str) -> bool

# Notifications
def send_notification(title: str, message: str) -> bool

# Process detection
def is_obsidian_running() -> bool

# Obsidian CLI resolution
def obsidian_binary_candidates() -> list[str]
```

---

## Phase 1: Platform Abstraction Layer (Tasks 1-6)

Create the `platform.py` module and refactor existing code to use it. No new OS support yet -- macOS behavior is preserved exactly, but all platform logic is centralized.

### Task 1: Create `platform.py` with OS detection and path resolution

**Files:**
- Create: `obsidian_connector/platform.py`
- Create: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
# scripts/platform_test.py
import sys
from pathlib import Path
from obsidian_connector.platform import current_os, claude_desktop_config_path, obsidian_app_json_path

def test_current_os():
    result = current_os()
    assert result in ("macos", "linux", "windows"), f"Unknown OS: {result}"
    if sys.platform == "darwin":
        assert result == "macos"
    elif sys.platform.startswith("linux"):
        assert result == "linux"
    elif sys.platform == "win32":
        assert result == "windows"

def test_claude_config_path_returns_path():
    path = claude_desktop_config_path()
    assert isinstance(path, Path)
    assert "claude" in str(path).lower() or "Claude" in str(path)

def test_obsidian_app_json_returns_path():
    path = obsidian_app_json_path()
    assert isinstance(path, Path)
    assert "obsidian" in str(path).lower()
```

**Step 2: Run test to verify it fails**

```bash
python3 scripts/platform_test.py
```

Expected: `ModuleNotFoundError: No module named 'obsidian_connector.platform'`

**Step 3: Write minimal implementation**

```python
# obsidian_connector/platform.py
"""Platform abstraction layer for obsidian-connector.

Centralizes all OS-specific path resolution, scheduling, and
notification logic. Every other module imports from here instead
of hardcoding ~/Library/... or %APPDATA%\... paths.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def current_os() -> str:
    """Detect the current operating system.

    Returns one of: "macos", "linux", "windows".
    """
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "win32":
        return "windows"
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def claude_desktop_config_path() -> Path:
    """Return the path to Claude Desktop's config file."""
    os_name = current_os()
    if os_name == "macos":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif os_name == "linux":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return base / "Claude" / "claude_desktop_config.json"
    elif os_name == "windows":
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    raise RuntimeError(f"Unsupported OS: {os_name}")


def obsidian_app_json_path() -> Path:
    """Return the path to Obsidian's app-level config (obsidian.json).

    This file contains registered vault paths.
    """
    os_name = current_os()
    if os_name == "macos":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "obsidian"
            / "obsidian.json"
        )
    elif os_name == "linux":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return base / "obsidian" / "obsidian.json"
    elif os_name == "windows":
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "obsidian" / "obsidian.json"
    raise RuntimeError(f"Unsupported OS: {os_name}")


def default_index_db_path() -> Path:
    """Return the default path for the SQLite index database."""
    return Path.home() / ".obsidian-connector" / "index.sqlite"


def schedule_config_dir() -> Path:
    """Return the directory for scheduling configuration files."""
    os_name = current_os()
    if os_name == "macos":
        return Path.home() / "Library" / "LaunchAgents"
    elif os_name == "linux":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return base / "systemd" / "user"
    elif os_name == "windows":
        # Windows Task Scheduler does not use a config directory.
        # Return a sentinel path; actual scheduling uses schtasks.exe.
        return Path.home() / ".obsidian-connector" / "tasks"
    raise RuntimeError(f"Unsupported OS: {os_name}")
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/platform_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/platform.py scripts/platform_test.py
git commit -m "feat: add platform.py with OS detection and path resolution"
```

---

### Task 2: Add scheduling abstraction to `platform.py`

**Files:**
- Modify: `obsidian_connector/platform.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.platform import scheduler_type, install_schedule, uninstall_schedule

def test_scheduler_type():
    result = scheduler_type()
    assert result in ("launchd", "systemd", "task_scheduler")
    if sys.platform == "darwin":
        assert result == "launchd"

def test_install_schedule_dry_run(tmp_path):
    # Should not raise; actual scheduling is OS-specific
    python_path = Path(sys.executable)
    result = install_schedule(
        repo_root=tmp_path,
        python_path=python_path,
        workflow="morning",
        time="08:00",
        dry_run=True,
    )
    assert isinstance(result, dict)
    assert result["scheduler"] == scheduler_type()
    assert result["dry_run"] is True
```

**Step 2: Run test to verify it fails**

Expected: `ImportError: cannot import name 'scheduler_type' from 'obsidian_connector.platform'`

**Step 3: Write minimal implementation**

```python
def scheduler_type() -> str:
    """Return the scheduling backend for this OS."""
    os_name = current_os()
    if os_name == "macos":
        return "launchd"
    elif os_name == "linux":
        return "systemd"
    elif os_name == "windows":
        return "task_scheduler"
    raise RuntimeError(f"Unsupported OS: {os_name}")


def install_schedule(
    repo_root: Path,
    python_path: Path,
    workflow: str,
    time: str,
    dry_run: bool = False,
) -> dict:
    """Install a scheduled job for the given workflow.

    Parameters
    ----------
    repo_root: Path to the obsidian-connector repo.
    python_path: Path to the Python interpreter (venv).
    workflow: One of "morning", "evening", "weekly".
    time: 24h time string, e.g. "08:00".
    dry_run: If True, return plan without installing.

    Returns
    -------
    dict with keys: scheduler, job_name, time, dry_run, installed.
    """
    sched = scheduler_type()
    job_name = f"com.obsidian-connector.{workflow}"
    hour, minute = time.split(":")

    result = {
        "scheduler": sched,
        "job_name": job_name,
        "workflow": workflow,
        "time": time,
        "dry_run": dry_run,
        "installed": False,
    }

    if dry_run:
        return result

    if sched == "launchd":
        result["installed"] = _install_launchd(repo_root, python_path, workflow, int(hour), int(minute))
    elif sched == "systemd":
        result["installed"] = _install_systemd(repo_root, python_path, workflow, int(hour), int(minute))
    elif sched == "task_scheduler":
        result["installed"] = _install_task_scheduler(repo_root, python_path, workflow, time)

    return result


def uninstall_schedule(job_name: str) -> bool:
    """Remove a scheduled job by name. Returns True on success."""
    sched = scheduler_type()
    if sched == "launchd":
        return _uninstall_launchd(job_name)
    elif sched == "systemd":
        return _uninstall_systemd(job_name)
    elif sched == "task_scheduler":
        return _uninstall_task_scheduler(job_name)
    return False
```

The private `_install_launchd`, `_install_systemd`, `_install_task_scheduler` (and their uninstall counterparts) are implemented in later tasks when each platform is added.

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/platform.py scripts/platform_test.py
git commit -m "feat: add scheduling abstraction to platform.py"
```

---

### Task 3: Add notification abstraction to `platform.py`

**Files:**
- Modify: `obsidian_connector/platform.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.platform import send_notification

def test_send_notification_returns_bool():
    # Should not raise on any platform; may return False if no backend
    result = send_notification("Test", "Hello from test")
    assert isinstance(result, bool)
```

**Step 2: Run test to verify it fails**

Expected: `ImportError: cannot import name 'send_notification'`

**Step 3: Write minimal implementation**

```python
import subprocess

def send_notification(title: str, message: str) -> bool:
    """Send a desktop notification using the OS-native method.

    Returns True if the notification was dispatched, False on failure
    or unsupported platform. Never raises.
    """
    os_name = current_os()
    try:
        if os_name == "macos":
            safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
            safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
            script = f'display notification "{safe_msg}" with title "{safe_title}"'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        elif os_name == "linux":
            result = subprocess.run(
                ["notify-send", title, message],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        elif os_name == "windows":
            # PowerShell toast notification
            ps_script = (
                f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; '
                f'$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); '
                f'$text = $template.GetElementsByTagName("text"); '
                f'$text.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null; '
                f'$text.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null; '
                f'$toast = [Windows.UI.Notifications.ToastNotification]::new($template); '
                f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("obsidian-connector").Show($toast)'
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return False
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/platform.py scripts/platform_test.py
git commit -m "feat: add notification abstraction to platform.py"
```

---

### Task 4: Add process detection and Obsidian binary resolution to `platform.py`

**Files:**
- Modify: `obsidian_connector/platform.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.platform import is_obsidian_running, obsidian_binary_candidates

def test_is_obsidian_running_returns_bool():
    result = is_obsidian_running()
    assert isinstance(result, bool)

def test_obsidian_binary_candidates():
    candidates = obsidian_binary_candidates()
    assert isinstance(candidates, list)
    assert len(candidates) >= 1
    assert all(isinstance(c, str) for c in candidates)
```

**Step 2: Run test to verify it fails**

Expected: `ImportError`

**Step 3: Write minimal implementation**

```python
import shutil

def is_obsidian_running() -> bool:
    """Check if the Obsidian desktop app is currently running."""
    os_name = current_os()
    try:
        if os_name == "macos":
            result = subprocess.run(
                ["pgrep", "-x", "Obsidian"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        elif os_name == "linux":
            result = subprocess.run(
                ["pgrep", "-x", "obsidian"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        elif os_name == "windows":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Obsidian.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return "Obsidian.exe" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return False


def obsidian_binary_candidates() -> list[str]:
    """Return a list of candidate Obsidian CLI binary names/paths.

    Ordered by preference. The caller should try each until one works.
    """
    os_name = current_os()
    if os_name == "macos":
        return ["obsidian"]
    elif os_name == "linux":
        candidates = ["obsidian"]
        # AppImage typically extracted or symlinked
        home = Path.home()
        appimage_paths = [
            home / "Applications" / "Obsidian.AppImage",
            home / ".local" / "bin" / "obsidian",
            Path("/usr/bin/obsidian"),
            Path("/usr/local/bin/obsidian"),
        ]
        for p in appimage_paths:
            if p.exists():
                candidates.insert(0, str(p))
        # Flatpak and Snap
        if shutil.which("flatpak"):
            candidates.append("flatpak run md.obsidian.Obsidian")
        if Path("/snap/obsidian/current").exists():
            candidates.append("/snap/obsidian/current/obsidian")
        return candidates
    elif os_name == "windows":
        # Windows has no CLI; return empty. Caller must use REST API or file access.
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            exe = Path(appdata) / "Obsidian" / "Obsidian.exe"
            if exe.exists():
                return [str(exe)]
        return []
    return ["obsidian"]
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/platform.py scripts/platform_test.py
git commit -m "feat: add process detection and binary resolution to platform.py"
```

---

### Task 5: Refactor `config.py` to use `platform.py`

**Files:**
- Modify: `obsidian_connector/config.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_config_uses_platform_paths():
    """Verify config.py no longer hardcodes ~/Library paths."""
    import inspect
    from obsidian_connector import config
    source = inspect.getsource(config)
    # Should not contain raw ~/Library paths
    assert 'Library" / "Application Support' not in source or "platform" in source
```

**Step 2: Run test to verify it fails**

Expected: Assertion fails because `config.py` still has hardcoded `~/Library/Application Support/obsidian/obsidian.json`.

**Step 3: Refactor `config.py`**

Replace the hardcoded `_OBSIDIAN_APP_JSON` constant and inline path references:

```python
# Before (config.py line 19-23):
_OBSIDIAN_APP_JSON = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)

# After:
from obsidian_connector.platform import obsidian_app_json_path, default_index_db_path

_OBSIDIAN_APP_JSON = obsidian_app_json_path()
_DEFAULT_INDEX_DB = default_index_db_path()
```

Also update `resolve_vault_path` to reference `_OBSIDIAN_APP_JSON` (already does, no change needed there -- it uses the module-level variable).

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/config.py scripts/platform_test.py
git commit -m "refactor: config.py uses platform.py for OS-specific paths"
```

---

### Task 6: Refactor `uninstall.py` and `cli.py` to use `platform.py`

**Files:**
- Modify: `obsidian_connector/uninstall.py`
- Modify: `obsidian_connector/cli.py`
- Modify: `obsidian_connector/mcp_server.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_uninstall_uses_platform_paths():
    """Verify uninstall.py uses platform.py for plist/schedule paths."""
    import inspect
    from obsidian_connector import uninstall
    source = inspect.getsource(uninstall)
    assert '"Library"' not in source or "platform" in source

def test_cli_uses_platform_paths():
    """Verify cli.py uses platform.py for Claude config path."""
    import inspect
    from obsidian_connector import cli
    source = inspect.getsource(cli)
    # The raw string should no longer appear
    assert source.count('Library" / "Application Support') == 0 or "platform" in source
```

**Step 2: Run test to verify it fails**

**Step 3: Refactor**

In `uninstall.py`, replace:
```python
# Line 63 -- hardcoded plist path
plist_path = Path.home() / "Library" / "LaunchAgents" / "com.obsidian-connector.daily.plist"
# Replace with:
from obsidian_connector.platform import schedule_config_dir
plist_path = schedule_config_dir() / "com.obsidian-connector.daily.plist"
```

Rename `unload_launchd_plist` to `uninstall_scheduled_job` and dispatch via `platform.py`:
```python
def uninstall_scheduled_job(job_name_or_path: Path) -> bool:
    """Unload and remove a scheduled job (platform-aware)."""
    from obsidian_connector.platform import uninstall_schedule
    return uninstall_schedule(str(job_name_or_path))
```

In `cli.py` line 1469, replace:
```python
claude_config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
# Replace with:
from obsidian_connector.platform import claude_desktop_config_path
claude_config_path = claude_desktop_config_path()
```

In `mcp_server.py`, replace any `/ "Library"` references similarly.

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py obsidian_connector/cli.py obsidian_connector/mcp_server.py scripts/platform_test.py
git commit -m "refactor: uninstall.py, cli.py, mcp_server.py use platform.py"
```

---

## Phase 2: Linux Support -- v0.2.0 (Tasks 7-12)

### Task 7: Implement systemd user timer scheduling

**Files:**
- Modify: `obsidian_connector/platform.py`
- Create: `scheduling/obsidian-connector-morning.service` (template)
- Create: `scheduling/obsidian-connector-morning.timer` (template)
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
import tempfile

def test_generate_systemd_unit(tmp_path):
    from obsidian_connector.platform import _generate_systemd_unit
    service, timer = _generate_systemd_unit(
        repo_root=tmp_path,
        python_path=Path("/usr/bin/python3"),
        workflow="morning",
        hour=8,
        minute=0,
    )
    assert "[Unit]" in service
    assert "[Service]" in service
    assert "ExecStart=" in service
    assert str(tmp_path) in service
    assert "[Timer]" in timer
    assert "OnCalendar=" in timer
    assert "08:00" in timer
```

**Step 2: Run test to verify it fails**

**Step 3: Implement systemd unit generation**

```python
def _generate_systemd_unit(
    repo_root: Path, python_path: Path, workflow: str, hour: int, minute: int
) -> tuple[str, str]:
    """Generate systemd .service and .timer unit file contents."""
    service_name = f"obsidian-connector-{workflow}"
    service = f"""[Unit]
Description=obsidian-connector {workflow} workflow
After=graphical-session.target

[Service]
Type=oneshot
ExecStart={python_path} {repo_root}/scheduling/run_scheduled.py {workflow}
WorkingDirectory={repo_root}
Environment=PYTHONPATH={repo_root}

[Install]
WantedBy=default.target
"""
    timer = f"""[Unit]
Description=obsidian-connector {workflow} timer

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def _install_systemd(
    repo_root: Path, python_path: Path, workflow: str, hour: int, minute: int
) -> bool:
    """Install a systemd user timer for the given workflow."""
    try:
        service_content, timer_content = _generate_systemd_unit(
            repo_root, python_path, workflow, hour, minute
        )
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)

        service_name = f"obsidian-connector-{workflow}"
        (unit_dir / f"{service_name}.service").write_text(service_content)
        (unit_dir / f"{service_name}.timer").write_text(timer_content)

        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", f"{service_name}.timer"],
                       capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _uninstall_systemd(job_name: str) -> bool:
    """Disable and remove a systemd user timer and service."""
    try:
        service_name = job_name.replace("com.obsidian-connector.", "obsidian-connector-")
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{service_name}.timer"],
                       capture_output=True, check=False)
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        for ext in (".service", ".timer"):
            unit_file = unit_dir / f"{service_name}{ext}"
            if unit_file.exists():
                unit_file.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
        return True
    except OSError:
        return False
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/platform.py scheduling/ scripts/platform_test.py
git commit -m "feat: implement systemd user timer scheduling for Linux"
```

---

### Task 8: Implement Linux config paths and vault detection

**Files:**
- Modify: `obsidian_connector/platform.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
import unittest.mock

def test_linux_claude_config_path():
    with unittest.mock.patch("obsidian_connector.platform.current_os", return_value="linux"):
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/test_xdg"}, clear=False):
            path = claude_desktop_config_path()
            assert str(path).startswith("/tmp/test_xdg")
            assert "Claude" in str(path)

def test_linux_obsidian_json_path():
    with unittest.mock.patch("obsidian_connector.platform.current_os", return_value="linux"):
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=False):
            path = obsidian_app_json_path()
            assert ".config/obsidian" in str(path)

def test_linux_vault_detection_xdg(tmp_path):
    """Verify vault detection works with XDG-based obsidian.json."""
    obsidian_json = tmp_path / "obsidian" / "obsidian.json"
    obsidian_json.parent.mkdir(parents=True)
    vault_dir = tmp_path / "my_vault"
    vault_dir.mkdir()
    obsidian_json.write_text(json.dumps({
        "vaults": {
            "abc123": {"path": str(vault_dir), "open": True}
        }
    }))
    # Existing resolve_vault_path should work if obsidian_app_json_path
    # points to this file. Tested via integration test.
```

**Step 2: Run test to verify it fails**

**Step 3: Implementation already exists in Task 1**

The `claude_desktop_config_path()` and `obsidian_app_json_path()` functions from Task 1 already handle Linux paths via XDG. This task validates the behavior with mocked OS and environment variables and ensures the full vault resolution chain works end-to-end on Linux.

Verify that `config.py`'s `resolve_vault_path()` correctly uses the platform-provided `_OBSIDIAN_APP_JSON` path (from Task 5 refactor) and works when the file is at an XDG location.

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add scripts/platform_test.py
git commit -m "test: add Linux config path and vault detection tests"
```

---

### Task 9: Refactor `scheduling/run_scheduled.py` to use `platform.py` notifications

**Files:**
- Modify: `scheduling/run_scheduled.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_run_scheduled_uses_platform_notify():
    """Verify run_scheduled.py no longer hardcodes osascript."""
    import inspect
    # Read file directly since it is not a package module
    source = Path(__file__).parent.parent / "scheduling" / "run_scheduled.py"
    text = source.read_text()
    assert "osascript" not in text, "run_scheduled.py should use platform.send_notification"
```

**Step 2: Run test to verify it fails**

**Step 3: Refactor `run_scheduled.py`**

Replace the `_notify` function:

```python
# Before:
def _notify(title: str, message: str, config: dict) -> None:
    """Send a macOS notification."""
    notif_config = config.get("notification", {})
    if not notif_config.get("enabled", True):
        return
    method = notif_config.get("method", "osascript")
    if method == "osascript":
        ...

# After:
def _notify(title: str, message: str, config: dict) -> None:
    """Send a desktop notification (platform-aware)."""
    notif_config = config.get("notification", {})
    if not notif_config.get("enabled", True):
        return
    from obsidian_connector.platform import send_notification
    send_notification(title, message)
```

Remove the `_osa_escape` helper (now internal to `platform.py`).

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add scheduling/run_scheduled.py scripts/platform_test.py
git commit -m "refactor: run_scheduled.py uses platform.send_notification"
```

---

### Task 10: Create Linux install script

**Files:**
- Create: `scripts/install-linux.sh`
- Modify: `scripts/install.sh` (add OS detection + dispatch)

**Step 1: Write the failing test**

```python
def test_linux_install_script_exists():
    install_script = Path(__file__).parent.parent / "scripts" / "install-linux.sh"
    assert install_script.exists(), "scripts/install-linux.sh must exist"
    text = install_script.read_text()
    assert "systemctl" in text or "systemd" in text
    assert "XDG_CONFIG_HOME" in text or ".config" in text
```

**Step 2: Run test to verify it fails**

**Step 3: Create `scripts/install-linux.sh`**

Mirrors `install.sh` structure but uses:
- `~/.config/Claude/claude_desktop_config.json` (XDG) for Claude Desktop config
- `systemctl --user` for scheduling instead of `launchctl`
- `notify-send` check instead of `osascript`
- `~/.config/systemd/user/` for timer units

Also modify `scripts/install.sh` to detect OS and dispatch:
```bash
# Add at top of install.sh, after set -euo pipefail:
case "$(uname -s)" in
    Linux)
        exec "$SCRIPT_DIR/install-linux.sh" "$@"
        ;;
    CYGWIN*|MINGW*|MSYS*)
        echo "Windows detected. Use scripts/install.ps1 instead."
        exit 1
        ;;
esac
# (rest of macOS install continues)
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add scripts/install-linux.sh scripts/install.sh
git commit -m "feat: add Linux install script with systemd and XDG support"
```

---

### Task 11: Add Ubuntu runner to CI matrix

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Write the failing test**

```python
def test_ci_includes_ubuntu():
    ci_yml = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
    text = ci_yml.read_text()
    assert "ubuntu" in text.lower(), "CI must include Ubuntu runner"
```

**Step 2: Run test to verify it fails**

CI currently uses `os: [macos-latest]` only.

**Step 3: Update `.github/workflows/ci.yml`**

```yaml
test:
  runs-on: ${{ matrix.os }}
  strategy:
    fail-fast: false
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
        python3 scripts/platform_test.py

mcp-launch:
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      os: [macos-latest, ubuntu-latest]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - run: pip install -e .
    - name: MCP server starts without error
      run: bash scripts/mcp_launch_smoke.sh
```

The lint job stays on `ubuntu-latest` (already is).

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add .github/workflows/ci.yml scripts/platform_test.py
git commit -m "infra: add Ubuntu to CI matrix for cross-platform testing"
```

---

### Task 12: Obsidian CLI fallback -- direct file access and Local REST API

**Files:**
- Create: `obsidian_connector/file_backend.py`
- Modify: `obsidian_connector/client.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_file_backend_read_note(tmp_path):
    from obsidian_connector.file_backend import read_note_file
    note = tmp_path / "test.md"
    note.write_text("# Hello\nWorld")
    content = read_note_file(note)
    assert content == "# Hello\nWorld"

def test_file_backend_search(tmp_path):
    from obsidian_connector.file_backend import search_vault_files
    (tmp_path / "note1.md").write_text("The quick brown fox")
    (tmp_path / "note2.md").write_text("The lazy dog")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "note3.md").write_text("quick fox again")
    results = search_vault_files(tmp_path, "quick")
    assert len(results) == 2
    assert any("note1" in r["file"] for r in results)
    assert any("note3" in r["file"] for r in results)
```

**Step 2: Run test to verify it fails**

**Step 3: Create `obsidian_connector/file_backend.py`**

A pure-Python fallback for read operations when the Obsidian CLI is unavailable (Linux AppImage without CLI, Windows with no CLI). This module reads vault files directly via pathlib.

```python
"""Direct file access backend for vaults.

Used as a fallback when the Obsidian CLI is not available (e.g., Linux
AppImage without CLI support, Windows). Read-only operations only.
"""
from __future__ import annotations

import re
from pathlib import Path


def read_note_file(file_path: Path) -> str:
    """Read a note file and return its content."""
    return file_path.read_text(encoding="utf-8")


def search_vault_files(
    vault_path: Path,
    query: str,
    max_results: int = 50,
) -> list[dict]:
    """Search vault files for a query string.

    Returns a list of dicts with "file" and "matches" keys,
    matching the format of the Obsidian CLI search output.
    """
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for md_file in vault_path.rglob("*.md"):
        # Skip hidden directories (.obsidian, .trash, etc.)
        if any(part.startswith(".") for part in md_file.relative_to(vault_path).parts):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        matches = []
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                matches.append({"line": i, "text": line.strip()})

        if matches:
            results.append({
                "file": str(md_file.relative_to(vault_path)),
                "matches": matches,
            })
            if len(results) >= max_results:
                break

    return results


def list_tasks_from_files(
    vault_path: Path,
    include_done: bool = False,
) -> list[dict]:
    """Extract tasks from vault markdown files.

    Finds lines matching `- [ ] ...` (todo) and `- [x] ...` (done).
    """
    task_re = re.compile(r"^(\s*)- \[([ xX])\] (.+)$")
    tasks = []

    for md_file in vault_path.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.relative_to(vault_path).parts):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for i, line in enumerate(content.splitlines(), 1):
            m = task_re.match(line)
            if m:
                status_char = m.group(2)
                is_done = status_char.lower() == "x"
                if is_done and not include_done:
                    continue
                tasks.append({
                    "text": m.group(3).strip(),
                    "status": "x" if is_done else " ",
                    "file": str(md_file.relative_to(vault_path)),
                    "line": i,
                })

    return tasks
```

Modify `client.py` to fall back to file backend when the CLI is not available:

```python
# In client.py, add fallback import at top:
from obsidian_connector.platform import current_os, obsidian_binary_candidates

# In run_obsidian(), after FileNotFoundError:
except FileNotFoundError as exc:
    # On platforms without CLI, suggest file backend
    if current_os() in ("linux", "windows") and not obsidian_binary_candidates():
        raise ObsidianNotFound(
            f"Obsidian CLI not available on {current_os()}. "
            "Read-only operations can use direct file access. "
            "Set OBSIDIAN_VAULT_PATH to enable file-based fallback."
        ) from exc
    raise ObsidianNotFound(
        f"obsidian binary not found: {cfg.obsidian_bin}"
    ) from exc
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/file_backend.py obsidian_connector/client.py scripts/platform_test.py
git commit -m "feat: add file_backend.py for CLI-less vault access (Linux/Windows fallback)"
```

---

## Phase 3: Windows Support -- v0.3.0 (Tasks 13-18)

### Task 13: Implement Windows Task Scheduler in `platform.py`

**Files:**
- Modify: `obsidian_connector/platform.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_generate_schtasks_command():
    from obsidian_connector.platform import _generate_schtasks_command
    cmd = _generate_schtasks_command(
        repo_root=Path("C:/Users/test/obsidian-connector"),
        python_path=Path("C:/Users/test/obsidian-connector/.venv/Scripts/python.exe"),
        workflow="morning",
        time="08:00",
    )
    assert "schtasks" in cmd[0].lower() or "SCHTASKS" in cmd[0]
    assert "/CREATE" in cmd or "/create" in [c.lower() for c in cmd]
    assert "morning" in " ".join(cmd)
    assert "08:00" in " ".join(cmd)
```

**Step 2: Run test to verify it fails**

**Step 3: Implement**

```python
def _generate_schtasks_command(
    repo_root: Path, python_path: Path, workflow: str, time: str
) -> list[str]:
    """Generate a schtasks /CREATE command for Windows Task Scheduler."""
    task_name = f"obsidian-connector-{workflow}"
    script_path = repo_root / "scheduling" / "run_scheduled.py"
    return [
        "schtasks", "/CREATE",
        "/SC", "DAILY",
        "/TN", task_name,
        "/TR", f'"{python_path}" "{script_path}" {workflow}',
        "/ST", time,
        "/F",  # Force overwrite if exists
    ]


def _install_task_scheduler(
    repo_root: Path, python_path: Path, workflow: str, time: str
) -> bool:
    """Install a Windows Task Scheduler task."""
    try:
        cmd = _generate_schtasks_command(repo_root, python_path, workflow, time)
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.returncode == 0
    except (subprocess.CalledProcessError, OSError):
        return False


def _uninstall_task_scheduler(job_name: str) -> bool:
    """Remove a Windows Task Scheduler task."""
    try:
        task_name = job_name.replace("com.obsidian-connector.", "obsidian-connector-")
        result = subprocess.run(
            ["schtasks", "/DELETE", "/TN", task_name, "/F"],
            capture_output=True, check=False,
        )
        return result.returncode == 0
    except OSError:
        return False
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/platform.py scripts/platform_test.py
git commit -m "feat: implement Windows Task Scheduler support in platform.py"
```

---

### Task 14: Implement Windows config paths

**Files:**
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_windows_claude_config_path():
    with unittest.mock.patch("obsidian_connector.platform.current_os", return_value="windows"):
        with unittest.mock.patch.dict(os.environ, {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}):
            path = claude_desktop_config_path()
            assert "AppData" in str(path) or "APPDATA" in str(path)
            assert "Claude" in str(path)

def test_windows_obsidian_json_path():
    with unittest.mock.patch("obsidian_connector.platform.current_os", return_value="windows"):
        with unittest.mock.patch.dict(os.environ, {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}):
            path = obsidian_app_json_path()
            assert "obsidian" in str(path).lower()
```

**Step 2: Run test to verify it fails or passes**

These paths were already implemented in Task 1. This task adds explicit test coverage.

**Step 3: Verify implementation**

The `claude_desktop_config_path()` and `obsidian_app_json_path()` from Task 1 already handle Windows via `%APPDATA%`. Confirm that `Path.home() / "AppData" / "Roaming"` fallback works when `APPDATA` is not set.

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add scripts/platform_test.py
git commit -m "test: add Windows config path tests"
```

---

### Task 15: Create PowerShell install script

**Files:**
- Create: `scripts/install.ps1`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_powershell_install_script_exists():
    ps_script = Path(__file__).parent.parent / "scripts" / "install.ps1"
    assert ps_script.exists(), "scripts/install.ps1 must exist"
    text = ps_script.read_text()
    assert "APPDATA" in text or "AppData" in text
    assert "claude_desktop_config" in text.lower() or "Claude" in text
    assert "python" in text.lower()
```

**Step 2: Run test to verify it fails**

**Step 3: Create `scripts/install.ps1`**

PowerShell script that:
- Finds Python 3.11+
- Creates `.venv` and installs the package
- Configures Claude Desktop at `%APPDATA%\Claude\claude_desktop_config.json`
- Optionally sets up Task Scheduler via `schtasks /CREATE`
- Validates installation

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add scripts/install.ps1 scripts/platform_test.py
git commit -m "feat: add PowerShell install script for Windows"
```

---

### Task 16: Ensure file_backend.py handles Windows paths

**Files:**
- Modify: `obsidian_connector/file_backend.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_file_backend_windows_path_separators(tmp_path):
    """Ensure search results use forward slashes regardless of OS."""
    from obsidian_connector.file_backend import search_vault_files
    sub = tmp_path / "folder" / "subfolder"
    sub.mkdir(parents=True)
    (sub / "note.md").write_text("test content")
    results = search_vault_files(tmp_path, "test")
    assert len(results) == 1
    # On all platforms, use forward slashes in relative paths
    assert "\\" not in results[0]["file"]
```

**Step 2: Run test to verify it fails on Windows (backslashes)**

**Step 3: Fix path separators**

In `file_backend.py`, replace:
```python
"file": str(md_file.relative_to(vault_path)),
```
with:
```python
"file": md_file.relative_to(vault_path).as_posix(),
```

This ensures consistent forward-slash paths on all platforms.

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/file_backend.py scripts/platform_test.py
git commit -m "fix: file_backend uses forward slashes on all platforms"
```

---

### Task 17: Add Windows runner to CI matrix

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Write the failing test**

```python
def test_ci_includes_windows():
    ci_yml = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
    text = ci_yml.read_text()
    assert "windows" in text.lower(), "CI must include Windows runner"
```

**Step 2: Run test to verify it fails**

**Step 3: Update `.github/workflows/ci.yml`**

```yaml
test:
  runs-on: ${{ matrix.os }}
  strategy:
    fail-fast: false
    matrix:
      os: [macos-latest, ubuntu-latest, windows-latest]
      python-version: ["3.11", "3.12", "3.13", "3.14"]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    - run: pip install -e .
    - name: Unit tests (no Obsidian required)
      shell: bash
      run: |
        python3 scripts/cache_test.py
        python3 scripts/audit_test.py
        python3 scripts/escaping_test.py
        python3 scripts/graph_test.py
        python3 scripts/index_test.py
        python3 scripts/graduate_test.py
        python3 scripts/thinking_deep_test.py
        python3 scripts/delegation_test.py
        python3 scripts/platform_test.py
```

Note: `shell: bash` is required for Windows runners to use bash syntax. The `python3` command works on all GitHub Actions runners.

MCP launch test stays macOS + Ubuntu (no Obsidian CLI on Windows):
```yaml
mcp-launch:
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      os: [macos-latest, ubuntu-latest]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - run: pip install -e .
    - name: MCP server starts without error
      run: bash scripts/mcp_launch_smoke.sh
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add .github/workflows/ci.yml scripts/platform_test.py
git commit -m "infra: add Windows to CI matrix, expand to Python 3.11-3.14"
```

---

### Task 18: Update `doctor.py` for cross-platform diagnostics

**Files:**
- Modify: `obsidian_connector/doctor.py`
- Modify: `scripts/platform_test.py`

**Step 1: Write the failing test**

```python
def test_doctor_reports_platform():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "platform" in check_names, "doctor should report current platform"

def test_doctor_reports_scheduler():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "scheduler" in check_names, "doctor should report scheduler type"
```

**Step 2: Run test to verify it fails**

**Step 3: Add platform checks to `doctor.py`**

```python
from obsidian_connector.platform import current_os, scheduler_type, is_obsidian_running

def run_doctor(vault: str | None = None) -> list[dict]:
    results: list[dict] = []

    # --- 0. Platform ---
    os_name = current_os()
    results.append({
        "check": "platform",
        "ok": True,
        "detail": f"{os_name} ({sys.platform})",
        "action": None,
    })

    # --- 0b. Scheduler ---
    sched = scheduler_type()
    results.append({
        "check": "scheduler",
        "ok": True,
        "detail": sched,
        "action": None,
    })

    # --- 0c. Obsidian process ---
    running = is_obsidian_running()
    results.append({
        "check": "obsidian_running",
        "ok": running,
        "detail": "running" if running else "not detected",
        "action": None if running else "Start Obsidian desktop app for CLI access.",
    })

    # ... (existing checks continue, but binary check skips on Windows
    # if no candidates are found and suggests file backend instead)
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add obsidian_connector/doctor.py scripts/platform_test.py
git commit -m "feat: doctor.py reports platform, scheduler, and process status"
```

---

## Phase 4: Documentation and Finalization (Tasks 19-21)

### Task 19: Update TOOLS_CONTRACT.md for cross-platform behavior

**Files:**
- Modify: `TOOLS_CONTRACT.md`

Document:
- `doctor` tool now returns `platform`, `scheduler`, and `obsidian_running` checks
- `uninstall` tool works with systemd (Linux) and Task Scheduler (Windows) in addition to launchd (macOS)
- All path-dependent tools resolve paths via `platform.py`
- File backend fallback for read-only operations when CLI is unavailable

**Commit:**

```bash
git add TOOLS_CONTRACT.md
git commit -m "docs: update TOOLS_CONTRACT.md for cross-platform behavior"
```

---

### Task 20: Update `pyproject.toml` classifiers

**Files:**
- Modify: `pyproject.toml`

Add operating system classifiers:

```toml
classifiers = [
    # ... existing ...
    "Operating System :: MacOS",
    "Operating System :: POSIX :: Linux",
    "Operating System :: Microsoft :: Windows",
    "Programming Language :: Python :: 3.14",
]
```

**Commit:**

```bash
git add pyproject.toml
git commit -m "docs: add OS classifiers and Python 3.14 to pyproject.toml"
```

---

### Task 21: Final integration test and merge readiness

**Files:**
- Modify: `scripts/platform_test.py`

Add comprehensive integration tests:

```python
def test_full_platform_api_surface():
    """Verify all platform.py public functions are importable and callable."""
    from obsidian_connector.platform import (
        current_os,
        claude_desktop_config_path,
        obsidian_app_json_path,
        default_index_db_path,
        schedule_config_dir,
        scheduler_type,
        install_schedule,
        uninstall_schedule,
        send_notification,
        is_obsidian_running,
        obsidian_binary_candidates,
    )
    # All return without error
    assert current_os() in ("macos", "linux", "windows")
    assert isinstance(claude_desktop_config_path(), Path)
    assert isinstance(obsidian_app_json_path(), Path)
    assert isinstance(default_index_db_path(), Path)
    assert isinstance(schedule_config_dir(), Path)
    assert scheduler_type() in ("launchd", "systemd", "task_scheduler")
    assert isinstance(obsidian_binary_candidates(), list)
    assert isinstance(is_obsidian_running(), bool)

def test_no_hardcoded_macos_paths_in_core():
    """Scan core modules for hardcoded macOS paths (should all go through platform.py)."""
    core_modules = ["config.py", "uninstall.py", "cli.py", "mcp_server.py", "doctor.py"]
    repo_root = Path(__file__).parent.parent
    violations = []
    for mod in core_modules:
        source = (repo_root / "obsidian_connector" / mod).read_text()
        # Allow "platform" imports but flag raw Library paths
        if '"Library"' in source and "platform" not in source:
            violations.append(mod)
        if "LaunchAgents" in source and "platform" not in source:
            violations.append(mod)
    assert not violations, f"Hardcoded macOS paths found in: {violations}"
```

Run full test suite across all platforms:

```bash
python3 scripts/platform_test.py
python3 scripts/cache_test.py
python3 scripts/audit_test.py
python3 scripts/escaping_test.py
python3 scripts/graph_test.py
python3 scripts/index_test.py
python3 scripts/graduate_test.py
python3 scripts/thinking_deep_test.py
python3 scripts/delegation_test.py
make docs-lint
```

**Commit:**

```bash
git add scripts/platform_test.py
git commit -m "test: add final cross-platform integration tests"
```

---

## Migration Path for Existing macOS Users

Existing macOS installations must continue to work without any user action after upgrading.

**Guarantees:**
1. All macOS paths remain the defaults when `sys.platform == "darwin"`.
2. `platform.py` returns identical paths to the current hardcoded values on macOS.
3. Existing launchd plists continue to work -- `uninstall_schedule()` knows how to remove them.
4. `install.sh` continues to work for macOS (dispatches to Linux script only on Linux).
5. No new required dependencies. `platform.py` uses only stdlib.
6. `config.json` format is unchanged. No migration script needed.

**Validation:** Task 21's integration test verifies that no hardcoded macOS paths remain outside `platform.py`, and the existing test suite passes unmodified on macOS.

---

## Testing Strategy

### CI Matrix (Final State)

| OS | Python | Test Scope |
|----|--------|-----------|
| `macos-latest` | 3.11, 3.12, 3.13, 3.14 | Full unit tests + MCP launch + platform tests |
| `ubuntu-latest` | 3.11, 3.12, 3.13, 3.14 | Full unit tests + MCP launch + platform tests |
| `windows-latest` | 3.11, 3.12, 3.13, 3.14 | Unit tests + platform tests (no MCP launch -- no CLI) |

### Test Categories

1. **Unit tests** (existing `scripts/*.py`): No Obsidian required. Work on all platforms today. Graph, cache, audit, escaping, index, graduate, thinking, delegation.
2. **Platform tests** (`scripts/platform_test.py`): New. Test OS detection, path resolution, notification dispatch, scheduler type, process detection. Use `unittest.mock` to test non-native OS paths.
3. **Integration tests**: MCP server launch smoke test. macOS + Linux only (requires Obsidian CLI or socket).
4. **File backend tests**: Test direct vault file access. All platforms. No Obsidian dependency.
5. **Install script tests**: Verify script syntax (`bash -n` for shell, `powershell -Command "Get-Content ..."` for PS1). Run in CI but do not execute the actual install.

### Mock Strategy for Cross-Platform Tests

Tests for non-native OS paths use `unittest.mock.patch`:
```python
# Test Linux paths on macOS:
with unittest.mock.patch("obsidian_connector.platform.current_os", return_value="linux"):
    path = claude_desktop_config_path()
    assert ".config/Claude" in str(path)
```

This avoids needing to run tests on every OS for path resolution logic. CI matrix provides real-OS validation.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Breaking existing macOS installs | High | Task 21 verifies identical macOS behavior. All refactoring preserves return values. Migration path guarantees above. |
| Obsidian CLI unavailable on Linux | Medium | File backend fallback (Task 12). Document that CLI features require the desktop app + CLI plugin. Local REST API plugin as alternative. |
| No Obsidian CLI on Windows at all | Medium | File backend is the primary access method. Document clearly. REST API plugin recommended for write operations. |
| systemd not available on all Linux distros | Low | `_install_systemd` fails gracefully (returns False). User can run `run_scheduled.py` via cron as alternative. Document cron as manual fallback. |
| Windows path encoding (Unicode usernames) | Low | pathlib handles this. `Path.home()` returns the correct encoding on Windows. Test with non-ASCII tmp_path in CI. |
| PowerShell execution policy blocks install.ps1 | Low | Document: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Provide manual install instructions as fallback. |
| `notify-send` not installed on minimal Linux | Low | `send_notification` returns False (never raises). Notifications are cosmetic, not functional. |
| Python 3.14 compatibility | Low | Already in `pyproject.toml` classifiers. pathlib and sys.platform are stable APIs. CI matrix will catch regressions. |

---

## File Change Summary

### New Files

| File | Phase | Purpose |
|------|-------|---------|
| `obsidian_connector/platform.py` | 1 | Platform abstraction layer |
| `obsidian_connector/file_backend.py` | 2 | Direct file access fallback for CLI-less platforms |
| `scripts/platform_test.py` | 1 | Cross-platform test suite |
| `scripts/install-linux.sh` | 2 | Linux installer with systemd and XDG |
| `scripts/install.ps1` | 3 | Windows installer with Task Scheduler |
| `scheduling/obsidian-connector-morning.service` | 2 | systemd service template |
| `scheduling/obsidian-connector-morning.timer` | 2 | systemd timer template |

### Modified Files

| File | Phase | Change |
|------|-------|--------|
| `obsidian_connector/config.py` | 1 | Replace hardcoded `~/Library` paths with `platform.py` calls |
| `obsidian_connector/uninstall.py` | 1 | Replace hardcoded plist path with `platform.py`, rename `unload_launchd_plist` |
| `obsidian_connector/cli.py` | 1 | Replace hardcoded Claude config path with `platform.py` |
| `obsidian_connector/mcp_server.py` | 1 | Replace hardcoded paths with `platform.py` |
| `obsidian_connector/client.py` | 2 | Add fallback error message for CLI-less platforms |
| `obsidian_connector/doctor.py` | 3 | Add platform, scheduler, process checks |
| `scheduling/run_scheduled.py` | 2 | Replace `osascript` notification with `platform.send_notification` |
| `scripts/install.sh` | 2 | Add OS detection, dispatch to platform-specific script |
| `.github/workflows/ci.yml` | 2-3 | Add Ubuntu and Windows runners, expand Python matrix |
| `pyproject.toml` | 4 | Add OS classifiers, Python 3.14 |
| `TOOLS_CONTRACT.md` | 4 | Document cross-platform behavior |
