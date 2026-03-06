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
                {"check": "obsidian_binary", "ok": True, "detail": path}
            )
        else:
            results.append(
                {
                    "check": "obsidian_binary",
                    "ok": False,
                    "detail": f"'{cfg.obsidian_bin}' not found on PATH",
                }
            )
    except Exception as exc:
        results.append(
            {"check": "obsidian_binary", "ok": False, "detail": str(exc)}
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
                }
            )
        else:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            results.append(
                {"check": "obsidian_version", "ok": False, "detail": detail}
            )
    except FileNotFoundError:
        results.append(
            {
                "check": "obsidian_version",
                "ok": False,
                "detail": f"binary '{cfg.obsidian_bin}' not found",
            }
        )
    except subprocess.TimeoutExpired:
        results.append(
            {
                "check": "obsidian_version",
                "ok": False,
                "detail": "timed out after 10s",
            }
        )
    except Exception as exc:
        results.append(
            {"check": "obsidian_version", "ok": False, "detail": str(exc)}
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
                }
            )
        else:
            results.append(
                {
                    "check": "vault_resolution",
                    "ok": False,
                    "detail": "no vault specified and no default configured",
                }
            )
    except Exception as exc:
        results.append(
            {"check": "vault_resolution", "ok": False, "detail": str(exc)}
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
                }
            )
        else:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            results.append(
                {"check": "vault_reachable", "ok": False, "detail": detail}
            )
    except FileNotFoundError:
        results.append(
            {
                "check": "vault_reachable",
                "ok": False,
                "detail": f"binary '{cfg.obsidian_bin}' not found",
            }
        )
    except subprocess.TimeoutExpired:
        results.append(
            {
                "check": "vault_reachable",
                "ok": False,
                "detail": "timed out after 15s",
            }
        )
    except Exception as exc:
        results.append(
            {"check": "vault_reachable", "ok": False, "detail": str(exc)}
        )

    return results
