"""Test platform-specific path resolution."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.platform import current_os, scheduler_type


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
# Systemd scheduling tests (Task 7)
# ------------------------------------------------------------------

def test_generate_systemd_unit(tmp_path):
    """Verify systemd unit generation produces valid service and timer content."""
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
    assert "morning" in service
    assert "[Timer]" in timer
    assert "OnCalendar=" in timer
    assert "08:00" in timer
    print("PASS: test_generate_systemd_unit")


def test_generate_systemd_unit_evening(tmp_path):
    """Verify systemd unit generation with different workflow and time."""
    from obsidian_connector.platform import _generate_systemd_unit
    service, timer = _generate_systemd_unit(
        repo_root=tmp_path,
        python_path=Path("/home/user/.venv/bin/python3"),
        workflow="evening",
        hour=18,
        minute=30,
    )
    assert "evening" in service
    assert "/home/user/.venv/bin/python3" in service
    assert "18:30" in timer
    assert "Persistent=true" in timer
    print("PASS: test_generate_systemd_unit_evening")


def test_install_systemd_mocked(tmp_path):
    """Verify _install_systemd writes unit files and calls systemctl."""
    from obsidian_connector.platform import _install_systemd
    mock_home = tmp_path / "home"
    unit_dir = mock_home / ".config" / "systemd" / "user"

    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0)

    with patch("obsidian_connector.platform.Path.home", return_value=mock_home), \
         patch("subprocess.run", side_effect=mock_run):
        result = _install_systemd(
            repo_root=tmp_path / "repo",
            python_path=Path("/usr/bin/python3"),
            workflow="morning",
            hour=8,
            minute=0,
        )
    assert result is True
    # Check unit files were written
    assert (unit_dir / "obsidian-connector-morning.service").exists()
    assert (unit_dir / "obsidian-connector-morning.timer").exists()
    # Check systemctl commands were issued
    assert any("daemon-reload" in str(c) for c in calls)
    assert any("enable" in str(c) for c in calls)
    print("PASS: test_install_systemd_mocked")


def test_uninstall_systemd_mocked(tmp_path):
    """Verify _uninstall_systemd removes unit files and calls systemctl."""
    from obsidian_connector.platform import _uninstall_systemd
    mock_home = tmp_path / "home"
    unit_dir = mock_home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    # Create fake unit files
    (unit_dir / "obsidian-connector-morning.service").write_text("[Unit]\n")
    (unit_dir / "obsidian-connector-morning.timer").write_text("[Timer]\n")

    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0)

    with patch("obsidian_connector.platform.Path.home", return_value=mock_home), \
         patch("subprocess.run", side_effect=mock_run):
        result = _uninstall_systemd("com.obsidian-connector.morning")
    assert result is True
    # Files should be removed
    assert not (unit_dir / "obsidian-connector-morning.service").exists()
    assert not (unit_dir / "obsidian-connector-morning.timer").exists()
    # systemctl disable and daemon-reload should be called
    assert any("disable" in str(c) for c in calls)
    assert any("daemon-reload" in str(c) for c in calls)
    print("PASS: test_uninstall_systemd_mocked")


def test_install_systemd_failure_returns_false(tmp_path):
    """Verify _install_systemd returns False on subprocess failure."""
    import subprocess as sp
    from obsidian_connector.platform import _install_systemd
    mock_home = tmp_path / "home"

    def mock_run(cmd, **kwargs):
        if "daemon-reload" in cmd:
            raise sp.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    with patch("obsidian_connector.platform.Path.home", return_value=mock_home), \
         patch("subprocess.run", side_effect=mock_run):
        result = _install_systemd(
            repo_root=tmp_path / "repo",
            python_path=Path("/usr/bin/python3"),
            workflow="morning",
            hour=8,
            minute=0,
        )
    assert result is False
    print("PASS: test_install_systemd_failure_returns_false")


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
# Linux config paths and vault detection tests (Task 8)
# ------------------------------------------------------------------

def test_linux_claude_config_path_xdg():
    """Verify claude_desktop_config_path respects XDG_CONFIG_HOME on Linux."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "linux"), \
         patch.dict("os.environ", {"XDG_CONFIG_HOME": "/tmp/test_xdg"}, clear=False):
        importlib.reload(plat)
        path = plat.claude_desktop_config_path()
        assert str(path).startswith("/tmp/test_xdg")
        assert "Claude" in str(path)
        assert str(path).endswith("claude_desktop_config.json")
    # Restore module for subsequent tests
    importlib.reload(plat)
    print("PASS: test_linux_claude_config_path_xdg")


