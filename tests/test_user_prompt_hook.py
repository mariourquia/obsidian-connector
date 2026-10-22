"""UserPromptSubmit context transport, without Claude calls or vault access."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("surface", ["src", "builds/claude-code"])
@pytest.mark.parametrize("prompt", ["Fix this bug", "Side thought: someday build a flight planner"])
def test_user_prompt_hook_emits_guidance_without_blocking(
    surface: str, prompt: str, tmp_path: Path
) -> None:
    """The actual hook command transports trusted text, never user input."""
    hooks_dir = ROOT / surface / "hooks"
    config = json.loads((hooks_dir / "hooks.json").read_text())
    handler = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert handler["type"] == "command", "Prompt hooks cannot return additionalContext"

    plugin_root = tmp_path / "plugin with spaces; literal"
    (plugin_root / "hooks").mkdir(parents=True)
    guidance = "Synthetic trusted guidance: detect tangents in the main session.\n"
    (plugin_root / "hooks" / "idea_detect.md").write_text(guidance)
    result = subprocess.run(
        ["bash", "-c", handler["command"]],
        input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt}),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(plugin_root)},
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout == guidance
    assert result.stderr == ""
    assert sorted(p.relative_to(plugin_root).as_posix() for p in plugin_root.rglob("*")) == [
        "hooks", "hooks/idea_detect.md",
    ]


def test_user_prompt_hook_missing_guidance_is_not_a_block(tmp_path: Path) -> None:
    config = json.loads((ROOT / "src/hooks/hooks.json").read_text())
    handler = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert handler["type"] == "command"
    result = subprocess.run(
        ["bash", "-c", handler["command"]],
        input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "Fix this bug"}),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(tmp_path)},
        timeout=5,
    )
    assert result.returncode == 1  # Claude reports a nonblocking hook error, not exit 2.
    assert result.stdout == ""


def test_shipped_hook_matches_source() -> None:
    source = json.loads((ROOT / "src/hooks/hooks.json").read_text())
    built = json.loads((ROOT / "builds/claude-code/hooks/hooks.json").read_text())
    assert built == source


def test_guidance_keeps_capture_in_the_main_session() -> None:
    guidance = (ROOT / "src/hooks/idea_detect.md").read_text()
    assert "obsidian_float_idea" in guidance
    assert "obsidian_incubate_project" in guidance
    assert "Do NOT capture" in guidance
