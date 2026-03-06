"""Thin wrapper -- delegates to obsidian_connector.cli for backward compat.

Allows ``python main.py ...`` to keep working alongside the installed
``obsx`` / ``obsidian-connector`` console scripts.
"""

import sys

from obsidian_connector.cli import main

if __name__ == "__main__":
    sys.exit(main())
