"""Health-check diagnostics for the obsidian-connector stack."""

from __future__ import annotations

import shutil
import subprocess
import sys

from obsidian_connector.config import load_config
from obsidian_connector.platform import (
    claude_desktop_config_path,
    current_os,
    get_platform_paths,
    is_obsidian_running,
    obsidian_binary_candidates,
    scheduler_type,
)


def run_doctor(vault: str | None = None) -> list[dict]:
    """Run a suite of health checks and return results.

    Parameters
    ----------
    vault:
        Optional vault name to check.  Falls back to config default.

    Returns
    -------
    list[dict]
        Each dict has keys ``check`` (str), ``ok`` (bool), ``detail`` (str).
    """
    cfg = load_config()
    results: list[dict] = []

    # --- 0. Platform ---
    os_name = current_os()
    results.append({
        "check": "platform",
        "ok": True,
        "detail": f"{os_name} ({sys.platform})",
        "action": None,
    })

    # --- 0b. Scheduler ---
    sched = scheduler_type()
    paths = get_platform_paths()
    sched_available = _check_scheduler_available(sched)
    sched_detail = f"{sched} ({'available' if sched_available else 'not implemented'})"
    results.append({
        "check": "scheduler",
        "ok": sched_available,
        "detail": sched_detail,
        "action": None if sched_available else f"{sched} scheduling is not yet implemented on {os_name}.",
    })

    # --- 0c. Config paths ---
    claude_cfg = claude_desktop_config_path()
    claude_exists = claude_cfg.exists()
    results.append({
        "check": "claude_config",
        "ok": claude_exists,
        "detail": str(claude_cfg),
        "action": None if claude_exists else "Claude Desktop config not found. Install Claude Desktop or create the config file.",
    })

    # --- 0d. Obsidian process ---
    running = is_obsidian_running()
    results.append({
        "check": "obsidian_running",
        "ok": running,
        "detail": "running" if running else "not detected",
        "action": None if running else "Start Obsidian desktop app for CLI access.",
    })

    # --- 1. obsidian_binary ---
    candidates = obsidian_binary_candidates()
    found_binary = None
    for candidate in candidates:
        # Handle multi-word candidates (e.g. "flatpak run md.obsidian.Obsidian")
        bin_name = candidate.split()[0]
        path = shutil.which(bin_name)
        if path:
            found_binary = candidate
            break

    if found_binary:
        results.append(
            {"check": "obsidian_binary", "ok": True, "detail": found_binary, "action": None}
        )
    else:
        results.append(
            {
                "check": "obsidian_binary",
                "ok": False,
                "detail": f"no Obsidian binary found (checked: {', '.join(candidates[:3])})",
                "action": "Install Obsidian or add to PATH. See https://obsidian.md",
            }
        )

    # --- 2. obsidian_version ---
    try:
        proc = subprocess.run(
            [cfg.obsidian_bin, "version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            results.append(
                {
                    "check": "obsidian_version",
                    "ok": True,
                    "detail": proc.stdout.strip(),
                    "action": None,
                }
            )
        else:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            results.append(
                {
                    "check": "obsidian_version",
                    "ok": False,
                    "detail": detail,
                    "action": "Ensure Obsidian is running and CLI is enabled (v1.12+)",
                }
            )
    except FileNotFoundError:
        results.append(
            {
                "check": "obsidian_version",
                "ok": False,
                "detail": f"binary '{cfg.obsidian_bin}' not found",
                "action": "Ensure Obsidian is running and CLI is enabled (v1.12+)",
            }
        )
    except subprocess.TimeoutExpired:
        results.append(
            {
                "check": "obsidian_version",
                "ok": False,
                "detail": "timed out after 10s",
                "action": "Ensure Obsidian is running and CLI is enabled (v1.12+)",
            }
        )
    except Exception as exc:
        results.append(
            {
                "check": "obsidian_version",
                "ok": False,
                "detail": str(exc),
                "action": "Ensure Obsidian is running and CLI is enabled (v1.12+)",
            }
        )

    # --- 3. vault_resolution ---
    try:
        effective_vault = vault or cfg.default_vault
        if effective_vault:
            results.append(
                {
                    "check": "vault_resolution",
                    "ok": True,
                    "detail": f"vault={effective_vault}",
                    "action": None,
                }
            )
        else:
            results.append(
                {
                    "check": "vault_resolution",
                    "ok": False,
                    "detail": "no vault specified and no default configured",
                    "action": "Set OBSIDIAN_VAULT env var or add default_vault to config.json",
                }
            )
    except Exception as exc:
        results.append(
            {
                "check": "vault_resolution",
                "ok": False,
                "detail": str(exc),
                "action": "Set OBSIDIAN_VAULT env var or add default_vault to config.json",
            }
        )

    # --- 4. vault_reachable ---
    try:
        cmd: list[str] = [cfg.obsidian_bin]
        effective_vault = vault or cfg.default_vault
        if effective_vault:
            cmd.append(f"vault={effective_vault}")
        cmd.extend(["files", "total"])

        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        if proc.returncode == 0:
            results.append(
                {
                    "check": "vault_reachable",
                    "ok": True,
                    "detail": proc.stdout.strip() or "ok",
                    "action": None,
                }
            )
        else:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            results.append(
                {
                    "check": "vault_reachable",
                    "ok": False,
                    "detail": detail,
                    "action": "Open Obsidian desktop app. The CLI communicates via IPC.",
                }
            )
    except FileNotFoundError:
        results.append(
            {
                "check": "vault_reachable",
                "ok": False,
                "detail": f"binary '{cfg.obsidian_bin}' not found",
                "action": "Open Obsidian desktop app. The CLI communicates via IPC.",
            }
        )
    except subprocess.TimeoutExpired:
        results.append(
            {
                "check": "vault_reachable",
                "ok": False,
                "detail": "timed out after 15s",
                "action": "Open Obsidian desktop app. The CLI communicates via IPC.",
            }
        )
    except Exception as exc:
        results.append(
            {
                "check": "vault_reachable",
                "ok": False,
                "detail": str(exc),
                "action": "Open Obsidian desktop app. The CLI communicates via IPC.",
            }
        )

    # --- 5. Platform feature summary ---
    features = _platform_feature_summary(os_name, sched)
    results.append({
        "check": "platform_features",
        "ok": True,
        "detail": features,
        "action": None,
    })

    return results


def _check_scheduler_available(sched: str) -> bool:
    """Check if the scheduler backend is actually implemented."""
    return sched in ("launchd", "systemd", "task_scheduler")


def _platform_feature_summary(os_name: str, sched: str) -> str:
    """Build a human-readable feature availability summary."""
    features: list[str] = []

    # CLI access
    if os_name in ("macos", "linux"):
        features.append("CLI: available")
    else:
        features.append("CLI: not available (use file backend)")

    # Scheduling
    sched_available = _check_scheduler_available(sched)
    status = "available" if sched_available else "not implemented"
    features.append(f"Scheduling: {sched} ({status})")

    # Graph tools (always available -- direct file access)
    features.append("Graph tools: available (direct file access)")

    # Notifications
    if os_name == "macos":
        features.append("Notifications: osascript (available)")
    elif os_name == "linux":
        features.append("Notifications: notify-send (if installed)")
    elif os_name == "windows":
        features.append("Notifications: PowerShell toast (available)")

    return "; ".join(features)
