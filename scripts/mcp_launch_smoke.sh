#!/usr/bin/env bash
# Smoke test: verify the MCP server starts, responds to initialize, lists tools, then exits cleanly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="${SCRIPT_DIR}/bin/obsx-mcp"

echo "=== MCP Server Launch Smoke Test ==="

# 1. Check server binary exists and is executable
if [[ ! -x "$SERVER" ]]; then
    echo "FAIL: $SERVER not found or not executable"
    exit 1
fi
echo "PASS: server binary exists"

# 2. Send initialize + notifications/initialized + tools/list, capture response
RESPONSE=$(printf '%s\n%s\n%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke-test","version":"1.0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
    | "$SERVER" 2>/dev/null)

# 3. Check initialize response
if echo "$RESPONSE" | grep -q '"serverInfo"'; then
    echo "PASS: initialize response contains serverInfo"
else
    echo "FAIL: no serverInfo in response"
    echo "  response: $RESPONSE"
    exit 1
fi

# 4. Check tools/list response
TOOL_COUNT=$(echo "$RESPONSE" | tr '\n' ' ' | grep -o '"name"' | wc -l | tr -d ' ')
if [[ "$TOOL_COUNT" -ge 8 ]]; then
    echo "PASS: tools/list returned $TOOL_COUNT tools (expected >=8)"
else
    echo "FAIL: tools/list returned $TOOL_COUNT tools (expected >=8)"
    exit 1
fi

echo "=== All MCP smoke checks passed ==="
