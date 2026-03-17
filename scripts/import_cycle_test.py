"""Verify no circular import issues in the package."""

import importlib
import sys


def test_clean_import_errors():
    """errors.py should import without triggering client.py side effects."""
    mods_to_remove = [k for k in sys.modules if k.startswith("obsidian_connector")]
    for m in mods_to_remove:
        del sys.modules[m]

    from obsidian_connector.errors import (
        ObsidianCLIError,
        ObsidianNotFound,
        ObsidianNotRunning,
        VaultNotFound,
        CommandTimeout,
        MalformedCLIOutput,
    )
    assert issubclass(ObsidianNotFound, ObsidianCLIError)
    assert issubclass(ObsidianNotRunning, ObsidianCLIError)
    print("PASS: test_clean_import_errors")


def test_clean_import_client():
    """client.py should import cleanly after errors.py."""
    mods_to_remove = [k for k in sys.modules if k.startswith("obsidian_connector")]
    for m in mods_to_remove:
        del sys.modules[m]

    from obsidian_connector.client import ObsidianCLIError, run_obsidian
    from obsidian_connector.errors import ObsidianNotFound

    assert issubclass(ObsidianNotFound, ObsidianCLIError)
    print("PASS: test_clean_import_client")


def test_top_level_import():
    """Package-level import should work."""
    mods_to_remove = [k for k in sys.modules if k.startswith("obsidian_connector")]
    for m in mods_to_remove:
        del sys.modules[m]

    import obsidian_connector
    assert hasattr(obsidian_connector, "ObsidianCLIError")
    assert hasattr(obsidian_connector, "ObsidianNotFound")
    print("PASS: test_top_level_import")


if __name__ == "__main__":
    test_clean_import_errors()
    test_clean_import_client()
    test_top_level_import()
    print("\nAll import cycle tests passed.")
