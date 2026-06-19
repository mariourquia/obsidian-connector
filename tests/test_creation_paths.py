# tests/test_creation_paths.py
import hashlib
from pathlib import Path
from obsidian_connector import creation_paths


def test_state_dir_is_outside_vault_and_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "icloud" / "creation"
    vault.mkdir(parents=True)
    d1 = creation_paths.creation_state_dir(vault)
    d2 = creation_paths.creation_state_dir(vault)
    assert d1 == d2                                   # stable
    assert str(tmp_path / "icloud") not in str(d1)    # NOT inside the vault
    assert d1.is_dir()                                # created
    vid = hashlib.sha256(str(vault.resolve()).encode()).hexdigest()[:16]
    assert d1.name == vid


def test_events_path_under_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"; vault.mkdir()
    ev = creation_paths.events_path(vault)
    assert ev.name == "creation_events.jsonl"
    assert ev.parent.name == "events"
    assert ev.parent.parent == creation_paths.creation_state_dir(vault)
