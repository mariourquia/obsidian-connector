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
