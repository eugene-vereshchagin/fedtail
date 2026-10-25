; fedtail's Windows installer (Inno Setup 6): the one-file build (dist\fedtail.exe) put in
; the user's own programs folder — no administrator, nothing for other users — with a
; Start menu entry, a desktop one if asked, and an uninstaller. The profile (config,
; posts, logs in %APPDATA%\fedtail) stays when it's uninstalled: it's the user's.
; Built by CI (ci.yml, windows-build):  iscc /DVersion=X.Y.Z /DHomepage=URL fedtail.iss

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Homepage
  #define Homepage ""
#endif

[Setup]
; one id for every version: a new one installs over the old
AppId={{6F3B2C1A-9E4D-4B7A-8C21-5A0D9F7E3B64}
AppName=fedtail
AppVersion={#Version}
AppVerName=fedtail {#Version}
AppPublisher=fedtail
AppPublisherURL={#Homepage}
AppSupportURL={#Homepage}
DefaultDirName={autopf}\fedtail
DefaultGroupName=fedtail
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=fedtail-setup
SetupIconFile=..\..\build\fedtail.ico
UninstallDisplayIcon={app}\fedtail.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\fedtail.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; where `fedtail --install-desktop` puts its own (desktop.py): the same one, not a second
Name: "{autoprograms}\fedtail"; Filename: "{app}\fedtail.exe"; Comment: "fediverse client"
Name: "{autodesktop}\fedtail"; Filename: "{app}\fedtail.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\fedtail.exe"; Description: "{cm:LaunchProgram,fedtail}"; Flags: nowait postinstall skipifsilent
