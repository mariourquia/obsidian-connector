"""Platform abstraction layer for obsidian-connector.

Centralizes all OS-specific path resolution, scheduling, and
notification logic. Every other module imports from here instead
of hardcoding ~/Library/... or %APPDATA%\\... paths.
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
