#!/usr/bin/env python3
"""Generate a Markdown compatibility matrix for obsidian-connector.

Shows which features (tools, commands, skills) are available on which
distribution surface (MCP, CLI, Python API, Portable).

Usage:
    python3 scripts/generate_compat_matrix.py

Output:
    Writes docs/references/compatibility-matrix.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def parse_mcp_tool_names(path: Path) -> list[str]:
    """Extract MCP tool function names from mcp_server.py.

    Looks for def statements immediately following @mcp.tool() decorators.
    Returns function names with the 'obsidian_' prefix stripped.
    """
    text = path.read_text()
    # Match function defs that are MCP tools (preceded by @mcp.tool block)
    names: list[str] = []
    for m in re.finditer(r"@mcp\.tool\([^)]*\)\s*\n(?:.*\n)*?def\s+(obsidian_\w+|_\w+)\(", text):
        raw = m.group(1)
        # Strip obsidian_ prefix for display
        name = raw.removeprefix("obsidian_")
        names.append(name)

    # Fallback: if regex above misses tools due to multi-line decorators,
    # parse more aggressively
    if not names:
        lines = text.splitlines()
        in_decorator = False
        for line in lines:
            if "@mcp.tool(" in line:
                in_decorator = True
            elif in_decorator and line.strip().startswith("def "):
                fn_match = re.match(r"\s*def\s+(\w+)\(", line)
                if fn_match:
                    raw = fn_match.group(1)
                    name = raw.removeprefix("obsidian_")
                    names.append(name)
                in_decorator = False
            elif in_decorator and line.strip() and not line.strip().startswith((")", "#", "@")):
                # Still inside decorator arguments
                pass
    return sorted(set(names))


def parse_cli_command_names(path: Path) -> list[str]:
    """Extract CLI command names from cli.py (add_parser calls)."""
    text = path.read_text()
    names: list[str] = []
    for m in re.finditer(r'\.add_parser\(\s*"([^"]+)"', text):
        names.append(m.group(1))
    return sorted(set(names))


def parse_skill_names(path: Path) -> list[str]:
    """Get skill slugs from skills/ directory."""
    if not path.is_dir():
        return []
    return sorted(
        d.name for d in path.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def parse_portable_skill_names(path: Path) -> list[str]:
    """Get skill slugs from portable/skills/ directory."""
    skills_dir = path / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def parse_python_api_names(path: Path) -> list[str]:
    """Extract public API function/class names from __init__.py __all__."""
    text = path.read_text()
    m = re.search(r"__all__\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not m:
        return []
    names: list[str] = []
    for item in re.findall(r'"(\w+)"', m.group(1)):
        # Skip exception classes, dataclasses, and utility names
        if item[0].isupper():
            continue
        names.append(item)
    return sorted(set(names))


def _normalize(name: str) -> str:
    """Normalize a feature name for comparison: lowercase, strip hyphens/underscores."""
    return name.lower().replace("-", "_")


def generate_matrix(repo_root: Path) -> str:
    """Build the full compatibility matrix as a Markdown string."""
    mcp_tools = parse_mcp_tool_names(repo_root / "obsidian_connector" / "mcp_server.py")
    cli_commands = parse_cli_command_names(repo_root / "obsidian_connector" / "cli.py")
    skills = parse_skill_names(repo_root / "skills")
    portable = parse_portable_skill_names(repo_root / "portable")
    python_api = parse_python_api_names(repo_root / "obsidian_connector" / "__init__.py")

    # Build normalized lookup sets
    mcp_set = {_normalize(n) for n in mcp_tools}
    cli_set = {_normalize(n) for n in cli_commands}
    skill_set = {_normalize(n) for n in skills}
    portable_set = {_normalize(n) for n in portable}
    api_set = {_normalize(n) for n in python_api}

    # Collect all unique feature names
    all_features: set[str] = set()
    all_features.update(mcp_set)
    all_features.update(cli_set)
    all_features.update(skill_set)
    all_features.update(portable_set)

    lines: list[str] = []
    lines.append("# Compatibility Matrix")
    lines.append("")
    lines.append("Which features are available on which distribution surface.")
    lines.append("")
    lines.append(f"Generated from code. MCP: {len(mcp_tools)} tools, "
                 f"CLI: {len(cli_commands)} commands, "
                 f"Skills: {len(skills)}, "
                 f"Portable: {len(portable)}, "
                 f"Python API: {len(python_api)} exports.")
    lines.append("")
    lines.append("| Feature | MCP | CLI | Python API | Portable |")
    lines.append("|---------|-----|-----|------------|----------|")

    for feature in sorted(all_features):
        in_mcp = "yes" if feature in mcp_set else "-"
        in_cli = "yes" if feature in cli_set else "-"
        in_api = "yes" if feature in api_set else "-"
        in_portable = "yes" if feature in portable_set else "-"
        lines.append(f"| {feature} | {in_mcp} | {in_cli} | {in_api} | {in_portable} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "docs" / "references"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "compatibility-matrix.md"

    matrix = generate_matrix(repo_root)
    output_path.write_text(matrix)

    print(f"Compatibility matrix written to {output_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
