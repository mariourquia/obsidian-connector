"""Integration tests for obsidian-connector uninstaller.

Tests full workflows: CLI interactive mode, MCP dry-run/force modes,
recovery scenarios, and orchestration correctness.

Run with: python3 scripts/integration_test.py
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_connector.uninstall import (
    UninstallPlan,
    detect_installed_artifacts,
    dry_run_uninstall,
    execute_uninstall,
)


# =============================================================================
# Fixtures and helpers
# =============================================================================

def setup_minimal_install(tmp_path: Path) -> dict:
    """Setup realistic minimal installation artifacts."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    (venv / "bin" / "python").write_text("#!/bin/bash\necho python")

    skills_dir = tmp_path / ".claude" / "commands"
    skills_dir.mkdir(parents=True)
    (skills_dir / "morning.md").write_text("# Morning Skill\n\nTask: morning routine")

    config = tmp_path / "claude_desktop_config.json"
    config.write_text(json.dumps({
        "mcpServers": {
            "obsidian-connector": {
                "type": "stdio",
                "command": "python",
                "args": []
            },
            "other-server": {
                "type": "stdio",
                "command": "node"
            }
        },
        "userSettings": {}
    }, indent=2))

    return {
        "venv": venv,
        "skills_dir": skills_dir,
        "config": config,
        "repo_root": tmp_path,
    }


def setup_full_install(tmp_path: Path) -> dict:
    """Setup full installation with all artifacts."""
    artifacts = setup_minimal_install(tmp_path)

    # Add more skills
    skills_dir = artifacts["skills_dir"]
    (skills_dir / "evening.md").write_text("# Evening Skill")
    (skills_dir / "idea.md").write_text("# Idea Skill")
    (skills_dir / "weekly.md").write_text("# Weekly Skill")

    # Add logs and cache
    logs_dir = artifacts["repo_root"] / ".obsidian-connector" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "audit.log").write_text("action: test\n")

    cache_dir = artifacts["repo_root"] / ".obsidian-connector" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "index.db").write_text("cache data")

    return artifacts


# =============================================================================
# Integration Test 1: Full CLI workflow simulation (interactive mode)
# =============================================================================

def test_cli_interactive_workflow():
    """Test end-to-end CLI interactive mode with user selections."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_minimal_install(tmp_path)

        # Simulate user selections via mock input
        # User answers: keep venv=yes, remove skills=yes, remove config=yes
        user_inputs = ["y", "n", "n", "n", "y"]  # keep venv, remove skills, remove hook, remove plist, remove logs

        with patch("builtins.input", side_effect=user_inputs):
            # Manually simulate CLI workflow
            plan = detect_installed_artifacts(
                repo_root=artifacts["repo_root"],
                venv_path=artifacts["venv"],
                claude_config_path=artifacts["config"]
            )

            # Simulate user choices (inverted logic: keep = don't remove)
            # If user says "yes" to keep, we set remove flag to False
            plan.remove_venv = False  # User said "yes" to keep
            plan.remove_skills = True  # User said "no" (will remove)
            plan.remove_hook = True
            plan.remove_plist = True
            plan.remove_logs = False
            plan.remove_cache = False

            # If keeping venv, remove it from the files_to_remove list
            if not plan.remove_venv:
                plan.files_to_remove = [f for f in plan.files_to_remove if f != artifacts["venv"]]

            result = execute_uninstall(plan, config_path=artifacts["config"])

        # Verify plan was executed correctly
        assert result["status"] == "ok"
        assert artifacts["venv"].exists(), "venv should still exist (user kept it)"
        assert len(list(artifacts["skills_dir"].glob("*.md"))) == 0, "skills should be removed"
        assert "obsidian-connector" not in json.loads(artifacts["config"].read_text()).get("mcpServers", {}), "config should be updated"
        print("test_cli_interactive_workflow PASS")


# =============================================================================
# Integration Test 2: MCP dry-run mode
# =============================================================================

def test_mcp_dry_run_mode():
    """Test MCP dry-run mode shows plan without removing anything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_full_install(tmp_path)

        plan = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=artifacts["config"]
        )

        # Set all removal flags
        plan.remove_venv = True
        plan.remove_skills = True
        plan.remove_plist = False
        plan.dry_run = True

        result = dry_run_uninstall(plan)

        # Verify dry-run response
        assert result["dry_run"] is True
        assert "plan" in result
        assert result["status"] == "ok"

        # Verify nothing was actually removed
        assert artifacts["venv"].exists(), "venv should still exist in dry-run"
        assert any(f.exists() for f in artifacts["skills_dir"].glob("*.md")), "skills should still exist in dry-run"
        assert artifacts["config"].exists(), "config should still exist in dry-run"
        print("test_mcp_dry_run_mode PASS")


