from dataclasses import dataclass, field
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
