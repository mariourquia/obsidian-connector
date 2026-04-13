"""Interactive terminal dashboard and setup wizard for obsidian-connector.

Provides a lightweight, zero-dependency interactive menu for vault
configuration, system health checks, and first-run onboarding.
Uses only the Python standard library -- no ``rich``, ``curses``, or
``prompt_toolkit`` required.

All user data stays local.  This module never makes network calls.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI helpers (works on macOS/Linux terminals and Windows 10+ Terminal)
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

# Disable colors if NO_COLOR is set or output is not a TTY.
if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    BOLD = DIM = RESET = GREEN = YELLOW = RED = CYAN = MAGENTA = BLUE = ""


def _hr(char: str = "─", width: int = 56) -> str:
    return DIM + char * width + RESET


def _header(text: str) -> str:
    return f"\n{BOLD}{CYAN}{'─' * 4} {text} {'─' * (50 - len(text))}{RESET}\n"


def _prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{BOLD}{text}{suffix}:{RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return answer or default


def _pick(prompt_text: str, options: list[str], default_idx: int = 0) -> int:
    """Present a numbered list and return the chosen index."""
    print(f"\n{BOLD}{prompt_text}{RESET}")
    for i, opt in enumerate(options):
        marker = f"{GREEN}→{RESET}" if i == default_idx else " "
        print(f"  {marker} {BOLD}{i + 1}{RESET}. {opt}")
    while True:
        raw = _prompt("Enter number", str(default_idx + 1))
        try:
            choice = int(raw) - 1
            if 0 <= choice < len(options):
                return choice
        except ValueError:
            pass
        print(f"  {RED}Invalid choice, try again.{RESET}")


def _confirm(text: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = _prompt(f"{text} [{hint}]")
    if not raw:
        return default
    return raw.lower() in ("y", "yes")


# ---------------------------------------------------------------------------
# Vault discovery (reads Obsidian's own registry)
# ---------------------------------------------------------------------------

def _discover_obsidian_vaults() -> list[dict]:
    """Read Obsidian's obsidian.json to find all registered vaults."""
    from obsidian_connector.platform import obsidian_app_json_path

    config_path = obsidian_app_json_path()
    if not config_path.is_file():
        return []

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    results = []
    for vid, vinfo in data.get("vaults", {}).items():
        vpath = Path(vinfo.get("path", ""))
        results.append({
            "name": vpath.name,
            "path": str(vpath),
            "id": vid,
            "exists": vpath.is_dir(),
        })
    return results


# ---------------------------------------------------------------------------
# Setup Wizard  (first-run onboarding)
# ---------------------------------------------------------------------------

def run_wizard() -> int:
    """Interactive first-run setup wizard.

    Auto-discovers Obsidian vaults, lets the user pick a default,
    and optionally installs the Claude Desktop MCP integration.

    Returns 0 on success.
    """
    print(_header("obsidian-connector Setup Wizard"))
    print(f"  Welcome! Let's get your environment configured.\n")
    print(f"  {DIM}All data stays on your machine. No accounts or sign-ups.{RESET}\n")

    # --- Step 1: Discover vaults -------------------------------------------
    print(f"  {CYAN}Step 1/3:{RESET} Detecting your Obsidian vaults...")
    vaults = _discover_obsidian_vaults()

    from obsidian_connector.vault_registry import VaultRegistry
    registry = VaultRegistry()

    if not vaults:
        print(f"\n  {YELLOW}⚠  No Obsidian vaults found on this system.{RESET}")
        print(f"  {DIM}You can register one manually later with:{RESET}")
        print(f"    obsx register-vault --name MyVault --path /path/to/vault\n")
    else:
        existing_vaults = [v for v in vaults if v["exists"]]
        print(f"\n  {GREEN}✓{RESET} Found {len(existing_vaults)} vault(s):\n")
        for i, v in enumerate(existing_vaults):
            print(f"    {BOLD}{i + 1}{RESET}. {v['name']}")
            print(f"       {DIM}{v['path']}{RESET}")

        if existing_vaults:
            default_idx = _pick(
                "Which vault should be your default?",
                [v["name"] for v in existing_vaults],
                default_idx=0,
            )
            chosen = existing_vaults[default_idx]

            # Register all discovered vaults, mark chosen as default
            for i, v in enumerate(existing_vaults):
                try:
                    registry.register(
                        name=v["name"],
                        path=v["path"],
                        is_default=(i == default_idx),
                    )
                except ValueError:
                    # Already registered -- just set default if needed
                    if i == default_idx:
                        try:
                            registry.set_default(v["name"])
                        except Exception:
                            pass

            print(f"\n  {GREEN}✓{RESET} Default vault set to: {BOLD}{chosen['name']}{RESET}")

    # --- Step 2: Claude Desktop integration --------------------------------
    print(f"\n  {CYAN}Step 2/3:{RESET} Claude Desktop Integration")

    has_claude = _detect_claude_desktop()
    if has_claude:
        print(f"  {GREEN}✓{RESET} Claude Desktop detected on this system.")
        if _confirm("  Install MCP server integration now?", default=True):
            _install_claude_mcp()
        else:
            print(f"  {DIM}Skipped. You can install later with: obsx install{RESET}")
    else:
        print(f"  {DIM}Claude Desktop not detected. Skipping MCP integration.{RESET}")
        print(f"  {DIM}You can install it later with: obsx install{RESET}")

    # --- Step 3: Summary ---------------------------------------------------
    print(_header("Setup Complete"))
    print(f"  Your obsidian-connector is ready to use!\n")
    print(f"  {BOLD}Quick start:{RESET}")
    print(f"    obsx today          → See your daily status")
    print(f"    obsx search <term>  → Search your vault")
    print(f"    obsx menu           → Open this configuration menu\n")
    print(f"  {DIM}For full docs: https://github.com/mariourquia/obsidian-connector{RESET}\n")

    # Mark wizard as completed
    _mark_wizard_completed()

    return 0


