import json
from pathlib import Path
from obsidian_connector.uninstall import UninstallPlan

def test_uninstall_plan_creation():
    plan = UninstallPlan(
        venv_path=Path(".venv"),
        files_to_remove=[],
        config_changes={},
        plist_path=None,
        remove_plist=False,
        remove_venv=False,
        remove_skills=False,
        remove_hook=False,
        remove_logs=False,
        remove_cache=False,
        dry_run=False
    )
    assert plan.venv_path == Path(".venv")
    assert plan.files_to_remove == []
    assert plan.config_changes == {}

if __name__ == "__main__":
    test_uninstall_plan_creation()
    print("PASS")