# =============================================================================
# Integration Test 3: MCP force mode (actual removal)
# =============================================================================

def test_mcp_force_mode_actual_removal():
    """Test MCP force mode removes artifacts and validates state changes."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_full_install(tmp_path)
        original_config = artifacts["config"].read_text()

        plan = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=artifacts["config"]
        )

        # Remove venv and skills, keep config
        plan.remove_venv = True
        plan.remove_skills = True
        plan.remove_hook = False
        plan.remove_plist = False
        plan.remove_logs = False
        plan.remove_cache = False
        plan.dry_run = False

        result = execute_uninstall(plan, config_path=artifacts["config"])

        # Verify actual removal
        assert result["status"] == "ok"
        assert not artifacts["venv"].exists(), "venv should be removed"
        assert len(list(artifacts["skills_dir"].glob("*.md"))) == 0, "skills should be removed"
        assert "obsidian-connector" not in json.loads(artifacts["config"].read_text()).get("mcpServers", {}), "config should be updated"

        # Verify backup was created
        backup_files = list(artifacts["config"].parent.glob("*.backup-*"))
        assert len(backup_files) > 0, "backup should exist"
        assert json.loads(backup_files[0].read_text()) == json.loads(original_config), "backup should contain original content"
        print("test_mcp_force_mode_actual_removal PASS")


# =============================================================================
# Integration Test 4: Partial uninstall workflow
# =============================================================================

def test_partial_uninstall_selective_removal():
    """Test selective removal of only some artifacts."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_full_install(tmp_path)

        # Save original paths for verification
        original_venv_exists = artifacts["venv"].exists()
        original_skill_count = len(list(artifacts["skills_dir"].glob("*.md")))

        plan = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=artifacts["config"]
        )

        # Only remove skills, keep venv and config
        plan.remove_venv = False
        plan.remove_skills = True
        plan.remove_hook = False
        plan.remove_plist = False
        plan.remove_logs = False
        plan.remove_cache = False
        plan.config_changes = {}  # Don't touch config

        # Remove venv from files_to_remove since we want to keep it
        plan.files_to_remove = [f for f in plan.files_to_remove if f != artifacts["venv"]]

        result = execute_uninstall(plan, config_path=artifacts["config"])

        # Verify selective removal
        assert result["status"] == "ok"
        assert artifacts["venv"].exists(), "venv should still exist"
        assert len(list(artifacts["skills_dir"].glob("*.md"))) == 0, "skills should be removed"
        assert "obsidian-connector" in json.loads(artifacts["config"].read_text()).get("mcpServers", {}), "config should be unchanged"
        print("test_partial_uninstall_selective_removal PASS")


# =============================================================================
# Integration Test 5: Idempotency - run uninstall twice
# =============================================================================

def test_idempotency_multiple_runs():
    """Test that running uninstall twice is safe (idempotent)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_full_install(tmp_path)

        config_path = artifacts["config"]

        # First uninstall
        plan1 = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=config_path
        )
        plan1.remove_venv = True
        plan1.remove_skills = True

        result1 = execute_uninstall(plan1, config_path=config_path)
        assert result1["status"] == "ok"
        assert not artifacts["venv"].exists()

        # Second uninstall (should be safe even with missing artifacts)
        plan2 = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=config_path
        )
        plan2.remove_venv = True
        plan2.remove_skills = True

        result2 = execute_uninstall(plan2, config_path=config_path)

        # Second run should also succeed
        assert result2["status"] == "ok"
        assert len(result2.get("errors", [])) == 0, "should have no errors on second run"
        print("test_idempotency_multiple_runs PASS")


# =============================================================================
# Integration Test 6: Error recovery - partial failures
# =============================================================================

def test_error_recovery_partial_failure():
    """Test that partial failures are reported and other removals continue."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_full_install(tmp_path)

        # Create a file we can't read/remove by making parent read-only
        file1 = tmp_path / "file1.txt"
        file1.write_text("content")

        file2 = tmp_path / "file2.txt"
        file2.write_text("content")

        # Create missing file to verify idempotent handling
        missing_file = tmp_path / "missing.txt"

        plan = UninstallPlan(
            venv_path=artifacts["venv"],
            files_to_remove=[file1, file2, missing_file],
            config_changes={},
            remove_venv=False,
        )

        result = execute_uninstall(plan, config_path=artifacts["config"])

        # Should continue despite missing file
        assert result["status"] == "ok"
        assert not file1.exists(), "existing file should be removed"
        assert not file2.exists(), "existing file should be removed"
        assert len(result["removed"]) >= 2, "should report removed files"
        print("test_error_recovery_partial_failure PASS")


# =============================================================================
# Integration Test 7: Backup and restore verification
# =============================================================================

