# -----------------------------------------------------------------------
# Build a Windows installer (.exe) for obsidian-connector using Inno Setup
#
# Stages project files, generates an Inno Setup script, and compiles
# it into a setup executable.
#
# Usage:
#   .\scripts\build-windows-installer.ps1                # auto-detect version
#   .\scripts\build-windows-installer.ps1 -Version v0.3.0
#
# Requirements:
#   - Inno Setup 6+ (iscc.exe on PATH or default install location)
# -----------------------------------------------------------------------

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

# -- Locate repo root and tools -------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

# Auto-detect version from pyproject.toml if not provided
if (-not $Version) {
    $toml = Get-Content (Join-Path $RepoRoot "pyproject.toml") -Raw
    if ($toml -match 'version\s*=\s*"([^"]+)"') {
        $Version = $Matches[1]
    } else {
        $Version = "0.0.0"
    }
}
# Strip leading 'v' if present (tags use v0.3.0, Inno Setup wants 0.3.0)
$CleanVersion = $Version -replace '^v', ''

Write-Host "Building Windows installer for obsidian-connector $CleanVersion"

# Find Inno Setup compiler
$ISCC = $null
$Candidates = @(
    "iscc.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
foreach ($candidate in $Candidates) {
    if (Test-Path $candidate -ErrorAction SilentlyContinue) {
        $ISCC = $candidate
        break
    }
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) {
        $ISCC = $found.Source
        break
    }
}
if (-not $ISCC) {
    Write-Error "Inno Setup compiler (iscc.exe) not found. Install from https://jrsoftware.org/isdown.php"
    exit 1
}
Write-Host "Using Inno Setup: $ISCC"

function Invoke-Robocopy {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $robocopyArgs = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    foreach ($dir in $ExcludeDirs) {
        $robocopyArgs += @("/XD", $dir)
    }
    foreach ($file in $ExcludeFiles) {
        $robocopyArgs += @("/XF", $file)
    }

    $output = & robocopy @robocopyArgs 2>&1
    if ($LASTEXITCODE -gt 7) {
        if ($output) {
            $output | ForEach-Object { Write-Host $_ }
        }
        Write-Error "robocopy failed with exit code $LASTEXITCODE"
        exit 1
    }
}

# -- Stage files -----------------------------------------------------------
# Prefer validated build artifacts from builds\claude-desktop\ when the
# build pipeline has been run. Fall back to the raw source tree for dev
# builds where someone hasn't run the build pipeline.

$DistDir = Join-Path $RepoRoot "dist"
$StagingDir = Join-Path $DistDir ".win-staging"
$BuildDir = Join-Path $RepoRoot "builds\claude-desktop"
$LicenseFile = Join-Path $RepoRoot "LICENSE"
$IxExcludeDirs = @(
    'ix_engine\core-ingestion\src',
    'ix_engine\core-ingestion\test-fixtures',
    'ix_engine\core-ingestion\node_modules\.bin',
    'ix_engine\ix-cli\src',
    'ix_engine\ix-cli\scripts',
    'ix_engine\ix-cli\test',
    'ix_engine\ix-cli\node_modules\.bin',
    'ix_engine\ix-cli\dist\cli\__tests__'
)
$IxExcludeFiles = @(
    'package-lock*.json',
    'tsconfig*.json'
)

$FilesSectionEntries = New-Object System.Collections.Generic.List[string]

if (Test-Path $BuildDir) {
    Write-Host "Using built artifacts directly from builds\claude-desktop\"

    # Point Inno Setup at the built tree directly. Copying the entire build into
    # a temporary staging directory was the dominant runtime cost in CI.
    $BuildObsidianExcludes = @(
        '__pycache__\*',
        '*.pyc',
        '.DS_Store'
    ) + ($IxExcludeDirs | ForEach-Object { "$_\*" }) + $IxExcludeFiles
    $ScriptExcludes = @(
        '__pycache__\*',
        '*.pyc',
        '.DS_Store'
    )

    $FilesSectionEntries.Add(
        'Source: "' + (Join-Path $BuildDir 'obsidian_connector\*') +
        '"; DestDir: "{app}\obsidian_connector"; Excludes: "' +
        ($BuildObsidianExcludes -join ',') +
        '"; Flags: ignoreversion recursesubdirs createallsubdirs'
    )

    if (Test-Path (Join-Path $BuildDir "bin")) {
        $FilesSectionEntries.Add(
            'Source: "' + (Join-Path $BuildDir 'bin\*') +
            '"; DestDir: "{app}\bin"; Excludes: "' +
            ($ScriptExcludes -join ',') +
            '"; Flags: ignoreversion recursesubdirs createallsubdirs'
        )
    }

    foreach ($supportFile in @("claude_desktop_config_snippet.json", "pyproject.toml", "requirements-lock.txt", "INSTALL.txt")) {
        $src = Join-Path $BuildDir $supportFile
        if (Test-Path $src) {
            $FilesSectionEntries.Add(
                'Source: "' + $src + '"; DestDir: "{app}"; Flags: ignoreversion'
            )
        }
    }

    if (Test-Path (Join-Path $RepoRoot "scripts")) {
        $FilesSectionEntries.Add(
            'Source: "' + (Join-Path $RepoRoot 'scripts\*') +
            '"; DestDir: "{app}\scripts"; Excludes: "' +
            ($ScriptExcludes -join ',') +
            '"; Flags: ignoreversion recursesubdirs createallsubdirs'
        )
    }
} else {
    if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

    Write-Host "Staging project files..."
    Write-Host "No builds\claude-desktop\ found, falling back to source tree"

    # Directories and patterns to exclude (mirrors create-dmg.sh)
    $ExcludeDirs = @(
        '.venv', '.git', '.claude', '.claude-plugin', 'dist',
        '__pycache__', '*.egg-info', 'vault-context-drafts',
        'templates', 'tools', 'dev', 'hooks', '.github'
    ) + ($IxExcludeDirs | ForEach-Object { Join-Path 'obsidian_connector' $_ })
    $ExcludeFiles = @(
        '*.pyc', '.DS_Store', 'firebase-debug.log',
        'AGENTS.md', 'Makefile', 'main.py', 'Install.command'
    ) + $IxExcludeFiles

    Invoke-Robocopy -Source $RepoRoot -Destination $StagingDir -ExcludeDirs $ExcludeDirs -ExcludeFiles $ExcludeFiles
    Write-Host "Staged to: $StagingDir"

    $FilesSectionEntries.Add(
        'Source: "' + (Join-Path $StagingDir '*') +
        '"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs'
    )
}

