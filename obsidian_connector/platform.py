"""Platform abstraction layer for obsidian-connector.

Centralizes all OS-specific path resolution, scheduling, and
notification logic. Every other module imports from here instead
of hardcoding ~/Library/... or %APPDATA%\\... paths.
"""
from __future__ import annotations

import os
import shutil
import subprocess
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
            scheduler_dir=None,
            data_dir=data_dir,
            log_dir=log_dir,
            scheduler_type="task_scheduler",
        )
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        return PlatformPaths(
            obsidian_config=xdg_config / "obsidian" / "obsidian.json",
            claude_config_dir=xdg_config / "Claude",
            scheduler_dir=xdg_config / "systemd" / "user",
            data_dir=data_dir,
            log_dir=log_dir,
            scheduler_type="systemd",
        )


# ------------------------------------------------------------------
# Backward-compatible convenience wrappers (used by existing code
# and referenced in cross-platform-plan docs).  New code should
# prefer ``get_platform_paths()`` directly.
# ------------------------------------------------------------------

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
    paths = get_platform_paths()
    return paths.claude_config_dir / "claude_desktop_config.json"


def obsidian_app_json_path() -> Path:
    """Return the path to Obsidian's app-level config (obsidian.json)."""
    return get_platform_paths().obsidian_config


def default_index_db_path() -> Path:
    """Return the default path for the SQLite index database."""
    return Path.home() / ".obsidian-connector" / "index.sqlite"


def schedule_config_dir() -> Path:
    """Return the directory for scheduling configuration files."""
    paths = get_platform_paths()
    if paths.scheduler_dir is not None:
        return paths.scheduler_dir
    # Windows fallback -- Task Scheduler doesn't use a config dir.
    return Path.home() / ".obsidian-connector" / "tasks"


# ------------------------------------------------------------------
# Scheduling abstraction
# ------------------------------------------------------------------

def scheduler_type() -> str:
    """Return the scheduling backend for this OS."""
    return get_platform_paths().scheduler_type


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
    dict with keys: scheduler, job_name, workflow, time, dry_run, installed.
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
        result["installed"] = _install_launchd(
            repo_root, python_path, workflow, int(hour), int(minute)
        )
    elif sched == "systemd":
        result["installed"] = _install_systemd(
            repo_root, python_path, workflow, int(hour), int(minute)
        )
    elif sched == "task_scheduler":
        result["installed"] = _install_task_scheduler(
            repo_root, python_path, workflow, time
        )

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


# ------------------------------------------------------------------
# Private scheduling implementations (platform-specific)
# ------------------------------------------------------------------

def _install_launchd(
    repo_root: Path, python_path: Path, workflow: str, hour: int, minute: int
) -> bool:
    """Install a launchd plist for the given workflow (macOS)."""
    job_name = f"com.obsidian-connector.{workflow}"
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{job_name}.plist"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{job_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{repo_root}/scheduling/run_scheduled.py</string>
        <string>{workflow}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>{repo_root}</string>
    <key>StandardErrorPath</key>
    <string>{repo_root}/logs/{workflow}-stderr.log</string>
    <key>StandardOutPath</key>
    <string>{repo_root}/logs/{workflow}-stdout.log</string>
</dict>
</plist>
"""
    try:
        plist_path.write_text(plist_content)
        subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _uninstall_launchd(job_name: str) -> bool:
    """Unload and remove a launchd plist (macOS)."""
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = plist_dir / f"{job_name}.plist"
    try:
        if plist_path.exists():
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                check=False,
            )
            plist_path.unlink()
        return True
    except (IOError, OSError):
        return False


def _install_systemd(
    repo_root: Path, python_path: Path, workflow: str, hour: int, minute: int
) -> bool:
    """Install a systemd user timer for the given workflow (Linux)."""
    raise NotImplementedError("systemd scheduling not yet implemented")


def _uninstall_systemd(job_name: str) -> bool:
    """Disable and remove a systemd user timer and service (Linux)."""
    raise NotImplementedError("systemd scheduling not yet implemented")


# ------------------------------------------------------------------
# Notification abstraction
# ------------------------------------------------------------------

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


def _install_task_scheduler(
    repo_root: Path, python_path: Path, workflow: str, time: str
) -> bool:
    """Install a Windows Task Scheduler task for the given workflow."""
    raise NotImplementedError("Windows Task Scheduler not yet implemented")


def _uninstall_task_scheduler(job_name: str) -> bool:
    """Remove a Windows Task Scheduler task."""
    raise NotImplementedError("Windows Task Scheduler not yet implemented")


# ------------------------------------------------------------------
# Process detection and binary resolution
# ------------------------------------------------------------------

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
        return ["obsidian", "/Applications/Obsidian.app/Contents/MacOS/Obsidian"]
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
        # Windows has no CLI; return the desktop app path.
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            exe = Path(appdata) / "Obsidian" / "Obsidian.exe"
            if exe.exists():
                return [str(exe)]
        return ["Obsidian.exe"]
    return ["obsidian"]
