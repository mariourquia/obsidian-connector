from __future__ import annotations

import builtins
import importlib
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _reload_cli():
    sys.modules.pop("obsidian_connector.ui_dashboard", None)
    sys.modules.pop("obsidian_connector.cli", None)
    return importlib.import_module("obsidian_connector.cli")


def _missing_textual(*_args, **_kwargs):
    raise ModuleNotFoundError("No module named 'textual'", name="textual")


def _install_textual_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyWidget:
        def __init__(self, *args, **kwargs):
            self.id = kwargs.get("id")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add_option(self, *args, **kwargs):
            return None

        def update(self, *args, **kwargs):
            return None

    class DummyApp:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return None

        def push_screen(self, *args, **kwargs):
            return None

        def exit(self):
            return None

    class DummyScreen(DummyWidget):
        def query_one(self, *args, **kwargs):
            return DummyWidget()

        def set_timer(self, *args, **kwargs):
            return None

    class DummyBinding:
        def __init__(self, *args, **kwargs):
            pass

    class DummyButton(DummyWidget):
        class Pressed:
            pass

    class DummyOption:
        def __init__(self, *args, **kwargs):
            self.id = kwargs.get("id")

    class DummyOptionList(DummyWidget):
        class OptionSelected:
            def __init__(self, option=None):
                self.option = option

    textual = ModuleType("textual")
    textual.on = lambda *args, **kwargs: (lambda fn: fn)

    textual_app = ModuleType("textual.app")
    textual_app.App = DummyApp
    textual_app.ComposeResult = object

    textual_binding = ModuleType("textual.binding")
    textual_binding.Binding = DummyBinding

    textual_containers = ModuleType("textual.containers")
    textual_containers.Container = DummyWidget
    textual_containers.Horizontal = DummyWidget
    textual_containers.Vertical = DummyWidget
    textual_containers.VerticalScroll = DummyWidget

    textual_screen = ModuleType("textual.screen")
    textual_screen.Screen = DummyScreen

    textual_widgets = ModuleType("textual.widgets")
    textual_widgets.Button = DummyButton
    textual_widgets.Footer = DummyWidget
    textual_widgets.Header = DummyWidget
    textual_widgets.Label = DummyWidget
    textual_widgets.ListItem = DummyWidget
    textual_widgets.ListView = DummyWidget
    textual_widgets.OptionList = DummyOptionList
    textual_widgets.Static = DummyWidget

    textual_widgets_option_list = ModuleType("textual.widgets.option_list")
    textual_widgets_option_list.Option = DummyOption

    for name, module in {
        "textual": textual,
        "textual.app": textual_app,
        "textual.binding": textual_binding,
        "textual.containers": textual_containers,
        "textual.screen": textual_screen,
        "textual.widgets": textual_widgets,
        "textual.widgets.option_list": textual_widgets_option_list,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_cli_import_and_parser_do_not_require_textual(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "textual" or name.startswith("textual."):
            raise AssertionError("cli import should not require textual")
        if name == "obsidian_connector.ui_dashboard":
            raise AssertionError("cli import should not require ui_dashboard")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    cli = _reload_cli()

    with pytest.raises(SystemExit) as exc_info:
        cli.build_parser().parse_args(["--help"])

    assert exc_info.value.code == 0


def test_main_without_command_works_without_textual_when_not_first_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _reload_cli()

    monkeypatch.setattr(cli, "is_first_run", lambda: False)
    monkeypatch.setattr(cli.importlib, "import_module", _missing_textual)

    exit_code = cli.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage:" in captured.out.lower()
    assert "obsidian_connector.ui_dashboard" not in sys.modules


def test_menu_command_without_textual_fails_gracefully(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _reload_cli()

    monkeypatch.setattr(cli.importlib, "import_module", _missing_textual)

    exit_code = cli.main(["menu"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "interactive dashboard requires the optional Textual dependency" in captured.err
    assert "obsidian-connector[tui]" in captured.err
    assert "pip install -e '.[tui]'" in captured.err


def test_first_run_without_textual_fails_gracefully(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _reload_cli()

    monkeypatch.setattr(cli, "is_first_run", lambda: True)
    monkeypatch.setattr(cli.importlib, "import_module", _missing_textual)

    exit_code = cli.main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "interactive setup wizard requires the optional Textual dependency" in captured.err
    assert "obsidian-connector[tui]" in captured.err


def test_menu_command_imports_and_runs_dashboard_with_textual_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_textual_stubs(monkeypatch)
    cli = _reload_cli()

    ui_dashboard = importlib.import_module("obsidian_connector.ui_dashboard")
    ran: list[str] = []
    monkeypatch.setattr(ui_dashboard.DashboardApp, "run", lambda self: ran.append("menu"))

    exit_code = cli.main(["menu"])

    assert exit_code == 0
    assert ran == ["menu"]


def test_first_run_marker_is_ui_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import obsidian_connector.startup as startup

    marker = tmp_path / ".setup-complete"
    monkeypatch.setattr(startup, "_WIZARD_MARKER", marker)

    sys.modules.pop("obsidian_connector.ui_dashboard", None)

    assert startup.is_first_run() is True

    startup.mark_wizard_completed()

    assert marker.read_text(encoding="utf-8") == "1"
    assert startup.is_first_run() is False
    assert "obsidian_connector.ui_dashboard" not in sys.modules


def test_tui_dependency_is_optional_and_install_surfaces_include_it() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert not any(dep.startswith("textual") for dep in project["dependencies"])
    assert any(
        dep.startswith("textual")
        for dep in project["optional-dependencies"]["tui"]
    )

    install_surfaces = {
        "scripts/install.sh": "[tui]",
        "scripts/setup.sh": "[tui]",
        "scripts/install-linux.sh": "textual>=1.0.0",
        "Install.command": ".[tui]",
        "scripts/Install.ps1": "[tui]",
    }

    for rel_path, expected in install_surfaces.items():
        content = (ROOT / rel_path).read_text(encoding="utf-8")
        assert expected in content, f"{rel_path} should include {expected!r}"
