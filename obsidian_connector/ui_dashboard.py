"""Interactive TUI dashboard and setup wizard for obsidian-connector.

Uses the ``textual`` framework to provide a rich, interactive terminal
interface for vault configuration, system health checks, and first-run
onboarding.

All user data stays local.  This module never makes network calls.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option


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


def _get_registry():
    from obsidian_connector.vault_registry import VaultRegistry
    return VaultRegistry()


# ---------------------------------------------------------------------------
# Claude Desktop helpers
# ---------------------------------------------------------------------------

def _detect_claude_desktop() -> bool:
    from obsidian_connector.platform import get_platform_paths
    return get_platform_paths().claude_config_dir.is_dir()


def _check_claude_mcp_installed() -> bool:
    from obsidian_connector.platform import claude_desktop_config_path
    config_path = claude_desktop_config_path()
    if not config_path.is_file():
        return False
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        return "obsidian-connector" in data.get("mcpServers", {})
    except (json.JSONDecodeError, OSError):
        return False


def _install_claude_mcp() -> str:
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
    module_path = Path(__file__).resolve().parent / "mcp_server.py"
    servers["obsidian-connector"] = {
        "command": sys.executable,
        "args": [str(module_path)],
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return f"✓ Installed. Config: {config_path}\nRestart Claude Desktop for changes to take effect."


def _uninstall_claude_mcp() -> str:
    from obsidian_connector.platform import claude_desktop_config_path
    config_path = claude_desktop_config_path()
    if not config_path.is_file():
        return "No Claude config file found."
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return "Could not parse Claude config."

    servers = data.get("mcpServers", {})
    if "obsidian-connector" not in servers:
        return "obsidian-connector is not in Claude config."

    del servers["obsidian-connector"]
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return "✓ Removed. Restart Claude Desktop for changes to take effect."


# ---------------------------------------------------------------------------
# Telemetry helpers
# ---------------------------------------------------------------------------

def _get_weekly_stats() -> dict:
    try:
        from obsidian_connector.telemetry import TelemetryCollector
        return TelemetryCollector().weekly_summary()
    except Exception:
        return {"sessions": 0, "notes_read": 0, "notes_written": 0,
                "retrieval_misses": 0, "errors": 0, "tools_called": {}}


# ---------------------------------------------------------------------------
# Health check helper
# ---------------------------------------------------------------------------

def _run_health_check() -> list[str]:
    lines = []
    registry = _get_registry()
    issues = registry.doctor()
    if not issues:
        lines.append("✅ All registered vaults are healthy.")
    else:
        for issue in issues:
            lines.append(f"❌ {issue}")

    from obsidian_connector.platform import is_obsidian_running
    if is_obsidian_running():
        lines.append("✅ Obsidian desktop app is running.")
    else:
        lines.append("⚠️  Obsidian desktop app is not running.")

    if _detect_claude_desktop():
        lines.append("✅ Claude Desktop detected.")
        if _check_claude_mcp_installed():
            lines.append("✅ MCP server integration installed.")
        else:
            lines.append("⚠️  MCP server integration not installed.")
    else:
        lines.append("── Claude Desktop not detected.")

    if shutil.which("node"):
        lines.append("✅ Node.js available (Ix engine ready).")
    else:
        lines.append("⚠️  Node.js not found (Ix engine unavailable).")

    return lines


# ---------------------------------------------------------------------------
# CSS for the TUI
# ---------------------------------------------------------------------------

DASHBOARD_CSS = """
Screen {
    background: $surface;
}

#sidebar {
    width: 32;
    dock: left;
    background: $panel;
    border-right: thick $accent;
    padding: 1;
}

#sidebar-title {
    text-style: bold;
    color: $text;
    padding: 1 0;
    text-align: center;
}

#main-content {
    padding: 1 2;
}

.status-card {
    border: round $accent;
    padding: 1;
    margin: 0 0 1 0;
    background: $boost;
}

.status-label {
    text-style: bold;
    color: $accent;
}

