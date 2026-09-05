; installer.iss - buduje Setup.exe (Inno Setup) z folderu dist/local_converter,
; ktory musi byc juz zbudowany przez build_release.py. W odroznieniu od
; przenosnej paczki ZIP, to prawdziwy instalator: wpisuje sie do "Aplikacje
; i funkcje" z odinstalowywaniem, dodaje wpis w Menu Start i opcjonalnie skrot
; na Pulpicie (bez potrzeby klikania osobnego .bat jak w wersji ZIP).
;
; Wymaga Inno Setup 6 (ISCC.exe) - winget install JRSoftware.InnoSetup.
; Kompilacja:
;   ISCC.exe assets\installer.iss
; Wynik:
;   dist_installer\local_converter-setup.exe

#define MyAppName "local_converter"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Sakor0"
#define MyAppURL "https://github.com/Sakor0/converter"
#define MyAppExeName "local_converter.exe"

[Setup]
AppId={{B4B4D9C1-3E1A-4F2E-9C7A-6C6E9E9C6A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=local_converter-setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Cala zawartosc dist/local_converter (exe, ffmpeg/ffprobe, biblioteki) OPROCZ
; "Utworz skrot na Pulpicie.bat" - ten .bat jest potrzebny tylko w przenosnej
; paczce ZIP (bez instalatora); tu skrot na Pulpicie robi [Tasks]+[Icons] niżej.
Source: "..\dist\local_converter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "Utworz skrot na Pulpicie.bat"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