# ---------------------------------------------------------------------------
# Interactive Menu  (`obsx menu`)
# ---------------------------------------------------------------------------

def run_menu() -> int:
    """Interactive configuration dashboard.

    Returns 0 on exit.
    """
    while True:
        print(_header("obsidian-connector Dashboard"))

        from obsidian_connector.vault_registry import VaultRegistry
        registry = VaultRegistry()
        all_vaults = registry.list_vaults()
        default_vault = registry.get_default()

        # Current state header
        if default_vault:
            print(f"  Active vault: {GREEN}{BOLD}{default_vault.name}{RESET}")
            print(f"  Path:         {DIM}{default_vault.path}{RESET}")
            print(f"  Profile:      {default_vault.profile}")
        else:
            print(f"  Active vault: {YELLOW}(none set){RESET}")

        # Health check
        issues = registry.doctor()
        if issues:
            print(f"\n  {RED}⚠ Health issues:{RESET}")
            for issue in issues:
                print(f"    {RED}•{RESET} {issue}")
        else:
            vault_count = len(all_vaults)
            print(f"  Registered:   {vault_count} vault(s) — {GREEN}all healthy{RESET}")

        # Telemetry stats
        _show_telemetry_summary()

        print(f"\n{_hr()}")

        options = [
            f"{CYAN}Switch default vault{RESET}",
            f"{CYAN}Register a new vault{RESET}",
            f"{CYAN}Remove a registered vault{RESET}",
            f"{CYAN}View all vaults{RESET}",
            f"{CYAN}Manage Claude Desktop integration{RESET}",
            f"{CYAN}View telemetry stats{RESET}",
            f"{CYAN}Run health check (doctor){RESET}",
            f"{RED}Exit{RESET}",
        ]

        choice = _pick("What would you like to do?", options)

        if choice == 0:
            _menu_switch_vault(registry)
        elif choice == 1:
            _menu_register_vault(registry)
        elif choice == 2:
            _menu_remove_vault(registry)
        elif choice == 3:
            _menu_list_vaults(registry)
        elif choice == 4:
            _menu_claude_integration()
        elif choice == 5:
            _menu_telemetry_detail()
        elif choice == 6:
            _menu_doctor(registry)
        elif choice == 7:
            print(f"\n  {DIM}Goodbye!{RESET}\n")
            return 0


# ---------------------------------------------------------------------------
# Menu action handlers
# ---------------------------------------------------------------------------

def _menu_switch_vault(registry) -> None:
    vaults = registry.list_vaults()
    if not vaults:
        print(f"\n  {YELLOW}No vaults registered. Register one first.{RESET}")
        return

    names = [
        f"{v.name} {GREEN}(current default){RESET}" if v.is_default else v.name
        for v in vaults
    ]
    idx = _pick("Select a vault to make default:", names)
    chosen = vaults[idx]
    registry.set_default(chosen.name)
    print(f"\n  {GREEN}✓{RESET} Default vault changed to: {BOLD}{chosen.name}{RESET}")


