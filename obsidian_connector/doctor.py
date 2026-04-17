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

    # --- 5. Python runtime (v0.11 platform reliability) ---
    py_check = _check_python_runtime(os_name)
    results.append(py_check)

    # --- 6. Node.js (for build tooling + Ix code exploration) ---
    node_check = _check_node_runtime()
    results.append(node_check)

    # --- 7. Textual (optional TUI dashboard) ---
    textual_check = _check_textual_available()
    results.append(textual_check)

    # --- 8. iCloud path detection for vault ---
    icloud_check = _check_icloud_vault_path(vault or cfg.default_vault, os_name)
    if icloud_check is not None:
        results.append(icloud_check)

    # --- 9. Full Disk Access hint (macOS only) ---
    if os_name == "macos":
        fda_check = _check_full_disk_access_hint()
        results.append(fda_check)

    # --- 10. Platform feature summary ---
    features = _platform_feature_summary(os_name, sched)
    results.append({
        "check": "platform_features",
        "ok": True,
        "detail": features,
        "action": None,
    })

    return results


# ---------------------------------------------------------------------------
# v0.11 platform-reliability helpers
# ---------------------------------------------------------------------------


def _check_python_runtime(os_name: str) -> dict:
    """Detect the Microsoft Store Python stub on Windows + sub-3.11 Pythons.

    The Store stub at ``%LOCALAPPDATA%\\Microsoft\\WindowsApps\\python.exe``
    is a no-op redirector that does NOT provide a working interpreter
    until the user launches the Store install flow. We look at the
    current executable path plus ``sys.version_info`` to catch both the
    stub and an old runtime.
    """
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    too_old = sys.version_info < (3, 11)
    stub = False
    detail_extra = ""
    if os_name == "windows":
        try:
            exe = (sys.executable or "").lower()
            if "windowsapps" in exe and "python" in exe:
                stub = True
                detail_extra = " (Microsoft Store stub detected)"
        except Exception:
            pass

    if stub:
        return {
            "check": "python_runtime",
            "ok": False,
            "detail": f"Python {version}{detail_extra}",
            "action": (
                "The Microsoft Store python.exe is a redirector stub, not a real interpreter. "
                "Install Python 3.11+ from https://python.org or via winget: "
                "`winget install Python.Python.3.12`."
            ),
        }
    if too_old:
        return {
            "check": "python_runtime",
            "ok": False,
            "detail": f"Python {version} (pyproject requires >=3.11)",
            "action": "Install Python 3.11 or newer; re-create the venv with `python3.11 -m venv .venv`.",
        }
    return {
        "check": "python_runtime",
        "ok": True,
        "detail": f"Python {version}",
        "action": None,
    }


def _check_node_runtime() -> dict:
    """Verify Node.js is on PATH for build tooling + Ix code exploration.

    Node is optional for end users but required to rebuild the plugin
    targets (`tools/build.ts`) and to run the Ix code-exploration
    sub-tools. Missing Node is a warning, not a hard failure.
    """
    node_path = shutil.which("node")
    if not node_path:
        return {
            "check": "node_runtime",
            "ok": False,
            "detail": "node not on PATH",
            "action": (
                "Optional. Only required for rebuilding plugin targets (`npx tsx tools/build.ts`) "
                "or Ix code-exploration. Install via https://nodejs.org or `brew install node` / "
                "`winget install OpenJS.NodeJS`."
            ),
        }
    try:
        proc = subprocess.run(
            [node_path, "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        ver = (proc.stdout or "").strip() or "unknown"
    except Exception as exc:
        return {
            "check": "node_runtime",
            "ok": False,
            "detail": f"node found but version probe failed: {exc}",
            "action": None,
        }
    return {
        "check": "node_runtime",
        "ok": True,
        "detail": f"node {ver} at {node_path}",
        "action": None,
    }


def _check_textual_available() -> dict:
    """Check for the optional Textual dependency used by the TUI dashboard."""
    try:
        import importlib

        importlib.import_module("textual")
        return {
            "check": "textual_available",
            "ok": True,
            "detail": "textual importable",
            "action": None,
        }
    except ImportError:
        return {
            "check": "textual_available",
            "ok": False,
            "detail": "textual not installed",
            "action": (
                "Optional. Only required for the TUI dashboard. Install with "
                "`pip install textual` inside the connector venv."
            ),
        }


def _check_icloud_vault_path(vault_hint: str | None, os_name: str) -> dict | None:
    """Warn when the vault path lives under iCloud Drive on macOS / Windows.

    iCloud Drive is supported (`docs/implementation/shared_vault.md` covers
    the setup), but it changes the expected behavior around conflict files
    and atomic renames. Surfacing the location gives operators a chance to
    cross-reference the shared-vault doc before they hit a surprise.

    Returns ``None`` when no vault hint is available (the vault_resolution
    check upstream already surfaces that gap).
    """
    if not vault_hint:
        return None

    # Best-effort path normalization. On macOS, iCloud Drive paths look
    # like ``~/Library/Mobile Documents/com~apple~CloudDocs/...``. On
    # Windows, they live under ``%USERPROFILE%\iCloudDrive\...``.
    hint_lower = vault_hint.lower()
    icloud_markers = (
        "mobile documents/com~apple~clouddocs",
        "icloud drive",
        "icloud~com~apple~cloud",
        "onedrive",  # surface OneDrive too; same shared-vault posture
        "dropbox",
    )
    hit = next((m for m in icloud_markers if m in hint_lower), None)
    if not hit:
        # Not in a known sync-root location; no warning.
        return {
            "check": "vault_sync_location",
            "ok": True,
            "detail": "vault path is not under a detected sync root",
            "action": None,
        }

    provider = {
        "mobile documents/com~apple~clouddocs": "iCloud Drive",
        "icloud drive": "iCloud Drive",
        "icloud~com~apple~cloud": "iCloud Drive",
        "onedrive": "OneDrive",
        "dropbox": "Dropbox",
    }[hit]

    return {
        "check": "vault_sync_location",
        "ok": True,  # informational, not a failure
        "detail": f"vault appears to live under {provider}",
        "action": (
            f"Supported. Review docs/implementation/shared_vault.md for {provider}-specific "
            f"conflict-file patterns and the operator reconciliation workflow. Run "
            f"`obsx vault-conflicts` to surface any current conflict files."
        ),
    }


def _check_full_disk_access_hint() -> dict:
    """macOS-only informational hint about Full Disk Access.

    Reading vault files under user-protected locations (Desktop, Documents,
    iCloud Drive) can fail with ``PermissionError: Operation not permitted``
    unless the Python binary or the calling app has been granted Full Disk
    Access in System Settings. We cannot programmatically check TCC
    permissions without private APIs, so this check always reports ``ok``
    and attaches a static hint.
    """
    return {
        "check": "full_disk_access_hint",
        "ok": True,
        "detail": "macOS TCC grants are not introspectable from Python",
        "action": (
            "If you see 'Operation not permitted' when reading vault files, grant Full Disk "
            "Access to the Python binary (or to Claude Desktop / Terminal) under "
            "System Settings -> Privacy & Security -> Full Disk Access."
        ),
    }


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
