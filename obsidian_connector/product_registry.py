"""Single source of truth for obsidian-connector product metadata.

Every count, version, and surface capability is derived from code and
filesystem -- never hardcoded.  Other scripts and docs reference this
module (or its generated output) rather than maintaining their own
copies of these numbers.

Usage::

    from obsidian_connector.product_registry import get_registry
    reg = get_registry()
    print(reg.version)           # "0.7.0"
    print(reg.mcp_tool_count)    # 62
    print(reg.skill_registry)    # [{id: "morning", ...}, ...]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Return the repo root (parent of obsidian_connector/)."""
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Core counts -- derived from code, never hardcoded
# ---------------------------------------------------------------------------

def count_mcp_tools(repo: Path | None = None) -> int:
    """Count @mcp.tool() decorators in mcp_server.py."""
    root = repo or _repo_root()
    path = root / "obsidian_connector" / "mcp_server.py"
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count("@mcp.tool")


def count_cli_subcommands(repo: Path | None = None) -> int:
    """Count leaf CLI subcommands (add_parser calls in cli.py)."""
    root = repo or _repo_root()
    path = root / "obsidian_connector" / "cli.py"
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count("add_parser")


def count_cli_top_level(repo: Path | None = None) -> int:
    """Count top-level CLI command groups (first-level add_parser only).

    This excludes sub-subcommands like 'graduate list', 'drafts approve', etc.
    Uses heuristic: lines matching `sub.add_parser` (the root subparsers object).
    """
    root = repo or _repo_root()
    path = root / "obsidian_connector" / "cli.py"
    if not path.is_file():
        return 0
    content = path.read_text(encoding="utf-8")
    # Top-level subparsers are added to `sub` (the root subparser group)
    # Sub-subparsers use different variable names (e.g., grad_sub, drafts_sub)
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("p = sub.add_parser") or stripped.startswith("sub.add_parser"):
            count += 1
        # Also count group commands that use sub.add_parser but assign to different var
        elif "= sub.add_parser" in stripped and "sub_sub" not in stripped:
            count += 1
    return count


def count_skills(repo: Path | None = None) -> int:
    """Count skill directories that contain SKILL.md."""
    root = repo or _repo_root()
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return 0
    return len(list(skills_dir.glob("*/SKILL.md")))


def count_portable_skills(repo: Path | None = None) -> int:
    """Count portable skill bundles."""
    root = repo or _repo_root()
    portable = root / "portable" / "skills"
    if not portable.is_dir():
        portable = root / "portable"
    if not portable.is_dir():
        return 0
    # Count directories with skill files
    count = 0
    for entry in portable.iterdir():
        if entry.is_dir() and any(entry.glob("*.md")):
            count += 1
    return count


def count_presets(repo: Path | None = None) -> int:
    """Count vault presets (VaultPreset instances in vault_presets.py)."""
    root = repo or _repo_root()
    path = root / "obsidian_connector" / "vault_presets.py"
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count("VaultPreset(")


def count_modules(repo: Path | None = None) -> int:
    """Count Python modules in obsidian_connector/."""
    root = repo or _repo_root()
    pkg = root / "obsidian_connector"
    if not pkg.is_dir():
        return 0
    return len([f for f in pkg.glob("*.py")])


def get_version(repo: Path | None = None) -> str:
    """Read version from pyproject.toml (source of truth)."""
    root = repo or _repo_root()
    path = root / "pyproject.toml"
    if not path.is_file():
        return "0.0.0"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------

@dataclass
class SkillEntry:
    """Metadata for a single skill."""
    id: str
    display_name: str
    group: str  # "workflow" | "knowledge" | "capture" | "ritual" | "vault" | "sync"
    aliases: list[str] = field(default_factory=list)
    requires_mcp: bool = False
    requires_binary: bool = False
    supported_surfaces: list[str] = field(default_factory=lambda: ["claude-code-plugin"])


def build_skill_registry(repo: Path | None = None) -> list[SkillEntry]:
    """Build skill registry from skills/ directory."""
    root = repo or _repo_root()
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return []

    registry = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        skill_id = skill_dir.name
        content = skill_md.read_text(encoding="utf-8", errors="replace")

        # Extract name from frontmatter
        display_name = skill_id.replace("-", " ").title()
        for line in content.splitlines()[:20]:
            if line.startswith("name:"):
                display_name = line.split(":", 1)[1].strip().strip('"').strip("'")
                break

        # Classify group
        knowledge_skills = {"obsidian-markdown", "obsidian-bases", "json-canvas", "obsidian-cli", "defuddle"}
        capture_skills = {"idea", "float", "capture"}
        ritual_skills = {"morning", "evening", "weekly", "ritual"}
        vault_skills = {"init-vault", "explore", "new-vault"}
        sync_skills = {"sync-vault", "sync"}

        if skill_id in knowledge_skills:
            group = "knowledge"
        elif skill_id in capture_skills:
            group = "capture"
        elif skill_id in ritual_skills:
            group = "ritual"
        elif skill_id in vault_skills:
            group = "vault"
        elif skill_id in sync_skills:
            group = "sync"
        else:
            group = "workflow"

        # Determine surfaces
        surfaces = ["claude-code-plugin"]
        if skill_id in knowledge_skills:
            surfaces.append("portable")

        # Check if skill needs MCP (workflow skills generally do)
        requires_mcp = group in ("workflow", "capture", "ritual", "vault", "sync")

        registry.append(SkillEntry(
            id=skill_id,
            display_name=display_name,
            group=group,
            requires_mcp=requires_mcp,
            requires_binary=requires_mcp,  # MCP skills need Obsidian binary
            supported_surfaces=surfaces,
        ))

    return registry


