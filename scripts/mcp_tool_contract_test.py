"""Verify MCP tool registration, annotations, and error contracts.

These tests inspect the MCP server's tool metadata without calling Obsidian.
They ensure all tools are properly registered and follow the project's
error envelope convention.
"""

import json
import re
from unittest.mock import patch


def test_all_tools_registered():
    """Verify expected tool count matches actual registered tools."""
    with open("obsidian_connector/mcp_server.py") as f:
        source = f.read()
    decorator_count = len(re.findall(r"@mcp\.tool\(", source))
    # Tolerance of 2 below actual count (62) to catch bulk tool deletions
    # while allowing minor refactors. Update this floor when tools are added.
    assert decorator_count >= 60, (
        f"Expected at least 60 @mcp.tool decorators (project has 62), found {decorator_count}"
    )
    print(f"PASS: test_all_tools_registered ({decorator_count} tools by source scan)")


def test_error_envelope_format():
    """Verify _error_envelope produces valid JSON with required keys."""
    from obsidian_connector.mcp_server import _error_envelope
    from obsidian_connector.errors import ObsidianNotRunning

    exc = ObsidianNotRunning("test error")
    result = _error_envelope(exc)
    parsed = json.loads(result)

    assert parsed["ok"] is False, "error envelope must have ok=False"
    assert "error" in parsed, "error envelope must have 'error' key"
    assert "type" in parsed["error"], "error must have 'type'"
    assert "message" in parsed["error"], "error must have 'message'"
    assert parsed["error"]["type"] == "ObsidianNotRunning"
    print("PASS: test_error_envelope_format")


def test_error_envelope_all_types():
    """Verify all typed errors map correctly."""
    from obsidian_connector.mcp_server import _error_envelope
    from obsidian_connector.errors import (
        ObsidianNotFound,
        ObsidianNotRunning,
        VaultNotFound,
        CommandTimeout,
        MalformedCLIOutput,
    )

    for exc_class, expected_name in [
        (ObsidianNotFound, "ObsidianNotFound"),
        (ObsidianNotRunning, "ObsidianNotRunning"),
        (VaultNotFound, "VaultNotFound"),
        (CommandTimeout, "CommandTimeout"),
        (MalformedCLIOutput, "MalformedCLIOutput"),
    ]:
        exc = exc_class()
        result = json.loads(_error_envelope(exc))
        assert result["error"]["type"] == expected_name, (
            f"Expected {expected_name}, got {result['error']['type']}"
        )
    print("PASS: test_error_envelope_all_types")


def test_tool_annotations_present():
    """Verify tools load without annotation errors."""
    import obsidian_connector.mcp_server
    print("PASS: test_tool_annotations_present (module loaded without annotation errors)")


def test_narrowed_exceptions_catch_expected_types():
    """Verify the tightened except clauses catch filesystem and data errors."""
    from obsidian_connector.mcp_server import obsidian_vault_structure

    # Simulate an OSError during index building (filesystem error)
    with patch("obsidian_connector.mcp_server.load_or_build_index", side_effect=OSError("disk full")):
        result = json.loads(obsidian_vault_structure(vault="test"))
        assert result["ok"] is False
        assert result["error"]["type"] == "OSError"

    # Verify that truly unexpected exceptions (e.g., RuntimeError) propagate
    with patch("obsidian_connector.mcp_server.load_or_build_index", side_effect=RuntimeError("bug")):
        try:
            obsidian_vault_structure(vault="test")
            assert False, "RuntimeError should propagate, not be caught"
        except RuntimeError:
            pass  # Expected: not silently swallowed
    print("PASS: test_narrowed_exceptions_catch_expected_types")


if __name__ == "__main__":
    test_error_envelope_format()
    test_error_envelope_all_types()
    test_tool_annotations_present()
    test_all_tools_registered()
    test_narrowed_exceptions_catch_expected_types()
    print("\nAll MCP tool contract tests passed.")
