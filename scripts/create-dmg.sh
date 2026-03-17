#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Build a signed .dmg installer for obsidian-connector
#
# Creates a macOS disk image containing a signed .app bundle.
# User opens DMG, sees "Install obsidian-connector.app" and a README.
# Double-clicking the .app runs the installer in Terminal.
#
# Usage:
#   ./scripts/create-dmg.sh                # builds dist/obsidian-connector.dmg
#   ./scripts/create-dmg.sh v0.2.0         # custom version in filename
#
# Requirements:
#   - Apple Developer ID certificate in keychain
#   - xcrun notarytool credentials (optional, for notarization)
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── Parse args ────────────────────────────────────────────────────────

VERSION=""
SIGN_IDENTITY=""
SKIP_SIGN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)    VERSION="$2"; shift 2 ;;
        --identity)   SIGN_IDENTITY="$2"; shift 2 ;;
        --no-sign)    SKIP_SIGN=true; shift ;;
        *)            VERSION="$1"; shift ;;
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

# Auto-detect signing identity if not provided
if [ -z "$SIGN_IDENTITY" ] && [ "$SKIP_SIGN" = false ]; then
    SIGN_IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null \
        | grep "Developer ID Application" \
        | head -1 \
        | sed 's/.*"\(.*\)"/\1/' || true)
    if [ -z "$SIGN_IDENTITY" ]; then
        echo "Warning: No Developer ID found. Building unsigned."
        SKIP_SIGN=true
    fi
fi

DMG_NAME="obsidian-connector-${VERSION}"
DIST_DIR="$REPO_ROOT/dist"
STAGING_DIR="$DIST_DIR/.dmg-staging"
APP_NAME="Install obsidian-connector.app"

echo "Building $DMG_NAME.dmg..."
[ "$SKIP_SIGN" = false ] && echo "Signing with: $SIGN_IDENTITY"

# ── Clean ─────────────────────────────────────────────────────────────

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/$DMG_NAME" "$DIST_DIR"

# ── Copy project files into hidden .content/ ──────────────────────────

mkdir -p "$STAGING_DIR/$DMG_NAME/.content"
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

chflags hidden "$STAGING_DIR/$DMG_NAME/.content" 2>/dev/null || true

# ── Build .app bundle ─────────────────────────────────────────────────

APP_DIR="$STAGING_DIR/$DMG_NAME/$APP_NAME"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>install</string>
    <key>CFBundleIdentifier</key>
    <string>com.obsidian-connector.installer</string>
    <key>CFBundleName</key>
    <string>Install obsidian-connector</string>
    <key>CFBundleDisplayName</key>
    <string>Install obsidian-connector</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHumanReadableCopyright</key>
    <string>MIT License</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
</dict>
</plist>
PLIST

# The executable -- copies project to writable location, then installs
cat > "$APP_DIR/Contents/MacOS/install" << 'LAUNCHER'
#!/usr/bin/env bash
# Launcher: copies project files to ~/obsidian-connector, then
# opens Terminal and runs the installer from the writable copy.

SCRIPT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
CONTENT_DIR="$SCRIPT_DIR/.content"
INSTALL_DIR="$HOME/obsidian-connector"

if [ ! -d "$CONTENT_DIR" ]; then
    osascript -e 'display alert "Installation Error" message "Could not find installer files. Please run from the mounted disk image." as critical'
    exit 1
fi

# Copy to writable location (~/obsidian-connector)
if [ -d "$INSTALL_DIR" ]; then
    # Ask before overwriting
    response=$(osascript -e 'display dialog "obsidian-connector is already installed at ~/obsidian-connector. Overwrite and reinstall?" buttons {"Cancel", "Reinstall"} default button "Reinstall" with icon caution' 2>/dev/null | grep "Reinstall" || true)
    if [ -z "$response" ]; then
        exit 0
    fi
    rm -rf "$INSTALL_DIR"
fi

cp -R "$CONTENT_DIR" "$INSTALL_DIR"

