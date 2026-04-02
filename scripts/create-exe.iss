; ──────────────────────────────────────────────────────────────────────
; Obsidian Connector -- Inno Setup installer script
;
; Builds a Windows .exe installer that:
;   1. Copies plugin files to %APPDATA%\obsidian-connector
;   2. Creates a Python venv and installs the package
;   3. Registers with Claude Code / Claude Desktop
;   4. Generates an uninstaller
;
; Build (from GitHub Actions or local with Inno Setup 6+):
;   iscc /DSourceDir="C:\path\to\repo" /DAppVersion="0.6.1" scripts\create-exe.iss
;
; Preprocessor variables (passed via /D flags):
;   SourceDir  -- absolute path to the repo checkout
;   AppVersion -- version string (e.g. "0.6.1")
; ──────────────────────────────────────────────────────────────────────

#ifndef SourceDir
  #error "SourceDir must be defined via /DSourceDir=..."
#endif

#ifndef AppVersion
  #define AppVersion "0.6.1"
#endif

[Setup]
AppName=Obsidian Connector
AppVersion={#AppVersion}
AppVerName=Obsidian Connector v{#AppVersion}
AppPublisher=Mario Urquia
AppPublisherURL=https://github.com/mariourquia/obsidian-connector
AppSupportURL=https://github.com/mariourquia/obsidian-connector/issues
DefaultDirName={%USERPROFILE}\obsidian-connector
DefaultGroupName=Obsidian Connector
OutputBaseFilename=obsidian-connector-v{#AppVersion}-setup
OutputDir={#SourceDir}\dist
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
LicenseFile={#SourceDir}\LICENSE
DisableProgramGroupPage=yes
DisableDirPage=no
UninstallDisplayName=Obsidian Connector v{#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Obsidian Connector for Claude
WelcomeLabel2=This will install Obsidian Connector v{#AppVersion} on your computer.%n%n62 MCP tools, 65 CLI commands, 17 skills. Morning briefings, idea capture, evening reflections, weekly reviews -- all driven by your Obsidian vault.%n%nRequires Python 3.11+ and Obsidian desktop.%n%nMIT License

; ──────────────────────────────────────────────────────────────────────
; Files -- explicit whitelist
;
; Root-level skills/, hooks/, .claude-plugin/, .mcp.json are symlinks
; pointing into src/. On Windows CI, symlinks may not resolve. We
; reference src/ paths directly as the canonical source of truth,
; with root-level fallbacks for local dev builds where symlinks work.
; ──────────────────────────────────────────────────────────────────────

[Files]
; Python package (always at root)
Source: "{#SourceDir}\obsidian_connector\*"; DestDir: "{app}\obsidian_connector"; Flags: ignoreversion recursesubdirs createallsubdirs
; CLI wrappers (always at root)
Source: "{#SourceDir}\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs createallsubdirs

; Skills (canonical: src/skills/, fallback: skills/ symlink)
Source: "{#SourceDir}\src\skills\*"; DestDir: "{app}\skills"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
; Portable skills
Source: "{#SourceDir}\portable\*"; DestDir: "{app}\portable"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
; Hooks (canonical: src/hooks/)
Source: "{#SourceDir}\src\hooks\*"; DestDir: "{app}\hooks"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
; Plugin manifest (canonical: src/plugin/)
Source: "{#SourceDir}\src\plugin\plugin.json"; DestDir: "{app}\.claude-plugin"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\src\plugin\marketplace.json"; DestDir: "{app}\.claude-plugin"; Flags: ignoreversion skipifsourcedoesntexist
; MCP config (canonical: src/plugin/.mcp.json)
Source: "{#SourceDir}\src\plugin\.mcp.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
; Scheduling
Source: "{#SourceDir}\scheduling\*"; DestDir: "{app}\scheduling"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
; Templates
Source: "{#SourceDir}\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
; Install scripts
Source: "{#SourceDir}\scripts\Install.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#SourceDir}\scripts\install.sh"; DestDir: "{app}\scripts"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\scripts\setup.sh"; DestDir: "{app}\scripts"; Flags: ignoreversion skipifsourcedoesntexist
; Package metadata
Source: "{#SourceDir}\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\main.py"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\config.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
; Root docs
Source: "{#SourceDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\SECURITY.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SourceDir}\CONTRIBUTING.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; ──────────────────────────────────────────────────────────────────────
; Post-install: create venv and install package
; ──────────────────────────────────────────────────────────────────────

[Run]
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\scripts\Install.ps1"" -InstallDir ""{app}"" -NonInteractive"; \
    Description: "Configure Obsidian Connector (venv + Claude registration)"; \
    StatusMsg: "Setting up Python environment and registering with Claude..."; \
    Flags: postinstall runhidden waituntilterminated

; ──────────────────────────────────────────────────────────────────────
; Uninstall
; ──────────────────────────────────────────────────────────────────────

[UninstallRun]
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -Command ""try {{ & claude plugin remove obsidian-connector 2>$null }} catch {{ }}"""; \
    Flags: runhidden waituntilterminated; \
    RunOnceId: "UnregisterPlugin"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