# ---------------------------------------------------------------------------
# Surface registry
# ---------------------------------------------------------------------------

@dataclass
class SurfaceEntry:
    """Metadata for a distribution surface."""
    id: str
    display_name: str
    install_method: str
    what_user_gets: str
    limitations: str
    os_support: dict[str, str]  # {"macos": "full", "linux": "full", "windows": "partial"}


SURFACE_REGISTRY: list[SurfaceEntry] = [
    SurfaceEntry(
        id="claude-code-plugin",
        display_name="Claude Code Plugin",
        install_method="claude plugin install obsidian-connector",
        what_user_gets="Skills + hooks + MCP tools",
        limitations="Requires Python venv setup via scripts/setup.sh",
        os_support={"macos": "full", "linux": "full", "windows": "partial (Unix venv paths)"},
    ),
    SurfaceEntry(
        id="claude-desktop",
        display_name="Claude Desktop MCP",
        install_method="scripts/install.sh or manual claude_desktop_config.json",
        what_user_gets="MCP tools only (no skills/hooks)",
        limitations="No slash commands, no session hooks",
        os_support={"macos": "full", "linux": "full", "windows": "full"},
    ),
    SurfaceEntry(
        id="macos-dmg",
        display_name="macOS DMG Installer",
        install_method="Download from GitHub Releases",
        what_user_gets="Double-click installer (configures Claude Desktop)",
        limitations="macOS only, MCP tools only",
        os_support={"macos": "full", "linux": "n/a", "windows": "n/a"},
    ),
    SurfaceEntry(
        id="windows-exe",
        display_name="Windows EXE Installer",
        install_method="Download from GitHub Releases",
        what_user_gets="Inno Setup installer (Python venv + Claude registration)",
        limitations="Requires Python 3.11+ pre-installed",
        os_support={"macos": "n/a", "linux": "n/a", "windows": "full"},
    ),
    SurfaceEntry(
        id="cli",
        display_name="CLI (obsx)",
        install_method="pip install -e . then obsx",
        what_user_gets="All CLI subcommands with --json and --vault flags",
        limitations="No MCP integration, no skills",
        os_support={"macos": "full", "linux": "full", "windows": "full"},
    ),
    SurfaceEntry(
        id="python-api",
        display_name="Python API",
        install_method="from obsidian_connector import ...",
        what_user_gets="Programmatic vault access",
        limitations="No CLI or MCP, developer-only",
        os_support={"macos": "full", "linux": "full", "windows": "full"},
    ),
    SurfaceEntry(
        id="portable",
        display_name="Portable Skills",
        install_method="Copy portable/ to agent skills directory",
        what_user_gets="Knowledge skills for Codex CLI, OpenCode, Gemini CLI",
        limitations="Knowledge skills only, no vault operations",
        os_support={"macos": "full", "linux": "full", "windows": "full"},
    ),
]


# ---------------------------------------------------------------------------
# Full registry
# ---------------------------------------------------------------------------

@dataclass
class ProductRegistry:
    """Complete product metadata, derived from code."""
    version: str
    mcp_tool_count: int
    cli_subcommand_count: int
    cli_top_level_count: int
    skill_count: int
    portable_skill_count: int
    preset_count: int
    module_count: int
    skill_registry: list[SkillEntry]
    surface_registry: list[SurfaceEntry]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "version": self.version,
            "mcp_tool_count": self.mcp_tool_count,
            "cli_subcommand_count": self.cli_subcommand_count,
            "cli_top_level_count": self.cli_top_level_count,
            "skill_count": self.skill_count,
            "portable_skill_count": self.portable_skill_count,
            "preset_count": self.preset_count,
            "module_count": self.module_count,
            "skills": [
                {
                    "id": s.id, "display_name": s.display_name,
                    "group": s.group, "aliases": s.aliases,
                    "requires_mcp": s.requires_mcp,
                    "supported_surfaces": s.supported_surfaces,
                }
                for s in self.skill_registry
            ],
            "surfaces": [
                {
                    "id": s.id, "display_name": s.display_name,
                    "install_method": s.install_method,
                    "what_user_gets": s.what_user_gets,
                    "os_support": s.os_support,
                }
                for s in self.surface_registry
            ],
        }


def get_registry(repo: Path | None = None) -> ProductRegistry:
    """Build the complete product registry from code and filesystem."""
    root = repo or _repo_root()
    return ProductRegistry(
        version=get_version(root),
        mcp_tool_count=count_mcp_tools(root),
        cli_subcommand_count=count_cli_subcommands(root),
        cli_top_level_count=count_cli_top_level(root),
        skill_count=count_skills(root),
        portable_skill_count=count_portable_skills(root),
        preset_count=count_presets(root),
        module_count=count_modules(root),
        skill_registry=build_skill_registry(root),
        surface_registry=SURFACE_REGISTRY,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    reg = get_registry()
    print(json.dumps(reg.to_dict(), indent=2))
