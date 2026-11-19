#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{74BA741E-0B31-469B-8B9A-1D9AD4129696}
AppName=DDTool
AppVersion={#AppVersion}
AppPublisher=AddBean
DefaultDirName={localappdata}\Programs\DDTool
DefaultGroupName=DDTool
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DDTool-Windows-x64-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\DDTool.exe
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\DDTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DDTool"; Filename: "{app}\DDTool.exe"

[UninstallRun]
Filename: "{app}\DDTool.exe"; Parameters: "--remove-install-integrations"; Flags: waituntilterminated; RunOnceId: "DDToolIntegrations"
