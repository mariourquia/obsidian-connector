"""Configuration loading for obsidian-connector.

Resolution order (highest wins):
    1. Explicit function argument  (handled in client.py / run_obsidian)
    2. Environment variable
    3. config.json value
    4. Built-in default
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_FILENAME = "config.json"


def _find_config_file() -> Path | None:
    """Locate config.json -- check CWD, then package parent directory."""
    candidates = [
        Path.cwd() / _CONFIG_FILENAME,
        Path(__file__).resolve().parent.parent / _CONFIG_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_config_file() -> dict:
    """Read and parse config.json.  Returns ``{}`` when not found."""
    path = _find_config_file()
    if path is None:
        return {}
    with open(path) as f:
        return json.load(f)


@dataclass
class ConnectorConfig:
    """Runtime configuration resolved from env vars, config.json, and defaults."""

    obsidian_bin: str = "obsidian"
    default_vault: str | None = None
    timeout_seconds: int = 30
    daily_note_behavior: str = "append"
    default_folders: dict[str, str] = field(default_factory=dict)
    cache_ttl: int = 0


def load_config() -> ConnectorConfig:
    """Build a ConnectorConfig by layering env vars over config.json."""
    file_cfg = _load_config_file()

    return ConnectorConfig(
        obsidian_bin=os.getenv("OBSIDIAN_BIN") or file_cfg.get("obsidian_bin", "obsidian"),
        default_vault=os.getenv("OBSIDIAN_VAULT") or file_cfg.get("default_vault"),
        timeout_seconds=int(os.getenv("OBSIDIAN_TIMEOUT") or file_cfg.get("timeout_seconds", 30)),
        daily_note_behavior=file_cfg.get("daily_note_behavior", "append"),
        default_folders=file_cfg.get("default_folders", {}),
        cache_ttl=int(os.getenv("OBSIDIAN_CACHE_TTL") or file_cfg.get("cache_ttl", 0)),
    )