def _menu_register_vault(registry) -> None:
    print(_header("Register a New Vault"))

    # Offer discovered but unregistered vaults first
    discovered = _discover_obsidian_vaults()
    registered_paths = {v.path for v in registry.list_vaults()}
    unregistered = [v for v in discovered if v["path"] not in registered_paths and v["exists"]]

    if unregistered:
        print(f"  Found {len(unregistered)} unregistered Obsidian vault(s):\n")
        options = [f"{v['name']} — {DIM}{v['path']}{RESET}" for v in unregistered]
        options.append(f"{MAGENTA}Enter a custom path instead{RESET}")
        idx = _pick("Pick a vault to register:", options)

        if idx < len(unregistered):
            chosen = unregistered[idx]
            name = _prompt("Vault name", chosen["name"])
            profile = _prompt("Profile (personal/work/research/creative)", "personal")
            try:
                registry.register(
                    name=name, path=chosen["path"], profile=profile,
                    is_default=not registry.list_vaults(),
                )
                print(f"\n  {GREEN}✓{RESET} Registered: {BOLD}{name}{RESET}")
            except (ValueError, FileNotFoundError) as e:
                print(f"\n  {RED}✗ {e}{RESET}")
            return

    # Manual path entry
    path = _prompt("Vault path")
    if not path:
        return
    name = _prompt("Vault name", Path(path).name)
    profile = _prompt("Profile (personal/work/research/creative)", "personal")
    try:
        registry.register(
            name=name, path=path, profile=profile,
            is_default=not registry.list_vaults(),
        )
        print(f"\n  {GREEN}✓{RESET} Registered: {BOLD}{name}{RESET}")
    except (ValueError, FileNotFoundError) as e:
        print(f"\n  {RED}✗ {e}{RESET}")


def _menu_remove_vault(registry) -> None:
    vaults = registry.list_vaults()
    if not vaults:
        print(f"\n  {YELLOW}No vaults registered.{RESET}")
        return

    names = [f"{v.name} — {DIM}{v.path}{RESET}" for v in vaults]
    idx = _pick("Select a vault to unregister:", names)
    chosen = vaults[idx]

    if _confirm(f"  Remove '{chosen.name}' from registry? (vault files are NOT deleted)"):
        registry.unregister(chosen.name)
        print(f"\n  {GREEN}✓{RESET} Unregistered: {chosen.name}")
        print(f"  {DIM}Your vault files at {chosen.path} are untouched.{RESET}")
    else:
        print(f"  {DIM}Cancelled.{RESET}")


def _menu_list_vaults(registry) -> None:
    vaults = registry.list_vaults()
    if not vaults:
        print(f"\n  {YELLOW}No vaults registered.{RESET}")
        return

    print(_header("Registered Vaults"))
    for v in vaults:
        default_tag = f" {GREEN}← default{RESET}" if v.is_default else ""
        exists = Path(v.path).is_dir()
        health = f"{GREEN}✓{RESET}" if exists else f"{RED}✗ missing{RESET}"
        print(f"  {health} {BOLD}{v.name}{RESET}{default_tag}")
        print(f"    Path:    {DIM}{v.path}{RESET}")
        print(f"    Profile: {v.profile}")
        if v.policies:
            print(f"    Policies: {json.dumps(v.policies)}")
        print()


def _menu_claude_integration() -> None:
    print(_header("Claude Desktop Integration"))

    has_claude = _detect_claude_desktop()
    if not has_claude:
        print(f"  {YELLOW}Claude Desktop not detected on this system.{RESET}")
        print(f"  {DIM}Download it from: https://claude.ai/download{RESET}\n")
        return

    is_installed = _check_claude_mcp_installed()

    if is_installed:
        print(f"  {GREEN}✓{RESET} MCP server is currently {GREEN}installed{RESET} in Claude Desktop.\n")
        options = [
            "Reinstall / update MCP config",
            "Remove MCP integration",
            "Back",
        ]
        choice = _pick("Action:", options)
        if choice == 0:
            _install_claude_mcp()
        elif choice == 1:
            _uninstall_claude_mcp()
    else:
        print(f"  {YELLOW}⚠{RESET} MCP server is {YELLOW}not installed{RESET} in Claude Desktop.\n")
        if _confirm("  Install now?", default=True):
            _install_claude_mcp()


def _menu_telemetry_detail() -> None:
    print(_header("Telemetry Stats (Local Only)"))
    from obsidian_connector.telemetry import TelemetryCollector
    collector = TelemetryCollector()
    weekly = collector.weekly_summary()

    if weekly["sessions"] == 0:
        print(f"  {DIM}No telemetry data recorded yet.{RESET}\n")
        return

    print(f"  {BOLD}Last 7 days:{RESET}")
    print(f"    Sessions:         {weekly['sessions']}")
    print(f"    Notes read:       {weekly['notes_read']}")
    print(f"    Notes written:    {weekly['notes_written']}")
    print(f"    Retrieval misses: {weekly['retrieval_misses']}")
    print(f"    Errors:           {weekly['errors']}")

    if weekly["tools_called"]:
        print(f"\n  {BOLD}Top tools (by invocation):{RESET}")
        sorted_tools = sorted(
            weekly["tools_called"].items(), key=lambda x: x[1], reverse=True,
        )
        for name, count in sorted_tools[:10]:
            bar = "█" * min(count, 30)
            print(f"    {name:30s} {DIM}{bar}{RESET} {count}")

    print()