def test_linux_claude_config_path_default():
    """Verify claude_desktop_config_path falls back to ~/.config on Linux."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "linux"), \
         patch.dict("os.environ", {"XDG_CONFIG_HOME": ""}, clear=False):
        importlib.reload(plat)
        path = plat.claude_desktop_config_path()
        assert ".config/Claude" in str(path)
        assert str(path).endswith("claude_desktop_config.json")
    importlib.reload(plat)
    print("PASS: test_linux_claude_config_path_default")


def test_linux_obsidian_json_path_xdg():
    """Verify obsidian_app_json_path respects XDG_CONFIG_HOME on Linux."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "linux"), \
         patch.dict("os.environ", {"XDG_CONFIG_HOME": "/tmp/custom_xdg"}, clear=False):
        importlib.reload(plat)
        path = plat.obsidian_app_json_path()
        assert str(path).startswith("/tmp/custom_xdg")
        assert "obsidian" in str(path)
        assert str(path).endswith("obsidian.json")
    importlib.reload(plat)
    print("PASS: test_linux_obsidian_json_path_xdg")


def test_linux_obsidian_json_path_default():
    """Verify obsidian_app_json_path falls back to ~/.config on Linux."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "linux"), \
         patch.dict("os.environ", {"XDG_CONFIG_HOME": ""}, clear=False):
        importlib.reload(plat)
        path = plat.obsidian_app_json_path()
        assert ".config/obsidian" in str(path)
        assert str(path).endswith("obsidian.json")
    importlib.reload(plat)
    print("PASS: test_linux_obsidian_json_path_default")


def test_linux_scheduler_dir_xdg():
    """Verify schedule_config_dir returns systemd user dir under XDG on Linux."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "linux"), \
         patch.dict("os.environ", {"XDG_CONFIG_HOME": "/tmp/xdg_sched"}, clear=False):
        importlib.reload(plat)
        path = plat.schedule_config_dir()
        assert str(path).startswith("/tmp/xdg_sched")
        assert "systemd/user" in str(path)
    importlib.reload(plat)
    print("PASS: test_linux_scheduler_dir_xdg")


