#!/usr/bin/env python3
"""
Installer Smoke Test
====================

Cross-platform validation of post-install state for obsidian-connector.

Checks that after an installer runs, the correct artifacts exist:
1. Plugin cache directory with plugin.json
2. installed_plugins.json is valid and contains the right entry
3. settings.json has the plugin enabled
4. Claude Desktop config (if dir exists) has MCP server entry
5. MCP server module imports successfully (if venv exists)
6. Version in registration matches pyproject.toml

Usage:
    python3 scripts/installer_smoke_test.py [--claude-home PATH] [--install-dir PATH]

Exit codes:
    0 -- all checks pass (SKIPs are acceptable)
    1 -- at least one check failed
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Version extraction
# ---------------------------------------------------------------------------

def get_pyproject_version(install_dir: Path) -> str | None:
    """Extract version from pyproject.toml using regex."""
    toml_path = install_dir / "pyproject.toml"
    if not toml_path.is_file():
        return None
    content = toml_path.read_text(encoding="utf-8")
    m = re.search(r'version = "([^"]+)"', content)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def get_desktop_config_dir() -> Path | None:
    """Return the Claude Desktop config directory for the current platform."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Claude"
        return None
    elif system == "Linux":
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(xdg) / "Claude"
    return None


def get_venv_python(install_dir: Path) -> Path | None:
    """Return the venv Python executable path if the venv exists."""
    system = platform.system()
    if system == "Windows":
        python_path = install_dir / ".venv" / "Scripts" / "python.exe"
    else:
        python_path = install_dir / ".venv" / "bin" / "python3"
    return python_path if python_path.is_file() else None


# ---------------------------------------------------------------------------
# Check functions -- each returns (status, message)
# status is one of: "PASS", "FAIL", "SKIP"
# ---------------------------------------------------------------------------

def check_plugin_cache(claude_home: Path, version: str) -> tuple[str, str]:
    """Check 1: Plugin cache directory exists with plugin.json."""
    cache_dir = claude_home / "plugins" / "cache" / "local" / "obsidian-connector" / version
    plugin_json = cache_dir / ".claude-plugin" / "plugin.json"

    if not cache_dir.is_dir():
        return "FAIL", f"Plugin cache directory not found: {cache_dir}"

    if not plugin_json.is_file():
        return "FAIL", f"plugin.json not found in cache: {plugin_json}"

    try:
        data = json.loads(plugin_json.read_text(encoding="utf-8"))
        if data.get("name") != "obsidian-connector":
            return "FAIL", f"plugin.json name mismatch: {data.get('name')}"
    except (json.JSONDecodeError, OSError) as e:
        return "FAIL", f"plugin.json parse error: {e}"

    return "PASS", f"Plugin cache OK at {cache_dir}"


