#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Build a .dmg installer for obsidian-connector
#
# Creates a macOS disk image with a clean installer UX:
# the user opens the DMG and sees only Install.command and a README.
# All project files are tucked into a hidden .content/ directory.
#
# Usage:
#   ./scripts/create-dmg.sh                # builds dist/obsidian-connector.dmg
#   ./scripts/create-dmg.sh v0.2.0         # custom version in filename
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
            VERSION="$1"
            shift
            ;;
    esac
done

if [ -z "$VERSION" ]; then
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
mkdir -p "$STAGING_DIR/$DMG_NAME/.content" "$DIST_DIR"

# ── Copy project files into hidden .content/ ──────────────────────────

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
    "$REPO_ROOT/" "$STAGING_DIR/$DMG_NAME/.content/"

# ── Create the top-level Install.command wrapper ──────────────────────
# This is the ONLY executable the user sees. It delegates to the real
# installer inside .content/.

cat > "$STAGING_DIR/$DMG_NAME/Install.command" << 'INSTALLER'
#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector installer
# Double-click this file to install.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENT_DIR="$SCRIPT_DIR/.content"

if [ ! -d "$CONTENT_DIR" ]; then
    echo "Error: .content directory not found."
    echo "Please run this from the mounted DMG, not a copied file."
    exit 1
fi

# Hand off to the real installer
exec bash "$CONTENT_DIR/Install.command"
INSTALLER
chmod +x "$STAGING_DIR/$DMG_NAME/Install.command"

# ── Create the visible README ─────────────────────────────────────────

cat > "$STAGING_DIR/$DMG_NAME/README.txt" << 'README'
┌─────────────────────────────────────────────┐
│         obsidian-connector installer         │
├─────────────────────────────────────────────┤
│                                             │
│  Double-click "Install.command" to start.   │
│                                             │
│  It will:                                   │
│    1. Set up a Python environment           │
│    2. Configure Claude Desktop              │
│    3. Connect Claude to your Obsidian vault │
│                                             │
│  Requirements:                              │
│    • Python 3.11+  (python.org/downloads)   │
│    • Obsidian      (obsidian.md)            │
│    • Claude Desktop                         │
│                                             │
│  If macOS blocks the file:                  │
│    Right-click → Open → click "Open"        │
│                                             │
└─────────────────────────────────────────────┘
README

# ── Hide .content/ from Finder ────────────────────────────────────────
# SetFile -a V makes a file/folder invisible in Finder but still
# accessible to scripts. chflags hidden is the modern equivalent.

chflags hidden "$STAGING_DIR/$DMG_NAME/.content" 2>/dev/null || true
# Also set the dot-prefix hides it on most systems by convention

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
echo "DMG contents visible to user:"
echo "  Install.command   (double-click to install)"
echo "  README.txt        (instructions)"
echo "  .content/         (hidden -- project files)"
