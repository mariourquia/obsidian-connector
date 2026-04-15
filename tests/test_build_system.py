"""Build system tests: golden, snapshot, and negative tests.

Requires builds to exist. Run `npx tsx tools/build.ts --target all` first
(excluding pypi, which needs python -m build).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / "builds"
SRC = ROOT / "src"
CONFIG = ROOT / "config"


def has_builds(*targets: str) -> bool:
    return all((BUILDS / t).is_dir() for t in targets)


# ── Golden tests ──────────────────────────────────────────────────────


class TestGoldenClaudeCode:
    """claude-code build must have all 17 skills, hooks, manifest, MCP config."""

    pytestmark = pytest.mark.skipif(
        not has_builds("claude-code"), reason="claude-code build missing"
    )

    def test_all_17_skills_present(self):
        skills_dir = BUILDS / "claude-code" / "skills"
        skills = [
            d.name
            for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]
        assert len(skills) == 17, f"Expected 17 skills, got {len(skills)}: {skills}"

    def test_hooks_json_present_and_valid(self):
        hooks_file = BUILDS / "claude-code" / "hooks" / "hooks.json"
        assert hooks_file.exists()
        data = json.loads(hooks_file.read_text())
        assert "hooks" in data
        assert "SessionStart" in data["hooks"]
        assert "Stop" in data["hooks"]

    def test_hook_scripts_present(self):
        hooks_dir = BUILDS / "claude-code" / "hooks"
        assert (hooks_dir / "session_start.sh").exists()
        assert (hooks_dir / "session_stop.sh").exists()
        assert (hooks_dir / "idea_detect.md").exists()

    def test_plugin_json_present(self):
        pj = BUILDS / "claude-code" / ".claude-plugin" / "plugin.json"
        assert pj.exists()
        data = json.loads(pj.read_text())
        assert data["name"] == "obsidian-connector"
        assert "version" in data
        assert "description" in data

    def test_mcp_config_present(self):
        mcp = BUILDS / "claude-code" / ".mcp.json"
        assert mcp.exists()
        data = json.loads(mcp.read_text())
        assert "mcpServers" in data
        assert "obsidian-connector" in data["mcpServers"]

    def test_python_package_present(self):
        init = BUILDS / "claude-code" / "obsidian_connector" / "__init__.py"
        assert init.exists()

    def test_bin_wrappers_present(self):
        assert (BUILDS / "claude-code" / "bin" / "obsx").exists()
        assert (BUILDS / "claude-code" / "bin" / "obsx-mcp").exists()


class TestGoldenClaudeDesktop:
    """claude-desktop build: MCP config + Python, no skills or hooks."""

    pytestmark = pytest.mark.skipif(
        not has_builds("claude-desktop"), reason="claude-desktop build missing"
    )

    def test_no_skills_directory(self):
        assert not (BUILDS / "claude-desktop" / "skills").exists()

    def test_no_hooks_directory(self):
        assert not (BUILDS / "claude-desktop" / "hooks").exists()

    def test_python_package_present(self):
        assert (BUILDS / "claude-desktop" / "obsidian_connector" / "__init__.py").exists()

    def test_mcp_config_snippet_valid(self):
        snippet = BUILDS / "claude-desktop" / "claude_desktop_config_snippet.json"
        assert snippet.exists()
        data = json.loads(snippet.read_text())
        assert "mcpServers" in data
        server = data["mcpServers"]["obsidian-connector"]
        assert "command" in server
        assert "args" in server


class TestGoldenPortable:
    """portable build: exactly 5 skills, no MCP references."""

    pytestmark = pytest.mark.skipif(
        not has_builds("portable"), reason="portable build missing"
    )

    EXPECTED_PORTABLE = {
        "obsidian-markdown",
        "obsidian-bases",
        "json-canvas",
        "obsidian-cli",
        "defuddle",
    }

    NON_PORTABLE = {
        "morning", "evening", "weekly", "idea", "ritual",
        "capture", "float", "explore", "sync", "sync-vault",
        "new-vault", "init-vault",
    }

    def test_exactly_5_portable_skills(self):
        skills_dir = BUILDS / "portable" / "skills"
        skills = {d.name for d in skills_dir.iterdir() if d.is_dir()}
        assert skills == self.EXPECTED_PORTABLE

    def test_no_workflow_skills_present(self):
        skills_dir = BUILDS / "portable" / "skills"
        present = {d.name for d in skills_dir.iterdir() if d.is_dir()}
        leaked = present & self.NON_PORTABLE
        assert not leaked, f"Workflow skills leaked into portable: {leaked}"

    def test_no_mcp_tool_references(self):
        """No portable skill should reference obsidian_* MCP tools."""
        pattern = re.compile(r"\bobsidian_\w+")
        skills_dir = BUILDS / "portable" / "skills"
        violations = []
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                content = skill_file.read_text()
                matches = pattern.findall(content)
                if matches:
                    violations.append((skill_dir.name, matches))
        assert not violations, f"MCP refs in portable skills: {violations}"

    def test_portable_header_present(self):
        for skill in self.EXPECTED_PORTABLE:
            content = (BUILDS / "portable" / "skills" / skill / "SKILL.md").read_text()
            assert "Portable skill" in content, f"{skill} missing portable header"

    def test_readme_present(self):
        assert (BUILDS / "portable" / "README.md").exists()

    def test_reference_files_copied(self):
        """Skills with references/ dirs should have them in the build."""
        refs = BUILDS / "portable" / "skills" / "obsidian-markdown" / "references"
        assert refs.is_dir()
        assert (refs / "CALLOUTS.md").exists()


# ── Version consistency ───────────────────────────────────────────────


class TestVersionConsistency:
    """All version sources must agree."""

    def test_versions_match(self):
        sources = {}

        # pyproject.toml
        pyproject = ROOT / "pyproject.toml"
        m = re.search(r'version\s*=\s*"([^"]+)"', pyproject.read_text())
        if m:
            sources["pyproject.toml"] = m.group(1)

        # plugin.json
        pj = SRC / "plugin" / "plugin.json"
        if pj.exists():
            sources["plugin.json"] = json.loads(pj.read_text())["version"]

        # product_registry.py
        pr = ROOT / "obsidian_connector" / "product_registry.py"
        if pr.exists():
            m = re.search(r'__version__\s*=\s*"([^"]+)"', pr.read_text())
            if m:
                sources["product_registry.py"] = m.group(1)

        # marketplace.json
        mj = ROOT / "marketplace.json"
        if mj.exists():
            sources["marketplace.json"] = json.loads(mj.read_text())["version"]

        # mcpb.json
        mcpb = ROOT / "mcpb.json"
        if mcpb.exists():
            sources["mcpb.json"] = json.loads(mcpb.read_text())["version"]

        versions = set(sources.values())
        assert len(versions) == 1, f"Version mismatch: {sources}"


# ── Snapshot tests ────────────────────────────────────────────────────


SNAPSHOTS = ROOT / "tests" / "snapshots"


class TestSnapshots:
    """Build output must match known-good snapshots."""

    pytestmark = pytest.mark.skipif(
        not has_builds("claude-code", "portable"), reason="builds missing"
    )

    def test_portable_defuddle_matches_snapshot(self):
        built = (BUILDS / "portable" / "skills" / "defuddle" / "SKILL.md").read_text()
        snapshot = (SNAPSHOTS / "portable_defuddle_SKILL.md").read_text()
        assert built == snapshot, "portable/defuddle/SKILL.md drifted from snapshot"

    def test_claude_code_plugin_json_matches_snapshot(self):
        built = json.loads(
            (BUILDS / "claude-code" / ".claude-plugin" / "plugin.json").read_text()
        )
        snapshot = json.loads(
            (SNAPSHOTS / "claude_code_plugin.json").read_text()
        )
        assert built == snapshot, "plugin.json drifted from snapshot"


# ── Negative tests ────────────────────────────────────────────────────


class TestNegativeValidation:
    """Build system should reject malformed input."""

    def test_unknown_target_rejected(self):
        result = subprocess.run(
            ["npx", "tsx", "tools/validate.ts", "--target", "nonexistent"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_skill_portability_config_valid(self):
        """All skills in portability config must exist in src/skills/."""
        import yaml

        config = yaml.safe_load(
            (CONFIG / "defaults" / "skill-portability.yaml").read_text()
        )
        src_skills = {d.name for d in (SRC / "skills").iterdir() if d.is_dir()}
        for skill in config["portable_skills"] + config["non_portable_skills"]:
            assert skill in src_skills, f"Skill '{skill}' in portability config but not in src/skills/"

    def test_all_source_skills_classified(self):
        """Every skill in src/skills/ must appear in the portability config."""
        import yaml

        config = yaml.safe_load(
            (CONFIG / "defaults" / "skill-portability.yaml").read_text()
        )
        classified = set(config["portable_skills"] + config["non_portable_skills"])
        src_skills = {d.name for d in (SRC / "skills").iterdir() if d.is_dir()}
        unclassified = src_skills - classified
        assert not unclassified, f"Skills not classified in portability config: {unclassified}"


class TestWindowsPackaging:
    """Windows packaging should use the shared packager and trim Ix dev-only files."""

    def test_windows_workflow_uses_shared_packager(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows-installer.yml").read_text()
        assert r".\scripts\build-windows-installer.ps1" in workflow
        assert "tools/build.ts --target claude-desktop" in workflow
        assert r"scripts\create-exe.iss" not in workflow

    def test_release_workflow_builds_claude_desktop_before_windows_packaging(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        assert "tools/build.ts --target claude-desktop" in workflow
        assert "tools/validate.ts --target claude-desktop" in workflow

    def test_shared_packager_excludes_ix_dev_only_paths(self):
        script = (ROOT / "scripts" / "build-windows-installer.ps1").read_text()
        for path in (
            r"ix_engine\core-ingestion\src",
            r"ix_engine\core-ingestion\test-fixtures",
            r"ix_engine\core-ingestion\node_modules\.bin",
            r"ix_engine\ix-cli\src",
            r"ix_engine\ix-cli\scripts",
            r"ix_engine\ix-cli\test",
            r"ix_engine\ix-cli\node_modules\.bin",
        ):
            assert path in script

    def test_shared_packager_uses_build_outputs_directly_when_available(self):
        script = (ROOT / "scripts" / "build-windows-installer.ps1").read_text()
        assert "Using built artifacts directly from builds\\claude-desktop\\" in script
        assert r"Join-Path $BuildDir 'obsidian_connector\*'" in script
        assert r"Join-Path $RepoRoot 'scripts\*'" in script

    def test_shared_packager_uses_faster_ci_compression_profile(self):
        script = (ROOT / "scripts" / "build-windows-installer.ps1").read_text()
        assert "Compression=zip" in script
        assert "SolidCompression=no" in script
