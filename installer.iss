[Setup]
AppId={{8F4E9A12-3B7C-4D9E-A1F0-7C2E5B8D9A01}
AppName=Circle to Search
AppVersion=2.0.0
AppPublisher=Mashiro
AppPublisherURL=https://github.com/NekoLimenyan/circle-to-search-windows
DefaultDirName={autopf}\Circle to Search
DefaultGroupName=Circle to Search
AllowNoIcons=yes
; Встановлення в профіль користувача без запиту прав адміністратора (але папку можна змінити на будь-яку)
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=CircleToSearch-Setup
SetupIconFile=app\circle_to_search.ico
UninstallDisplayIcon={app}\CircleToSearch.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=CircleToSearch.exe

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Запускати автоматично разом із Windows"; GroupDescription: "Додаткові параметри:"

[Files]
Source: "dist\CircleToSearch.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Circle to Search"; Filename: "{app}\CircleToSearch.exe"; Comment: "Увімкнути або вимкнути Circle to Search (Alt+Q)"
Name: "{group}\Видалити Circle to Search"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Circle to Search"; Filename: "{app}\CircleToSearch.exe"; Tasks: desktopicon; Comment: "Увімкнути або вимкнути Circle to Search (Alt+Q)"
Name: "{userstartup}\Circle to Search"; Filename: "{app}\CircleToSearch.exe"; Tasks: startupicon; Comment: "Автозапуск Circle to Search"

[Run]
Filename: "{app}\CircleToSearch.exe"; Description: "Запустити Circle to Search зараз"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM CircleToSearch.exe"; Flags: runhidden; RunOnceId: "StopCircleToSearch"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /T /IM CircleToSearch.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;