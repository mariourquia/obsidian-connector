# tests/test_creation_backlog_cli.py
import json

from obsidian_connector import cli
from obsidian_connector import creation_backlog as cb
from obsidian_connector import creation_events as ce


def _run(monkeypatch, tmp_path, argv):
    """Run the CLI with vault resolved to tmp_path/v via --vault flag."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    # Pass --vault as the actual path so vault resolution in main() uses the tmp dir.
    full_argv = ["--vault", str(vault)] + argv
    return cli.main(full_argv)


def test_add_is_dry_run_by_default(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "v"
    rc = _run(monkeypatch, tmp_path,
              ["creation", "backlog", "add", "--title", "t", "--project", "p"])
    assert rc == 0
    assert "[dry-run]" in capsys.readouterr().out
    assert ce.read_events(vault) == []           # nothing written


def test_add_allow_write_persists_and_logs(tmp_path, monkeypatch, capsys):
    logged = []
    monkeypatch.setattr(cli, "log_action",
                        lambda *a, **k: logged.append((a, k)))
    vault = tmp_path / "v"
    rc = _run(monkeypatch, tmp_path,
              ["creation", "backlog", "add", "--title", "t", "--project", "p",
               "--repos", "a,b", "--allow-write", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    item_id = out["data"]["id"]
    assert cb.show_backlog_item(vault, item_id=item_id) is not None
    assert logged and logged[-1][1].get("dry_run") is False


def test_list_and_show_roundtrip(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "v"
    _run(monkeypatch, tmp_path,
         ["creation", "backlog", "add", "--title", "t", "--project", "p",
          "--allow-write"])
    capsys.readouterr()  # clear the add output
    rc = _run(monkeypatch, tmp_path, ["creation", "backlog", "list", "--json"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)["data"]["items"]
    assert len(rows) == 1
    rc = _run(monkeypatch, tmp_path,
              ["creation", "backlog", "show", "--id", rows[0]["id"], "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["data"]["title"] == "t"
