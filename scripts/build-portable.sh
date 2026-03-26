#!/usr/bin/env bash
# build-portable.sh -- Assemble the portable skills bundle.
#
# Copies the 5 parity skills (compatible with kepano/obsidian-skills)
# into portable/skills/ for distribution to Codex CLI, OpenCode,
# Gemini CLI, and any Agent Skills-compliant agent.
#
# Only knowledge skills are included. Workflow skills that require
# the MCP server are excluded.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORTABLE_DIR="$REPO_ROOT/portable/skills"

# Explicitly list portable-eligible skills (no glob -- conscious additions only)
PORTABLE_SKILLS=(
  obsidian-markdown
  obsidian-bases
  json-canvas
  obsidian-cli
  defuddle
)

echo "Building portable skills bundle..."
echo ""

# Clean and recreate
rm -rf "$PORTABLE_DIR"
mkdir -p "$PORTABLE_DIR"

file_count=0
for skill in "${PORTABLE_SKILLS[@]}"; do
  src="$REPO_ROOT/skills/$skill"
  if [[ ! -d "$src" ]]; then
    echo "  WARNING: skills/$skill not found, skipping"
    continue
  fi
  cp -r "$src" "$PORTABLE_DIR/$skill"
  count=$(find "$PORTABLE_DIR/$skill" -type f | wc -l | tr -d ' ')
  file_count=$((file_count + count))
  echo "  Copied: $skill ($count files)"
done

echo ""
echo "Portable bundle ready: ${#PORTABLE_SKILLS[@]} skills, $file_count files"
echo "Location: portable/skills/"
echo ""
echo "Install:"
echo "  Codex CLI:  cp -r portable/skills/* ~/.codex/skills/"
echo "  OpenCode:   cp -r portable/skills/* ~/.opencode/skills/"
echo "  Gemini CLI: cp -r portable/skills/* ~/.gemini/skills/"
echo "  Claude Code: cp -r portable/skills/* .claude/skills/"
echo "  Universal:  cp -r portable/skills/* ~/.agents/skills/"
