#!/usr/bin/env python3
"""
Plugin Integrity & Documentation Drift Checker
===============================================
Zero-dependency script that validates:
  - Plugin structure: plugin.json, hooks.json, .mcp.json
  - Skill integrity: every skill dir has SKILL.md
  - Count consistency: tools, commands, skills, presets across all doc surfaces
  - Version consistency: pyproject.toml version matches all version-bearing files
  - Stale version detection: no references to prior versions in non-CHANGELOG files
  - Legacy file detection: macOS duplicates, empty dirs, sensitive files
  - Module inventory: every .py file in obsidian_connector/ is listed in ARCHITECTURE.md

Runs in CI and blocks releases on any FAIL result.

Usage:
    python3 scripts/integrity_check.py
"""

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PKG_DIR = REPO_ROOT / "obsidian_connector"
SKILLS_DIR = REPO_ROOT / "skills"


# ---------------------------------------------------------------------------
# Actual counts from code
# ---------------------------------------------------------------------------

def count_mcp_tools() -> int:
    path = PKG_DIR / "mcp_server.py"
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count("@mcp.tool")


def count_cli_commands() -> int:
    path = PKG_DIR / "cli.py"
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count("add_parser")


def count_skills() -> int:
    if not SKILLS_DIR.is_dir():
        return 0
    return len(list(SKILLS_DIR.glob("*/SKILL.md")))


def count_presets() -> int:
    path = PKG_DIR / "vault_presets.py"
    if not path.is_file():
        return 0
    content = path.read_text(encoding="utf-8")
    return content.count("VaultPreset(")


def count_modules() -> int:
    if not PKG_DIR.is_dir():
        return 0
    return len([f for f in PKG_DIR.glob("*.py") if f.name != "__pycache__"])


def get_version() -> str:
    path = REPO_ROOT / "pyproject.toml"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

def validate_plugin_structure() -> list[str]:
    """Verify plugin manifest, hooks, and MCP config exist and parse."""
    failures = []

    pj = REPO_ROOT / ".claude-plugin" / "plugin.json"
    if not pj.is_file():
        failures.append("FAIL  .claude-plugin/plugin.json not found")
    else:
        try:
            json.loads(pj.read_text())
        except json.JSONDecodeError as e:
            failures.append(f"FAIL  plugin.json invalid JSON: {e}")

    hj = REPO_ROOT / "hooks" / "hooks.json"
    if not hj.is_file():
        failures.append("FAIL  hooks/hooks.json not found")
    else:
        try:
            data = json.loads(hj.read_text())
            if "hooks" not in data:
                failures.append("FAIL  hooks.json missing 'hooks' key")
        except json.JSONDecodeError as e:
            failures.append(f"FAIL  hooks.json invalid JSON: {e}")

    mcp = REPO_ROOT / ".mcp.json"
    if not mcp.is_file():
        failures.append("FAIL  .mcp.json not found")
    else:
        try:
            json.loads(mcp.read_text())
        except json.JSONDecodeError as e:
            failures.append(f"FAIL  .mcp.json invalid JSON: {e}")

    return failures


def validate_skill_integrity() -> list[str]:
    """Every skill dir must have SKILL.md."""
    failures = []
    if not SKILLS_DIR.is_dir():
        failures.append("FAIL  skills/ directory not found")
        return failures

    for entry in sorted(SKILLS_DIR.iterdir()):
        if entry.is_dir() and not (entry / "SKILL.md").is_file():
            failures.append(f"FAIL  skills/{entry.name}/ missing SKILL.md")

    return failures


