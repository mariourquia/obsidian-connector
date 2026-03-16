#!/usr/bin/env python3
"""Headless scheduled runner for obsidian-connector.

Calls Python API directly (no LLM needed). Writes structured output
to the daily note and sends a desktop notification (cross-platform).

Usage:
    python3 scheduling/run_scheduled.py morning
    python3 scheduling/run_scheduled.py evening
    python3 scheduling/run_scheduled.py weekly
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.client import ObsidianCLIError, log_to_daily
from obsidian_connector.workflows import (
    close_day_reflection,
    detect_delegations,
    graduate_candidates,
    list_open_loops,
    today_brief,
)


def _load_config() -> dict:
    """Load schedule config from default locations.

    Falls back to built-in defaults if pyyaml is not installed or
    the YAML file is malformed.
    """
    candidates = [
        Path.home() / ".config" / "obsidian-connector" / "schedule.yaml",
        Path(__file__).resolve().parent / "config.yaml",
    ]
    for path in candidates:
        if path.exists():
            try:
                import yaml
                with open(path) as f:
                    return yaml.safe_load(f) or {}
            except ImportError:
                # pyyaml not installed -- use defaults
                return {}
            except Exception as exc:
                print(f"Warning: failed to parse {path}: {exc}", file=sys.stderr)
                return {}
    return {}


def _is_workflow_enabled(config: dict, workflow: str) -> bool:
    """Check if a workflow is enabled in config (default: True)."""
    return config.get(workflow, {}).get("enabled", True)


def _notify(title: str, message: str, config: dict) -> None:
    """Send a desktop notification (platform-aware).

    Delegates to platform.send_notification() which uses the native
    notification method for the current OS (macOS, Linux, or Windows).
    """
    notif_config = config.get("notification", {})
    if not notif_config.get("enabled", True):
        return

    from obsidian_connector.platform import send_notification
    send_notification(title, message)


def run_morning(config: dict) -> None:
    """Generate and write morning briefing to daily note."""
    if not _is_workflow_enabled(config, "morning"):
        print("Morning workflow disabled in config.")
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        brief = today_brief()
    except ObsidianCLIError:
        brief = {}

    try:
        loops = list_open_loops()
    except ObsidianCLIError:
        loops = []

    try:
        delegations = detect_delegations()
        pending = [d for d in delegations if d.get("status") != "done"]
    except ObsidianCLIError:
        pending = []

    # Build briefing
    parts = [f"## Morning Briefing", f"**Generated:** {ts}", ""]

    tasks = brief.get("open_tasks", [])
    if tasks:
        parts.append(f"**Open tasks:** {len(tasks)}")
        for t in tasks[:5]:
            parts.append(f"- {t.get('text', '').strip()}")
        if len(tasks) > 5:
            parts.append(f"- ... and {len(tasks) - 5} more")
        parts.append("")

    if loops:
        parts.append(f"**Open loops:** {len(loops)}")
        for loop in loops[:5]:
            parts.append(f"- {loop.get('text', '').strip()}")
        if len(loops) > 5:
            parts.append(f"- ... and {len(loops) - 5} more")
        parts.append("")

    if pending:
        parts.append(f"**Pending delegations:** {len(pending)}")
        for d in pending[:3]:
            parts.append(f"- {d.get('instruction', '').strip()}")
        parts.append("")

    if not tasks and not loops and not pending:
        parts.append("Clean slate. Nothing carried over.")

    content = "\n".join(parts)

    try:
        log_to_daily(content)
        _notify("Morning Briefing", f"{len(tasks)} tasks, {len(loops)} loops", config)
        print(f"Morning briefing written ({len(tasks)} tasks, {len(loops)} loops)")
    except ObsidianCLIError as exc:
        print(f"Error writing briefing: {exc}", file=sys.stderr)
        sys.exit(1)


def run_evening(config: dict) -> None:
    """Generate and write evening close to daily note."""
    if not _is_workflow_enabled(config, "evening"):
        print("Evening workflow disabled in config.")
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        close = close_day_reflection()
    except ObsidianCLIError:
        close = {}

    parts = [f"## Day Close", f"**Generated:** {ts}", ""]

    done = close.get("completed_tasks", [])
    if done:
        parts.append(f"**Completed:** {len(done)} tasks")
        for t in done[:5]:
            parts.append(f"- {t.get('text', '').strip()}")
        parts.append("")

    remaining = close.get("remaining_tasks", [])
    if remaining:
        parts.append(f"**Remaining:** {len(remaining)} tasks")
        for t in remaining[:5]:
            parts.append(f"- {t.get('text', '').strip()}")
        parts.append("")

    prompts = close.get("reflection_prompts", [])
    if prompts:
        parts.append("**Reflect:**")
        for p in prompts:
            parts.append(f"- {p}")
        parts.append("")

    content = "\n".join(parts)

    try:
        log_to_daily(content)
        _notify("Day Closed", f"{len(done)} done, {len(remaining)} remaining", config)
        print(f"Evening close written ({len(done)} done, {len(remaining)} remaining)")
    except ObsidianCLIError as exc:
        print(f"Error writing close: {exc}", file=sys.stderr)
        sys.exit(1)


def run_weekly(config: dict) -> None:
    """Generate and write weekly review to daily note."""
    if not _is_workflow_enabled(config, "weekly"):
        print("Weekly workflow disabled in config.")
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        candidates = graduate_candidates(lookback_days=7)
    except ObsidianCLIError:
        candidates = []

    try:
        loops = list_open_loops()
    except ObsidianCLIError:
        loops = []

    parts = [f"## Weekly Review", f"**Generated:** {ts}", ""]

    if candidates:
        parts.append(f"**Graduate candidates:** {len(candidates)} ideas worth promoting")
        for c in candidates:
            parts.append(f"- {c.get('title', '?')}")
        parts.append("")

    if loops:
        parts.append(f"**Open loops:** {len(loops)} total")
        parts.append("")

    content = "\n".join(parts)

    try:
        log_to_daily(content)
        _notify("Weekly Review", f"{len(candidates)} ideas, {len(loops)} loops", config)
        print(f"Weekly review written ({len(candidates)} candidates, {len(loops)} loops)")
    except ObsidianCLIError as exc:
        print(f"Error writing review: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="obsidian-connector scheduled runner")
    parser.add_argument("workflow", choices=["morning", "evening", "weekly"])
    args = parser.parse_args()

    config = _load_config()

    if args.workflow == "morning":
        run_morning(config)
    elif args.workflow == "evening":
        run_evening(config)
    elif args.workflow == "weekly":
        run_weekly(config)

    return 0


if __name__ == "__main__":
    sys.exit(main())
