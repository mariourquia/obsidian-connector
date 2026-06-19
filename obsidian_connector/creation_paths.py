# obsidian_connector/creation_paths.py
"""Filesystem paths for Creation Vault OS state that must live OUTSIDE iCloud.

The canonical markdown notes live in the iCloud vault; the hot, append-only event
log and derived indexes live here, beside the existing audit log, so a hot-append
file never races iCloud sync. See docs/plans/2026-06-18-creation-vault-os.md.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _root() -> Path:
    return Path(os.path.expanduser("~/.obsidian-connector/creation"))


def _vault_id(vault_path: Path) -> str:
    return hashlib.sha256(str(Path(vault_path).resolve()).encode()).hexdigest()[:16]


def creation_state_dir(vault_path: Path) -> Path:
    d = _root() / _vault_id(vault_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def events_path(vault_path: Path) -> Path:
    d = creation_state_dir(vault_path) / "events"
    d.mkdir(parents=True, exist_ok=True)
    return d / "creation_events.jsonl"


def index_dir(vault_path: Path) -> Path:
    d = creation_state_dir(vault_path) / "index"
    d.mkdir(parents=True, exist_ok=True)
    return d
