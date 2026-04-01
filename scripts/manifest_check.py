#!/usr/bin/env python3
"""Validate tool/skill/preset/command counts across all documentation surfaces.

Detects drift between actual code counts and advertised counts in README.md,
CLAUDE.md, TOOLS_CONTRACT.md, marketplace.json, and mcpb.json.

Usage:
    python3 scripts/manifest_check.py

Exit codes:
    0 -- all counts and versions match
    1 -- at least one mismatch detected
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Source-of-truth counters
# ---------------------------------------------------------------------------

def count_mcp_tools(path: Path) -> int:
    """Count @mcp.tool() decorators in mcp_server.py."""
    text = path.read_text()
    return len(re.findall(r"@mcp\.tool\(", text))


def count_cli_commands(path: Path) -> int:
    """Count subparser additions (add_parser calls) in cli.py.

    Counts all add_parser calls on any subparsers object, which includes
    top-level commands and sub-subcommands (e.g. graduate list/execute).
    """
    text = path.read_text()
    return len(re.findall(r"\.add_parser\(", text))


def count_skills(path: Path) -> int:
    """Count directories in skills/ that contain a SKILL.md file."""
    if not path.is_dir():
        return 0
    return sum(1 for d in path.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def count_presets(path: Path) -> int:
    """Count _register(VaultPreset(...)) calls in vault_presets.py."""
    text = path.read_text()
    return len(re.findall(r"_register\(VaultPreset\(", text))


# ---------------------------------------------------------------------------
# Documentation extractors
# ---------------------------------------------------------------------------

def _extract_number_before(pattern: str, text: str) -> int | None:
    """Extract the integer immediately before a pattern like 'MCP tools'."""
    m = re.search(rf"(\d+)\s+{pattern}", text)
    return int(m.group(1)) if m else None


def extract_readme_counts(path: Path) -> dict[str, int | None]:
    """Regex-extract advertised counts from README.md."""
    text = path.read_text()
    return {
        "tools": _extract_number_before(r"MCP tools", text),
        "commands": _extract_number_before(r"CLI commands", text),
        "skills": _extract_number_before(r"skills", text),
        "presets": _extract_number_before(r"(?:vault )?presets", text),
    }


def extract_claude_md_counts(path: Path) -> dict[str, int | None]:
    """Regex-extract counts from CLAUDE.md."""
    text = path.read_text()
    tools = _extract_number_before(r"tools", text)
    commands = _extract_number_before(r"commands", text)
    # CLAUDE.md may not mention skills or presets
    skills = _extract_number_before(r"skills", text)
    presets = _extract_number_before(r"presets", text)
    return {
        "tools": tools,
        "commands": commands,
        "skills": skills,
        "presets": presets,
    }


def extract_tools_contract_counts(path: Path) -> dict[str, int | None]:
    """Extract tool count from TOOLS_CONTRACT.md."""
    text = path.read_text()
    tools = _extract_number_before(r"tools", text)
    return {
        "tools": tools,
        "commands": None,
        "skills": None,
        "presets": None,
    }


def extract_marketplace_counts(path: Path) -> dict[str, int | None]:
    """Extract tools_count from marketplace.json if present."""
    try:
        data = json.loads(path.read_text())
        # marketplace.json may have tools_count at plugin level
        for plugin in data.get("plugins", []):
            tc = plugin.get("tools_count")
            if tc is not None:
                return {"tools": tc, "commands": None, "skills": None, "presets": None}
    except (json.JSONDecodeError, KeyError):
        pass
    return {"tools": None, "commands": None, "skills": None, "presets": None}


def extract_mcpb_counts(path: Path) -> dict[str, int | None]:
    """Extract tools_count from mcpb.json if present."""
    try:
        data = json.loads(path.read_text())
        tc = data.get("tools_count")
        return {"tools": tc, "commands": None, "skills": None, "presets": None}
    except (json.JSONDecodeError, KeyError):
        return {"tools": None, "commands": None, "skills": None, "presets": None}


# ---------------------------------------------------------------------------
# Version checker
# ---------------------------------------------------------------------------

def check_versions(repo_root: Path) -> dict[str, str | None]:
    """Read version strings from all canonical locations."""
    versions: dict[str, str | None] = {}

    # pyproject.toml
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE)
        versions["pyproject.toml"] = m.group(1) if m else None
    else:
        versions["pyproject.toml"] = None

    # plugin.json
    plugin_json = repo_root / "plugin.json"
    if plugin_json.exists():
        try:
            data = json.loads(plugin_json.read_text())
            versions["plugin.json"] = data.get("version")
        except json.JSONDecodeError:
            versions["plugin.json"] = None
    else:
        versions["plugin.json"] = None

    # marketplace.json
    marketplace = repo_root / "marketplace.json"
    if marketplace.exists():
        try:
            data = json.loads(marketplace.read_text())
            for plugin in data.get("plugins", []):
                v = plugin.get("version")
                if v:
                    versions["marketplace.json"] = v
                    break
            else:
                versions["marketplace.json"] = None
        except json.JSONDecodeError:
            versions["marketplace.json"] = None
    else:
        versions["marketplace.json"] = None

    # mcpb.json
    mcpb = repo_root / "mcpb.json"
    if mcpb.exists():
        try:
            data = json.loads(mcpb.read_text())
            versions["mcpb.json"] = data.get("version")
        except json.JSONDecodeError:
            versions["mcpb.json"] = None
    else:
        versions["mcpb.json"] = None

    # __init__.py
    init = repo_root / "obsidian_connector" / "__init__.py"
    if init.exists():
        m = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text())
        versions["__init__.py"] = m.group(1) if m else None
    else:
        versions["__init__.py"] = None

    return versions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    # Source-of-truth counts
    mcp_tools = count_mcp_tools(repo_root / "obsidian_connector" / "mcp_server.py")
    cli_commands = count_cli_commands(repo_root / "obsidian_connector" / "cli.py")
    skills = count_skills(repo_root / "skills")
    presets = count_presets(repo_root / "obsidian_connector" / "vault_presets.py")

    print("Manifest Check Results")
    print("======================")
    print(f"MCP tools:    {mcp_tools} (mcp_server.py)")
    print(f"CLI commands: {cli_commands} (cli.py)")
    print(f"Skills:       {skills} (skills/)")
    print(f"Presets:      {presets} (vault_presets.py)")
    print()

    truth = {"tools": mcp_tools, "commands": cli_commands, "skills": skills, "presets": presets}

    # Documentation surfaces
    sources: list[tuple[str, dict[str, int | None]]] = []

    readme = repo_root / "README.md"
    if readme.exists():
        sources.append(("README.md", extract_readme_counts(readme)))

    claude_md = repo_root / "CLAUDE.md"
    if claude_md.exists():
        sources.append(("CLAUDE.md", extract_claude_md_counts(claude_md)))

    tools_contract = repo_root / "TOOLS_CONTRACT.md"
    if tools_contract.exists():
        sources.append(("TOOLS_CONTRACT", extract_tools_contract_counts(tools_contract)))

    marketplace = repo_root / "marketplace.json"
    if marketplace.exists():
        sources.append(("marketplace.json", extract_marketplace_counts(marketplace)))

    mcpb = repo_root / "mcpb.json"
    if mcpb.exists():
        sources.append(("mcpb.json", extract_mcpb_counts(mcpb)))

    # Print comparison table
    header = f"{'Source':<20}| {'Tools':>5} | {'Commands':>8} | {'Skills':>6} | {'Presets':>7} | Status"
    print(header)
    print("-" * len(header))

    has_mismatch = False
    for name, counts in sources:
        status = "OK"
        for key in ("tools", "commands", "skills", "presets"):
            advertised = counts[key]
            if advertised is not None and advertised != truth[key]:
                status = "MISMATCH"
                has_mismatch = True
                break

        def _fmt(val: int | None) -> str:
            return str(val) if val is not None else "-"

        print(
            f"{name:<20}| {_fmt(counts['tools']):>5} | {_fmt(counts['commands']):>8} "
            f"| {_fmt(counts['skills']):>6} | {_fmt(counts['presets']):>7} | {status}"
        )

    # Version check
    print()
    print("Version Check")
    print("-------------")
    versions = check_versions(repo_root)
    version_values: set[str] = set()
    for file, ver in versions.items():
        tag = ver if ver else "(not found)"
        print(f"  {file:<20} {tag}")
        if ver is not None:
            version_values.add(ver)

    if len(version_values) == 0:
        print("Status: NO VERSIONS FOUND")
        has_mismatch = True
    elif len(version_values) == 1:
        print("Status: OK")
    else:
        print("Status: MISMATCH")
        has_mismatch = True

    print()
    if has_mismatch:
        print("RESULT: MISMATCH detected -- documentation is out of sync with code.")
        return 1
    else:
        print("RESULT: All counts and versions match.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
