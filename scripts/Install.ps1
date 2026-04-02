# ──────────────────────────────────────────────────────────────────────
# Obsidian Connector installer for Windows
#
# Called by the Inno Setup installer after file copy, or run standalone:
#   powershell -ExecutionPolicy Bypass -File Install.ps1 -InstallDir "C:\path\to\plugin"
#
# 1. Creates Python venv and installs the package
# 2. Detects Claude Code CLI and registers as plugin
# 3. Detects Claude Desktop and configures MCP server
# ──────────────────────────────────────────────────────────────────────

param(
    [string]$InstallDir = $PSScriptRoot
)

if ($InstallDir -eq $PSScriptRoot) {
    $InstallDir = Split-Path $PSScriptRoot -Parent
}

$ErrorActionPreference = 'Continue'

function Write-Green  { param([string]$Text) Write-Host $Text -ForegroundColor Green }
function Write-Blue   { param([string]$Text) Write-Host $Text -ForegroundColor Blue }
function Write-Yellow { param([string]$Text) Write-Host $Text -ForegroundColor Yellow }
function Write-Red    { param([string]$Text) Write-Host $Text -ForegroundColor Red }
function Write-Bold   { param([string]$Text) Write-Host $Text -ForegroundColor White }
function Write-Dim    { param([string]$Text) Write-Host $Text -ForegroundColor DarkGray }

Write-Host ""
Write-Blue @"

  ___  _         _    _ _                ___
 / _ \| |__  ___(_) _| (_) __ _ _ __    / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

"@

Write-Bold  "  Obsidian Connector Installer"
Write-Dim   "  62 MCP tools | 17 skills | 13 presets"
Write-Host  ""

# ── Verify files exist ──────────────────────────────────────────────

if (-not (Test-Path (Join-Path $InstallDir "obsidian_connector")) -or
    -not (Test-Path (Join-Path $InstallDir "pyproject.toml"))) {
    Write-Red "  Could not find the Obsidian Connector files."
    Write-Host "  Expected at: $InstallDir"
    Write-Host ""
    Write-Bold "  Press Enter to close this window."
    Read-Host
    exit 1
}

Write-Green "  Files found at: $InstallDir"
Write-Host ""

# ── Step 1: Python check ───────────────────────────────────────────

Write-Bold "  Step 1: Checking Python..."

$PythonCmd = $null
foreach ($cmd in @("python3", "python", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "3\.\d+") {
                $PythonCmd = $cmd
                Write-Green "  Python found: $ver"
                break
            }
        } catch {}
    }
}

if (-not $PythonCmd) {
    Write-Red "  Python 3.11+ not found."
    Write-Host "  Install from: https://www.python.org/downloads/"
    Write-Host ""
    Write-Bold "  Press Enter to close this window."
    Read-Host
    exit 1
}

# ── Step 2: Create venv and install ─────────────────────────────────

Write-Bold "  Step 2: Setting up Python environment..."

$VenvDir = Join-Path $InstallDir ".venv"
if (-not (Test-Path $VenvDir)) {
    & $PythonCmd -m venv $VenvDir
    Write-Green "  Virtual environment created"
} else {
    Write-Green "  Virtual environment already exists"
}

$PipPath = Join-Path $VenvDir "Scripts\pip.exe"
if (Test-Path $PipPath) {
    & $PipPath install -e $InstallDir --quiet 2>&1 | Out-Null
    Write-Green "  Package installed"
} else {
    Write-Yellow "  Could not find pip in venv. Try: $PythonCmd -m venv $VenvDir"
}

# ── Step 3: Register with Claude Code ───────────────────────────────

Write-Host ""
Write-Bold "  Step 3: Registering with Claude..."

$HasClaudeCode = $false
$HasClaudeDesktop = $false
$InstalledSomewhere = $false

# Check for Claude Code CLI
$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudeCmd) {
    $npmClaudePath = Join-Path $env:APPDATA "npm\claude.cmd"
    if (Test-Path $npmClaudePath) {
        $claudeCmd = Get-Item $npmClaudePath
    }
}

if ($claudeCmd) {
    $HasClaudeCode = $true
    Write-Green "  Claude Code CLI found"

    try {
        if ($claudeCmd.Source) {
            $output = & $claudeCmd.Source plugin add $InstallDir 2>&1
        } else {
            $output = & claude plugin add $InstallDir 2>&1
        }
        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
            Write-Green "  Plugin registered with Claude Code (skills + hooks + MCP tools)"
            $InstalledSomewhere = $true
        } else {
            Write-Yellow "  'plugin add' returned non-zero. Try: claude --plugin-dir `"$InstallDir`""
            $InstalledSomewhere = $true
        }
    } catch {
        Write-Yellow "  'plugin add' not available. Use: claude --plugin-dir `"$InstallDir`""
        $InstalledSomewhere = $true
    }
} else {
    Write-Dim "  Claude Code CLI not found (optional)"
}

# ── Step 4: Register with Claude Desktop ────────────────────────────

$DesktopConfigPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
if (Test-Path $DesktopConfigPath) {
    $HasClaudeDesktop = $true
    Write-Green "  Claude Desktop found"

    try {
        $config = Get-Content $DesktopConfigPath -Raw | ConvertFrom-Json
        if (-not $config.mcpServers) {
            $config | Add-Member -MemberType NoteProperty -Name mcpServers -Value @{} -Force
        }

        $pythonPath = Join-Path $VenvDir "Scripts\python.exe"
        $config.mcpServers."obsidian-connector" = @{
            command = $pythonPath
            args = @("-m", "obsidian_connector.mcp_server")
            env = @{
                PYTHONPATH = $InstallDir
            }
        }

        # Backup existing config
        $backupPath = "${DesktopConfigPath}.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $DesktopConfigPath $backupPath

        $config | ConvertTo-Json -Depth 10 | Set-Content $DesktopConfigPath -Encoding UTF8
        Write-Green "  MCP server registered in Claude Desktop config"
        Write-Dim  "  Config backed up to: $(Split-Path $backupPath -Leaf)"
        $InstalledSomewhere = $true
    } catch {
        Write-Yellow "  Could not update Claude Desktop config: $_"
        Write-Dim  "  Manual: add obsidian-connector to claude_desktop_config.json"
    }
} else {
    Write-Dim "  Claude Desktop not found (optional)"
}

Write-Host ""

# ── Summary ─────────────────────────────────────────────────────────

if ($InstalledSomewhere) {
    Write-Green "  Installation complete!"
    Write-Host ""
    if ($HasClaudeCode) {
        Write-Host "  Claude Code: Try /capture, /ritual, /sync in any conversation"
    }
    if ($HasClaudeDesktop) {
        Write-Host "  Claude Desktop: Restart Desktop to load 62 MCP tools"
    }
} else {
    Write-Yellow "  Neither Claude Code nor Claude Desktop detected."
    Write-Host ""
    Write-Host "  After installing Claude Code or Desktop:"
    Write-Host "    Claude Code:    claude plugin add `"$InstallDir`""
    Write-Host "    Claude Desktop: Add to claude_desktop_config.json"
}

Write-Host ""
$skillCount = (Get-ChildItem (Join-Path $InstallDir "skills") -Directory -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Dim "  Installed to: $InstallDir"
Write-Dim "  Skills: $skillCount | MCP tools: 62 | CLI: obsx"
Write-Host ""
Write-Bold "  Press Enter to close this window."
Read-Host
