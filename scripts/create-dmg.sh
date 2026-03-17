#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Build a .dmg installer for obsidian-connector
#
# Creates a macOS disk image that non-technical users can download,
# open, and double-click Install.command to set everything up.
#
# Usage:
#   ./scripts/create-dmg.sh                # builds dist/obsidian-connector.dmg
#   ./scripts/create-dmg.sh --version 0.2  # custom version in filename
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VERSION=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        *)
            # Treat a bare positional argument as the version value.
            VERSION="$1"
            shift
            ;;
    esac
done

if [ -z "$VERSION" ]; then
    # Read from pyproject.toml
    VERSION=$(python3 -c "
import re
with open('pyproject.toml') as f:
    m = re.search(r'version\s*=\s*\"(.+?)\"', f.read())
    print(m.group(1) if m else '0.1.0')
" 2>/dev/null || echo "0.1.0")
fi

DMG_NAME="obsidian-connector-${VERSION}"
DIST_DIR="$REPO_ROOT/dist"
STAGING_DIR="$DIST_DIR/.dmg-staging"

echo "Building $DMG_NAME.dmg..."

# ── Clean ─────────────────────────────────────────────────────────────

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/$DMG_NAME" "$DIST_DIR"

# ── Copy project files (exclude dev artifacts) ────────────────────────

rsync -a \
    --exclude='.venv' \
    --exclude='.git' \
    --exclude='.claude' \
    --exclude='.claude-plugin' \
    --exclude='dist' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='firebase-debug.log' \
    --exclude='vault-context-drafts' \
    --exclude='*.egg-info' \
    --exclude='AGENTS.md' \
    --exclude='Makefile' \
    --exclude='templates' \
    --exclude='tools' \
    --exclude='dev' \
    --exclude='hooks' \
    --exclude='main.py' \
    "$REPO_ROOT/" "$STAGING_DIR/$DMG_NAME/"

# ── Create a visible README in the DMG ────────────────────────────────

cat > "$STAGING_DIR/$DMG_NAME/START HERE.txt" << 'README'
obsidian-connector
==================

Double-click "Install.command" to set everything up.

It will:
  1. Set up the Python environment
  2. Configure Claude Desktop automatically
  3. Give Claude access to your Obsidian vault

Requirements:
  - Python 3.11+ (https://python.org/downloads)
  - Obsidian desktop app (https://obsidian.md)
  - Claude Desktop

If macOS says the file can't be opened because it's from an
unidentified developer: right-click Install.command, select
"Open", then click "Open" in the dialog.
README

# ── Build DMG ─────────────────────────────────────────────────────────

hdiutil create \
    -volname "$DMG_NAME" \
    -srcfolder "$STAGING_DIR/$DMG_NAME" \
    -ov \
    -format UDZO \
    "$DIST_DIR/$DMG_NAME.dmg" \
    -quiet

# ── Clean staging ─────────────────────────────────────────────────────

rm -rf "$STAGING_DIR"

echo ""
echo "Created: $DIST_DIR/$DMG_NAME.dmg"
SIZE=$(du -h "$DIST_DIR/$DMG_NAME.dmg" | cut -f1 | tr -d ' ')
echo "Size: $SIZE"
echo ""
echo "Upload this to GitHub Releases for distribution."
