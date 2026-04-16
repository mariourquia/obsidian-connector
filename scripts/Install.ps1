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
    [string]$InstallDir = $PSScriptRoot,
    [switch]$NonInteractive
)

if ($InstallDir -eq $PSScriptRoot) {
    $InstallDir = Split-Path $PSScriptRoot -Parent
}

# Detect non-interactive mode (explicit flag, Inno Setup /VERYSILENT, piped stdin, CI)
if (-not $NonInteractive) {
    $NonInteractive = (-not [Environment]::UserInteractive) -or ([Console]::IsInputRedirected) -or ($env:CI -eq "true")
}

$ErrorActionPreference = 'Continue'

# ── Log file for non-interactive mode ────────────────────────────────
# When Inno Setup runs with -NonInteractive and the window is hidden,
# users can find this log at %TEMP%\obsidian-connector-install.log

$LogFile = Join-Path $env:TEMP "obsidian-connector-install.log"

if ($NonInteractive) {
    try {
        Start-Transcript -Path $LogFile -Force -ErrorAction SilentlyContinue | Out-Null
    } catch {
        # Transcript already running or unavailable -- write a manual log
    }
}

# ── Config ───────────────────────────────────────────────────────────

$TelemetryUrl = "https://cre-skills-feedback-api.vercel.app/api/installer-telemetry"
$PluginNameConst = "obsidian-connector"
$InstallerVersionConst = "0.8.3"
$TotalSteps = 6

# ── Timing ───────────────────────────────────────────────────────────

$InstallStart = Get-Date

# ── Step tracking ────────────────────────────────────────────────────

$StepResults = @{
    python   = "pending"
    venv     = "pending"
    pip      = "pending"
    register = "pending"
    desktop  = "pending"
    verify   = "pending"
}

$PythonVersion = ""
$PythonSource = ""
$ClaudeCodePresent = $false
$ClaudeDesktopPresent = $false
$EdgeCases = [System.Collections.Generic.List[string]]::new()
$Remediations = [System.Collections.Generic.List[string]]::new()
$FinalStatus = "failure"
$FailedStep = ""
$FailedMsg = ""

# ── Helpers ──────────────────────────────────────────────────────────

function Write-Green  { param([string]$Text) Write-Host $Text -ForegroundColor Green }
function Write-Blue   { param([string]$Text) Write-Host $Text -ForegroundColor Blue }
function Write-Yellow { param([string]$Text) Write-Host $Text -ForegroundColor Yellow }
function Write-Red    { param([string]$Text) Write-Host $Text -ForegroundColor Red }
function Write-Bold   { param([string]$Text) Write-Host $Text -ForegroundColor White }
function Write-Dim    { param([string]$Text) Write-Host $Text -ForegroundColor DarkGray }

function Write-Step {
    param([int]$N, [string]$Text)
    Write-Host ""
    Write-Bold "  [$N/$TotalSteps] $Text"
}

function Add-EdgeCase {
    param([string]$Name)
    if (-not $EdgeCases.Contains($Name)) { $EdgeCases.Add($Name) }
}

function Add-Remediation {
    param([string]$Name)
    if (-not $Remediations.Contains($Name)) { $Remediations.Add($Name) }
}

# ── Install ID ───────────────────────────────────────────────────────

function Get-InstallHash {
    $idSource = "$env:COMPUTERNAME-$env:USERNAME"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($idSource))
    return [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLower()
}

$InstallHash = Get-InstallHash

# ── Telemetry ────────────────────────────────────────────────────────

function Send-InstallerTelemetry {
    param(
        [string]$Status,
        [string]$StepFailed = "",
        [string]$ErrorMsg = ""
    )
    try {
        $elapsed = [int]((Get-Date) - $InstallStart).TotalSeconds

        $eventSeed = "$Status-$StepFailed-$(Get-Date -Format 'yyyyMMddHHmmssffff')"
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $eventBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($eventSeed))
        $eventId = "it_" + [System.BitConverter]::ToString($eventBytes).Replace("-", "").ToLower().Substring(0, 16)

        if ($ErrorMsg.Length -gt 2000) { $ErrorMsg = $ErrorMsg.Substring(0, 2000) }

        $body = @{
            id                  = $eventId
            plugin_name         = $PluginNameConst
            plugin_version      = $InstallerVersionConst
            installer_type      = "ps1"
            os                  = "windows"
            os_version          = [System.Environment]::OSVersion.Version.ToString()
            arch                = $env:PROCESSOR_ARCHITECTURE
            status              = $Status
            install_id_hash     = $InstallHash
            python_version      = $PythonVersion
            python_source       = $PythonSource
            claude_code_present = $ClaudeCodePresent
            claude_desktop_present = $ClaudeDesktopPresent
            step_results        = $StepResults
            edge_cases          = ($EdgeCases -join ",")
            remediations        = ($Remediations -join ",")
            total_duration_s    = $elapsed
            step_failed         = $StepFailed
            error_message       = $ErrorMsg
        } | ConvertTo-Json -Depth 5 -Compress

        Invoke-RestMethod -Uri $TelemetryUrl -Method POST -Body $body `
            -ContentType "application/json" -TimeoutSec 5 `
            -ErrorAction SilentlyContinue | Out-Null
    } catch {
        # Telemetry is best-effort -- never block installation
    }
}

