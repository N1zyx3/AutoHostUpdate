; Inno Setup 6: установщик AutoHostUpdate (заготовка, требует проверки на чистой VM).
; Сборка: iscc packaging\installer.iss

#define AppName "AutoHostUpdate"
#define AppVersion "0.2.0"
#define AppPublisher "AutoHostUpdate"
#define AppExe "AutoHostUpdate.exe"

[Setup]
AppId={{0F3C9F1A-7A2B-4C1E-9D3E-A1B2C3D4E5F6}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AutoHostUpdate-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0.17763
; Не даём устанавливать/удалять, пока запущен UI (Local) или CLI-обновление (Global).
AppMutex=Local\AutoHostUpdate_UI,Global\AutoHostUpdate_RunOnce
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "schedule"; Description: "Запускать обновление при входе в систему"; GroupDescription: "Автоматизация:"

[Run]
; Задача регистрируется от администратора (Setup уже elevated).
Filename: "{app}\{#AppExe}"; Parameters: "--install-task"; Flags: runhidden; Tasks: schedule
; UI запускаем от исходного (неэлевированного) пользователя.
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--uninstall-task"; Flags: runhidden; RunOnceId: "RemoveTask"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AutoHostUpdate"
