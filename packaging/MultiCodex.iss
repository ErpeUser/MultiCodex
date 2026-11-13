#define AppName "MultiCodex"
#ifndef AppVersion
  #define AppVersion "0.2.0-dev"
#endif
[Setup]
AppId={{CCB8A29E-9E8D-4856-976E-0C873B4C98A2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=MultiCodex contributors
LicenseFile=..\LICENSE
DefaultDirName={localappdata}\Programs\MultiCodex
DefaultGroupName=MultiCodex
UninstallDisplayIcon={app}\MultiCodex.exe
OutputDir=..\output
OutputBaseFilename=Codex-Multi-Studio-Setup-v{#AppVersion}
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\MultiCodex\*"; DestDir: "{app}"; Flags: ignoreversion recurseSubdirs createallsubdirs

[Icons]
Name: "{group}\MultiCodex"; Filename: "{app}\MultiCodex.exe"
Name: "{userdesktop}\MultiCodex"; Filename: "{app}\MultiCodex.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MultiCodex.exe"; Description: "Start MultiCodex"; Flags: nowait postinstall skipifsilent