# ── Global error trap ────────────────────────────────────────────────

trap {
    Write-Host ""
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Red
    Write-Host "  INSTALLATION ERROR" -ForegroundColor Red
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Red
    Write-Host ""
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""

    $step = if ($FailedStep) { $FailedStep } else { "unhandled_exception" }
    Send-InstallerTelemetry -Status "failure" -StepFailed $step -ErrorMsg $_.Exception.Message

    Write-Dim "  An anonymous error report was sent to help improve the installer."
    if ($NonInteractive) {
        Write-Dim "  Install log: $LogFile"
    }
    Write-Host ""
    Write-Host "  Submit a bug report:" -ForegroundColor Yellow
    Write-Host "  https://github.com/mariourquia/obsidian-connector/issues/new?labels=bug,installer" -ForegroundColor Cyan
    Write-Host ""
    if (-not $NonInteractive) {
        Write-Bold "  Press Enter to close this window."
        Read-Host
    }
    if ($NonInteractive) { try { Stop-Transcript -ErrorAction SilentlyContinue } catch {} }
    exit 1
}

# ── Banner ───────────────────────────────────────────────────────────

Write-Host ""
Write-Blue @"

  ___  _         _    _ _                ___
 / _ \| |__  ___(_) _| (_) __ _ _ __    / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

"@

Write-Bold  "  Obsidian Connector Installer v$InstallerVersionConst"
Write-Dim   "  100+ MCP tools | 15+ skills | 10+ presets"
Write-Host  ""
if ($NonInteractive) {
    Write-Dim "  Running in non-interactive mode"
    Write-Dim "  Log file: $LogFile"
    Write-Host ""
}

# ── Verify files exist ──────────────────────────────────────────────

if (-not (Test-Path (Join-Path $InstallDir "obsidian_connector")) -or
    -not (Test-Path (Join-Path $InstallDir "pyproject.toml"))) {
    Write-Red "  Could not find the Obsidian Connector files."
    Write-Host "  Expected at: $InstallDir"
    $FailedStep = "preflight"
    $FailedMsg = "Project files not found at $InstallDir"
    if (-not $NonInteractive) {
        Write-Bold "  Press Enter to close this window."
        Read-Host
    }
    exit 1
}

Write-Green "  Files found at: $InstallDir"

# ── Pre-flight edge case detection ──────────────────────────────────

if ($InstallDir -match ' ') {
    Add-EdgeCase "spaces_in_path"
    Write-Yellow "  Note: install path contains spaces"
}

if ($env:USERNAME -match '[^\x00-\x7F]') {
    Add-EdgeCase "non_ascii_username"
}

# Read-only check
$testFile = Join-Path $InstallDir ".install_write_test"
try {
    [System.IO.File]::WriteAllText($testFile, "test")
    Remove-Item $testFile -ErrorAction SilentlyContinue
} catch {
    Add-EdgeCase "read_only_filesystem"
    Write-Red "  Error: cannot write to install directory"
    Write-Dim "  Path: $InstallDir"
    $FailedStep = "preflight"
    Send-InstallerTelemetry -Status "failure" -StepFailed "preflight" -ErrorMsg "Read-only filesystem at $InstallDir"
    if (-not $NonInteractive) {
        Write-Bold "  Press Enter to close this window."
        Read-Host
    }
    exit 1
}

# ── Step 1/6: Python check ──────────────────────────────────────────

Write-Step 1 "Checking Python..."

$PythonCmd = $null