def check_installed_plugins(claude_home: Path, version: str) -> tuple[str, str]:
    """Check 2: installed_plugins.json is valid and has correct entry."""
    ip_path = claude_home / "plugins" / "installed_plugins.json"

    if not ip_path.is_file():
        return "FAIL", f"installed_plugins.json not found: {ip_path}"

    try:
        data = json.loads(ip_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return "FAIL", f"installed_plugins.json parse error: {e}"

    plugin_key = "obsidian-connector@local"
    plugins = data.get("plugins", {})

    if plugin_key not in plugins:
        return "FAIL", f"Key '{plugin_key}' not found in installed_plugins.json"

    entry = plugins[plugin_key]
    # Entry is a list of installations (one per scope)
    if isinstance(entry, list):
        if not entry:
            return "FAIL", f"'{plugin_key}' entry is empty list"
        first = entry[0]
        entry_version = first.get("version")
        install_path = first.get("installPath")
    elif isinstance(entry, dict):
        entry_version = entry.get("version")
        install_path = entry.get("installPath")
    else:
        return "FAIL", f"'{plugin_key}' has unexpected type: {type(entry).__name__}"

    if entry_version != version:
        return "FAIL", f"Version mismatch: installed_plugins says {entry_version}, pyproject.toml says {version}"

    if not install_path:
        return "FAIL", f"installPath is empty for '{plugin_key}'"

    return "PASS", f"installed_plugins.json OK: {plugin_key} v{entry_version}"


def check_settings(claude_home: Path) -> tuple[str, str]:
    """Check 3: settings.json has the plugin enabled."""
    settings_path = claude_home / "settings.json"

    if not settings_path.is_file():
        return "FAIL", f"settings.json not found: {settings_path}"

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return "FAIL", f"settings.json parse error: {e}"

    plugin_key = "obsidian-connector@local"
    enabled = data.get("enabledPlugins", {})

    if plugin_key not in enabled:
        return "FAIL", f"'{plugin_key}' not in enabledPlugins"

    if enabled[plugin_key] is not True:
        return "FAIL", f"enabledPlugins['{plugin_key}'] = {enabled[plugin_key]} (expected true)"

    return "PASS", f"settings.json OK: {plugin_key} enabled"


def check_desktop_config() -> tuple[str, str]:
    """Check 4: Claude Desktop config has MCP server entry (if dir exists)."""
    config_dir = get_desktop_config_dir()

    if config_dir is None:
        return "SKIP", "Could not determine Claude Desktop config directory"

    if not config_dir.is_dir():
        return "SKIP", f"Claude Desktop config directory not found: {config_dir}"

    config_path = config_dir / "claude_desktop_config.json"
    if not config_path.is_file():
        return "SKIP", f"claude_desktop_config.json not found: {config_path}"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return "FAIL", f"claude_desktop_config.json parse error: {e}"

    servers = data.get("mcpServers", {})
    if "obsidian-connector" not in servers:
        return "FAIL", "obsidian-connector not in mcpServers"

    entry = servers["obsidian-connector"]
    command = entry.get("command", "")
    if not command:
        return "FAIL", "mcpServers.obsidian-connector.command is empty"

    return "PASS", f"Claude Desktop config OK: command={command}"


def check_mcp_import(install_dir: Path) -> tuple[str, str]:
    """Check 5: MCP server module imports successfully via venv Python."""
    venv_python = get_venv_python(install_dir)

    if venv_python is None:
        return "SKIP", "No venv found -- skipping MCP import check"

    try:
        result = subprocess.run(
            [str(venv_python), "-c", "from obsidian_connector.mcp_server import mcp; print('OK')"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(install_dir),
            env={**os.environ, "PYTHONPATH": str(install_dir)},
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return "PASS", "MCP server module imports successfully"
        else:
            stderr = result.stderr.strip()[:200] if result.stderr else "(no stderr)"
            return "FAIL", f"MCP import failed (exit {result.returncode}): {stderr}"
    except subprocess.TimeoutExpired:
        return "FAIL", "MCP import timed out after 30s"
    except OSError as e:
        return "FAIL", f"Could not run venv Python: {e}"


def check_version_match(claude_home: Path, version: str) -> tuple[str, str]:
    """Check 6: Version in registration matches pyproject.toml."""
    ip_path = claude_home / "plugins" / "installed_plugins.json"

    if not ip_path.is_file():
        return "SKIP", "installed_plugins.json not found -- cannot verify version"

    try:
        data = json.loads(ip_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "SKIP", "installed_plugins.json unreadable -- cannot verify version"

    plugin_key = "obsidian-connector@local"
    plugins = data.get("plugins", {})

    if plugin_key not in plugins:
        return "SKIP", f"'{plugin_key}' not registered -- cannot verify version"

    entry = plugins[plugin_key]
    if isinstance(entry, list) and entry:
        registered_version = entry[0].get("version")
    elif isinstance(entry, dict):
        registered_version = entry.get("version")
    else:
        return "SKIP", "Unexpected entry format"

    if registered_version == version:
        return "PASS", f"Version match: registered={registered_version}, pyproject={version}"
    else:
        return "FAIL", f"Version mismatch: registered={registered_version}, pyproject={version}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_checks(claude_home: Path, install_dir: Path) -> list[tuple[str, str, str]]:
    """Run all checks and return list of (name, status, message)."""
    version = get_pyproject_version(install_dir)
    if version is None:
        return [("pyproject.toml", "FAIL", f"Could not extract version from {install_dir / 'pyproject.toml'}")]

    results: list[tuple[str, str, str]] = []

    results.append(("Plugin cache", *check_plugin_cache(claude_home, version)))
    results.append(("installed_plugins.json", *check_installed_plugins(claude_home, version)))
    results.append(("settings.json", *check_settings(claude_home)))
    results.append(("Claude Desktop config", *check_desktop_config()))
    results.append(("MCP server import", *check_mcp_import(install_dir)))
    results.append(("Version match", *check_version_match(claude_home, version)))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate obsidian-connector post-install state",
    )
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=Path.home() / ".claude",
        help="Path to Claude home directory (default: ~/.claude)",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Path to obsidian-connector repo root (default: parent of scripts/)",
    )
    args = parser.parse_args()

    claude_home = args.claude_home.resolve()
    install_dir = args.install_dir.resolve()

    version = get_pyproject_version(install_dir)

    print("obsidian-connector Installer Smoke Test")
    print("=" * 42)
    print(f"  Claude home:  {claude_home}")
    print(f"  Install dir:  {install_dir}")
    print(f"  Version:      {version or '(not found)'}")
    print(f"  Platform:     {platform.system()} {platform.machine()}")
    print()

    results = run_checks(claude_home, install_dir)

    fail_count = 0
    pass_count = 0
    skip_count = 0

    for name, status, message in results:
        tag = status.ljust(4)
        print(f"  [{tag}] {name}")
        print(f"         {message}")
        if status == "FAIL":
            fail_count += 1
        elif status == "PASS":
            pass_count += 1
        else:
            skip_count += 1

    print()
    print(f"Results: {pass_count} passed, {fail_count} failed, {skip_count} skipped")

    if fail_count > 0:
        print("STATUS: FAIL")
        return 1
    else:
        print("STATUS: PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())