if (-not (Test-Path $LicenseFile)) {
    Write-Error "Required license file missing: $LicenseFile"
    exit 1
}
$FilesSectionEntries.Add(
    'Source: "' + $LicenseFile + '"; DestDir: "{app}"; Flags: ignoreversion'
)
$FilesSection = $FilesSectionEntries -join "`r`n"

# -- Generate Inno Setup script -------------------------------------------

$IssFile = Join-Path $DistDir "obsidian-connector.iss"
$OutputExe = "obsidian-connector-${CleanVersion}-setup"

Write-Host "Generating Inno Setup script..."

$IssContent = @"
; obsidian-connector Windows installer
; Auto-generated by build-windows-installer.ps1

[Setup]
AppId={{B7E3F2A1-8C4D-4F5E-9A6B-1D2E3F4A5B6C}
AppName=obsidian-connector
AppVersion=$CleanVersion
AppVerName=obsidian-connector $CleanVersion
AppPublisher=Mario Urquia
AppPublisherURL=https://github.com/mariourquia/obsidian-connector
AppSupportURL=https://github.com/mariourquia/obsidian-connector/issues
DefaultDirName={userappdata}\obsidian-connector
DefaultGroupName=obsidian-connector
DisableProgramGroupPage=yes
LicenseFile=$LicenseFile
OutputDir=$DistDir
OutputBaseFilename=$OutputExe
; Favor build throughput over maximum compression so CI can finish in a
; predictable window when bundling the embedded Ix runtime.
Compression=zip
SolidCompression=no
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install obsidian-connector $CleanVersion on your computer.%n%nobsidian-connector connects Claude to your Obsidian vault -- morning briefings, idea capture, evening reflections, and 35 MCP tools.%n%nRequirements: Python 3.11+, Obsidian, Claude Desktop.

[Components]
Name: "core"; Description: "Core installation (MCP server + CLI)"; Types: full compact custom; Flags: fixed
Name: "claude_config"; Description: "Auto-configure Claude Desktop"; Types: full compact custom; Flags: fixed
Name: "skills"; Description: "Install Claude Code skills (/morning, /evening, etc.)"; Types: full
Name: "schedule"; Description: "Daily scheduled briefing (8:00 AM)"; Types: full

[Files]
$FilesSection

[Run]
; Create venv, install package, configure Claude Desktop
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\Install.ps1"" -NonInteractive"; \
    StatusMsg: "Setting up Python environment and configuring Claude Desktop..."; \
    Flags: runhidden waituntilterminated

; Install skills if selected
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\Install.ps1"" -NonInteractive -InstallSkills"; \
    StatusMsg: "Installing Claude Code skills..."; \
    Components: skills; \
    Flags: runhidden waituntilterminated

; Install scheduled task if selected
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\Install.ps1"" -NonInteractive -InstallSchedule"; \
    StatusMsg: "Setting up daily scheduled briefing..."; \
    Components: schedule; \
    Flags: runhidden waituntilterminated

[UninstallRun]
; Remove scheduled task on uninstall
Filename: "schtasks.exe"; \
    Parameters: "/DELETE /TN obsidian-connector-morning /F"; \
    Flags: runhidden; RunOnceId: "RemoveScheduledTask"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
"@

$IssContent | Out-File -FilePath $IssFile -Encoding UTF8

Write-Host "Generated: $IssFile"

# -- Compile installer -----------------------------------------------------

Write-Host "Compiling installer..."
& $ISCC $IssFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup compilation failed"
    exit 1
}

$ExePath = Join-Path $DistDir "$OutputExe.exe"
if (Test-Path $ExePath) {
    $Size = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
    Write-Host ""
    Write-Host "Created: $ExePath"
    Write-Host "Size: ${Size} MB"
} else {
    Write-Error "Expected output not found: $ExePath"
    exit 1
}

# -- Cleanup ---------------------------------------------------------------

if (Test-Path $StagingDir) {
    Remove-Item -Recurse -Force $StagingDir
}
Remove-Item -Force $IssFile

Write-Host ""
Write-Host "Windows installer build complete."
