; installer_windows.iss
; ---------------------
; Inno Setup 6 script.
; Build with: iscc installer_windows.iss
; Produces:   installer_output\PiSdBackup_Setup.exe
;
; Prerequisites:
;   1. Run PyInstaller first:  pyinstaller pi_sd_backup.spec
;   2. Install Inno Setup 6:   https://jrsoftware.org/isdl.php

#define AppName      "Pi SD Backup"
#define AppVersion   "1.0.0"
#define AppPublisher "PiBackupTool"
#define AppURL       "https://github.com/your-username/pi-sd-backup"
#define AppExeName   "PiSdBackup.exe"
#define BuildDir     "dist\pi_sd_backup"

[Setup]
AppId={{A3F2C1B0-9D4E-4F7A-8C2D-1E5B6F3A0D9C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Require elevated privileges so the app can be installed system-wide
PrivilegesRequired=admin
OutputDir=installer_output
OutputBaseFilename=PiSdBackup_Setup
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Minimum Windows 10
MinVersion=10.0
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Launch {#AppName} on Windows startup"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Include the entire PyInstaller output folder
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Optional startup entry
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove settings file left behind by the app
Type: files; Name: "{userappdata}\{#AppPublisher}\settings.ini"
