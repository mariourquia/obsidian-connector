"""Test audit log directory permissions."""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_audit_dir_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        test_dir = Path(tmp) / "audit-test" / "logs"
        with patch("obsidian_connector.audit.AUDIT_DIR", test_dir):
            from obsidian_connector.audit import log_action
            log_action(
                command="test",
                args={"q": "secret query"},
                vault="test-vault",
            )
        assert test_dir.exists(), "audit dir should be created"
        mode = stat.S_IMODE(test_dir.stat().st_mode)
        assert mode == 0o700, (
            f"audit dir should be 0o700 (owner-only), got {oct(mode)}"
        )
    print("PASS: test_audit_dir_permissions")


def test_audit_parent_dir_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp) / "obsidian-connector-test"
        test_dir = parent / "logs"
        with patch("obsidian_connector.audit.AUDIT_DIR", test_dir):
            from obsidian_connector.audit import log_action
            log_action(
                command="test",
                args={},
                vault=None,
            )
        mode = stat.S_IMODE(parent.stat().st_mode)
        assert mode == 0o700, (
            f"parent dir should be 0o700, got {oct(mode)}"
        )
    print("PASS: test_audit_parent_dir_permissions")


if __name__ == "__main__":
    test_audit_dir_permissions()
    test_audit_parent_dir_permissions()
    print("\nAll audit permission tests passed.")
