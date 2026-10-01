"""Exercise the shell smoke assertions with synthetic protocol responses."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("tool_count", "has_server_info", "expected_exit"),
    [(1000, True, 0), (2, True, 1), (1000, False, 1)],
)
def test_mcp_launch_smoke_response_assertions(
    tmp_path: Path, tool_count: int, has_server_info: bool, expected_exit: int
) -> None:
    fixture_root = tmp_path / "plugin"
    scripts = fixture_root / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "mcp_launch_smoke.sh"
    source = Path(__file__).resolve().parents[1] / "scripts/mcp_launch_smoke.sh"
    shutil.copyfile(source, script)
    server = fixture_root / "bin/obsx-mcp"
    server.parent.mkdir()
    initialize = {"result": {"serverInfo": {"name": "synthetic-server"}}}
    if not has_server_info:
        initialize = {"result": {}}
    tools = {
        "result": {
            "tools": [
                {"name": f"synthetic-tool-{index}", "description": "public fixture " * 40}
                for index in range(tool_count)
            ]
        }
    }
    response = json.dumps(initialize) + "\n" + json.dumps(tools)
    server.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stdin.read()\nprint({response!r})\n"
    )
    server.chmod(0o755)
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == expected_exit, result.stdout[-1000:]
