import json
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
            if "obsidian-connector" in cfg.get("mcpServers", {}):
                config_changes["claude_desktop_config.json"] = {
                    "action": "remove_key",
                    "path": ["mcpServers", "obsidian-connector"]
                }
        except (json.JSONDecodeError, IOError):
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