def _menu_doctor(registry) -> None:
    print(_header("Health Check"))

    issues = registry.doctor()
    if not issues:
        print(f"  {GREEN}✓ All registered vaults are healthy.{RESET}\n")
    else:
        print(f"  {RED}Found {len(issues)} issue(s):{RESET}\n")
        for issue in issues:
            print(f"  {RED}✗{RESET} {issue}")
        print()

    # Check Obsidian running
    from obsidian_connector.platform import is_obsidian_running
    if is_obsidian_running():
        print(f"  {GREEN}✓{RESET} Obsidian desktop app is running.")
    else:
        print(f"  {YELLOW}⚠{RESET} Obsidian desktop app is not running.")

    # Check Claude Desktop
    if _detect_claude_desktop():
        print(f"  {GREEN}✓{RESET} Claude Desktop detected.")
        if _check_claude_mcp_installed():
            print(f"  {GREEN}✓{RESET} MCP server integration installed.")
        else:
            print(f"  {YELLOW}⚠{RESET} MCP server integration not installed.")
    else:
        print(f"  {DIM}─{RESET} Claude Desktop not detected.")

    # Check Node.js (for Ix engine)
    if shutil.which("node"):
        print(f"  {GREEN}✓{RESET} Node.js available (required for Ix engine).")
    else:
        print(f"  {YELLOW}⚠{RESET} Node.js not found (Ix engine will be unavailable).")

    print()


# ---------------------------------------------------------------------------
# Helper: telemetry summary (inline in dashboard header)
# ---------------------------------------------------------------------------

def _show_telemetry_summary() -> None:
    try:
        from obsidian_connector.telemetry import TelemetryCollector
        collector = TelemetryCollector()
        weekly = collector.weekly_summary()
        if weekly["sessions"] > 0:
            print(
                f"  This week:    {weekly['notes_read']} reads, "
                f"{weekly['notes_written']} writes, "
                f"{weekly['sessions']} sessions"
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helper: Claude Desktop detection and MCP wiring
# ---------------------------------------------------------------------------

def _detect_claude_desktop() -> bool:
    """Check if Claude Desktop config directory exists."""
    from obsidian_connector.platform import get_platform_paths
    paths = get_platform_paths()
    return paths.claude_config_dir.is_dir()


def _check_claude_mcp_installed() -> bool:
    """Check if obsidian-connector is already in Claude's MCP config."""
    from obsidian_connector.platform import claude_desktop_config_path
    config_path = claude_desktop_config_path()
    if not config_path.is_file():
        return False
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        return "obsidian-connector" in servers
    except (json.JSONDecodeError, OSError):
        return False


def _install_claude_mcp() -> None:
    """Add obsidian-connector to Claude Desktop's MCP config."""
    from obsidian_connector.platform import claude_desktop_config_path

    config_path = claude_desktop_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.is_file():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    servers = data.setdefault("mcpServers", {})

    python_path = sys.executable
    module_path = Path(__file__).resolve().parent / "mcp_server.py"

    servers["obsidian-connector"] = {
        "command": python_path,
        "args": [str(module_path)],
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\n  {GREEN}✓{RESET} MCP server installed in Claude Desktop config.")
    print(f"    {DIM}Config: {config_path}{RESET}")
    print(f"    {DIM}Please restart Claude Desktop for changes to take effect.{RESET}\n")


def _uninstall_claude_mcp() -> None:
    """Remove obsidian-connector from Claude Desktop's MCP config."""
    from obsidian_connector.platform import claude_desktop_config_path

    config_path = claude_desktop_config_path()
    if not config_path.is_file():
        print(f"  {YELLOW}No Claude config file found.{RESET}")
        return

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"  {RED}Could not parse Claude config.{RESET}")
        return

    servers = data.get("mcpServers", {})
    if "obsidian-connector" not in servers:
        print(f"  {YELLOW}obsidian-connector is not in Claude config.{RESET}")
        return

    if _confirm("  Remove obsidian-connector from Claude Desktop?", default=False):
        del servers["obsidian-connector"]
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"\n  {GREEN}✓{RESET} Removed from Claude Desktop config.")
        print(f"  {DIM}Restart Claude Desktop for changes to take effect.{RESET}\n")


# ---------------------------------------------------------------------------
# First-run detection
# ---------------------------------------------------------------------------

_WIZARD_MARKER = Path.home() / ".config" / "obsidian-connector" / ".setup-complete"


def _mark_wizard_completed() -> None:
    _WIZARD_MARKER.parent.mkdir(parents=True, exist_ok=True)
    _WIZARD_MARKER.write_text("1", encoding="utf-8")


def is_first_run() -> bool:
    """Return True if the setup wizard has never been completed."""
    return not _WIZARD_MARKER.is_file()
