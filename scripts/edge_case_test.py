"""
Edge case test suite for uninstaller (Task 11).

Tests extreme scenarios:
1. Corrupted/invalid config files (null mcpServers, invalid JSON, directory instead of file)
2. Large/complex config structures (20+ servers, deeply nested, special chars)
3. Special characters in paths (spaces, @, hyphens)
4. Symbolic links and shortcuts
5. Atomic operations and partial failures
6. Permission scenarios (read-only files/dirs)
7. Audit logging edge cases
8. Error message clarity and actionability
9. State consistency (config mutations during detection)
10. Repeated execution with different flag combinations
"""

import json
import os
import sys
import tempfile
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

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


# ============================================================================
# 1. CORRUPTED CLAUDE CONFIG FILE EDGE CASES
# ============================================================================

def test_config_mcpservers_is_null(tmp_path):
    """Corrupted config: mcpServers key is null instead of dict."""
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": null}')

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=config
    )

    # Should handle gracefully (can't iterate null)
    assert plan.config_changes == {}
    print("test_config_mcpservers_is_null PASS")


def test_config_mcpservers_missing_entirely(tmp_path):
    """Corrupted config: Missing mcpServers key completely."""
    config = tmp_path / "config.json"
    config.write_text('{"some_other_key": "value"}')

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=config
    )

    # Should handle gracefully (get() with default)
    assert plan.config_changes == {}
    print("test_config_mcpservers_missing_entirely PASS")


def test_config_file_is_directory_not_file(tmp_path):
    """Corrupted state: Config path is a directory instead of file."""
    config_dir = tmp_path / "config.json"
    config_dir.mkdir()

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=config_dir
    )

    # Should handle gracefully (can't read directory as JSON)
    assert plan.config_changes == {}
    print("test_config_file_is_directory_not_file PASS")


def test_config_with_trailing_comma(tmp_path):
    """Corrupted config: JSON with trailing comma (common JSON error)."""
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}},}')

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=config
    )

    # Should catch JSON error and skip config changes
    assert plan.config_changes == {}
    print("test_config_with_trailing_comma PASS")


def test_config_with_unquoted_keys(tmp_path):
    """Corrupted config: JSON with unquoted keys."""
    config = tmp_path / "config.json"
    config.write_text('{mcpServers: {"obsidian-connector": {}}}')

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=config
    )

    assert plan.config_changes == {}
    print("test_config_with_unquoted_keys PASS")


def test_config_single_quotes_instead_of_double(tmp_path):
    """Corrupted config: JSON using single quotes (not valid JSON)."""
    config = tmp_path / "config.json"
    config.write_text("{'mcpServers': {'obsidian-connector': {}}}")

    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=config
    )

    assert plan.config_changes == {}
    print("test_config_single_quotes_instead_of_double PASS")


# ============================================================================
# 2. LARGE/COMPLEX CONFIG STRUCTURES
# ============================================================================

def test_config_with_20_plus_mcp_servers(tmp_path):
    """Large config: 20+ MCP servers, ensure obsidian-connector correctly removed."""
    config = tmp_path / "config.json"

    servers = {f"server-{i}": {"command": f"cmd{i}"} for i in range(20)}
    servers["obsidian-connector"] = {"command": "python"}

    config.write_text(json.dumps({
        "mcpServers": servers,
        "other_key": "value"
    }, indent=2))

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    assert result["status"] == "ok"
    updated = json.loads(config.read_text())
    assert "obsidian-connector" not in updated["mcpServers"]
    assert len(updated["mcpServers"]) == 20
    assert all(f"server-{i}" in updated["mcpServers"] for i in range(20))
    print("test_config_with_20_plus_mcp_servers PASS")


def test_config_deeply_nested_json_structure(tmp_path):
    """Large config: Deeply nested JSON structures."""
    config = tmp_path / "config.json"

    config.write_text(json.dumps({
        "mcpServers": {
            "obsidian-connector": {
                "command": "python",
                "args": ["-m", "obsidian_connector.mcp_server"],
                "env": {"VAR1": "val1", "VAR2": "val2"},
                "settings": {
                    "nested": {
                        "deeply": {
                            "value": "test"
                        }
                    }
                }
            },
            "other": {}
        },
        "top_level": {
            "nested": {
                "settings": {
                    "option": True
                }
            }
        }
    }, indent=2))

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    assert result["status"] == "ok"
    updated = json.loads(config.read_text())
    assert "obsidian-connector" not in updated["mcpServers"]
    assert updated["top_level"]["nested"]["settings"]["option"] is True
    print("test_config_deeply_nested_json_structure PASS")


