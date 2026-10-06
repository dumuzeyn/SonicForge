#define MyAppName "SonicForge"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Dumuzeyn"
#define MyAppExeName "SonicForge.exe"
#define MyAppUserModelID "Dumuzeyn.SonicForge"
#ifndef SourceRoot
#define SourceRoot "..\dist\SonicForge"
#endif

[Setup]
AppId={{1B9EA71F-7D06-4F35-88B7-F71B12642E50}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/dumuzeyn/SonicForge
AppSupportURL=https://github.com/dumuzeyn/SonicForge/issues
DefaultDirName={localappdata}\Programs\Sonic Forge
DefaultGroupName=Sonic Forge
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=..\dist
OutputBaseFilename=SonicForge-Setup-{#MyAppVersion}
SetupIconFile=..\assets\sonic_forge_mark.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
VersionInfoVersion=2.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=SonicForge installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sonic Forge"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\sonic_forge_mark.ico"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{autodesktop}\Sonic Forge"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\sonic_forge_mark.ico"; Tasks: desktopicon; AppUserModelID: "{#MyAppUserModelID}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\SonicForge.exe"; ValueType: string; ValueName: ""; ValueData: "{app}\SonicForge.exe"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\SonicForge.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Sonic Forge"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\SonicForge.exe\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\_internal\assets\sonic_forge_mark.ico"
Root: HKCU; Subkey: "Software\Classes\Applications\SonicForge.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\SonicForge.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\SonicForge.Audio"; ValueType: string; ValueName: ""; ValueData: "Sonic Forge Audio"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SonicForge.Audio\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\_internal\assets\sonic_forge_mark.ico"
Root: HKCU; Subkey: "Software\Classes\SonicForge.Audio\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\SonicForge.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\SonicForge.Audio\Application"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Sonic Forge"
Root: HKCU; Subkey: "Software\Classes\SonicForge.Audio\Application"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\_internal\assets\sonic_forge_mark.ico"
Root: HKCU; Subkey: "Software\Dumuzeyn\SonicForge\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Sonic Forge"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Dumuzeyn\SonicForge\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Audio editor and music file tools"
Root: HKCU; Subkey: "Software\Dumuzeyn\SonicForge\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\_internal\assets\sonic_forge_mark.ico"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Sonic Forge"; ValueData: "Software\Dumuzeyn\SonicForge\Capabilities"; Flags: uninsdeletevalue
#dim AudioExts[8] {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
#define ExtIndex 0
#sub RegisterAudioExtension
Root: HKCU; Subkey: "Software\Classes\Applications\SonicForge.exe\SupportedTypes"; ValueType: string; ValueName: "{#AudioExts[ExtIndex]}"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\{#AudioExts[ExtIndex]}\OpenWithProgids"; ValueType: string; ValueName: "SonicForge.Audio"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Dumuzeyn\SonicForge\Capabilities\FileAssociations"; ValueType: string; ValueName: "{#AudioExts[ExtIndex]}"; ValueData: "SonicForge.Audio"
#endsub
#for {ExtIndex = 0; ExtIndex < DimOf(AudioExts); ExtIndex++} RegisterAudioExtension

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Sonic Forge"; Flags: nowait postinstall skipifsilent
