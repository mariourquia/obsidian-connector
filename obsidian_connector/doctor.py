"""Health-check diagnostics for the obsidian-connector stack."""

from __future__ import annotations

import shutil
import subprocess

from obsidian_connector.config import load_config


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

    # --- 1. obsidian_binary ---
    try:
        path = shutil.which(cfg.obsidian_bin)
        if path:
            results.append(
                {"check": "obsidian_binary", "ok": True, "detail": path, "action": None}
            )
        else:
            results.append(
                {
                    "check": "obsidian_binary",
                    "ok": False,
                    "detail": f"'{cfg.obsidian_bin}' not found on PATH",
                    "action": "Install Obsidian or add to PATH. See https://obsidian.md",
                }
            )
    except Exception as exc:
        results.append(
            {
                "check": "obsidian_binary",
                "ok": False,
                "detail": str(exc),
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

    return results