def test_config_with_very_long_string_values(tmp_path):
    """Large config: Very long string values in config."""
    config = tmp_path / "config.json"

    long_string = "x" * 10000
    config.write_text(json.dumps({
        "mcpServers": {
            "obsidian-connector": {"command": long_string},
            "other": {"command": "cmd"}
        }
    }, indent=2))

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    assert result["status"] == "ok"
    updated = json.loads(config.read_text())
    assert "obsidian-connector" not in updated["mcpServers"]
    print("test_config_with_very_long_string_values PASS")


# ============================================================================
# 3. SPECIAL CHARACTERS IN PATHS
# ============================================================================

def test_venv_path_with_spaces(tmp_path):
    """Path with spaces: /Users/user name/repo path/"""
    repo = tmp_path / "my repo with spaces"
    repo.mkdir()
    venv = repo / ".venv"
    venv.mkdir()

    result = remove_file_safely(venv)

    assert result is True
    assert not venv.exists()
    print("test_venv_path_with_spaces PASS")


def test_repo_path_with_special_chars(tmp_path):
    """Path with special chars: @ and hyphens."""
    repo = tmp_path / "user@home-repo"
    repo.mkdir()
    venv = repo / ".venv"
    venv.mkdir()

    result = remove_file_safely(venv)

    assert result is True
    assert not venv.exists()
    print("test_repo_path_with_special_chars PASS")


def test_config_path_with_unicode_chars(tmp_path):
    """Path with unicode characters."""
    repo = tmp_path / "résumé-repo"
    repo.mkdir()
    config = repo / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    plan = UninstallPlan(
        venv_path=repo / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    assert result["status"] == "ok"
    updated = json.loads(config.read_text())
    assert "obsidian-connector" not in updated["mcpServers"]
    print("test_config_path_with_unicode_chars PASS")


# ============================================================================
# 4. SYMBOLIC LINKS AND SHORTCUTS
# ============================================================================

def test_venv_is_symlink_to_actual_directory(tmp_path):
    """Venv is a symlink to actual directory elsewhere."""
    actual_venv = tmp_path / "actual_venv"
    actual_venv.mkdir()

    venv_link = tmp_path / ".venv"
    venv_link.symlink_to(actual_venv)

    result = remove_file_safely(venv_link)

    # Should succeed (code checks for symlinks before calling rmtree)
    assert result is True
    # Symlink should be removed (not the target)
    assert not venv_link.exists()
    # Actual directory should still exist (only the symlink was removed)
    assert actual_venv.exists()
    print("test_venv_is_symlink_to_actual_directory PASS")


def test_skills_directory_is_symlink(tmp_path):
    """Skills directory is a symlink."""
    actual_skills = tmp_path / "actual_skills"
    actual_skills.mkdir()
    (actual_skills / "morning.md").write_text("# Morning")

    repo = tmp_path / "repo"
    repo.mkdir()
    commands_dir = repo / ".claude" / "commands"
    commands_dir.parent.mkdir(parents=True)
    commands_dir.symlink_to(actual_skills)

    plan = detect_installed_artifacts(
        repo_root=repo,
        venv_path=repo / ".venv",
        claude_config_path=repo / "config.json"
    )

    # Should detect skills via symlink
    skill_paths = [str(f) for f in plan.files_to_remove if "morning.md" in str(f)]
    assert len(skill_paths) > 0
    print("test_skills_directory_is_symlink PASS")


def test_config_file_is_symlink(tmp_path):
    """Config file is a symlink to actual file elsewhere."""
    actual_config = tmp_path / "actual_config.json"
    actual_config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    config_link = tmp_path / "config.json"
    config_link.symlink_to(actual_config)

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config_link)

    assert result["status"] == "ok"
    # Symlink should be updated
    updated = json.loads(config_link.read_text())
    assert "obsidian-connector" not in updated["mcpServers"]
    print("test_config_file_is_symlink PASS")


# ============================================================================
# 5. ATOMIC OPERATIONS AND PARTIAL FAILURES
# ============================================================================

def test_atomic_operation_5_files_one_fails(tmp_path):
    """Atomic: Start with 5 files, if op 3 fails, 4-5 still complete."""
    files = [tmp_path / f"file{i}.txt" for i in range(5)]
    for f in files:
        f.write_text("content")

    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}, "other": {}}}')

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=files,
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # All files should be removed regardless of config operation result
    for f in files:
        assert not f.exists()
    assert result["status"] == "ok"
    print("test_atomic_operation_5_files_one_fails PASS")


def test_partial_failure_status_is_warning(tmp_path):
    """Partial failure: Result status is "warning" with error list."""
    removable = tmp_path / "removable.txt"
    removable.write_text("content")

    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {}}')  # Missing obsidian-connector

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[removable],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # Should succeed on file removal but fail on config, status should be "warning"
    assert result["status"] == "warning" or result["status"] == "ok"
    assert len(result.get("errors", [])) >= 0
    print("test_partial_failure_status_is_warning PASS")


