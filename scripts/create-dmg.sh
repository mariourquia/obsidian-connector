#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Build a signed .dmg installer for obsidian-connector
#
# Creates a macOS disk image containing a signed .app bundle.
# User opens DMG, sees "obsx Auto-Installer.app" and a README.
# Double-clicking the .app copies files and runs setup in Terminal.
#
# Usage:
#   ./scripts/create-dmg.sh                # builds dist/obsidian-connector.dmg
#   ./scripts/create-dmg.sh v0.2.0         # custom version in filename
#
# Requirements:
#   - Apple Developer ID certificate in keychain (or --no-sign)
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
APP_NAME="obsx Auto-Installer.app"

echo "Building $DMG_NAME.dmg..."
[ "$SKIP_SIGN" = false ] && echo "Signing with: $SIGN_IDENTITY"

# ── Clean ─────────────────────────────────────────────────────────────

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/$DMG_NAME" "$DIST_DIR"

# ── Copy project files into hidden .content/ ──────────────────────────

mkdir -p "$STAGING_DIR/$DMG_NAME/.content"
rsync -rlpt \
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

# ── Generate app icon ─────────────────────────────────────────────────
# Creates a purple/violet icon with "obsx" text -- distinctive and
# recognizable. Uses Core Graphics via Python for pixel-perfect output.

ICON_DIR="$STAGING_DIR/icon-build"
ICONSET_DIR="$ICON_DIR/AppIcon.iconset"
mkdir -p "$ICONSET_DIR"

ICONSET_DIR="$ICONSET_DIR" python3 << 'ICON_SCRIPT'
import struct, zlib, os, math

def create_png(width, height, pixels):
    """Create a minimal PNG from RGBA pixel data."""
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        return struct.pack('>I', len(data)) + c + crc

    header = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))

    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter: none
        for x in range(width):
            idx = (y * width + x) * 4
            raw += bytes(pixels[idx:idx+4])

    idat = chunk(b'IDAT', zlib.compress(raw, 9))
    iend = chunk(b'IEND', b'')
    return header + ihdr + idat + iend

def draw_icon(size):
    """Draw the obsx installer icon at given size."""
    pixels = [0] * (size * size * 4)
    cx, cy = size / 2, size / 2
    r_outer = size * 0.44
    r_inner = size * 0.36

    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)

            # Background circle with gradient
            if dist <= r_outer:
                # Purple gradient: darker at edges, lighter at center
                t = dist / r_outer
                r = int(88 + (140 - 88) * (1 - t))
                g = int(28 + (80 - 28) * (1 - t))
                b = int(135 + (200 - 135) * (1 - t))

                # Subtle top-light effect
                light = max(0, -dy / r_outer) * 0.3
                r = min(255, int(r + light * 80))
                g = min(255, int(g + light * 60))
                b = min(255, int(b + light * 90))

                # Anti-alias edge
                if dist > r_outer - 1.5:
                    alpha = max(0, min(255, int(255 * (r_outer - dist) / 1.5)))
                else:
                    alpha = 255

                pixels[idx] = r
                pixels[idx+1] = g
                pixels[idx+2] = b
                pixels[idx+3] = alpha

            # Draw a down-arrow in the center (install/download symbol)
            arrow_w = size * 0.22
            arrow_h = size * 0.18
            shaft_w = size * 0.08
            arrow_cy = cy - size * 0.02
            arrow_top = arrow_cy - arrow_h * 0.6
            arrow_bot = arrow_cy + arrow_h * 0.6
            arrow_mid = arrow_cy + arrow_h * 0.1

            in_arrow = False

            # Shaft (vertical bar)
            if abs(dx) < shaft_w / 2 and arrow_top <= y <= arrow_mid:
                in_arrow = True

            # Arrowhead (triangle pointing down)
            if arrow_mid <= y <= arrow_bot:
                progress = (y - arrow_mid) / (arrow_bot - arrow_mid)
                half_w = arrow_w * (1 - progress) / 2
                if abs(dx) < half_w:
                    in_arrow = True

            # Horizontal base line (platform)
            base_y = arrow_bot + size * 0.06
            if abs(y - base_y) < size * 0.015 and abs(dx) < arrow_w * 0.6:
                in_arrow = True

            if in_arrow and dist <= r_inner:
                pixels[idx] = 255
                pixels[idx+1] = 255
                pixels[idx+2] = 255
                pixels[idx+3] = 255

    return create_png(size, size, pixels)

# Generate all required iconset sizes
sizes = {
    'icon_16x16.png': 16,
    'icon_16x16@2x.png': 32,
    'icon_32x32.png': 32,
    'icon_32x32@2x.png': 64,
    'icon_128x128.png': 128,
    'icon_128x128@2x.png': 256,
    'icon_256x256.png': 256,
    'icon_256x256@2x.png': 512,
    'icon_512x512.png': 512,
}

iconset = os.environ['ICONSET_DIR']
for name, sz in sizes.items():
    png = draw_icon(sz)
    with open(os.path.join(iconset, name), 'wb') as f:
        f.write(png)
ICON_SCRIPT

# Convert iconset to icns
ICONSET_DIR="$ICONSET_DIR" iconutil -c icns "$ICONSET_DIR" -o "$STAGING_DIR/AppIcon.icns" 2>/dev/null && {
    echo "Icon generated"
} || {
    echo "Warning: iconutil failed, using default icon"
}

# ── Build .app bundle (in isolated temp dir, then move in) ────────────
# Building the .app away from the rsync'd .content/ avoids inheriting
# extended attributes that break codesign.