def validate_count_consistency() -> list[str]:
    """Verify counts in doc files match code."""
    failures = []

    actual = {
        "tools": count_mcp_tools(),
        "commands": count_cli_commands(),
        "skills": count_skills(),
        "presets": count_presets(),
    }

    doc_files = {
        "README.md": [
            (r"(\d+)\s+MCP\s+tools", "tools"),
            (r"(\d+)\s+CLI\s+commands", "commands"),
            (r"(\d+)\s+skills", "skills"),
            (r"(\d+)\s+vault\s+presets", "presets"),
        ],
        "CLAUDE.md": [
            (r"(\d+)\s+tools", "tools"),
            (r"(\d+)\s+commands", "commands"),
        ],
        "AGENTS.md": [
            (r"(\d+)\s+CLI\s+subcommands", "commands"),
            (r"(\d+)\s+MCP\s+tools", "tools"),
            (r"(\d+)\s+Claude\s+Code\s+plugin\s+skills", "skills"),
        ],
        "ARCHITECTURE.md": [
            (r"(\d+)\s+argparse\s+subcommands", "commands"),
            (r"(\d+)\s+tools\s+for\s+Claude", "tools"),
            (r"(\d+)\s+skills:\s+\d+\s+workflow", "skills"),
        ],
        "TOOLS_CONTRACT.md": [
            (r"(\d+)\s+tools\s+are\s+available", "tools"),
            (r"Commands\s+\((\d+)\s+total\)", "commands"),
        ],
        "mcpb.json": [
            (r'"tools_count":\s*(\d+)', "tools"),
        ],
    }

    for relpath, patterns in doc_files.items():
        fpath = REPO_ROOT / relpath
        if not fpath.is_file():
            continue
        content = fpath.read_text(encoding="utf-8")

        for pattern, asset_type in patterns:
            for match in re.finditer(pattern, content):
                found = int(match.group(1))
                if found != actual[asset_type]:
                    failures.append(
                        f"FAIL  {relpath}: says {found} {asset_type} but code has {actual[asset_type]}"
                    )
                    break

    return failures


def validate_version_consistency() -> list[str]:
    """All version-bearing files must match pyproject.toml."""
    failures = []
    sot = get_version()
    if not sot:
        failures.append("FAIL  pyproject.toml has no version field")
        return failures

    version_files = [
        ("obsidian_connector/__init__.py", re.compile(r'__version__\s*=\s*"([^"]+)"')),
        ("marketplace.json", re.compile(r'"version":\s*"([^"]+)"')),
        ("mcpb.json", re.compile(r'"version":\s*"([^"]+)"')),
    ]

    for relpath, pattern in version_files:
        fpath = REPO_ROOT / relpath
        if not fpath.is_file():
            continue
        content = fpath.read_text(encoding="utf-8")
        match = pattern.search(content)
        if match and match.group(1) != sot:
            failures.append(
                f"FAIL  {relpath}: version {match.group(1)} != pyproject.toml {sot}"
            )

    return failures


def validate_stale_versions() -> list[str]:
    """Detect references to prior versions in non-historical files."""
    failures = []
    current = get_version()
    if not current:
        return failures

    current_mm = ".".join(current.split(".")[:2])
    major, minor = int(current.split(".")[0]), int(current.split(".")[1])

    prior = set()
    for m in range(0, major + 1):
        for n in range(0, 10):
            vm = f"{m}.{n}"
            if vm != current_mm:
                prior.add(vm)

    exempt_files = {"CHANGELOG.md", "LICENSE", "SBOM.md"}
    exempt_dirs = {"docs/generated", "docs/exec-plans", "docs/plans", "docs/", ".claude", ".github"}
    scan_ext = {".md", ".json", ".yml", ".yaml", ".toml"}

    for fpath in sorted(REPO_ROOT.rglob("*")):
        if not fpath.is_file() or ".git" in fpath.parts or ".claude" in fpath.parts or ".venv" in fpath.parts:
            continue
        if fpath.suffix not in scan_ext:
            continue
        relpath = str(fpath.relative_to(REPO_ROOT))
        if fpath.name in exempt_files:
            continue
        if any(relpath.startswith(d) for d in exempt_dirs):
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for match in re.finditer(r'["\s]v?(\d+\.\d+\.\d+)["\s,]', content):
            found = match.group(1)
            found_mm = ".".join(found.split(".")[:2])
            if found_mm in prior and found != current:
                line = content[:match.start()].count("\n") + 1
                failures.append(
                    f"FAIL  {relpath}:{line}: stale version v{found} (current is v{current})"
                )
                break

    return failures