.health-ok {
    color: $success;
}

.health-warn {
    color: $warning;
}

.health-error {
    color: $error;
}

.section-title {
    text-style: bold;
    color: $accent;
    padding: 1 0 0 0;
}

.detail-text {
    color: $text-muted;
    padding: 0 0 0 2;
}

#action-buttons {
    padding: 1 0;
    layout: horizontal;
    height: auto;
}

#action-buttons Button {
    margin: 0 1;
}

.result-text {
    padding: 1;
    border: round $accent;
    margin: 1 0;
}
"""


# ---------------------------------------------------------------------------
# Dashboard Screen
# ---------------------------------------------------------------------------

class DashboardScreen(Screen):
    """Main interactive dashboard for vault management."""

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("🔮 obsidian-connector", id="sidebar-title")
                yield OptionList(
                    Option("🏠 Dashboard", id="dashboard"),
                    Option("───────────────────", id="_sep1"),
                    Option("🔄 Switch Vault", id="switch_vault"),
                    Option("➕ Register Vault", id="register_vault"),
                    Option("🗑  Remove Vault", id="remove_vault"),
                    Option("📋 View All Vaults", id="list_vaults"),
                    Option("───────────────────", id="_sep2"),
                    Option("🤖 Claude Integration", id="claude"),
                    Option("📊 Telemetry Stats", id="telemetry"),
                    Option("🩺 Health Check", id="doctor"),
                    Option("───────────────────", id="_sep3"),
                    Option("🚪 Exit", id="exit"),
                    id="nav",
                )

            with VerticalScroll(id="main-content"):
                yield Static("", id="content-area")

        yield Footer()

    def on_mount(self) -> None:
        self._show_dashboard()

    @on(OptionList.OptionSelected, "#nav")
    def nav_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id == "dashboard":
            self._show_dashboard()
        elif option_id == "switch_vault":
            self._show_switch_vault()
        elif option_id == "register_vault":
            self._show_register_vault()
        elif option_id == "remove_vault":
            self._show_remove_vault()
        elif option_id == "list_vaults":
            self._show_list_vaults()
        elif option_id == "claude":
            self._show_claude()
        elif option_id == "telemetry":
            self._show_telemetry()
        elif option_id == "doctor":
            self._show_doctor()
        elif option_id == "exit":
            self.app.exit()

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_refresh(self) -> None:
        self._show_dashboard()

    # -- Views --------------------------------------------------------------

    def _set_content(self, text: str) -> None:
        self.query_one("#content-area", Static).update(text)

    def _show_dashboard(self) -> None:
        registry = _get_registry()
        default_vault = registry.get_default()
        all_vaults = registry.list_vaults()
        weekly = _get_weekly_stats()

        lines = ["[bold cyan]── Dashboard ──────────────────────────────[/]\n"]

        if default_vault:
            lines.append(f"[bold]Active vault:[/]  [green]{default_vault.name}[/]")
            lines.append(f"[dim]Path:[/]           {default_vault.path}")
            lines.append(f"[dim]Profile:[/]        {default_vault.profile}")
        else:
            lines.append("[yellow]Active vault:[/]  (none set)")

        issues = registry.doctor()
        if issues:
            lines.append(f"\n[red]⚠ {len(issues)} health issue(s)[/]")
        else:
            lines.append(f"\n[green]✓[/] {len(all_vaults)} vault(s) registered — all healthy")

        if weekly["sessions"] > 0:
            lines.append(
                f"\n[bold cyan]── This Week ──────────────────────────────[/]"
            )
            lines.append(f"  Sessions:       {weekly['sessions']}")
            lines.append(f"  Notes read:     {weekly['notes_read']}")
            lines.append(f"  Notes written:  {weekly['notes_written']}")
            lines.append(f"  Errors:         {weekly['errors']}")

        lines.append(
            "\n[dim]Use the sidebar to navigate. Press [bold]r[/bold] to refresh, "
            "[bold]q[/bold] to quit.[/]"
        )

        self._set_content("\n".join(lines))

    def _show_switch_vault(self) -> None:
        registry = _get_registry()
        vaults = registry.list_vaults()
        if not vaults:
            self._set_content("[yellow]No vaults registered. Register one first.[/]")
            return

        lines = ["[bold cyan]── Switch Default Vault ───────────────────[/]\n"]
        for i, v in enumerate(vaults):
            marker = " [green]← current[/]" if v.is_default else ""
            exists = "✓" if Path(v.path).is_dir() else "✗"
            lines.append(f"  [{i + 1}] {exists} [bold]{v.name}[/]{marker}")
            lines.append(f"      [dim]{v.path}[/]")

        lines.append(
            "\n[dim]To switch, run:[/] [bold]obsx set-default-vault <name>[/]"
        )
        self._set_content("\n".join(lines))

    def _show_register_vault(self) -> None:
        registry = _get_registry()
        discovered = _discover_obsidian_vaults()
        registered_paths = {v.path for v in registry.list_vaults()}
        unregistered = [
            v for v in discovered
            if v["path"] not in registered_paths and v["exists"]
        ]

        lines = ["[bold cyan]── Register a Vault ───────────────────────[/]\n"]

        if unregistered:
            lines.append(f"[green]Found {len(unregistered)} unregistered Obsidian vault(s):[/]\n")
            for i, v in enumerate(unregistered):
                lines.append(f"  [{i + 1}] [bold]{v['name']}[/]")
                lines.append(f"      [dim]{v['path']}[/]")
            lines.append(
                "\n[dim]Register with:[/] "
                "[bold]obsx register-vault --name <name> --path <path>[/]"
            )
        else:
            lines.append("[dim]All detected Obsidian vaults are already registered.[/]")
            lines.append(
                "\n[dim]Register manually:[/] "
                "[bold]obsx register-vault --name <name> --path <path>[/]"
            )

        self._set_content("\n".join(lines))

    def _show_remove_vault(self) -> None:
        registry = _get_registry()
        vaults = registry.list_vaults()
        if not vaults:
            self._set_content("[yellow]No vaults registered.[/]")
            return

        lines = ["[bold cyan]── Remove a Vault ─────────────────────────[/]\n"]
        for i, v in enumerate(vaults):
            lines.append(f"  [{i + 1}] [bold]{v.name}[/]")
            lines.append(f"      [dim]{v.path}[/]")

        lines.append(
            "\n[dim]Unregister with:[/] "
            "[bold]obsx unregister-vault <name>[/]"
        )
        lines.append("[dim]Note: vault files on disk are never deleted.[/]")
        self._set_content("\n".join(lines))

    def _show_list_vaults(self) -> None:
        registry = _get_registry()
        vaults = registry.list_vaults()
        if not vaults:
            self._set_content("[yellow]No vaults registered.[/]")
            return

        lines = ["[bold cyan]── All Registered Vaults ──────────────────[/]\n"]
        for v in vaults:
            default_tag = " [green]← default[/]" if v.is_default else ""
            exists = Path(v.path).is_dir()
            health = "[green]✓[/]" if exists else "[red]✗ missing[/]"
            lines.append(f"  {health} [bold]{v.name}[/]{default_tag}")
            lines.append(f"    Path:    [dim]{v.path}[/]")
            lines.append(f"    Profile: {v.profile}")
            if v.policies:
                lines.append(f"    Policies: {json.dumps(v.policies)}")
            lines.append("")

        self._set_content("\n".join(lines))

    def _show_claude(self) -> None:
        lines = ["[bold cyan]── Claude Desktop Integration ─────────────[/]\n"]

        if not _detect_claude_desktop():
            lines.append("[yellow]Claude Desktop not detected on this system.[/]")
            lines.append("[dim]Download: https://claude.ai/download[/]")
        else:
            if _check_claude_mcp_installed():
                lines.append("[green]✓ MCP server is installed in Claude Desktop.[/]\n")
                lines.append("[dim]Actions:[/]")
                lines.append("  • [bold]obsx install[/]    — reinstall / update")
                lines.append("  • [bold]obsx uninstall[/]  — remove integration")
            else:
                lines.append("[yellow]⚠ MCP server is not installed.[/]\n")
                lines.append("[dim]Install with:[/] [bold]obsx install[/]")

        self._set_content("\n".join(lines))

    def _show_telemetry(self) -> None:
        weekly = _get_weekly_stats()
        lines = ["[bold cyan]── Telemetry Stats (Local Only) ───────────[/]\n"]

        if weekly["sessions"] == 0:
            lines.append("[dim]No telemetry data recorded yet.[/]")
        else:
            lines.append(f"[bold]Last 7 days:[/]")
            lines.append(f"  Sessions:         {weekly['sessions']}")
            lines.append(f"  Notes read:       {weekly['notes_read']}")
            lines.append(f"  Notes written:    {weekly['notes_written']}")
            lines.append(f"  Retrieval misses: {weekly['retrieval_misses']}")
            lines.append(f"  Errors:           {weekly['errors']}")

            if weekly.get("tools_called"):
                lines.append(f"\n[bold]Top tools:[/]")
                sorted_tools = sorted(
                    weekly["tools_called"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                for name, count in sorted_tools[:10]:
                    bar = "█" * min(count, 30)
                    lines.append(f"  {name:30s} [dim]{bar}[/] {count}")

        self._set_content("\n".join(lines))

    def _show_doctor(self) -> None:
        checks = _run_health_check()
        lines = ["[bold cyan]── Health Check ───────────────────────────[/]\n"]
        for check in checks:
            if check.startswith("✅"):
                lines.append(f"[green]{check}[/]")
            elif check.startswith("⚠"):
                lines.append(f"[yellow]{check}[/]")
            elif check.startswith("❌"):
                lines.append(f"[red]{check}[/]")
            else:
                lines.append(f"[dim]{check}[/]")

        self._set_content("\n".join(lines))


# ---------------------------------------------------------------------------
# Wizard Screens
# ---------------------------------------------------------------------------

class WizardVaultScreen(Screen):
    """Step 1: Discover and select vaults."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll():
            yield Static(
                "[bold cyan]── Step 1/3: Select Your Default Vault ────[/]\n\n"
                "[dim]All data stays on your machine. No accounts or sign-ups.[/]\n",
                id="wizard-header",
            )
            yield Static("", id="vault-list")
            yield OptionList(id="vault-picker")
            yield Static("", id="wizard-status")
        yield Footer()

    def on_mount(self) -> None:
        vaults = _discover_obsidian_vaults()
        existing = [v for v in vaults if v["exists"]]
        self._vaults = existing

        vault_list = self.query_one("#vault-list", Static)
        picker = self.query_one("#vault-picker", OptionList)

        if not existing:
            vault_list.update(
                "[yellow]⚠ No Obsidian vaults found.[/]\n"
                "[dim]You can register one later with: "
                "obsx register-vault --name X --path /path[/]"
            )
        else:
            vault_list.update(
                f"[green]✓[/] Found {len(existing)} vault(s):\n"
            )
            for v in existing:
                picker.add_option(
                    Option(f"{v['name']}  [dim]{v['path']}[/]", id=v["name"])
                )

    @on(OptionList.OptionSelected, "#vault-picker")
    def vault_selected(self, event: OptionList.OptionSelected) -> None:
        selected_name = event.option.id
        registry = _get_registry()

        # Register all discovered vaults, chosen one as default
        for v in self._vaults:
            try:
                registry.register(
                    name=v["name"],
                    path=v["path"],
                    is_default=(v["name"] == selected_name),
                )
            except ValueError:
                if v["name"] == selected_name:
                    try:
                        registry.set_default(v["name"])
                    except Exception:
                        pass

        status = self.query_one("#wizard-status", Static)
        status.update(f"\n[green]✓ Default vault set to: [bold]{selected_name}[/][/]")

        # Move to next step after a short delay
        self.set_timer(1.0, lambda: self.app.push_screen(WizardClaudeScreen()))


