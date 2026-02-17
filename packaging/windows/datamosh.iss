#define MyAppName "Datamosh"
#define MyAppPublisher "Datamosh GUI"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "dist\\Datamosh"
#endif
#ifndef OutDir
  #define OutDir "release-artifacts"
#endif
#ifndef OutName
  #define OutName "Datamosh-installer"
#endif

[Setup]
AppId={{267AFBD9-E16B-49F8-AF34-D5DF9E7EC49A}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir={#OutDir}
OutputBaseFilename={#OutName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile=LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\Datamosh.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Datamosh.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Datamosh.exe"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
