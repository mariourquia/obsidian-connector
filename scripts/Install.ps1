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

# Global error trap: keep window open on any crash
trap {
    Write-Host ""
    Write-Host "  An error occurred: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Press Enter to close this window." -ForegroundColor White
    Read-Host
    exit 1
}

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
# Official install paths per Anthropic docs:
#   Windows native: $env:USERPROFILE\.local\bin\claude.exe
#   npm global:     $env:APPDATA\npm\claude.cmd
#   Homebrew:       /opt/homebrew/bin/claude (macOS only)
#   WinGet:         same as native
$ClaudePath = $null

# Method 1: PATH lookup
$found = Get-Command claude -ErrorAction SilentlyContinue
if ($found) {
    $ClaudePath = $found.Source
}

# Method 2: Official Windows install location (native installer / WinGet)
if (-not $ClaudePath) {
    $nativePath = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
    if (Test-Path $nativePath) {
        $ClaudePath = $nativePath
    }
}

# Method 3: npm global install
if (-not $ClaudePath) {
    $npmPath = Join-Path $env:APPDATA "npm\claude.cmd"
    if (Test-Path $npmPath) {
        $ClaudePath = $npmPath
    }
}

# Check ~/.claude dir -- exists if either Claude Code or Claude Desktop was used
$ClaudeHome = Join-Path $env:USERPROFILE ".claude"
$HasClaudeHome = Test-Path $ClaudeHome

if ($ClaudePath) {
    $HasClaudeCode = $true
    try {
        $ver = & $ClaudePath --version 2>$null
        Write-Green "  Claude Code CLI found: $ver"
    } catch {
        Write-Green "  Claude Code CLI found at: $ClaudePath"
    }
} else {
    Write-Yellow "  Claude Code CLI not found"
    Write-Dim  "  Install: irm https://claude.ai/install.ps1 | iex"
    if ($HasClaudeHome) {
        Write-Dim  "  (~/.claude exists -- will register plugin there)"
    }
}

# Check for Claude Desktop -- check directory existence (not just config file)
$ClaudeDesktopDir = Join-Path $env:APPDATA "Claude"
if (Test-Path $ClaudeDesktopDir) {
    $HasClaudeDesktop = $true
    Write-Green "  Claude Desktop found"
} else {
    $ClaudeLocalDir = Join-Path $env:LOCALAPPDATA "Claude"
    if (Test-Path $ClaudeLocalDir) {
        $HasClaudeDesktop = $true
        $ClaudeDesktopDir = $ClaudeLocalDir
        Write-Green "  Claude Desktop found (LocalAppData)"
    } else {
        Write-Yellow "  Claude Desktop not found (optional)"
    }
}

# Bail early if neither found
if (-not $HasClaudeCode -and -not $HasClaudeDesktop -and -not $HasClaudeHome) {
    Write-Host ""
    Write-Red "  Neither Claude Code nor Claude Desktop was found."
    Write-Host ""
    Write-Host "  Install one of these first:"
    Write-Host "    Claude Code:    irm https://claude.ai/install.ps1 | iex"
    Write-Host "    Claude Desktop: https://claude.ai/download"
    Write-Host ""
    Write-Host "  After installing, re-run this script or register manually:"
    Write-Dim  "    claude plugin add `"$InstallDir`""
    Write-Host ""
    Write-Bold "  Press Enter to close this window."
    Read-Host
    exit 0
}

# Register plugin via ~/.claude/ plugin cache (works for both Claude Code and Desktop)
# Register via ~/.claude/ plugin cache (works for Claude Code + Desktop)
# Triggers if we found Claude CLI, Desktop dir, OR ~/.claude exists
if ($HasClaudeCode -or $HasClaudeDesktop -or $HasClaudeHome) {
    Write-Blue "  Registering plugin in Claude plugin system..."
    $PluginVersion = (Get-Content (Join-Path $InstallDir "pyproject.toml") | Select-String 'version = "([^"]+)"').Matches.Groups[1].Value
    if (-not $PluginVersion) { $PluginVersion = "0.7.0" }
    $PluginCachePath = Join-Path $ClaudeHome "plugins\cache\local\obsidian-connector\$PluginVersion"
    $InstalledPluginsFile = Join-Path $ClaudeHome "plugins\installed_plugins.json"
    $SettingsFile = Join-Path $ClaudeHome "settings.json"

    try {
        # 1. Copy plugin files to the plugin cache
        if (-not (Test-Path $PluginCachePath)) {
            New-Item -ItemType Directory -Path $PluginCachePath -Force | Out-Null
        }

        $robocopyArgs = @(
            $InstallDir,
            $PluginCachePath,
            '/MIR',
            '/XD', '.git', '__pycache__', 'node_modules', 'dist', '.venv', '.local', '.claude',
            '/XF', '*.pyc', '.DS_Store', 'firebase-debug.log',
            '/NFL', '/NDL', '/NJH', '/NJS', '/NP'
        )
        & robocopy @robocopyArgs | Out-Null

        if ($LASTEXITCODE -ge 8) {
            throw "Robocopy failed with exit code $LASTEXITCODE"
        }
        Write-Green "  Plugin files copied to cache"

        # 2. Register in installed_plugins.json
        $pluginKey = "obsidian-connector@local"
        $now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")

        if (Test-Path $InstalledPluginsFile) {
            $ipData = Get-Content $InstalledPluginsFile -Raw | ConvertFrom-Json
        } else {
            New-Item -ItemType Directory -Path (Split-Path $InstalledPluginsFile) -Force | Out-Null
            $ipData = [PSCustomObject]@{ version = 2; plugins = [PSCustomObject]@{} }
        }

        $entry = @(
            [PSCustomObject]@{
                scope = "user"
                installPath = $PluginCachePath
                version = $PluginVersion
                installedAt = $now
                lastUpdated = $now
            }
        )

        if ($ipData.plugins.PSObject.Properties.Name -contains $pluginKey) {
            $ipData.plugins.$pluginKey = $entry
        } else {
            $ipData.plugins | Add-Member -NotePropertyName $pluginKey -NotePropertyValue $entry
        }

        $ipData | ConvertTo-Json -Depth 10 | Set-Content $InstalledPluginsFile -Encoding UTF8
        Write-Green "  Plugin registered in installed_plugins.json"

        # 3. Enable in settings.json
        if (Test-Path $SettingsFile) {
            $settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json
        } else {
            $settings = [PSCustomObject]@{ enabledPlugins = [PSCustomObject]@{} }
        }

        if (-not ($settings.PSObject.Properties.Name -contains "enabledPlugins")) {
            $settings | Add-Member -NotePropertyName "enabledPlugins" -NotePropertyValue ([PSCustomObject]@{})
        }

        if ($settings.enabledPlugins.PSObject.Properties.Name -contains $pluginKey) {
            $settings.enabledPlugins.$pluginKey = $true
        } else {
            $settings.enabledPlugins | Add-Member -NotePropertyName $pluginKey -NotePropertyValue $true
        }

        $settings | ConvertTo-Json -Depth 10 | Set-Content $SettingsFile -Encoding UTF8
        Write-Green "  Plugin enabled in settings.json"
        Write-Green "  17 skills + hooks + MCP tools registered"

        $InstalledSomewhere = $true

    } catch {
        Write-Yellow "  Could not register plugin automatically: $_"
        Write-Host ""
        Write-Host "  Manual install:"
        Write-Dim  "    claude plugin add `"$InstallDir`""
        $InstalledSomewhere = $true
    }
    Write-Host ""
}