def validate_module_inventory() -> list[str]:
    """Every .py module in obsidian_connector/ should be in ARCHITECTURE.md."""
    failures = []
    arch = REPO_ROOT / "ARCHITECTURE.md"
    if not arch.is_file():
        return failures

    content = arch.read_text(encoding="utf-8")
    modules = [f.stem for f in PKG_DIR.glob("*.py") if f.stem not in ("__init__", "__main__", "__pycache__")]

    for mod in modules:
        if f"`{mod}.py`" not in content and f"{mod}.py" not in content:
            failures.append(f"FAIL  ARCHITECTURE.md missing module: {mod}.py")

    return failures


def validate_legacy_files() -> list[str]:
    """Detect files that shouldn't be in a release."""
    failures = []

    for fpath in REPO_ROOT.rglob("* 2*"):
        if ".git" in fpath.parts or ".venv" in fpath.parts:
            continue
        relpath = str(fpath.relative_to(REPO_ROOT))
        failures.append(f"FAIL  {relpath}: macOS duplicate -- delete before release")

    if SKILLS_DIR.is_dir():
        for entry in sorted(SKILLS_DIR.iterdir()):
            if entry.is_dir() and not any(entry.iterdir()):
                failures.append(f"FAIL  skills/{entry.name}/: empty directory")

    sensitive = [".env", ".env.local", "credentials.json"]
    for pattern in sensitive:
        for fpath in REPO_ROOT.glob(pattern):
            if ".git" not in fpath.parts:
                failures.append(f"FAIL  {fpath.name}: sensitive file in repo")

    return failures


def validate_required_files() -> list[str]:
    """Verify all required files exist."""
    failures = []
    required = [
        "LICENSE", "README.md", "SECURITY.md", "CHANGELOG.md",
        "CONTRIBUTING.md", "PRIVACY.md", "SBOM.md",
        ".claude-plugin/plugin.json", "hooks/hooks.json", ".mcp.json",
    ]
    for f in required:
        if not (REPO_ROOT / f).exists():
            failures.append(f"FAIL  Missing required file: {f}")
    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Plugin Integrity Check -- obsidian-connector")
    print(f"Root: {REPO_ROOT}")
    print()

    actual = {
        "MCP tools": count_mcp_tools(),
        "CLI commands": count_cli_commands(),
        "Skills": count_skills(),
        "Presets": count_presets(),
        "Modules": count_modules(),
        "Version": get_version(),
    }

    print("Actual counts:")
    for k, v in actual.items():
        print(f"  {k}: {v}")
    print()

    checks = [
        ("Plugin Structure", validate_plugin_structure()),
        ("Skill Integrity", validate_skill_integrity()),
        ("Count Consistency", validate_count_consistency()),
        ("Version Consistency", validate_version_consistency()),
        ("Stale Versions", validate_stale_versions()),
        ("Module Inventory", validate_module_inventory()),
        ("Legacy Files", validate_legacy_files()),
        ("Required Files", validate_required_files()),
    ]

    all_failures = []
    for name, failures in checks:
        status = "PASS" if not failures else f"FAIL ({len(failures)})"
        print(f"  [{status}] {name}")
        for msg in failures:
            print(f"    {msg}")
        all_failures.extend(failures)

    print()
    clean = sum(1 for _, f in checks if not f)
    print("=" * 60)
    print(f"CHECKS: {clean}/{len(checks)} clean, {len(all_failures)} failures")

    if all_failures:
        print("STATUS: FAIL")
        sys.exit(1)
    else:
        print("STATUS: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
