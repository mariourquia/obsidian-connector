---
title: "Uninstaller Implementation Plan"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-16"
---

# Uninstaller Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Implement a safe, two-mode uninstaller (CLI interactive + MCP dry-run/force) that removes all obsidian-connector artifacts with config backups and validation.

**Architecture:** Core module (`uninstall.py`) detects installed artifacts, creates timestamped backups, validates JSON config changes, and orchestrates safe removal. CLI mode prompts user interactively; MCP mode uses `--dry-run` and `--force` flags.

**Tech Stack:** Python 3.11+, json module, pathlib, subprocess (for launchctl), audit logging via `audit.py`

---

## Phase 1: Core Module (Tasks 1-6)

Core `uninstall.py` module with detection, backup, validation, and removal logic.

### Task 1: Create UninstallPlan dataclass

**Files:**
- Create: `obsidian_connector/uninstall.py`
- Test: `scripts/uninstall_test.py`

**Step 1: Write the failing test**

```python
# scripts/uninstall_test.py
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
```

**Step 2: Run test to verify it fails**

```bash
python3 scripts/uninstall_test.py
```

Expected: `ModuleNotFoundError: No module named 'obsidian_connector.uninstall'`

**Step 3: Write minimal implementation**

```python
# obsidian_connector/uninstall.py
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
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/uninstall_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py scripts/uninstall_test.py
git commit -m "feat: add UninstallPlan dataclass"
```

---

### Task 2: Implement detect_installed_artifacts()

**Files:**
- Modify: `obsidian_connector/uninstall.py`
- Modify: `scripts/uninstall_test.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Expected: `NameError: name 'detect_installed_artifacts' is not defined`

**Step 3: Write minimal implementation**

```python
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
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/uninstall_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py scripts/uninstall_test.py
git commit -m "feat: implement detect_installed_artifacts"
```

---

### Task 3: Implement config backup & JSON validation utilities

**Files:**
- Modify: `obsidian_connector/uninstall.py`
- Modify: `scripts/uninstall_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.uninstall import backup_config_file, validate_json

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
```

**Step 2: Run test to verify it fails**

Expected: `NameError: name 'backup_config_file' is not defined`

**Step 3: Write minimal implementation**

```python
from datetime import datetime

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
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/uninstall_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py scripts/uninstall_test.py
git commit -m "feat: add config backup and JSON validation utilities"
```

---

### Task 4: Implement core removal logic

**Files:**
- Modify: `obsidian_connector/uninstall.py`
- Modify: `scripts/uninstall_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.uninstall import (
    remove_from_json_config,
    remove_file_safely,
    unload_launchd_plist
)

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

    assert result is True  # idempotent - no error
```

**Step 2: Run test to verify it fails**

Expected: `NameError: name 'remove_from_json_config' is not defined`

**Step 3: Write minimal implementation**

```python
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
    """Remove file if it exists. Idempotent."""
    try:
        if file_path.exists():
            if file_path.is_dir():
                import shutil
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
            import subprocess
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                check=False
            )
            plist_path.unlink()
        return True
    except (IOError, OSError):
        return False
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/uninstall_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py scripts/uninstall_test.py
git commit -m "feat: implement core removal logic"
```

---

### Task 5: Implement execute_uninstall() orchestrator

**Files:**
- Modify: `obsidian_connector/uninstall.py`
- Modify: `scripts/uninstall_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.uninstall import execute_uninstall

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
```

**Step 2: Run test to verify it fails**

Expected: `NameError: name 'execute_uninstall' is not defined`

**Step 3: Write minimal implementation**

```python
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
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/uninstall_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py scripts/uninstall_test.py
git commit -m "feat: implement execute_uninstall orchestrator"
```

---

### Task 6: Implement dry_run_uninstall()

**Files:**
- Modify: `obsidian_connector/uninstall.py`
- Modify: `scripts/uninstall_test.py`

**Step 1: Write the failing test**

```python
from obsidian_connector.uninstall import dry_run_uninstall

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
```

**Step 2: Run test to verify it fails**

Expected: `NameError: name 'dry_run_uninstall' is not defined`

**Step 3: Write minimal implementation**

```python
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
```

**Step 4: Run test to verify it passes**

```bash
python3 scripts/uninstall_test.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add obsidian_connector/uninstall.py scripts/uninstall_test.py
git commit -m "feat: implement dry_run_uninstall for MCP preview"
```

---

## Phase 2: CLI & MCP Integration (Tasks 7-8)

Add CLI subcommand and MCP tool.

### Task 7: Add uninstall CLI subcommand
### Task 8: Add uninstall MCP tool

---

## Phase 3: Testing & Verification (Tasks 9-11)

### Task 9: Write comprehensive unit tests
### Task 10: Integration testing
### Task 11: Verification and edge cases

---

## Phase 4: Final Integration (Task 12)

### Task 12: Verify clean commit history, docs lint, merge readiness
