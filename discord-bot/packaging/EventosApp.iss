; Inno Setup script for Eventos App.  Compile with:  ISCC /DAppVersion=0.1.0 packaging\EventosApp.iss
; (build_windows.ps1 does this after PyInstaller.)  Saved as UTF-8 with BOM so the Spanish text is read correctly.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Eventos App"
#define AppExe "EventosApp.exe"

[Setup]
AppId={{76659804-A9EC-4306-83E5-C3ADBA499386}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL=https://github.com/Yendaxddd/eventos-app
; Per-user install: no administrator prompt, and the install folder stays writable, which is where
; the app keeps data/, assets/, logs/ and settings.json.
PrivilegesRequired=lowest
DefaultDirName={autopf}\EventosApp
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\eventos_app\resources\icon.ico
OutputDir=..\dist
OutputBaseFilename=EventosApp-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; If the app is open during an update, offer to close it instead of failing on locked files.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; The PyInstaller runtime is replaced wholesale on every update, so old DLLs don't pile up.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\EventosApp\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\EventosApp\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\EventosApp\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion
; User data: never overwrite what is already there (player stats, GIFs the GMs added...) and never
; delete it on uninstall. New files shipped with an update are still added.
Source: "..\dist\EventosApp\data\*"; DestDir: "{app}\data"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs
Source: "..\dist\EventosApp\assets\*"; DestDir: "{app}\assets"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    if MsgBox('¿Quieres borrar también tus datos (token, datos de jugadores, GIFs y registros)?' + #13#10 + #13#10 +
              'Carpeta: ' + ExpandConstant('{app}') + #13#10 + #13#10 +
              'Si respondes que no, se conservan por si vuelves a instalar la app.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