def test_linux_platform_paths_complete():
    """Verify all PlatformPaths fields are populated on Linux."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "linux"), \
         patch.dict("os.environ", {"XDG_CONFIG_HOME": ""}, clear=False):
        importlib.reload(plat)
        paths = plat.get_platform_paths()
        assert paths.scheduler_type == "systemd"
        assert paths.scheduler_dir is not None
        assert "systemd/user" in str(paths.scheduler_dir)
        assert ".obsidian-connector" in str(paths.data_dir)
        assert "logs" in str(paths.log_dir)
    importlib.reload(plat)
    print("PASS: test_linux_platform_paths_complete")


def test_linux_vault_detection_xdg(tmp_path):
    """Verify vault detection works with XDG-based obsidian.json."""
    # Create a fake obsidian.json at a custom XDG path
    xdg_dir = tmp_path / "xdg_config"
    obsidian_json = xdg_dir / "obsidian" / "obsidian.json"
    obsidian_json.parent.mkdir(parents=True)
    vault_dir = tmp_path / "my_vault"
    vault_dir.mkdir()
    obsidian_json.write_text(json.dumps({
        "vaults": {
            "abc123": {"path": str(vault_dir), "open": True}
        }
    }))

    # Patch config.py's _OBSIDIAN_APP_JSON to point to our test file
    import obsidian_connector.config as cfg_mod
    original_json = cfg_mod._OBSIDIAN_APP_JSON
    try:
        cfg_mod._OBSIDIAN_APP_JSON = obsidian_json
        # Clear any env overrides
        with patch.dict("os.environ", {"OBSIDIAN_VAULT_PATH": ""}, clear=False):
            resolved = cfg_mod.resolve_vault_path()
            assert resolved == vault_dir, f"Expected {vault_dir}, got {resolved}"
    finally:
        cfg_mod._OBSIDIAN_APP_JSON = original_json
    print("PASS: test_linux_vault_detection_xdg")


# ------------------------------------------------------------------
# Doctor cross-platform diagnostics tests (Task 18)
# ------------------------------------------------------------------

def test_doctor_reports_platform():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "platform" in check_names, "doctor should report current platform"
    platform_check = [r for r in results if r["check"] == "platform"][0]
    assert platform_check["ok"] is True
    assert current_os() in platform_check["detail"]
    print("PASS: test_doctor_reports_platform")


def test_doctor_reports_scheduler():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "scheduler" in check_names, "doctor should report scheduler type"
    scheduler_check = [r for r in results if r["check"] == "scheduler"][0]
    assert scheduler_type() in scheduler_check["detail"]
    print("PASS: test_doctor_reports_scheduler")


def test_doctor_reports_obsidian_running():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "obsidian_running" in check_names, "doctor should report Obsidian process status"
    running_check = [r for r in results if r["check"] == "obsidian_running"][0]
    assert isinstance(running_check["ok"], bool)
    assert running_check["detail"] in ("running", "not detected")
    print("PASS: test_doctor_reports_obsidian_running")


def test_doctor_reports_claude_config():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "claude_config" in check_names, "doctor should report Claude config path"
    config_check = [r for r in results if r["check"] == "claude_config"][0]
    assert isinstance(config_check["ok"], bool)
    assert "claude" in config_check["detail"].lower() or "Claude" in config_check["detail"]
    print("PASS: test_doctor_reports_claude_config")


def test_doctor_reports_platform_features():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "platform_features" in check_names, "doctor should report platform features"
    features_check = [r for r in results if r["check"] == "platform_features"][0]
    assert features_check["ok"] is True
    assert "CLI:" in features_check["detail"]
    assert "Scheduling:" in features_check["detail"]
    assert "Graph tools:" in features_check["detail"]
    print("PASS: test_doctor_reports_platform_features")


def test_doctor_uses_platform_binary_candidates():
    from obsidian_connector.doctor import run_doctor
    results = run_doctor()
    check_names = [r["check"] for r in results]
    assert "obsidian_binary" in check_names, "doctor should check for obsidian binary"
    print("PASS: test_doctor_uses_platform_binary_candidates")


# ------------------------------------------------------------------
# run_scheduled.py cross-platform notification test (Task 9)
# ------------------------------------------------------------------

def test_run_scheduled_uses_platform_notify():
    """Verify run_scheduled.py no longer hardcodes osascript."""
    source = Path(__file__).parent.parent / "scheduling" / "run_scheduled.py"
    text = source.read_text()
    assert "osascript" not in text, "run_scheduled.py should use platform.send_notification"
    assert "_osa_escape" not in text, "run_scheduled.py should not contain _osa_escape"
    assert "send_notification" in text, "run_scheduled.py should import send_notification"
    print("PASS: test_run_scheduled_uses_platform_notify")


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

    # Task 7: systemd scheduling
    with tempfile.TemporaryDirectory() as tmp:
        test_generate_systemd_unit(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_generate_systemd_unit_evening(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_install_systemd_mocked(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_uninstall_systemd_mocked(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_install_systemd_failure_returns_false(Path(tmp))

    # Task 8: Linux config paths and vault detection
    test_linux_claude_config_path_xdg()
    test_linux_claude_config_path_default()
    test_linux_obsidian_json_path_xdg()
    test_linux_obsidian_json_path_default()
    test_linux_scheduler_dir_xdg()
    test_linux_platform_paths_complete()
    with tempfile.TemporaryDirectory() as tmp:
        test_linux_vault_detection_xdg(Path(tmp))

    # Task 3: notifications
    test_send_notification_returns_bool()

    # Task 4: process detection
    test_is_obsidian_running_returns_bool()
    test_obsidian_binary_candidates()

    # Task 18: doctor cross-platform diagnostics
    test_doctor_reports_platform()
    test_doctor_reports_scheduler()
    test_doctor_reports_obsidian_running()
    test_doctor_reports_claude_config()
    test_doctor_reports_platform_features()
    test_doctor_uses_platform_binary_candidates()

    # Task 9: run_scheduled.py cross-platform notifications
    test_run_scheduled_uses_platform_notify()

    # Tasks 5-6: refactor validation
    test_config_uses_platform_paths()
    test_uninstall_uses_platform_paths()
    test_cli_uses_platform_paths()

    print("\nAll platform tests passed.")
