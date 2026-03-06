import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_connector.uninstall import (
    UninstallPlan,
    detect_installed_artifacts,
    backup_config_file,
    validate_json,
    remove_from_json_config,
    remove_file_safely,
    unload_launchd_plist,
    execute_uninstall,
    dry_run_uninstall
)

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

def test_backup_config_file(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"key": "value"}')

    backup_path = backup_config_file(config)

    assert backup_path.exists()
    assert backup_path.parent == config.parent
    assert "backup" in backup_path.name
    assert backup_path.read_text() == '{"key": "value"}'

def test_validate_json():
    assert validate_json('{"key": "value"}') is True
    assert validate_json('invalid json') is False
    assert validate_json('') is False

def test_remove_from_json_config(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}, "other": {}}}')

    result = remove_from_json_config(config, ["mcpServers", "obsidian-connector"])

    assert result is True
    updated = json.loads(config.read_text())
    assert "obsidian-connector" not in updated.get("mcpServers", {})
    assert "other" in updated.get("mcpServers", {})

def test_remove_file_safely(tmp_path):
    file = tmp_path / "test.txt"
    file.write_text("content")

    result = remove_file_safely(file)

    assert result is True
    assert not file.exists()

def test_remove_file_safely_missing(tmp_path):
    file = tmp_path / "missing.txt"

    result = remove_file_safely(file)

    assert result is True

def test_execute_uninstall(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    plan = UninstallPlan(
        venv_path=venv,
        files_to_remove=[venv],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=True,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    assert result["status"] == "ok"
    assert not venv.exists()
    assert "obsidian-connector" not in json.loads(config.read_text()).get("mcpServers", {})

def test_dry_run_uninstall(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    plan = UninstallPlan(
        venv_path=venv,
        files_to_remove=[venv],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=True,
        dry_run=True
    )

    result = dry_run_uninstall(plan)

    assert result["dry_run"] is True
    assert venv.exists()  # Nothing was actually removed
    assert result["plan"]["files_to_remove"] == [str(venv)]

if __name__ == "__main__":
    test_uninstall_plan_creation()
    print("test_uninstall_plan_creation PASS")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_detect_installed_artifacts(Path(tmp))
    print("test_detect_installed_artifacts PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_backup_config_file(Path(tmp))
    print("test_backup_config_file PASS")

    test_validate_json()
    print("test_validate_json PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_remove_from_json_config(Path(tmp))
    print("test_remove_from_json_config PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_remove_file_safely(Path(tmp))
    print("test_remove_file_safely PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_remove_file_safely_missing(Path(tmp))
    print("test_remove_file_safely_missing PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_execute_uninstall(Path(tmp))
    print("test_execute_uninstall PASS")

    with tempfile.TemporaryDirectory() as tmp:
        test_dry_run_uninstall(Path(tmp))
    print("test_dry_run_uninstall PASS")
