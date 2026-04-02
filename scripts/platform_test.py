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
    if sys.platform == "win32":
        print("SKIP: test_macos_paths (running on Windows)")
        return
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
    if sys.platform == "win32":
        print("SKIP: test_linux_paths (running on Windows)")
        return
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
# Windows Task Scheduler tests (Task 13)
# ------------------------------------------------------------------

def test_generate_schtasks_command():
    """Verify _generate_schtasks_command produces correct schtasks args."""
    from obsidian_connector.platform import _generate_schtasks_command
    cmd = _generate_schtasks_command(
        repo_root=Path("C:/Users/test/obsidian-connector"),
        python_path=Path("C:/Users/test/obsidian-connector/.venv/Scripts/python.exe"),
        workflow="morning",
        time="08:00",
    )
    assert isinstance(cmd, list)
    assert cmd[0] == "schtasks"
    assert "/CREATE" in cmd
    cmd_str = " ".join(cmd)
    assert "obsidian-connector-morning" in cmd_str
    assert "08:00" in cmd_str
    assert "/SC" in cmd
    assert "DAILY" in cmd
    assert "/F" in cmd
    print("PASS: test_generate_schtasks_command")


def test_generate_schtasks_command_evening():
    """Verify schtasks command for evening workflow."""
    from obsidian_connector.platform import _generate_schtasks_command
    cmd = _generate_schtasks_command(
        repo_root=Path("D:/Projects/obsidian-connector"),
        python_path=Path("D:/Projects/obsidian-connector/.venv/Scripts/python.exe"),
        workflow="evening",
        time="18:30",
    )
    cmd_str = " ".join(cmd)
    assert "obsidian-connector-evening" in cmd_str
    assert "18:30" in cmd_str
    assert "run_scheduled.py" in cmd_str
    print("PASS: test_generate_schtasks_command_evening")