foreach ($cmd in @("python3", "python", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $found) { continue }

    # Reject Windows Store stub (WindowsApps directory)
    if ($found.Source -match 'WindowsApps') {
        Add-EdgeCase "windows_store_stub"
        Write-Dim "  Skipping Windows Store stub: $($found.Source)"

        # Try to disable App Execution Alias (best-effort, needs no admin)
        try {
            $aliasPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe"
            if (Test-Path $aliasPath) {
                Write-Dim "  Attempting to disable App Execution Alias..."
                # Note: this registry key may not control the alias on all Windows versions
                Add-Remediation "store_alias_disable_attempted"
            }
        } catch {}
        continue
    }

    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)\.(\d+)") {
            $minor = [int]$Matches[1]
            $patch = $Matches[2]
            if ($minor -ge 11) {
                $PythonCmd = $cmd
                $PythonVersion = "3.$minor.$patch"
                # Determine source
                $pyPath = $found.Source
                if ($pyPath -match 'Programs\\Python') { $PythonSource = "python.org" }
                elseif ($pyPath -match 'scoop') { $PythonSource = "scoop" }
                elseif ($pyPath -match 'chocolatey') { $PythonSource = "choco" }
                elseif ($pyPath -match 'winget') { $PythonSource = "winget" }
                else { $PythonSource = "system" }
                Write-Green "  Python found: $ver ($PythonSource)"
                break
            } else {
                Write-Dim "  $ver found but 3.11+ required"
            }
        }
    } catch {
        Write-Dim "  $cmd found but --version failed"
    }
}

# Try py launcher with -3 flag
if (-not $PythonCmd) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher -and $pyLauncher.Source -notmatch 'WindowsApps') {
        try {
            $ver = & py -3 --version 2>&1
            if ($ver -match "Python 3\.(\d+)\.(\d+)" -and [int]$Matches[1] -ge 11) {
                $PythonCmd = "py"
                $PythonVersion = "3.$($Matches[1]).$($Matches[2])"
                $PythonSource = "py-launcher"
                Write-Green "  Python found via launcher: $ver"
            }
        } catch {}
    }
}

# Check common install locations
if (-not $PythonCmd) {
    foreach ($path in @(
        "${env:LOCALAPPDATA}\Programs\Python\Python314\python.exe",
        "${env:LOCALAPPDATA}\Programs\Python\Python313\python.exe",
        "${env:LOCALAPPDATA}\Programs\Python\Python312\python.exe",
        "${env:LOCALAPPDATA}\Programs\Python\Python311\python.exe",
        "C:\Python314\python.exe",
        "C:\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "${env:ProgramFiles}\Python312\python.exe",
        "${env:ProgramFiles}\Python311\python.exe"
    )) {
        if (Test-Path $path) {
            try {
                $ver = & $path --version 2>&1
                if ($ver -match "Python 3\.(\d+)\.(\d+)" -and [int]$Matches[1] -ge 11) {
                    $PythonCmd = $path
                    $PythonVersion = "3.$($Matches[1]).$($Matches[2])"
                    $PythonSource = "manual"
                    Add-EdgeCase "python_not_in_path"
                    Write-Green "  Python found at: $path ($ver)"

                    # Add to PATH for current session
                    $pyDir = Split-Path $path -Parent
                    $env:PATH = "$pyDir;$env:PATH"
                    Add-Remediation "path_fix_session"
                    Write-Dim "  Added $pyDir to PATH for this session"
                    break
                }
            } catch {}
        }
    }
}

