import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_connector.platform import (
    current_os,
    claude_desktop_config_path,
    obsidian_app_json_path,
    default_index_db_path,
    schedule_config_dir,
    scheduler_type,
    install_schedule,
    uninstall_schedule,
)


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


def test_default_index_db_path():
    path = default_index_db_path()
    assert isinstance(path, Path)
    assert "index.sqlite" in str(path)


def test_schedule_config_dir():
    path = schedule_config_dir()
    assert isinstance(path, Path)
    if sys.platform == "darwin":
        assert "LaunchAgents" in str(path)


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
    assert result["installed"] is False


def test_uninstall_schedule_returns_bool():
    # Calling with a non-existent job should not crash
    result = uninstall_schedule("com.obsidian-connector.nonexistent")
    assert isinstance(result, bool)


if __name__ == "__main__":
    test_current_os()
    print("test_current_os PASS")

    test_claude_config_path_returns_path()
    print("test_claude_config_path_returns_path PASS")

    test_obsidian_app_json_returns_path()
    print("test_obsidian_app_json_returns_path PASS")

    test_default_index_db_path()
    print("test_default_index_db_path PASS")

    test_schedule_config_dir()
    print("test_schedule_config_dir PASS")

    test_scheduler_type()
    print("test_scheduler_type PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_install_schedule_dry_run(Path(tmp))
    print("test_install_schedule_dry_run PASS")

    test_uninstall_schedule_returns_bool()
    print("test_uninstall_schedule_returns_bool PASS")
