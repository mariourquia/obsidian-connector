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


if __name__ == "__main__":
    test_macos_paths()
    test_linux_paths()
    test_windows_paths()
    test_data_dir_creation()
    print("\nAll platform tests passed.")