# Auto-install if still not found
if (-not $PythonCmd) {
    Write-Yellow "  Python 3.11+ not found. Attempting to install..."

    $installed = $false

    # Try winget
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Dim "  Installing Python 3.12 via winget..."
        & winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent 2>&1 | Out-Null
        # Refresh PATH
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")

        foreach ($cmd in @("python3", "python")) {
            $found = Get-Command $cmd -ErrorAction SilentlyContinue
            if ($found -and $found.Source -notmatch 'WindowsApps') {
                try {
                    $ver = & $cmd --version 2>&1
                    if ($ver -match "Python 3\.(\d+)\.(\d+)" -and [int]$Matches[1] -ge 11) {
                        $PythonCmd = $cmd
                        $PythonVersion = "3.$($Matches[1]).$($Matches[2])"
                        $PythonSource = "winget"
                        $installed = $true
                        Add-Remediation "winget_install"
                        Write-Green "  Python installed via winget: $ver"
                        break
                    }
                } catch {}
            }
        }
    }

    # Try chocolatey
    if (-not $installed) {
        $choco = Get-Command choco -ErrorAction SilentlyContinue
        if ($choco) {
            Write-Dim "  Installing Python 3.12 via chocolatey..."
            & choco install python312 -y --no-progress 2>&1 | Out-Null
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")

            foreach ($cmd in @("python3", "python")) {
                $found = Get-Command $cmd -ErrorAction SilentlyContinue
                if ($found -and $found.Source -notmatch 'WindowsApps') {
                    try {
                        $ver = & $cmd --version 2>&1
                        if ($ver -match "Python 3\.(\d+)\.(\d+)" -and [int]$Matches[1] -ge 11) {
                            $PythonCmd = $cmd
                            $PythonVersion = "3.$($Matches[1]).$($Matches[2])"
                            $PythonSource = "choco"
                            $installed = $true
                            Add-Remediation "choco_install"
                            Write-Green "  Python installed via chocolatey: $ver"
                            break
                        }
                    } catch {}
                }
            }
        }
    }

    if (-not $PythonCmd) {
        $StepResults["python"] = "fail"
        Write-Red "  Python 3.11+ could not be installed automatically."
        Write-Host "  Install from: https://www.python.org/downloads/"
        Write-Host ""
        Send-InstallerTelemetry -Status "failure" -StepFailed "python_check" `
            -ErrorMsg "Python 3.11+ not found and auto-install failed"
        if (-not $NonInteractive) {
            Write-Bold "  Press Enter to close this window."
            Read-Host
        }
        exit 1
    }
}

$StepResults["python"] = "ok"

# ── Step 2/6: Create venv ────────────────────────────────────────────

Write-Step 2 "Creating virtual environment..."

$VenvDir = Join-Path $InstallDir ".venv"
$VenvCreated = $false

if (Test-Path $VenvDir) {
    $venvPy = Join-Path $VenvDir "Scripts\python.exe"
    if (Test-Path $venvPy) {
        Write-Green "  Virtual environment already exists"
        $VenvCreated = $true
    } else {
        Add-EdgeCase "corrupt_venv"
        Write-Yellow "  Existing venv is broken, recreating..."
        Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $VenvCreated) {
    try {
        & $PythonCmd -m venv $VenvDir 2>&1 | Out-Null

        # Antivirus quarantine check: verify python.exe exists after creation
        $venvPy = Join-Path $VenvDir "Scripts\python.exe"
        if (-not (Test-Path $venvPy)) {
            Add-EdgeCase "antivirus_quarantine"
            Write-Yellow "  Warning: python.exe missing after venv creation"
            Write-Yellow "  This often means antivirus software quarantined it."
            Write-Dim  "  Check Windows Security > Virus & threat protection > Protection history"
            throw "python.exe quarantined after venv creation"
        }

        Write-Green "  Virtual environment created"
        $VenvCreated = $true
    } catch {
        Add-EdgeCase "venv_module_failed"
        Write-Yellow "  venv module failed: $_"
        Write-Yellow "  Trying virtualenv..."

        try {
            & $PythonCmd -m pip install --user virtualenv 2>&1 | Out-Null
            & $PythonCmd -m virtualenv $VenvDir 2>&1 | Out-Null

            $venvPy = Join-Path $VenvDir "Scripts\python.exe"
            if (Test-Path $venvPy) {
                $VenvCreated = $true
                Add-Remediation "virtualenv_fallback"
                Write-Green "  Created with virtualenv"
            }
        } catch {
            Write-Dim "  virtualenv also failed: $_"
        }
    }
}

if (-not $VenvCreated) {
    $StepResults["venv"] = "fail"
    Write-Red "  Failed to create virtual environment"
    Write-Dim "  Tried: python -m venv, virtualenv"
    Send-InstallerTelemetry -Status "failure" -StepFailed "venv_create" `
        -ErrorMsg "Both venv and virtualenv failed"
    if (-not $NonInteractive) {
        Write-Bold "  Press Enter to close this window."
        Read-Host
    }
    exit 1
}

$StepResults["venv"] = "ok"

# ── Step 3/6: Install packages ───────────────────────────────────────

Write-Step 3 "Installing packages..."

$PipPath = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $PipPath)) {
    Add-EdgeCase "pip_missing"
    Write-Yellow "  pip not found in venv, attempting ensurepip..."
    $venvPy = Join-Path $VenvDir "Scripts\python.exe"
    try {
        & $venvPy -m ensurepip --upgrade 2>&1 | Out-Null
        Add-Remediation "ensurepip"
    } catch {}
}