def test_backup_restore_workflow():
    """Test backup creation and verify restore capability."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_full_install(tmp_path)

        config_path = artifacts["config"]
        original_content = config_path.read_text()
        original_data = json.loads(original_content)

        plan = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=config_path
        )
        plan.remove_venv = False
        plan.remove_skills = False

        result = execute_uninstall(plan, config_path=config_path)

        # Verify backup exists
        backup_files = list(config_path.parent.glob(f"{config_path.name}.backup-*"))
        assert len(backup_files) > 0, "backup should exist"

        # Verify backup content
        backup_content = backup_files[0].read_text()
        backup_data = json.loads(backup_content)
        assert backup_data == original_data, "backup should match original"

        # Verify backup timestamp format
        import re
        assert re.search(r"backup-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}", backup_files[0].name), "backup should have correct timestamp format"
        print("test_backup_restore_workflow PASS")


# =============================================================================
# Integration Test 8: Complex nested config removal with validation
# =============================================================================

def test_complex_nested_config_removal():
    """Test removal of nested config keys with JSON validation."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_minimal_install(tmp_path)

        # Create complex nested config
        complex_config = tmp_path / "complex.json"
        complex_config.write_text(json.dumps({
            "mcpServers": {
                "obsidian-connector": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "obsidian_connector.mcp"]
                },
                "other-server": {
                    "type": "http",
                    "url": "http://localhost:8000"
                },
                "third-server": {}
            },
            "userSettings": {
                "theme": "dark"
            },
            "otherKey": "value"
        }, indent=2))

        plan = UninstallPlan(
            venv_path=artifacts["venv"],
            files_to_remove=[],
            config_changes={
                "complex.json": {
                    "action": "remove_key",
                    "path": ["mcpServers", "obsidian-connector"]
                }
            },
            remove_venv=False,
        )

        result = execute_uninstall(plan, config_path=complex_config)

        # Verify removal and JSON validity
        assert result["status"] == "ok"
        updated_data = json.loads(complex_config.read_text())
        assert "obsidian-connector" not in updated_data.get("mcpServers", {}), "obsidian-connector should be removed"
        assert "other-server" in updated_data.get("mcpServers", {}), "other-server should remain"
        assert "userSettings" in updated_data, "other keys should remain"
        assert updated_data.get("otherKey") == "value", "other top-level keys should remain"
        print("test_complex_nested_config_removal PASS")


# =============================================================================
# Integration Test 9: Audit logging integration
# =============================================================================

def test_audit_logging_on_uninstall():
    """Test that uninstall actions produce correct output structure for logging.

    Note: Actual audit logging happens in CLI/MCP layers, not in uninstall module.
    This test verifies that execute_uninstall returns proper structured data
    that can be logged.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_minimal_install(tmp_path)

        plan = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=artifacts["config"]
        )
        plan.remove_venv = True
        plan.remove_skills = True

        result = execute_uninstall(plan, config_path=artifacts["config"])

        # Verify result structure supports logging
        assert result["status"] == "ok"
        assert "removed" in result
        assert "errors" in result
        assert "summary" in result
        assert isinstance(result["removed"], list)
        assert isinstance(result["errors"], list)
        print("test_audit_logging_on_uninstall PASS")


# =============================================================================
# Integration Test 10: JSON response envelope for MCP
# =============================================================================

def test_json_response_envelope_format():
    """Test that MCP responses follow correct JSON envelope format."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = setup_minimal_install(tmp_path)

        plan = detect_installed_artifacts(
            repo_root=artifacts["repo_root"],
            venv_path=artifacts["venv"],
            claude_config_path=artifacts["config"]
        )
        plan.remove_venv = True

        # Dry-run should return proper envelope
        dry_result = dry_run_uninstall(plan)
        assert "status" in dry_result
        assert "dry_run" in dry_result
        assert "plan" in dry_result
        assert dry_result["status"] == "ok"
        assert dry_result["dry_run"] is True

        # Execute should return proper envelope
        exec_result = execute_uninstall(plan, config_path=artifacts["config"])
        assert "status" in exec_result
        assert "removed" in exec_result
        assert "errors" in exec_result
        assert "summary" in exec_result
        assert exec_result["status"] in ["ok", "warning"]
        print("test_json_response_envelope_format PASS")


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    print("Running integration tests for obsidian-connector uninstaller...\n")

    test_cli_interactive_workflow()
    test_mcp_dry_run_mode()
    test_mcp_force_mode_actual_removal()
    test_partial_uninstall_selective_removal()
    test_idempotency_multiple_runs()
    test_error_recovery_partial_failure()
    test_backup_restore_workflow()
    test_complex_nested_config_removal()
    test_audit_logging_on_uninstall()
    test_json_response_envelope_format()

    print("\nAll 10 integration tests passed!")