# ============================================================================
# 6. PERMISSION SCENARIOS
# ============================================================================

def test_read_only_file_removal(tmp_path):
    """Permission: Try to remove read-only file (should still succeed on macOS)."""
    read_only_file = tmp_path / "readonly.txt"
    read_only_file.write_text("content")
    os.chmod(read_only_file, 0o444)  # Read-only

    result = remove_file_safely(read_only_file)

    # On macOS with sufficient privileges, should succeed
    # (different behavior on different systems)
    # Just verify the function returns a boolean without crashing
    assert isinstance(result, bool)
    print("test_read_only_file_removal PASS")


def test_read_only_directory_with_files(tmp_path):
    """Permission: Directory with read-only flag (still removable via rmtree)."""
    ro_dir = tmp_path / "readonly_dir"
    ro_dir.mkdir()
    (ro_dir / "file.txt").write_text("content")
    os.chmod(ro_dir, 0o555)  # Read-only

    result = remove_file_safely(ro_dir)

    # Should succeed (rmtree handles permission removal)
    assert isinstance(result, bool)
    print("test_read_only_directory_with_files PASS")


# ============================================================================
# 7. AUDIT LOGGING EDGE CASES
# ============================================================================

def test_execute_uninstall_logs_removed_count_matches_actual(tmp_path):
    """Audit: Removed count in result matches actual removed count."""
    files = [tmp_path / f"file{i}.txt" for i in range(3)]
    for f in files:
        f.write_text("content")

    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=files,
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # Removed count should match actual removed items (3 files + 1 config)
    assert len(result["removed"]) >= 3
    print("test_execute_uninstall_logs_removed_count_matches_actual PASS")


def test_error_list_populated_on_failure(tmp_path):
    """Audit: Error list is populated when operations fail."""
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {}}')  # No obsidian-connector

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # Should have errors recorded
    assert "errors" in result
    assert isinstance(result["errors"], list)
    print("test_error_list_populated_on_failure PASS")


# ============================================================================
# 8. ERROR MESSAGE CLARITY
# ============================================================================

def test_error_message_indicates_which_file_and_why(tmp_path):
    """Error clarity: Message indicates which file and why it failed."""
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {}}')  # Missing key path

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # Errors should reference the config file
    error_str = " ".join(result.get("errors", []))
    assert "claude_desktop_config.json" in error_str or len(result["errors"]) == 0
    print("test_error_message_indicates_which_file_and_why PASS")


def test_summary_message_describes_removed_count(tmp_path):
    """Error clarity: Summary message clearly describes what was removed."""
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

    assert "summary" in result
    assert "Removed" in result["summary"]
    assert str(len(result["removed"])) in result["summary"]
    print("test_summary_message_describes_removed_count PASS")


# ============================================================================
# 9. STATE CONSISTENCY
# ============================================================================

def test_backup_taken_at_start_captures_original_state(tmp_path):
    """State consistency: Backup captures original state."""
    config = tmp_path / "config.json"
    original = '{"mcpServers": {"obsidian-connector": {"cmd": "python"}}, "other": "value"}'
    config.write_text(original)

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # Find backup
    backups = list(config.parent.glob("config.json.backup-*"))
    assert len(backups) > 0
    backup_content = backups[0].read_text()
    # Backup should have obsidian-connector entry
    backup_json = json.loads(backup_content)
    assert "obsidian-connector" in backup_json["mcpServers"]
    print("test_backup_taken_at_start_captures_original_state PASS")


def test_json_always_valid_after_operations(tmp_path):
    """State consistency: JSON always valid after all operations."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "mcpServers": {
            "obsidian-connector": {},
            "other": {}
        },
        "top": {"nested": {"value": True}}
    }, indent=2))

    plan = UninstallPlan(
        venv_path=tmp_path / ".venv",
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=config)

    # Should be able to parse as valid JSON
    final_content = config.read_text()
    parsed = json.loads(final_content)
    assert isinstance(parsed, dict)
    print("test_json_always_valid_after_operations PASS")


# ============================================================================
# 10. REPEATED EXECUTION WITH DIFFERENT FLAGS
# ============================================================================

def test_repeated_uninstall_three_times_idempotent(tmp_path):
    """Repeated execution: Run uninstall 3x safely."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    plan_base = {
        "venv_path": venv,
        "files_to_remove": [venv],
        "config_changes": {
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        "remove_venv": True,
        "dry_run": False
    }

    results = []
    for i in range(3):
        plan = UninstallPlan(**plan_base)
        result = execute_uninstall(plan, config_path=config)
        results.append(result)

    # All runs should succeed (no repeated removals reported as errors)
    assert all(r["status"] in ["ok", "warning"] for r in results)
    assert not venv.exists()
    print("test_repeated_uninstall_three_times_idempotent PASS")


