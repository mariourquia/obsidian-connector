# -----------------------------------------------------------------------
# obsidian-connector Windows installer (PowerShell)
#
# One-command setup: creates the Python venv, installs the package,
# and configures Claude Desktop to use the MCP server.
#
# Usage:
#   .\scripts\Install.ps1              # from repo root (interactive)
#   powershell -File scripts\Install.ps1
#   .\scripts\Install.ps1 -NonInteractive -InstallSkills  # silent mode
# -----------------------------------------------------------------------

param(
    [switch]$NonInteractive,
    [switch]$InstallSchedule,
    [switch]$InstallSkills
)

$ErrorActionPreference = "Stop"

# -- Helpers ------------------------------------------------------------

function Write-Bold { param([string]$Text) Write-Host $Text -ForegroundColor White }
function Write-Success { param([string]$Text) Write-Host $Text -ForegroundColor Green }
function Write-Dim { param([string]$Text) Write-Host $Text -ForegroundColor DarkGray }
function Write-Err { param([string]$Text) Write-Host "ERROR: $Text" -ForegroundColor Red }

# -- Locate repo root ---------------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

Write-Bold "obsidian-connector installer (Windows)"
Write-Dim "repo: $RepoRoot"
Write-Host ""

# -- Step 1: Check Python -----------------------------------------------

Write-Bold "[1/4] Checking Python..."

$PythonExe = $null
$Candidates = @("python3", "python", "py")

foreach ($candidate in $Candidates) {
    try {
        $version = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($version) {
            $parts = $version.Split(".")
            $major = [int]$parts[0]
            $minor = [int]$parts[1]
            if ($major -ge 3 -and $minor -ge 11) {
                $PythonExe = $candidate
                break
            }
        }
    }
    catch {
        # Candidate not found, try next
    }
}

if (-not $PythonExe) {
    Write-Err "Python 3.11+ is required but not found."
    Write-Host "  Install from https://www.python.org/downloads/ and re-run this script."
    exit 1
}

$PythonVersion = & $PythonExe --version 2>&1
Write-Success "  Found $PythonExe ($PythonVersion)"

# -- Step 2: Create venv and install -------------------------------------

Write-Bold "[2/4] Setting up Python environment..."

$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts" "python.exe"
$VenvPip = Join-Path $VenvDir "Scripts" "pip.exe"

if (-not (Test-Path $VenvDir)) {
    & $PythonExe -m venv $VenvDir
    Write-Dim "  Created .venv"
}
else {
    Write-Dim "  .venv already exists"
}

try {
    & $VenvPip install --quiet --upgrade pip
    & $VenvPip install --quiet -r (Join-Path $RepoRoot "requirements-lock.txt")
    & $VenvPip install --quiet --no-deps -e $RepoRoot
    Write-Success "  Installed obsidian-connector"
}
catch {
    Write-Err "Failed to install package: $_"
    exit 1
}

# -- Step 3: Configure Claude Desktop -----------------------------------

Write-Bold "[3/4] Configuring Claude Desktop..."

$ClaudeConfigDir = Join-Path $env:APPDATA "Claude"
if (-not $env:APPDATA) {
    $ClaudeConfigDir = Join-Path $HOME "AppData" "Roaming" "Claude"
}
$ClaudeConfig = Join-Path $ClaudeConfigDir "claude_desktop_config.json"

$ClaudeConfigured = $false

try {
    if (-not (Test-Path $ClaudeConfigDir)) {
        New-Item -ItemType Directory -Path $ClaudeConfigDir -Force | Out-Null
    }

    $ServerEntry = @{
        command = $VenvPython
        args    = @("-u", "-m", "obsidian_connector.mcp_server")
        cwd     = $RepoRoot
        env     = @{
            PYTHONPATH = $RepoRoot
        }
    }

    if (Test-Path $ClaudeConfig) {
        $config = Get-Content $ClaudeConfig -Raw | ConvertFrom-Json
        if (-not $config.mcpServers) {
            $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue @{} -Force
        }

        # Convert to hashtable for manipulation
        $servers = @{}
        if ($config.mcpServers -is [PSCustomObject]) {
            $config.mcpServers.PSObject.Properties | ForEach-Object {
                $servers[$_.Name] = $_.Value
            }
        }

        $servers["obsidian-connector"] = $ServerEntry
        $config.mcpServers = $servers

        $config | ConvertTo-Json -Depth 10 | Set-Content $ClaudeConfig -Encoding UTF8
        Write-Success "  Claude Desktop configured (updated existing)"
    }
    else {
        $config = @{
            mcpServers = @{
                "obsidian-connector" = $ServerEntry
            }
        }
        $config | ConvertTo-Json -Depth 10 | Set-Content $ClaudeConfig -Encoding UTF8
        Write-Success "  Claude Desktop configured (created new)"
    }

    $ClaudeConfigured = $true
}
catch {
    Write-Dim "  Could not auto-configure Claude Desktop: $_"
    Write-Dim "  See manual instructions below."
}