class WizardClaudeScreen(Screen):
    """Step 2: Claude Desktop integration."""

    BINDINGS = [
        Binding("y", "install", "Install"),
        Binding("n", "skip", "Skip"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll():
            yield Static(
                "[bold cyan]── Step 2/3: Claude Desktop Integration ───[/]\n",
                id="claude-header",
            )
            yield Static("", id="claude-status")
            with Horizontal(id="action-buttons"):
                yield Button("Install MCP", id="install-btn", variant="success")
                yield Button("Skip", id="skip-btn", variant="default")
            yield Static("", id="claude-result")
        yield Footer()

    def on_mount(self) -> None:
        status = self.query_one("#claude-status", Static)
        if _detect_claude_desktop():
            if _check_claude_mcp_installed():
                status.update("[green]✓ MCP server is already installed in Claude Desktop.[/]")
            else:
                status.update(
                    "[green]✓[/] Claude Desktop detected.\n\n"
                    "Would you like to install the MCP server integration?\n"
                    "This allows Claude to read and write to your Obsidian vault.\n"
                )
        else:
            status.update(
                "[dim]Claude Desktop not detected.\n"
                "You can install it later with: obsx install[/]"
            )

    @on(Button.Pressed, "#install-btn")
    def do_install(self) -> None:
        result = _install_claude_mcp()
        self.query_one("#claude-result", Static).update(f"\n[green]{result}[/]")
        self.set_timer(1.5, lambda: self.app.push_screen(WizardCompleteScreen()))

    @on(Button.Pressed, "#skip-btn")
    def do_skip(self) -> None:
        self.app.push_screen(WizardCompleteScreen())

    def action_install(self) -> None:
        self.do_install()

    def action_skip(self) -> None:
        self.do_skip()


class WizardCompleteScreen(Screen):
    """Step 3: Summary and completion."""

    BINDINGS = [
        Binding("enter", "finish", "Done"),
        Binding("q", "finish", "Done"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll():
            yield Static(
                "[bold cyan]── Setup Complete! ────────────────────────[/]\n\n"
                "[green]Your obsidian-connector is ready to use![/]\n\n"
                "[bold]Quick start:[/]\n"
                "  [bold]obsx today[/]          → See your daily status\n"
                "  [bold]obsx search <term>[/]  → Search your vault\n"
                "  [bold]obsx menu[/]           → Open this config dashboard\n"
                "  [bold]obsx ix map .[/]       → Map your codebase for AI\n\n"
                "[dim]For full docs: https://github.com/mariourquia/obsidian-connector[/]\n\n"
                "[dim]Press Enter or Q to exit.[/]",
            )
        yield Footer()

    def action_finish(self) -> None:
        _mark_wizard_completed()
        self.app.exit()


# ---------------------------------------------------------------------------
# App classes
# ---------------------------------------------------------------------------

class DashboardApp(App):
    """The main interactive dashboard application."""

    CSS = DASHBOARD_CSS
    TITLE = "obsidian-connector"
    SUB_TITLE = "Configuration Dashboard"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())


class WizardApp(App):
    """The first-run setup wizard application."""

    CSS = DASHBOARD_CSS
    TITLE = "obsidian-connector"
    SUB_TITLE = "Setup Wizard"

    def on_mount(self) -> None:
        self.push_screen(WizardVaultScreen())


# ---------------------------------------------------------------------------
# Public entry points (called from cli.py)
# ---------------------------------------------------------------------------

def run_menu() -> int:
    """Launch the interactive TUI dashboard. Returns 0."""
    app = DashboardApp()
    app.run()
    return 0


def run_wizard() -> int:
    """Launch the guided setup wizard. Returns 0."""
    app = WizardApp()
    app.run()
    return 0


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