# ── Step 4: Register with Claude Desktop ────────────────────────────

if ($HasClaudeDesktop) {
    $DesktopConfigPath = Join-Path $ClaudeDesktopDir "claude_desktop_config.json"
    Write-Blue "  Registering with Claude Desktop..."
    Write-Dim  "  Config: $DesktopConfigPath"

    # Create config file if directory exists but config doesn't
    if (-not (Test-Path $DesktopConfigPath)) {
        '{"mcpServers":{}}' | Set-Content $DesktopConfigPath -Encoding UTF8
        Write-Dim "  Created claude_desktop_config.json"
    }

    try {
        $pythonExe = Join-Path $VenvDir "Scripts\python.exe"
        if (-not (Test-Path $pythonExe)) {
            Write-Yellow "  Venv python not found at: $pythonExe"
            Write-Dim  "  Using system Python instead"
            $pythonExe = $PythonCmd
        }

        # Write a temp Python script to avoid path escaping issues in here-strings
        $tempScript = Join-Path $env:TEMP "obsidian_connector_setup_desktop.py"
        @"
import json, shutil, os, sys
from datetime import datetime

config_path = sys.argv[1]
python_exe = sys.argv[2]
install_dir = sys.argv[3]

# Backup
if os.path.exists(config_path):
    backup = config_path + '.backup-' + datetime.now().strftime('%Y%m%d-%H%M%S')
    shutil.copy2(config_path, backup)

# Read or create config
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
else:
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

config['mcpServers']['obsidian-connector'] = {
    'command': python_exe,
    'args': ['-m', 'obsidian_connector.mcp_server'],
    'env': {'PYTHONPATH': install_dir}
}

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2)

print('OK')
"@ | Set-Content $tempScript -Encoding UTF8

        Write-Dim  "  Running: $PythonCmd $tempScript"
        Write-Dim  "  Args: config=$DesktopConfigPath python=$pythonExe dir=$InstallDir"
        $result = & $PythonCmd $tempScript $DesktopConfigPath $pythonExe $InstallDir 2>&1
        Remove-Item $tempScript -ErrorAction SilentlyContinue

        if ($result -match "OK") {
            Write-Green "  MCP server registered in Claude Desktop config"
            Write-Dim  "  Restart Claude Desktop to load 62 MCP tools."
            $InstalledSomewhere = $true
        } else {
            Write-Yellow "  Config update returned: $result"
            $InstalledSomewhere = $true
        }
    } catch {
        Write-Yellow "  Could not update Claude Desktop config: $_"
        Write-Dim  "  Manual: add obsidian-connector to claude_desktop_config.json"
    }
} else {
    Write-Dim "  Claude Desktop not detected -- skipping MCP config"
}
}

Write-Host ""

# ── Summary ─────────────────────────────────────────────────────────

Write-Green "  Installation complete!"
Write-Host ""
if ($HasClaudeCode) {
    Write-Host "  Claude Code: Try /capture, /ritual, /sync in any conversation"
}
if ($HasClaudeDesktop) {
    Write-Host "  Claude Desktop: Restart Desktop to load 62 MCP tools"
}

Write-Host ""
$skillCount = (Get-ChildItem (Join-Path $InstallDir "skills") -Directory -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Dim "  Installed to: $InstallDir"
Write-Dim "  Skills: $skillCount | MCP tools: 62 | CLI: obsx"
Write-Host ""
Write-Bold "  Press Enter to close this window."
Read-Host