# -- Step 4: Verify -----------------------------------------------------

Write-Bold "[4/4] Verifying installation..."

try {
    $ImportCheck = & $VenvPython -c "import obsidian_connector; print('  Package OK')" 2>&1
    Write-Host $ImportCheck
    Write-Success "  Installation verified"
}
catch {
    Write-Err "Package import failed. Check the output above for errors."
    exit 1
}

# -- Done ---------------------------------------------------------------

Write-Host ""
Write-Host ("=" * 60)
Write-Success "  Installation complete!"
Write-Host ("=" * 60)
Write-Host ""

if ($ClaudeConfigured) {
    Write-Bold "Next steps:"
    Write-Host "  1. Make sure Obsidian is running"
    Write-Host "  2. Restart Claude Desktop"
    Write-Host "  3. The Obsidian tools will appear automatically"
}
else {
    Write-Bold "Almost done -- manual step needed:"
    Write-Host ""
    Write-Host "  Add this to: $ClaudeConfig"
    Write-Host ""
    Write-Host '  {'
    Write-Host '    "mcpServers": {'
    Write-Host '      "obsidian-connector": {'
    Write-Host "        `"command`": `"$VenvPython`","
    Write-Host '        "args": ["-u", "-m", "obsidian_connector.mcp_server"],'
    Write-Host "        `"cwd`": `"$RepoRoot`","
    Write-Host '        "env": {'
    Write-Host "          `"PYTHONPATH`": `"$RepoRoot`""
    Write-Host '        }'
    Write-Host '      }'
    Write-Host '    }'
    Write-Host '  }'
    Write-Host ""
    Write-Bold "Then:"
    Write-Host "  1. Make sure Obsidian is running"
    Write-Host "  2. Restart Claude Desktop"
    Write-Host "  3. The Obsidian tools will appear automatically"
}

# -- Optional: Scheduled Task -------------------------------------------

Write-Host ""
Write-Bold "Optional: Scheduled Task"
Write-Dim "Set up a daily scheduled task to run workflows automatically."
Write-Host ""

if (-not $NonInteractive) {
    $InstallSchedule = (Read-Host "  Install scheduled daily briefing (Windows Task Scheduler)? [y/N]") -match "^[Yy]$"
}
if ($InstallSchedule) {
    try {
        $TaskName = "obsidian-connector-morning"
        $ScriptPath = Join-Path $RepoRoot "scheduling" "run_scheduled.py"
        $TaskAction = "`"$VenvPython`" `"$ScriptPath`" morning"

        schtasks /CREATE /SC DAILY /TN $TaskName /TR $TaskAction /ST "08:00" /F 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Success "  Scheduled daily briefing installed (08:00 daily)"
            Write-Dim "  Task name: $TaskName"
            Write-Dim "  Uninstall: schtasks /DELETE /TN $TaskName /F"
        }
        else {
            Write-Dim "  Task creation failed. You may need to run as Administrator."
        }
    }
    catch {
        Write-Dim "  Could not create scheduled task: $_"
    }
}
else {
    Write-Dim "  Skipped scheduling"
}

# -- Optional: Skills ---------------------------------------------------

Write-Host ""
if (-not $NonInteractive) {
    $InstallSkills = (Read-Host "  Install Claude Code skills (/morning, /evening, /idea, /weekly)? [y/N]") -match "^[Yy]$"
}
if ($InstallSkills) {
    $CommandsDir = Join-Path $RepoRoot ".claude" "commands"
    if (-not (Test-Path $CommandsDir)) {
        New-Item -ItemType Directory -Path $CommandsDir -Force | Out-Null
    }
    $SkillsDir = Join-Path $RepoRoot "skills"
    $Copied = 0
    if (Test-Path $SkillsDir) {
        Get-ChildItem -Path $SkillsDir -Filter "*.md" | ForEach-Object {
            Copy-Item $_.FullName -Destination $CommandsDir
            $Copied++
        }
    }
    if ($Copied -gt 0) {
        Write-Success "  Installed $Copied skill(s) to .claude/commands/"
    }
    else {
        Write-Dim "  No skill files found in skills/"
    }
}
else {
    Write-Dim "  Skipped skills"
}

Write-Host ""
Write-Dim "CLI available at: $RepoRoot\bin\obsx"
Write-Dim "Health check:     $VenvPython -m obsidian_connector.cli doctor"
Write-Host ""