if (Test-Path $PipPath) {
    $EditableInstallTarget = "${InstallDir}[tui]"
    Write-Dim "  Upgrading pip..."
    & $PipPath install --upgrade pip 2>&1 | ForEach-Object { Write-Dim "    $_" }

    $pipOk = $false

    # Attempt 1: normal install
    Write-Dim "  Installing obsidian-connector..."
    try {
        $pipOutput = & $PipPath install -e $EditableInstallTarget 2>&1
        $pipOutput | ForEach-Object {
            if ($_ -match '(Downloading|Installing|Collecting|Building|Successfully)') {
                Write-Dim "    $_"
            }
        }
        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) { $pipOk = $true }
    } catch {}

    # Attempt 2: --no-cache-dir (cache corruption or proxy issues)
    if (-not $pipOk) {
        Add-EdgeCase "pip_failed_first_attempt"
        Write-Yellow "  Retrying with --no-cache-dir..."
        try {
            & $PipPath install --no-cache-dir -e $EditableInstallTarget 2>&1 | ForEach-Object {
                if ($_ -match '(Downloading|Installing|Collecting|Building|Successfully)') {
                    Write-Dim "    $_"
                }
            }
            if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
                $pipOk = $true
                Add-Remediation "pip_no_cache_retry"
            }
        } catch {}
    }

    # Attempt 3: proxy/SSL issues
    if (-not $pipOk) {
        if ($env:HTTP_PROXY -or $env:HTTPS_PROXY -or $env:http_proxy -or $env:https_proxy) {
            Add-EdgeCase "corporate_proxy"
        }
        Write-Yellow "  Retrying with trusted hosts..."
        try {
            & $PipPath install --no-cache-dir `
                --trusted-host pypi.org `
                --trusted-host pypi.python.org `
                --trusted-host files.pythonhosted.org `
                -e $EditableInstallTarget 2>&1 | ForEach-Object {
                if ($_ -match '(Downloading|Installing|Collecting|Building|Successfully)') {
                    Write-Dim "    $_"
                }
            }
            if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
                $pipOk = $true
                Add-Remediation "pip_trusted_host_retry"
            }
        } catch {}
    }

    if ($pipOk) {
        $StepResults["pip"] = "ok"
        Write-Green "  Package installed (including dashboard dependencies)"
    } else {
        $StepResults["pip"] = "fail"
        Write-Red "  Package installation failed after 3 attempts"
        Send-InstallerTelemetry -Status "failure" -StepFailed "pip_install" `
            -ErrorMsg "All pip install attempts failed"
        if (-not $NonInteractive) {
            Write-Bold "  Press Enter to close this window."
            Read-Host
        }
        exit 1
    }
} else {
    $StepResults["pip"] = "fail"
    Write-Red "  pip not found and ensurepip failed"
    Send-InstallerTelemetry -Status "failure" -StepFailed "pip_missing" `
        -ErrorMsg "pip.exe not found at $PipPath after ensurepip"
    if (-not $NonInteractive) {
        Write-Bold "  Press Enter to close this window."
        Read-Host
    }
    exit 1
}

# ── Step 4/6: Register with Claude Code ──────────────────────────────

Write-Host ""
Write-Step 4 "Registering with Claude Code..."

$HasClaudeCode = $false
$HasClaudeDesktop = $false
$InstalledSomewhere = $false

# Check for Claude Code CLI
$ClaudePath = $null

# Method 1: PATH lookup
$found = Get-Command claude -ErrorAction SilentlyContinue
if ($found) { $ClaudePath = $found.Source }

# Method 2: Official Windows install location
if (-not $ClaudePath) {
    $nativePath = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
    if (Test-Path $nativePath) { $ClaudePath = $nativePath }
}

# Method 3: npm global install
if (-not $ClaudePath) {
    $npmPath = Join-Path $env:APPDATA "npm\claude.cmd"
    if (Test-Path $npmPath) { $ClaudePath = $npmPath }
}

$ClaudeHome = Join-Path $env:USERPROFILE ".claude"
$HasClaudeHome = Test-Path $ClaudeHome

