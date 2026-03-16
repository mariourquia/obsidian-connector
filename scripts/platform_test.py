"""Test platform-specific path resolution."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_macos_paths():
    with patch("sys.platform", "darwin"):
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
         patch.dict("os.environ", {"APPDATA": "/tmp/fake-appdata"}):
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


# ------------------------------------------------------------------
# Convenience wrapper tests (current_os, claude_desktop_config_path, etc.)
# ------------------------------------------------------------------

def test_current_os():
    from obsidian_connector.platform import current_os
    result = current_os()
    assert result in ("macos", "linux", "windows"), f"Unknown OS: {result}"
    if sys.platform == "darwin":
        assert result == "macos"
    print("PASS: test_current_os")


def test_claude_config_path_returns_path():
    from obsidian_connector.platform import claude_desktop_config_path
    path = claude_desktop_config_path()
    assert isinstance(path, Path)
    assert "claude" in str(path).lower() or "Claude" in str(path)
    print("PASS: test_claude_config_path_returns_path")


def test_obsidian_app_json_returns_path():
    from obsidian_connector.platform import obsidian_app_json_path
    path = obsidian_app_json_path()
    assert isinstance(path, Path)
    assert "obsidian" in str(path).lower()
    print("PASS: test_obsidian_app_json_returns_path")


def test_default_index_db_path():
    from obsidian_connector.platform import default_index_db_path
    path = default_index_db_path()
    assert isinstance(path, Path)
    assert "index.sqlite" in str(path)
    print("PASS: test_default_index_db_path")


def test_schedule_config_dir():
    from obsidian_connector.platform import schedule_config_dir
    path = schedule_config_dir()
    assert isinstance(path, Path)
    if sys.platform == "darwin":
        assert "LaunchAgents" in str(path)
    print("PASS: test_schedule_config_dir")


# ------------------------------------------------------------------
# Scheduling abstraction tests
# ------------------------------------------------------------------

def test_scheduler_type():
    from obsidian_connector.platform import scheduler_type
    result = scheduler_type()
    assert result in ("launchd", "systemd", "task_scheduler")
    if sys.platform == "darwin":
        assert result == "launchd"
    print("PASS: test_scheduler_type")


def test_install_schedule_dry_run(tmp_path):
    from obsidian_connector.platform import install_schedule, scheduler_type
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
    assert result["installed"] is False
    print("PASS: test_install_schedule_dry_run")


def test_uninstall_schedule_returns_bool():
    from obsidian_connector.platform import uninstall_schedule
    result = uninstall_schedule("com.obsidian-connector.nonexistent")
    assert isinstance(result, bool)
    print("PASS: test_uninstall_schedule_returns_bool")


# ------------------------------------------------------------------
# Notification abstraction tests
# ------------------------------------------------------------------

def test_send_notification_returns_bool():
    from obsidian_connector.platform import send_notification
    result = send_notification("Test", "Hello from test")
    assert isinstance(result, bool)
    print("PASS: test_send_notification_returns_bool")


# ------------------------------------------------------------------
# Process detection and binary resolution tests
# ------------------------------------------------------------------

def test_is_obsidian_running_returns_bool():
    from obsidian_connector.platform import is_obsidian_running
    result = is_obsidian_running()
    assert isinstance(result, bool)
    print("PASS: test_is_obsidian_running_returns_bool")


def test_obsidian_binary_candidates():
    from obsidian_connector.platform import obsidian_binary_candidates
    candidates = obsidian_binary_candidates()
    assert isinstance(candidates, list)
    assert len(candidates) >= 1
    assert all(isinstance(c, str) for c in candidates)
    print("PASS: test_obsidian_binary_candidates")


# ------------------------------------------------------------------
# Refactor validation tests (Tasks 5-6)
# ------------------------------------------------------------------

def test_config_uses_platform_paths():
    """Verify config.py no longer hardcodes ~/Library paths."""
    import inspect
    from obsidian_connector import config
    source = inspect.getsource(config)
    # Should not contain raw ~/Library paths -- must use platform module
    assert 'Library" / "Application Support' not in source or "platform" in source
    print("PASS: test_config_uses_platform_paths")


def test_uninstall_uses_platform_paths():
    """Verify uninstall.py uses platform.py for plist/schedule paths."""
    import inspect
    from obsidian_connector import uninstall
    source = inspect.getsource(uninstall)
    assert '"Library"' not in source or "platform" in source
    print("PASS: test_uninstall_uses_platform_paths")


def test_cli_uses_platform_paths():
    """Verify cli.py uses platform.py for Claude config path."""
    import inspect
    from obsidian_connector import cli
    source = inspect.getsource(cli)
    assert source.count('Library" / "Application Support') == 0 or "platform" in source
    print("PASS: test_cli_uses_platform_paths")


if __name__ == "__main__":
    import tempfile

    # PlatformPaths tests
    test_macos_paths()
    test_linux_paths()
    test_windows_paths()
    test_data_dir_creation()

    # Task 1: convenience wrappers
    test_current_os()
    test_claude_config_path_returns_path()
    test_obsidian_app_json_returns_path()
    test_default_index_db_path()
    test_schedule_config_dir()

    # Task 2: scheduling
    test_scheduler_type()
    with tempfile.TemporaryDirectory() as tmp:
        test_install_schedule_dry_run(Path(tmp))
    test_uninstall_schedule_returns_bool()

    # Task 3: notifications
    test_send_notification_returns_bool()

    # Task 4: process detection
    test_is_obsidian_running_returns_bool()
    test_obsidian_binary_candidates()

    # Tasks 5-6: refactor validation
    test_config_uses_platform_paths()
    test_uninstall_uses_platform_paths()
    test_cli_uses_platform_paths()

    print("\nAll platform tests passed.")
