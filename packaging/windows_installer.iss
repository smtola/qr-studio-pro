; Inno Setup 6 script. Compile with:  iscc /DAppVersion=1.0.0 packaging\windows_installer.iss
; (scripts\build_windows.ps1 does this for you.) Installs per-user by default, no administrator rights needed.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "QR Studio Pro"
#define AppExe "QRStudioPro.exe"

[Setup]
AppId={{6F3C2E1A-5B7D-4C9E-8A11-3D2B9F0E7A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=QR Studio
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\icons\app.ico
OutputDir=..\dist
OutputBaseFilename=QRStudioPro-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
VersionInfoVersion={#AppVersion}
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\QRStudioPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.qrsp"; ValueType: string; ValueData: "QRStudioPro.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\QRStudioPro.Project"; ValueType: string; ValueData: "QR Studio project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\QRStudioPro.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\QRStudioPro.Project\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
; In-app updates run this installer silently over the existing install (same AppId = upgrade, no uninstall); restart the app afterwards.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

; User data (settings, presets, logs) lives in %APPDATA%\QRStudioPro and is intentionally kept on uninstall.