# Open Terminal and run the installer from the writable copy
osascript << EOF
tell application "Terminal"
    activate
    do script "clear && bash '$INSTALL_DIR/Install.command'"
end tell
EOF
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/install"

# Generate a simple app icon (blue circle with arrow)
# Using a script to create a basic .icns from a PNG
python3 -c "
import subprocess, tempfile, os

# Create a 256x256 PNG icon using sips (built into macOS)
icon_dir = tempfile.mkdtemp()
iconset = os.path.join(icon_dir, 'AppIcon.iconset')
os.makedirs(iconset)

# Generate a simple icon using a 1x1 blue pixel scaled up
# We'll use the system's generic app icon as fallback
try:
    # Try to use the built-in Terminal icon as base
    subprocess.run([
        'sips', '-z', '256', '256',
        '/System/Applications/Utilities/Terminal.app/Contents/Resources/Terminal.icns',
        '--out', os.path.join(iconset, 'icon_256x256.png')
    ], capture_output=True, check=True)
    subprocess.run([
        'iconutil', '-c', 'icns', iconset,
        '-o', '$APP_DIR/Contents/Resources/AppIcon.icns'
    ], capture_output=True, check=True)
except Exception:
    pass  # No icon is fine -- macOS shows a default
" 2>/dev/null || true

# ── Create README.txt ─────────────────────────────────────────────────

cat > "$STAGING_DIR/$DMG_NAME/README.txt" << 'README'
┌─────────────────────────────────────────────┐
│         obsidian-connector installer         │
├─────────────────────────────────────────────┤
│                                             │
│  Double-click the app icon to install.      │
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
└─────────────────────────────────────────────┘
README

# ── Sign the .app bundle ──────────────────────────────────────────────

if [ "$SKIP_SIGN" = false ]; then
    echo "Stripping extended attributes..."
    xattr -cr "$APP_DIR" 2>/dev/null || true
    xattr -cr "$STAGING_DIR/$DMG_NAME/.content" 2>/dev/null || true

    echo "Signing .app bundle..."
    codesign --deep --force --verify --verbose \
        --sign "$SIGN_IDENTITY" \
        --options runtime \
        "$APP_DIR" 2>&1 | grep -v "^$" || true

    echo "Verifying signature..."
    codesign --verify --deep --strict "$APP_DIR" 2>&1 && echo "Signature valid" || {
        echo "Warning: Signature verification failed. Continuing anyway."
    }
fi

# ── Build DMG ─────────────────────────────────────────────────────────

hdiutil create \
    -volname "$DMG_NAME" \
    -srcfolder "$STAGING_DIR/$DMG_NAME" \
    -ov \
    -format UDZO \
    "$DIST_DIR/$DMG_NAME.dmg" \
    -quiet

# ── Sign the DMG itself ───────────────────────────────────────────────

if [ "$SKIP_SIGN" = false ]; then
    echo "Signing DMG..."
    codesign --force --sign "$SIGN_IDENTITY" "$DIST_DIR/$DMG_NAME.dmg" 2>&1 || true
fi

# ── Clean staging ─────────────────────────────────────────────────────

rm -rf "$STAGING_DIR"

echo ""
echo "Created: $DIST_DIR/$DMG_NAME.dmg"
SIZE=$(du -h "$DIST_DIR/$DMG_NAME.dmg" | cut -f1 | tr -d ' ')
echo "Size: $SIZE"
[ "$SKIP_SIGN" = false ] && echo "Signed: $SIGN_IDENTITY"
echo ""
echo "DMG contents visible to user:"
echo "  Install obsidian-connector.app  (double-click to install)"
echo "  README.txt                      (instructions)"
echo ""
echo "Optional: notarize for full Gatekeeper bypass:"
echo "  xcrun notarytool submit $DIST_DIR/$DMG_NAME.dmg \\"
echo "    --apple-id YOUR_APPLE_ID \\"
echo "    --team-id $APPLE_TEAM_ID \\"
echo "    --password APP_SPECIFIC_PASSWORD \\"
echo "    --wait"
echo "  xcrun stapler staple $DIST_DIR/$DMG_NAME.dmg"