if ($ClaudePath) {
    $HasClaudeCode = $true
    $ClaudeCodePresent = $true
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

# Check for Claude Desktop
$ClaudeDesktopDir = Join-Path $env:APPDATA "Claude"
if (Test-Path $ClaudeDesktopDir) {
    $HasClaudeDesktop = $true
    $ClaudeDesktopPresent = $true
    Write-Green "  Claude Desktop found"
} else {
    $ClaudeLocalDir = Join-Path $env:LOCALAPPDATA "Claude"
    if (Test-Path $ClaudeLocalDir) {
        $HasClaudeDesktop = $true
        $ClaudeDesktopPresent = $true
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
    $StepResults["register"] = "skipped"
    $StepResults["desktop"] = "skipped"
    # Not fatal -- user can install Claude later
    $InstalledSomewhere = $false
} else {
    # Register plugin via ~/.claude/ plugin cache
    if ($HasClaudeCode -or $HasClaudeDesktop -or $HasClaudeHome) {
        Write-Blue "  Registering plugin in Claude plugin system..."
        $PluginVersion = (Get-Content (Join-Path $InstallDir "pyproject.toml") | Select-String 'version = "([^"]+)"').Matches.Groups[1].Value
        if (-not $PluginVersion) { $PluginVersion = $InstallerVersionConst }
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
            $StepResults["register"] = "ok"

        } catch {
            Write-Yellow "  Could not register plugin automatically: $_"
            $StepResults["register"] = "fail"
            $FailedStep = "plugin_registration"
            Send-InstallerTelemetry -Status "failure" -StepFailed "plugin_registration" -ErrorMsg "$_"
            Write-Host ""
            Write-Host "  Manual install:"
            Write-Dim  "    claude plugin add `"$InstallDir`""
            $InstalledSomewhere = $true
        }
        Write-Host ""
    }
}

# ── Step 5/6: Configure Claude Desktop ───────────────────────────────

Write-Step 5 "Configuring Claude Desktop..."

if ($HasClaudeDesktop) {
    $DesktopConfigPath = Join-Path $ClaudeDesktopDir "claude_desktop_config.json"
    Write-Dim  "  Config: $DesktopConfigPath"

    # Check write permission
    try {
        $testPath = Join-Path $ClaudeDesktopDir ".write_test"
        [System.IO.File]::WriteAllText($testPath, "test")
        Remove-Item $testPath -ErrorAction SilentlyContinue
    } catch {
        Add-EdgeCase "config_dir_no_write"
        Write-Yellow "  Cannot write to Claude Desktop config directory"

        # Try alternate location
        $altDir = Join-Path $env:LOCALAPPDATA "Claude"
        if ($altDir -ne $ClaudeDesktopDir -and (Test-Path $altDir)) {
            $ClaudeDesktopDir = $altDir
            $DesktopConfigPath = Join-Path $altDir "claude_desktop_config.json"
            Add-Remediation "alt_config_location"
            Write-Dim "  Trying alternate: $DesktopConfigPath"
        }
    }

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
            # Resolve to absolute path -- MCP config needs a full path
            $resolved = Get-Command $PythonCmd -ErrorAction SilentlyContinue
            if ($resolved) {
                $pythonExe = $resolved.Source
            } else {
                $pythonExe = $PythonCmd
            }
        }

        $tempScript = Join-Path $env:TEMP "obsidian_connector_setup_desktop.py"
        @"
import json, shutil, os, sys, platform
from datetime import datetime

config_path = sys.argv[1]
python_exe = sys.argv[2]
install_dir = sys.argv[3]

# Backup
if os.path.exists(config_path):
    backup = config_path + '.backup-' + datetime.now().strftime('%Y%m%d-%H%M%S')
    shutil.copy2(config_path, backup)

# Read or create config. utf-8-sig tolerates the BOM that PowerShell's
# Set-Content -Encoding UTF8 prepends on older Windows builds.
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8-sig') as f:
        config = json.load(f)
else:
    config = {}

if 'mcpServers' not in config:
    config['mcpServers'] = {}

# Windows: use cmd /c wrapper for reliable stdio MCP communication
# This prevents issues with non-absolute paths and .cmd wrappers
if platform.system() == 'Windows':
    config['mcpServers']['obsidian-connector'] = {
        'command': 'cmd',
        'args': ['/c', python_exe, '-m', 'obsidian_connector.mcp_server'],
        'env': {'PYTHONPATH': install_dir}
    }
else:
    config['mcpServers']['obsidian-connector'] = {
        'command': python_exe,
        'args': ['-m', 'obsidian_connector.mcp_server'],
        'env': {'PYTHONPATH': install_dir}
    }

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2)

print('OK')
"@ | Set-Content $tempScript -Encoding UTF8

        $result = & $PythonCmd $tempScript $DesktopConfigPath $pythonExe $InstallDir 2>&1
        Remove-Item $tempScript -ErrorAction SilentlyContinue

        if ($result -match "OK") {
            Write-Green "  MCP server registered in Claude Desktop config"
            Write-Dim  "  Restart Claude Desktop to load 100+ MCP tools."
            $InstalledSomewhere = $true
            $StepResults["desktop"] = "ok"
        } else {
            Write-Yellow "  Config update returned: $result"
            $StepResults["desktop"] = "warn"
            $InstalledSomewhere = $true
        }

        # MCP config path validation
        Write-Host ""
        Write-Blue "  Verifying MCP config..."

        $verifyScript = Join-Path $env:TEMP "obsidian_connector_verify_mcp.py"
        @"
import json, sys, os

config_path = sys.argv[1]

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception as e:
    print(f'ERROR: Could not read config: {e}')
    sys.exit(2)

entry = data.get('mcpServers', {}).get('obsidian-connector', {})
if not entry:
    print('ERROR: mcpServers.obsidian-connector entry not found in config')
    sys.exit(2)

cmd = entry.get('command', '')
args = entry.get('args', [])
env = entry.get('env', {})

print(f'command={cmd}')
print(f'args={json.dumps(args)}')
print(f'env={json.dumps(env)}')

if not cmd:
    print('WARNING: command field is empty')
    sys.exit(1)

if os.path.exists(cmd):
    print('command_exists=true')
    print('MCP config verification: OK')
    sys.exit(0)
else:
    print('command_exists=false')
    print(f'WARNING: command path does not exist: {cmd}')
    sys.exit(1)
"@ | Set-Content $verifyScript -Encoding UTF8

        $verifyOutput = & $PythonCmd $verifyScript $DesktopConfigPath 2>&1
        $verifyExit = $LASTEXITCODE
        Remove-Item $verifyScript -ErrorAction SilentlyContinue

        foreach ($line in ($verifyOutput -split "`n")) {
            $trimmed = $line.Trim()
            if ($trimmed -match '^command=(.+)$') {
                Write-Dim  "    Command path: $($Matches[1])"
            } elseif ($trimmed -match '^command_exists=(.+)$') {
                if ($Matches[1] -eq 'true') {
                    Write-Green "    Command exists: YES"
                } else {
                    Write-Red   "    Command exists: NO"
                }
            } elseif ($trimmed -match '^args=(.+)$') {
                Write-Dim  "    Args: $($Matches[1])"
            } elseif ($trimmed -match '^env=(.+)$') {
                Write-Dim  "    Env: $($Matches[1])"
            } elseif ($trimmed -match '^(WARNING|ERROR):') {
                Write-Yellow "    $trimmed"
            } elseif ($trimmed -eq 'MCP config verification: OK') {
                Write-Green "    $trimmed"
            }
        }

        if ($verifyExit -eq 1) {
            Add-EdgeCase "mcp_command_missing"
            Write-Host ""
            Write-Yellow "  The MCP command path does not exist on disk."
            Write-Yellow "  Claude Desktop will not be able to start the MCP server."
            Write-Host ""
            Write-Host "  Possible causes:"
            Write-Dim  "    - Python venv was not created successfully"
            Write-Dim  "    - Path contains spaces or special characters"
            Write-Dim  "    - Antivirus quarantined the python.exe"
            Write-Host ""
            Write-Host "  Try recreating the venv:"
            Write-Dim  "    $PythonCmd -m venv `"$VenvDir`""
        } elseif ($verifyExit -ge 2) {
            Write-Yellow "  Could not verify MCP config (exit code $verifyExit)"
        }

    } catch {
        Write-Yellow "  Could not update Claude Desktop config: $_"
        $StepResults["desktop"] = "fail"
        Send-InstallerTelemetry -Status "failure" -StepFailed "desktop_mcp_config" -ErrorMsg "$_"
        Write-Dim  "  Manual: add obsidian-connector to claude_desktop_config.json"
    }
} else {
    $StepResults["desktop"] = "skipped"
    Write-Dim "  Claude Desktop not detected -- skipping MCP config"
}

Write-Host ""

# ── Step 6/6: Verify installation ────────────────────────────────────

Write-Step 6 "Verifying installation..."

$verifyFails = 0

# Check 1: venv python exists
$venvPy = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $venvPy) {
    Write-Green "  Venv python: OK"
} else {
    Write-Red "  Venv python missing: $venvPy"
    $verifyFails++
}

# Check 2: obsidian_connector package importable
if (Test-Path $venvPy) {
    try {
        $importCheck = & $venvPy -c "import obsidian_connector; print('OK')" 2>&1
        if ("$importCheck" -match "OK") {
            Write-Green "  Package import: OK"
        } else {
            Write-Red "  Package import failed: $importCheck"
            $verifyFails++
        }
    } catch {
        Write-Red "  Package import check failed: $_"
        $verifyFails++
    }

    # Check 2b: MCP server can initialize (quick smoke test)
    try {
        $mcpCheck = & $venvPy -c "from obsidian_connector.mcp_server import mcp; print('MCP_OK')" 2>&1
        if ("$mcpCheck" -match "MCP_OK") {
            Write-Green "  MCP server import: OK"
        } else {
            Write-Yellow "  MCP server import issue: $mcpCheck"
        }
    } catch {
        Write-Yellow "  MCP server import check skipped: $_"
    }
}

# Check 3: Plugin cache and .claude-plugin/plugin.json
if ($InstalledSomewhere) {
    $cacheDir = Join-Path (Join-Path $env:USERPROFILE ".claude") "plugins\cache\local\obsidian-connector"
    if (Test-Path $cacheDir) {
        Write-Green "  Plugin cache: OK"
        # Verify .claude-plugin/plugin.json exists in cache (required for Desktop Code tab)
        $cacheVersionDirs = Get-ChildItem $cacheDir -Directory -ErrorAction SilentlyContinue
        foreach ($vdir in $cacheVersionDirs) {
            $cpj = Join-Path $vdir.FullName ".claude-plugin\plugin.json"
            if (Test-Path $cpj) {
                Write-Green "  .claude-plugin/plugin.json in cache: OK"
            } else {
                Write-Yellow "  .claude-plugin/plugin.json missing in cache -- skills won't load in Desktop Code tab"
                $verifyFails++
            }
        }
    } else {
        Write-Yellow "  Plugin cache not found (non-fatal)"
    }

    # Check 4: settings.json has plugin enabled
    $settingsCheck = Join-Path (Join-Path $env:USERPROFILE ".claude") "settings.json"
    if (Test-Path $settingsCheck) {
        $sContent = Get-Content $settingsCheck -Raw
        if ($sContent -match "obsidian-connector") {
            Write-Green "  settings.json: plugin enabled"
        } else {
            Write-Red "  settings.json: plugin not in enabledPlugins"
            $verifyFails++
        }
    }
}

if ($verifyFails -gt 0) {
    $StepResults["verify"] = "warn"
    Write-Yellow "  $verifyFails verification check(s) failed"
} else {
    $StepResults["verify"] = "ok"
    Write-Green "  All verification checks passed"
}

Write-Host ""

# ── Success telemetry ────────────────────────────────────────────────

$FinalStatus = "success"
Send-InstallerTelemetry -Status "success"

# ── Summary ──────────────────────────────────────────────────────────

$elapsed = [int]((Get-Date) - $InstallStart).TotalSeconds

Write-Green "  Installation complete!"
Write-Host ""
if ($HasClaudeCode) {
    Write-Host "  Claude Code: Try /capture, /ritual, /sync in any conversation"
}
if ($HasClaudeDesktop) {
    Write-Host "  Claude Desktop: Restart Desktop to load 100+ MCP tools"
}

Write-Host ""
$skillCount = (Get-ChildItem (Join-Path $InstallDir "skills") -Directory -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Dim "  Installed to: $InstallDir"
Write-Dim "  Skills: $skillCount | MCP tools: 62 | CLI: obsx"

if ($EdgeCases.Count -gt 0) {
    Write-Dim "  Edge cases detected: $($EdgeCases -join ', ')"
}
if ($Remediations.Count -gt 0) {
    Write-Dim "  Auto-fixes applied: $($Remediations -join ', ')"
}
Write-Dim "  Completed in ${elapsed}s"

if ($NonInteractive) {
    Write-Dim "  Log saved to: $LogFile"
}

Write-Host ""
if (-not $NonInteractive) {
    Write-Bold "  Press Enter to close this window."
    Read-Host
}

if ($NonInteractive) {
    try { Stop-Transcript -ErrorAction SilentlyContinue } catch {}
}