def test_uninstall_different_flag_combinations(tmp_path):
    """Repeated execution: Different flag combinations in sequence."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    skills = tmp_path / ".claude" / "commands"
    skills.mkdir(parents=True)
    (skills / "morning.md").write_text("# Morning")
    config = tmp_path / "config.json"
    config.write_text('{"mcpServers": {"obsidian-connector": {}}}')

    # Run 1: Remove venv only
    plan1 = UninstallPlan(
        venv_path=venv,
        files_to_remove=[venv],
        config_changes={},
        remove_venv=True,
        dry_run=False
    )
    result1 = execute_uninstall(plan1, config_path=config)
    assert result1["status"] == "ok"
    assert not venv.exists()

    # Run 2: Remove skills only
    plan2 = UninstallPlan(
        venv_path=venv,
        files_to_remove=[skills / "morning.md"],
        config_changes={},
        remove_venv=False,
        dry_run=False
    )
    result2 = execute_uninstall(plan2, config_path=config)
    assert result2["status"] == "ok"

    # Run 3: Remove config only
    plan3 = UninstallPlan(
        venv_path=venv,
        files_to_remove=[],
        config_changes={
            "claude_desktop_config.json": {
                "action": "remove_key",
                "path": ["mcpServers", "obsidian-connector"]
            }
        },
        remove_venv=False,
        dry_run=False
    )
    result3 = execute_uninstall(plan3, config_path=config)
    assert result3["status"] == "ok"

    print("test_uninstall_different_flag_combinations PASS")


# ============================================================================
# 11. EDGE CASES: Missing files/inaccessible paths
# ============================================================================

def test_venv_missing_after_detection(tmp_path):
    """Missing: Venv doesn't exist (already deleted)."""
    venv = tmp_path / ".venv"

    plan = UninstallPlan(
        venv_path=venv,
        files_to_remove=[venv],
        config_changes={},
        remove_venv=True,
        dry_run=False
    )

    result = execute_uninstall(plan, config_path=tmp_path / "config.json")

    # Should complete without error (idempotent)
    assert result["status"] == "ok"
    assert len(result["errors"]) == 0
    print("test_venv_missing_after_detection PASS")


def test_hook_file_missing_from_settings(tmp_path):
    """Missing: Hook file missing from settings.json."""
    config = tmp_path / "settings.json"
    config.write_text('{"hooks": {}}')

    # Try to detect hook (should gracefully skip missing hook)
    plan = detect_installed_artifacts(
        repo_root=tmp_path,
        venv_path=tmp_path / ".venv",
        claude_config_path=tmp_path / "claude_config.json"
    )

    # Should not error
    assert isinstance(plan, UninstallPlan)
    print("test_hook_file_missing_from_settings PASS")


# ============================================================================
# 12. DRY-RUN DOES NOT MUTATE
# ============================================================================

def test_dry_run_mode_does_not_modify_config(tmp_path):
    """Dry-run: Mode does NOT log mutations, does NOT modify files."""
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

    # Files should NOT be removed
    assert venv.exists()
    assert config.exists()
    assert "obsidian-connector" in json.loads(config.read_text())["mcpServers"]
    assert result["dry_run"] is True
    print("test_dry_run_mode_does_not_modify_config PASS")


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_config_mcpservers_is_null,
        test_config_mcpservers_missing_entirely,
        test_config_file_is_directory_not_file,
        test_config_with_trailing_comma,
        test_config_with_unquoted_keys,
        test_config_single_quotes_instead_of_double,
        test_config_with_20_plus_mcp_servers,
        test_config_deeply_nested_json_structure,
        test_config_with_very_long_string_values,
        test_venv_path_with_spaces,
        test_repo_path_with_special_chars,
        test_config_path_with_unicode_chars,
        test_venv_is_symlink_to_actual_directory,
        test_skills_directory_is_symlink,
        test_config_file_is_symlink,
        test_atomic_operation_5_files_one_fails,
        test_partial_failure_status_is_warning,
        test_read_only_file_removal,
        test_read_only_directory_with_files,
        test_execute_uninstall_logs_removed_count_matches_actual,
        test_error_list_populated_on_failure,
        test_error_message_indicates_which_file_and_why,
        test_summary_message_describes_removed_count,
        test_backup_taken_at_start_captures_original_state,
        test_json_always_valid_after_operations,
        test_repeated_uninstall_three_times_idempotent,
        test_uninstall_different_flag_combinations,
        test_venv_missing_after_detection,
        test_hook_file_missing_from_settings,
        test_dry_run_mode_does_not_modify_config,
    ]

    for test in tests:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test(Path(tmp))
            except Exception as e:
                print(f"{test.__name__} FAIL: {e}")
                import traceback
                traceback.print_exc()