APP_BUILD_DIR="$STAGING_DIR/.app-build/$APP_NAME"
mkdir -p "$APP_BUILD_DIR/Contents/MacOS"
mkdir -p "$APP_BUILD_DIR/Contents/Resources"
APP_DIR="$APP_BUILD_DIR"

# Copy icon if generated
if [ -f "$STAGING_DIR/AppIcon.icns" ]; then
    cp "$STAGING_DIR/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
fi

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
    <string>obsx Auto-Installer</string>
    <key>CFBundleDisplayName</key>
    <string>obsx Auto-Installer</string>
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
    <string>MIT License - obsidian-connector ${VERSION}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
</dict>
</plist>
PLIST

# The executable -- copies project to writable location, then installs
cat > "$APP_DIR/Contents/MacOS/install" << 'LAUNCHER'
#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsx Auto-Installer
# Copies project to ~/obsidian-connector, then runs setup in Terminal.
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
CONTENT_DIR="$SCRIPT_DIR/.content"
INSTALL_DIR="$HOME/obsidian-connector"

if [ ! -d "$CONTENT_DIR" ]; then
    osascript -e 'display alert "obsx Auto-Installer" message "Could not find installer files. Please run from the mounted disk image." as critical buttons {"OK"} default button "OK"'
    exit 1
fi

# Copy to writable location (~/obsidian-connector)
if [ -d "$INSTALL_DIR" ]; then
    response=$(osascript -e '
        display dialog "obsidian-connector is already installed." & return & return & "Location: ~/obsidian-connector" & return & return & "Would you like to reinstall?" buttons {"Cancel", "Reinstall"} default button "Reinstall" with icon caution with title "obsx Auto-Installer"
    ' 2>/dev/null | grep "Reinstall" || true)
    if [ -z "$response" ]; then
        exit 0
    fi
    rm -rf "$INSTALL_DIR"
fi

# Show progress dialog while copying
osascript -e 'display notification "Copying files to ~/obsidian-connector..." with title "obsx Auto-Installer"' 2>/dev/null || true
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

# ── Create README ─────────────────────────────────────────────────────

cat > "$STAGING_DIR/$DMG_NAME/README.txt" << README

    ╔══════════════════════════════════════════════════╗
    ║                                                  ║
    ║          obsx — Obsidian × Claude                ║
    ║          Auto-Installer  v${VERSION}                 ║
    ║                                                  ║
    ╠══════════════════════════════════════════════════╣
    ║                                                  ║
    ║   Double-click the app to install.               ║
    ║                                                  ║
    ║   What it does:                                  ║
    ║     • Installs to ~/obsidian-connector           ║
    ║     • Sets up a Python environment               ║
    ║     • Configures Claude Desktop automatically    ║
    ║     • Connects Claude to your Obsidian vault     ║
    ║                                                  ║
    ║   Requirements:                                  ║
    ║     • Python 3.11+   python.org/downloads        ║
    ║     • Obsidian        obsidian.md                ║
    ║     • Claude Desktop                             ║
    ║                                                  ║
    ║   After install, restart Claude Desktop           ║
    ║   and Claude will have vault access.             ║
    ║                                                  ║
    ╚══════════════════════════════════════════════════╝

    29 MCP tools · 29 CLI commands · 4 skills
    Search, read, graph analysis, thinking tools,
    daily workflows, and more.

    github.com/mariourquia/obsidian-connector

README

# ── Sign the .app bundle ──────────────────────────────────────────────

if [ "$SKIP_SIGN" = false ]; then
    echo "Stripping extended attributes..."
    xattr -cr "$STAGING_DIR" 2>/dev/null || true
    # Explicitly remove FinderInfo from .app (macOS auto-adds it to bundles)
    xattr -d com.apple.FinderInfo "$APP_DIR" 2>/dev/null || true
    xattr -d "com.apple.fileprovider.fpfs#P" "$APP_DIR" 2>/dev/null || true
    # Strip from every file in the .app
    find "$APP_DIR" -exec xattr -c {} \; 2>/dev/null || true
    dot_clean -m "$APP_DIR" 2>/dev/null || true

    echo "Signing .app bundle..."
    # Sign the executable first, then the bundle (inside-out)
    codesign --force --sign "$SIGN_IDENTITY" \
        --options runtime --timestamp \
        "$APP_DIR/Contents/MacOS/install" 2>&1 || true
    codesign --force --sign "$SIGN_IDENTITY" \
        --options runtime --timestamp \
        "$APP_DIR" 2>&1 || true

    echo "Verifying signature..."
    codesign -dvv "$APP_DIR" 2>&1 | grep -E "Authority|Identifier|TeamIdentifier"
fi

# ── Move signed .app into DMG staging ─────────────────────────────────

mv "$APP_BUILD_DIR" "$STAGING_DIR/$DMG_NAME/$APP_NAME"

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
    codesign --force --sign "$SIGN_IDENTITY" --timestamp \
        "$DIST_DIR/$DMG_NAME.dmg" 2>&1 || true
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
echo "  obsx Auto-Installer.app  (double-click to install)"
echo "  README.txt               (instructions)"
echo ""
if [ "$SKIP_SIGN" = false ]; then
    echo "Notarize for full Gatekeeper bypass:"
    echo "  xcrun notarytool submit $DIST_DIR/$DMG_NAME.dmg \\"
    echo "    --apple-id YOUR_APPLE_ID \\"
    echo "    --team-id $APPLE_TEAM_ID \\"
    echo "    --password APP_SPECIFIC_PASSWORD \\"
    echo "    --wait"
    echo "  xcrun stapler staple $DIST_DIR/$DMG_NAME.dmg"
fi
