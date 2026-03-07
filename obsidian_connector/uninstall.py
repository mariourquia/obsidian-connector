import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


@dataclass
class UninstallPlan:
    """Tracks artifacts to remove during uninstall."""
    venv_path: Path
    files_to_remove: List[Path] = field(default_factory=list)
    config_changes: Dict[str, Any] = field(default_factory=dict)
    plist_path: Path | None = None
    remove_plist: bool = False
    remove_venv: bool = False
    remove_skills: bool = False
    remove_hook: bool = False
    remove_logs: bool = False
    remove_cache: bool = False
    dry_run: bool = False


def detect_installed_artifacts(
    repo_root: Path,
    venv_path: Path,
    claude_config_path: Path
) -> UninstallPlan:
    """Scan system to detect what's installed."""
    files_to_remove = []
    config_changes = {}

    # Check venv
    if venv_path.exists():
        files_to_remove.append(venv_path)

    # Check skills
    skills_dir = repo_root / ".claude" / "commands"
    if skills_dir.exists():
        for skill in skills_dir.glob("*.md"):
            if skill.name in ["morning.md", "evening.md", "idea.md", "weekly.md"]:
                files_to_remove.append(skill)

    # Check Claude config
    if claude_config_path.exists():
        try:
            with open(claude_config_path) as f:
                cfg = json.load(f)
            mcp_servers = cfg.get("mcpServers", {})
            # Handle case where mcpServers is null or not a dict
            if mcp_servers and isinstance(mcp_servers, dict):
                if "obsidian-connector" in mcp_servers:
                    config_changes["claude_desktop_config.json"] = {
                        "action": "remove_key",
                        "path": ["mcpServers", "obsidian-connector"]
                    }
        except (json.JSONDecodeError, IOError, TypeError):
            pass

    # Check plist
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.obsidian-connector.daily.plist"

    return UninstallPlan(
        venv_path=venv_path,
        files_to_remove=files_to_remove,
        config_changes=config_changes,
        plist_path=plist_path if plist_path.exists() else None
    )


def backup_config_file(config_path: Path) -> Path:
    """Create timestamped backup of config file."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    backup_path = config_path.parent / f"{config_path.name}.backup-{timestamp}"
    backup_path.write_text(config_path.read_text())
    return backup_path


def validate_json(content: str) -> bool:
    """Check if string is valid JSON."""
    if not content or not content.strip():
        return False
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError:
        return False


def remove_from_json_config(config_path: Path, key_path: List[str]) -> bool:
    """Remove a key from JSON config file. Validates JSON after change."""
    try:
        with open(config_path) as f:
            cfg = json.load(f)

        # Navigate to parent of target key
        obj = cfg
        for key in key_path[:-1]:
            obj = obj[key]

        # Remove target key
        del obj[key_path[-1]]

        # Validate and write back
        content = json.dumps(cfg, indent=2) + "\n"
        if not validate_json(content):
            return False

        config_path.write_text(content)
        return True
    except (KeyError, TypeError, json.JSONDecodeError, IOError):
        return False


def remove_file_safely(file_path: Path) -> bool:
    """Remove file if it exists. Idempotent. Handles symlinks correctly."""
    try:
        if file_path.exists() or file_path.is_symlink():
            # Check for symlink first (is_dir follows symlinks)
            if file_path.is_symlink():
                file_path.unlink()
            elif file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
        return True
    except (IOError, OSError):
        return False


def unload_launchd_plist(plist_path: Path) -> bool:
    """Unload and remove launchd plist."""
    try:
        if plist_path.exists():
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                check=False
            )
            plist_path.unlink()
        return True
    except (IOError, OSError):
        return False


def dry_run_uninstall(plan: UninstallPlan) -> Dict[str, Any]:
    """Preview-only uninstall (no actual removal). Returns JSON."""
    return {
        "status": "ok",
        "dry_run": True,
        "plan": {
            "files_to_remove": [str(f) for f in plan.files_to_remove],
            "config_changes": plan.config_changes,
            "plist_action": "unload" if plan.remove_plist and plan.plist_path else None,
            "summary": f"Would remove {len(plan.files_to_remove)} files"
        }
    }


def execute_uninstall(plan: UninstallPlan, config_path: Path) -> Dict[str, Any]:
    """Execute uninstall plan. Creates backups, removes artifacts."""
    removed = []
    errors = []

    # Backup config if changes needed
    if plan.config_changes and config_path.exists():
        backup_config_file(config_path)

    # Remove files
    for file_path in plan.files_to_remove:
        if remove_file_safely(file_path):
            removed.append(str(file_path))
        else:
            errors.append(f"Failed to remove: {file_path}")

    # Remove config entries
    for config_file, change in plan.config_changes.items():
        if change.get("action") == "remove_key":
            if remove_from_json_config(config_path, change.get("path", [])):
                removed.append(f"{config_file}: removed {change['path'][-1]}")
            else:
                errors.append(f"Failed to update {config_file}")

    # Unload plist
    if plan.remove_plist and plan.plist_path:
        if unload_launchd_plist(plan.plist_path):
            removed.append(str(plan.plist_path))
        else:
            errors.append(f"Failed to unload plist: {plan.plist_path}")

    return {
        "status": "ok" if not errors else "warning",
        "removed": removed,
        "errors": errors,
        "summary": f"Removed {len(removed)} artifacts" + (f" ({len(errors)} errors)" if errors else "")
    }
