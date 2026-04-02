#!/usr/bin/env python3
"""Validate counts, versions, tool coverage, and skill completeness across all
user-facing files.

Uses ``obsidian_connector.product_registry`` as the single source of truth.
Every number advertised in README.md, CLAUDE.md, AGENTS.md, ARCHITECTURE.md,
TOOLS_CONTRACT.md, docs/*, Install.command, portable/README.md,
scheduling/README.md, marketplace.json, mcpb.json, and plugin.json is checked
against the registry.

Usage::

    python3 scripts/manifest_check.py

Exit codes:
    0 -- all checks pass
    1 -- at least one mismatch detected

Importable API::

    from scripts.manifest_check import run_checks
    result = run_checks()          # returns structured dict
    assert result["pass"] is True
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: ensure repo root is on sys.path so we can import the registry
# even when invoked as ``python3 scripts/manifest_check.py``.
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from obsidian_connector.product_registry import get_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_all_ints(pattern: str, text: str) -> list[int]:
    """Return all integers captured by group(1) of *pattern* in *text*."""
    return [int(m.group(1)) for m in re.finditer(pattern, text)]


def _first_int(pattern: str, text: str) -> int | None:
    """Return the first integer captured by group(1), or None."""
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def _extract_mcp_func_names(repo: Path) -> set[str]:
    """Extract every function name directly following an @mcp.tool decorator."""
    path = repo / "obsidian_connector" / "mcp_server.py"
    if not path.is_file():
        return set()
    content = path.read_text(encoding="utf-8")
    names: set[str] = set()
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        if "@mcp.tool" in lines[i]:
            # Scan forward past the decorator (may span multiple lines) to
            # the def line.
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("def "):
                j += 1
            if j < len(lines):
                m = re.match(r"\s*def\s+(\w+)\s*\(", lines[j])
                if m:
                    names.add(m.group(1))
            i = j + 1
        else:
            i += 1
    return names


def _extract_contract_tool_names(repo: Path) -> set[str]:
    """Extract every tool name listed in TOOLS_CONTRACT.md table rows."""
    path = repo / "TOOLS_CONTRACT.md"
    if not path.is_file():
        return set()
    content = path.read_text(encoding="utf-8")
    # Match table rows like: | `obsidian_search` | ...
    return set(re.findall(r"\|\s*`(obsidian_\w+)`\s*\|", content))


# ---------------------------------------------------------------------------
# File-level count checks
# ---------------------------------------------------------------------------

# Each entry: (relative_path, list of (regex_pattern, asset_key) tuples)
# asset_key maps to a ProductRegistry field name.
FILE_COUNT_SPECS: list[tuple[str, list[tuple[str, str]]]] = [
    ("README.md", [
        (r"(\d+)\s+MCP\s+tools", "mcp_tool_count"),
        (r"(\d+)\s+CLI\s+commands", "cli_subcommand_count"),
        (r"(\d+)\s+skills", "skill_count"),
        (r"(\d+)\s+(?:vault\s+)?presets", "preset_count"),
    ]),
    ("CLAUDE.md", [
        (r"(\d+)\s+tools", "mcp_tool_count"),
        (r"(\d+)\s+commands", "cli_subcommand_count"),
    ]),
    ("AGENTS.md", [
        (r"(\d+)\s+MCP\s+tools", "mcp_tool_count"),
        (r"(\d+)\s+CLI\s+subcommands", "cli_subcommand_count"),
        (r"(\d+)\s+(?:Claude\s+Code\s+)?(?:plugin\s+)?skills", "skill_count"),
    ]),
    ("ARCHITECTURE.md", [
        (r"(\d+)\s+tools\s+for\s+Claude", "mcp_tool_count"),
        (r"(\d+)\s+argparse\s+subcommands", "cli_subcommand_count"),
        (r"(\d+)\s+skills", "skill_count"),
        (r"(\d+)\s+modules", "module_count"),
    ]),
    ("TOOLS_CONTRACT.md", [
        (r"(\d+)\s+tools\s+are\s+available", "mcp_tool_count"),
        (r"Commands\s+\((\d+)\s+total\)", "cli_subcommand_count"),
    ]),
    ("docs/setup-guide.md", [
        (r"(\d+)\s+(?:MCP\s+)?tools", "mcp_tool_count"),
        (r"(\d+)\s+skills", "skill_count"),
    ]),
    ("docs/second-brain-overview.md", [
        (r"(\d+)\s+skills", "skill_count"),
    ]),
    ("docs/daily-optimization.md", [
        (r"(\d+)\s+tools", "mcp_tool_count"),
    ]),
    ("Install.command", [
        (r"(\d+)\s+tools", "mcp_tool_count"),
    ]),
    ("portable/README.md", [
        (r"(\d+)\s+skills", "portable_skill_count"),
    ]),
    ("scheduling/README.md", [
        (r"(\d+)\s+tools", "mcp_tool_count"),
        (r"(\d+)\s+skills", "skill_count"),
    ]),
]

# JSON files with embedded counts checked separately.
JSON_COUNT_FILES: list[tuple[str, str, str]] = [
    # (relative_path, json_pointer_description, asset_key)
    ("mcpb.json", "tools_count", "mcp_tool_count"),
]


# ---------------------------------------------------------------------------
# Version parity files
# ---------------------------------------------------------------------------

VERSION_FILES: list[tuple[str, Any]] = [
    # (relative_path, extractor)
    # extractor is either a regex (applied to text) or a callable(json_data)->str|None
    ("pyproject.toml", re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)),
    (".claude-plugin/plugin.json", lambda d: d.get("version")),
    ("marketplace.json", lambda d: next(
        (p.get("version") for p in d.get("plugins", []) if p.get("version")), None
    )),
    ("mcpb.json", lambda d: d.get("version")),
    ("obsidian_connector/__init__.py", re.compile(r'__version__\s*=\s*"([^"]+)"')),
]


# ---------------------------------------------------------------------------
# Core check functions
# ---------------------------------------------------------------------------

def _check_file_counts(repo: Path, registry: Any) -> list[dict]:
    """Validate embedded counts in markdown / shell files."""
    results: list[dict] = []

    for relpath, patterns in FILE_COUNT_SPECS:
        fpath = repo / relpath
        if not fpath.is_file():
            results.append({
                "file": relpath,
                "status": "SKIP",
                "details": "file not found",
                "mismatches": [],
            })
            continue

        content = fpath.read_text(encoding="utf-8")
        mismatches: list[dict] = []
        checked: list[str] = []

        for pattern, key in patterns:
            expected = getattr(registry, key)
            found_values = _extract_all_ints(pattern, content)
            if not found_values:
                continue
            # Use the first match for the verdict
            found = found_values[0]
            label = key.replace("_", " ")
            checked.append(f"{label}={found}")
            if found != expected:
                mismatches.append({
                    "asset": key,
                    "found": found,
                    "expected": expected,
                })

        status = "OK" if not mismatches else "MISMATCH"
        results.append({
            "file": relpath,
            "status": status,
            "details": " ".join(checked) if checked else "(no counts found)",
            "mismatches": mismatches,
        })

    # JSON count files
    for relpath, json_key, asset_key in JSON_COUNT_FILES:
        fpath = repo / relpath
        if not fpath.is_file():
            results.append({
                "file": relpath,
                "status": "SKIP",
                "details": "file not found",
                "mismatches": [],
            })
            continue

        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results.append({
                "file": relpath,
                "status": "ERROR",
                "details": "invalid JSON",
                "mismatches": [],
            })
            continue

        found = data.get(json_key)
        expected = getattr(registry, asset_key)
        label = asset_key.replace("_", " ")
        if found is None:
            results.append({
                "file": relpath,
                "status": "SKIP",
                "details": f"{json_key} not present",
                "mismatches": [],
            })
        elif found != expected:
            results.append({
                "file": relpath,
                "status": "MISMATCH",
                "details": f"{label}={found}",
                "mismatches": [{"asset": asset_key, "found": found, "expected": expected}],
            })
        else:
            results.append({
                "file": relpath,
                "status": "OK",
                "details": f"{label}={found}",
                "mismatches": [],
            })

    return results


def _check_versions(repo: Path, registry: Any) -> list[dict]:
    """Validate that all version-bearing files match pyproject.toml."""
    expected = registry.version
    results: list[dict] = []

    for relpath, extractor in VERSION_FILES:
        fpath = repo / relpath
        if not fpath.is_file():
            results.append({
                "file": relpath,
                "version": None,
                "status": "SKIP",
            })
            continue

        content = fpath.read_text(encoding="utf-8")
        found: str | None = None

        if isinstance(extractor, re.Pattern):
            m = extractor.search(content)
            found = m.group(1) if m else None
        elif callable(extractor):
            try:
                data = json.loads(content)
                found = extractor(data)
            except (json.JSONDecodeError, Exception):
                found = None
        else:
            found = None

        if found is None:
            status = "SKIP"
        elif found == expected:
            status = "OK"
        else:
            status = "MISMATCH"

        results.append({
            "file": relpath,
            "version": found,
            "status": status,
        })

    return results


def _check_tool_contract(repo: Path, registry: Any) -> dict:
    """Validate every @mcp.tool function appears in TOOLS_CONTRACT.md."""
    code_tools = _extract_mcp_func_names(repo)
    contract_tools = _extract_contract_tool_names(repo)

    missing_from_contract = sorted(code_tools - contract_tools)
    extra_in_contract = sorted(contract_tools - code_tools)

    documented = len(code_tools) - len(missing_from_contract)
    total = len(code_tools)
    status = "OK" if not missing_from_contract else "MISMATCH"

    return {
        "total": total,
        "documented": documented,
        "missing_from_contract": missing_from_contract,
        "extra_in_contract": extra_in_contract,
        "status": status,
    }


def _check_skill_registry(repo: Path, registry: Any) -> dict:
    """Validate every skills/*/SKILL.md is represented in the skill registry."""
    skills_dir = repo / "skills"
    if not skills_dir.is_dir():
        return {
            "total_on_disk": 0,
            "total_in_registry": 0,
            "missing_from_registry": [],
            "extra_in_registry": [],
            "status": "SKIP",
        }

    disk_skills: set[str] = set()
    for entry in skills_dir.iterdir():
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            disk_skills.add(entry.name)

    registry_skills = {s.id for s in registry.skill_registry}

    missing = sorted(disk_skills - registry_skills)
    extra = sorted(registry_skills - disk_skills)

    status = "OK" if not missing else "MISMATCH"

    return {
        "total_on_disk": len(disk_skills),
        "total_in_registry": len(registry_skills),
        "missing_from_registry": missing,
        "extra_in_registry": extra,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_checks(repo_root: Path | None = None) -> dict:
    """Run all manifest checks and return a structured result dict.

    Parameters
    ----------
    repo_root : Path, optional
        Override the repo root (defaults to parent of scripts/).

    Returns
    -------
    dict with keys:
        pass (bool), registry (dict), file_checks (list), version_checks (list),
        tool_contract (dict), skill_registry (dict)
    """
    root = repo_root or REPO_ROOT
    reg = get_registry(root)

    file_results = _check_file_counts(root, reg)
    version_results = _check_versions(root, reg)
    tool_contract = _check_tool_contract(root, reg)
    skill_reg = _check_skill_registry(root, reg)

    all_pass = (
        all(r["status"] in ("OK", "SKIP") for r in file_results)
        and all(r["status"] in ("OK", "SKIP") for r in version_results)
        and tool_contract["status"] in ("OK", "SKIP")
        and skill_reg["status"] in ("OK", "SKIP")
    )

    return {
        "pass": all_pass,
        "registry": {
            "version": reg.version,
            "mcp_tool_count": reg.mcp_tool_count,
            "cli_subcommand_count": reg.cli_subcommand_count,
            "cli_top_level_count": reg.cli_top_level_count,
            "skill_count": reg.skill_count,
            "portable_skill_count": reg.portable_skill_count,
            "preset_count": reg.preset_count,
            "module_count": reg.module_count,
        },
        "file_checks": file_results,
        "version_checks": version_results,
        "tool_contract": tool_contract,
        "skill_registry": skill_reg,
    }


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def _print_results(result: dict) -> None:
    """Print human-readable output matching the spec."""
    reg = result["registry"]

    print("obsidian-connector Manifest Check")
    print("==================================")
    print("Source of truth (from code):")
    print(f"  Version:          {reg['version']}")
    print(f"  MCP tools:        {reg['mcp_tool_count']}")
    print(f"  CLI subcommands:  {reg['cli_subcommand_count']}")
    print(f"  CLI top-level:    {reg['cli_top_level_count']}")
    print(f"  Skills:           {reg['skill_count']}")
    print(f"  Portable skills:  {reg['portable_skill_count']}")
    print(f"  Presets:          {reg['preset_count']}")
    print(f"  Modules:          {reg['module_count']}")
    print()

    # -- File checks --
    print("File Checks:")
    max_name = max(len(r["file"]) for r in result["file_checks"]) if result["file_checks"] else 20
    for r in result["file_checks"]:
        name = r["file"].ljust(max_name)
        details = r["details"]
        status = r["status"]
        if status == "MISMATCH":
            mismatch_detail = ", ".join(
                f"{m['asset'].replace('_', ' ')} found={m['found']} expected={m['expected']}"
                for m in r["mismatches"]
            )
            print(f"  {name}  {details:<50s}  MISMATCH ({mismatch_detail})")
        else:
            print(f"  {name}  {details:<50s}  {status}")
    print()

    # -- Version checks --
    print("Version Checks:")
    expected_ver = reg["version"]
    for r in result["version_checks"]:
        name = r["file"].ljust(max_name)
        ver = r["version"] if r["version"] else "(not found)"
        status = r["status"]
        if status == "MISMATCH":
            print(f"  {name}  {ver:<12s}  MISMATCH (expected {expected_ver})")
        else:
            print(f"  {name}  {ver:<12s}  {status}")
    print()

    # -- Tool contract --
    tc = result["tool_contract"]
    print("Tool Contract Completeness:")
    print(f"  {tc['documented']}/{tc['total']} tools documented" + (" " * 30) + f"  {tc['status']}")
    if tc["missing_from_contract"]:
        print(f"  Missing from contract: {', '.join(tc['missing_from_contract'])}")
    else:
        print("  Missing from contract: (none)")
    if tc["extra_in_contract"]:
        print(f"  Extra in contract (not in code): {', '.join(tc['extra_in_contract'])}")
    print()

    # -- Skill registry --
    sr = result["skill_registry"]
    print("Skill Registry Completeness:")
    print(
        f"  {sr['total_in_registry']}/{sr['total_on_disk']} skills registered"
        + (" " * 30) + f"  {sr['status']}"
    )
    if sr["missing_from_registry"]:
        print(f"  Missing from registry: {', '.join(sr['missing_from_registry'])}")
    else:
        print("  Missing from registry: (none)")
    print()

    # -- Final verdict --
    if result["pass"]:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    result = run_checks()
    _print_results(result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