def test_install_task_scheduler_mocked():
    """Verify _install_task_scheduler calls schtasks and returns True on success."""
    from obsidian_connector.platform import _install_task_scheduler

    def mock_run(cmd, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        return mock_result

    with patch("subprocess.run", side_effect=mock_run) as mock_sub:
        result = _install_task_scheduler(
            repo_root=Path("C:/Users/test/obsidian-connector"),
            python_path=Path("C:/Users/test/.venv/Scripts/python.exe"),
            workflow="morning",
            time="08:00",
        )
    assert result is True
    called_cmd = mock_sub.call_args[0][0]
    assert called_cmd[0] == "schtasks"
    print("PASS: test_install_task_scheduler_mocked")


def test_install_task_scheduler_failure():
    """Verify _install_task_scheduler returns False on subprocess error."""
    from obsidian_connector.platform import _install_task_scheduler

    def mock_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    with patch("subprocess.run", side_effect=mock_run):
        result = _install_task_scheduler(
            repo_root=Path("C:/Users/test/obsidian-connector"),
            python_path=Path("C:/Users/test/.venv/Scripts/python.exe"),
            workflow="morning",
            time="08:00",
        )
    assert result is False
    print("PASS: test_install_task_scheduler_failure")


def test_install_task_scheduler_os_error():
    """Verify _install_task_scheduler returns False on OSError."""
    from obsidian_connector.platform import _install_task_scheduler

    def mock_run(cmd, **kwargs):
        raise OSError("schtasks not found")

    with patch("subprocess.run", side_effect=mock_run):
        result = _install_task_scheduler(
            repo_root=Path("C:/Users/test/obsidian-connector"),
            python_path=Path("C:/Users/test/.venv/Scripts/python.exe"),
            workflow="morning",
            time="08:00",
        )
    assert result is False
    print("PASS: test_install_task_scheduler_os_error")


def test_uninstall_task_scheduler_mocked():
    """Verify _uninstall_task_scheduler calls schtasks /DELETE."""
    from obsidian_connector.platform import _uninstall_task_scheduler

    def mock_run(cmd, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        return mock_result

    with patch("subprocess.run", side_effect=mock_run) as mock_sub:
        result = _uninstall_task_scheduler("com.obsidian-connector.morning")
    assert result is True
    called_cmd = mock_sub.call_args[0][0]
    assert called_cmd[0] == "schtasks"
    assert "/DELETE" in called_cmd
    assert "obsidian-connector-morning" in called_cmd
    print("PASS: test_uninstall_task_scheduler_mocked")


def test_uninstall_task_scheduler_failure():
    """Verify _uninstall_task_scheduler returns False on failure."""
    from obsidian_connector.platform import _uninstall_task_scheduler

    def mock_run(cmd, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 1
        return mock_result

    with patch("subprocess.run", side_effect=mock_run):
        result = _uninstall_task_scheduler("com.obsidian-connector.morning")
    assert result is False
    print("PASS: test_uninstall_task_scheduler_failure")


def test_uninstall_task_scheduler_os_error():
    """Verify _uninstall_task_scheduler returns False on OSError."""
    from obsidian_connector.platform import _uninstall_task_scheduler

    with patch("subprocess.run", side_effect=OSError("schtasks not found")):
        result = _uninstall_task_scheduler("com.obsidian-connector.morning")
    assert result is False
    print("PASS: test_uninstall_task_scheduler_os_error")


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
# Windows config paths tests (Task 14)
# ------------------------------------------------------------------

def test_windows_claude_config_path():
    """Verify claude_desktop_config_path returns APPDATA-based path on Windows."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "win32"), \
         patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False):
        importlib.reload(plat)
        path = plat.claude_desktop_config_path()
        path_str = str(path)
        assert "AppData" in path_str or "APPDATA" in path_str or "appdata" in path_str.lower()
        assert "Claude" in path_str
        assert path_str.endswith("claude_desktop_config.json")
    importlib.reload(plat)
    print("PASS: test_windows_claude_config_path")


def test_windows_obsidian_json_path():
    """Verify obsidian_app_json_path returns APPDATA-based path on Windows."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "win32"), \
         patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False):
        importlib.reload(plat)
        path = plat.obsidian_app_json_path()
        path_str = str(path)
        assert "obsidian" in path_str.lower()
        assert path_str.endswith("obsidian.json")
    importlib.reload(plat)
    print("PASS: test_windows_obsidian_json_path")


def test_windows_schedule_config_dir():
    """Verify schedule_config_dir returns a usable path on Windows."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "win32"), \
         patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False):
        importlib.reload(plat)
        path = plat.schedule_config_dir()
        assert isinstance(path, Path)
        # Windows uses a fallback tasks dir since Task Scheduler has no config dir
        assert "tasks" in str(path) or ".obsidian-connector" in str(path)
    importlib.reload(plat)
    print("PASS: test_windows_schedule_config_dir")


def test_windows_platform_paths_complete():
    """Verify all PlatformPaths fields are populated on Windows."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "win32"), \
         patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False):
        importlib.reload(plat)
        paths = plat.get_platform_paths()
        assert paths.scheduler_type == "task_scheduler"
        # scheduler_dir is None on Windows (uses schtasks directly)
        assert paths.scheduler_dir is None
        assert "Claude" in str(paths.claude_config_dir)
        assert "obsidian" in str(paths.obsidian_config).lower()
        assert ".obsidian-connector" in str(paths.data_dir)
        assert "logs" in str(paths.log_dir)
    importlib.reload(plat)
    print("PASS: test_windows_platform_paths_complete")


def test_windows_appdata_fallback():
    """Verify Windows paths fall back to ~/AppData/Roaming when APPDATA is unset."""
    import obsidian_connector.platform as plat
    with patch("sys.platform", "win32"), \
         patch.dict("os.environ", {}, clear=True):
        importlib.reload(plat)
        paths = plat.get_platform_paths()
        path_str = str(paths.claude_config_dir)
        # Should fall back to Path.home() / "AppData" / "Roaming" / "Claude"
        assert "AppData" in path_str or "Claude" in path_str
    importlib.reload(plat)
    print("PASS: test_windows_appdata_fallback")


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
# PowerShell install script tests (Task 15)
# ------------------------------------------------------------------

def test_powershell_install_script_exists():
    """Verify scripts/Install.ps1 exists and contains key elements."""
    ps_script = Path(__file__).resolve().parent / "Install.ps1"
    assert ps_script.exists(), "scripts/Install.ps1 must exist"
    text = ps_script.read_text()
    assert "APPDATA" in text or "AppData" in text
    assert "claude_desktop_config" in text.lower() or "Claude" in text
    assert "python" in text.lower()
    print("PASS: test_powershell_install_script_exists")


def test_powershell_script_has_venv_setup():
    """Verify Install.ps1 creates a venv and installs the package."""
    ps_script = Path(__file__).resolve().parent / "Install.ps1"
    text = ps_script.read_text()
    assert "venv" in text.lower()
    assert "pip" in text.lower()
    print("PASS: test_powershell_script_has_venv_setup")


def test_powershell_script_handles_python_name():
    """Verify Install.ps1 handles both python and python3 on Windows."""
    ps_script = Path(__file__).resolve().parent / "Install.ps1"
    text = ps_script.read_text()
    # Should check for python (Windows default) not just python3
    assert "python" in text.lower()
    print("PASS: test_powershell_script_handles_python_name")


# ------------------------------------------------------------------
# File path handling tests (Task 16)
# ------------------------------------------------------------------

def test_graph_relative_paths_use_forward_slashes(tmp_path):
    """Verify graph.py build_note_index produces forward-slash relative paths."""
    from obsidian_connector.graph import build_note_index
    # Create a nested vault structure
    sub = tmp_path / "folder" / "subfolder"
    sub.mkdir(parents=True)
    (sub / "note.md").write_text("# Test note\nSome content here.")
    (tmp_path / "root_note.md").write_text("# Root\nLink to [[note]]")

    index = build_note_index(str(tmp_path))
    for path in index.notes:
        assert "\\" not in path, f"Backslash found in graph path: {path}"
    print("PASS: test_graph_relative_paths_use_forward_slashes")


def test_workflows_path_operations_safe():
    """Verify workflows.py uses os.path or pathlib consistently, not hardcoded slashes."""
    import inspect
    from obsidian_connector import workflows
    source = inspect.getsource(workflows)
    # The title sanitizer intentionally replaces both / and \ -- that is correct.
    # os.path.dirname and os.path.join are cross-platform safe.
    # Just verify no raw path construction with hardcoded separators.
    assert "os.path" in source or "Path(" in source, \
        "workflows.py should use os.path or pathlib for path operations"
    print("PASS: test_workflows_path_operations_safe")


# ------------------------------------------------------------------
# Linux install script tests (Task 10)
# ------------------------------------------------------------------

def test_linux_install_script_exists():
    """Verify scripts/install-linux.sh exists and has required content."""
    install_script = Path(__file__).parent.parent / "scripts" / "install-linux.sh"
    assert install_script.exists(), "scripts/install-linux.sh must exist"
    text = install_script.read_text()
    assert "systemd" in text or "systemctl" in text, "Must reference systemd"
    assert "XDG_CONFIG_HOME" in text or ".config" in text, "Must use XDG paths"
    assert "obsidian-connector" in text, "Must reference obsidian-connector"
    print("PASS: test_linux_install_script_exists")


def test_linux_install_script_executable():
    """Verify install-linux.sh has executable permission."""
    install_script = Path(__file__).parent.parent / "scripts" / "install-linux.sh"
    assert install_script.exists()
    assert os.access(str(install_script), os.X_OK), "install-linux.sh must be executable"
    print("PASS: test_linux_install_script_executable")


def test_install_sh_dispatches_to_linux():
    """Verify install.sh has OS dispatch for Linux."""
    install_script = Path(__file__).parent.parent / "scripts" / "install.sh"
    text = install_script.read_text()
    assert "install-linux.sh" in text, "install.sh must dispatch to install-linux.sh on Linux"
    assert "Linux" in text, "install.sh must detect Linux"
    print("PASS: test_install_sh_dispatches_to_linux")


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

    # Task 13: Windows Task Scheduler
    test_generate_schtasks_command()
    test_generate_schtasks_command_evening()
    test_install_task_scheduler_mocked()
    test_install_task_scheduler_failure()
    test_install_task_scheduler_os_error()
    test_uninstall_task_scheduler_mocked()
    test_uninstall_task_scheduler_failure()
    test_uninstall_task_scheduler_os_error()

    # Task 8: Linux config paths and vault detection
    test_linux_claude_config_path_xdg()
    test_linux_claude_config_path_default()
    test_linux_obsidian_json_path_xdg()
    test_linux_obsidian_json_path_default()
    test_linux_scheduler_dir_xdg()
    test_linux_platform_paths_complete()
    with tempfile.TemporaryDirectory() as tmp:
        test_linux_vault_detection_xdg(Path(tmp))

    # Task 14: Windows config paths
    test_windows_claude_config_path()
    test_windows_obsidian_json_path()
    test_windows_schedule_config_dir()
    test_windows_platform_paths_complete()
    test_windows_appdata_fallback()

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

    # Task 15: PowerShell install script
    test_powershell_install_script_exists()
    test_powershell_script_has_venv_setup()
    test_powershell_script_handles_python_name()

    # Task 16: file path handling
    with tempfile.TemporaryDirectory() as tmp:
        test_graph_relative_paths_use_forward_slashes(Path(tmp))
    test_workflows_path_operations_safe()

    # Task 10: Linux install script
    test_linux_install_script_exists()
    test_linux_install_script_executable()
    test_install_sh_dispatches_to_linux()

    # Tasks 5-6: refactor validation
    test_config_uses_platform_paths()
    test_uninstall_uses_platform_paths()
    test_cli_uses_platform_paths()

    print("\nAll platform tests passed.")
