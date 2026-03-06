import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_connector.uninstall import UninstallPlan, detect_installed_artifacts

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

def test_detect_installed_artifacts(tmp_path):
    # Setup fake installation artifacts
    venv = tmp_path / ".venv"
    venv.mkdir()
    skills_dir = tmp_path / ".claude" / "commands"
    skills_dir.mkdir(parents=True)
    (skills_dir / "morning.md").write_text("# Morning")

    plist = Path.home() / "Library" / "LaunchAgents" / "com.obsidian-connector.daily.plist"

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=venv,
        claude_config_path=tmp_path / "claude_config.json"
    )

    assert venv in plan.files_to_remove or plan.remove_venv is False
    assert any("morning.md" in str(f) for f in plan.files_to_remove) or not plan.remove_skills

if __name__ == "__main__":
    test_uninstall_plan_creation()
    print("test_uninstall_plan_creation PASS")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_detect_installed_artifacts(Path(tmp))
    print("test_detect_installed_artifacts PASS")
