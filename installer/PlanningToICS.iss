#define MyAppName "Planning to ICS"
#define MyAppVersion "1.07"
#define MyAppPublisher "Mamat"
#define MyAppExeName "Planning to ICS.exe"

[Setup]
AppId=PlanningToICS-{#MyAppVersion}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
DisableProgramGroupPage=no
PrivilegesRequired=lowest
OutputDir=..\installer-output
OutputBaseFilename=Planning_to_ICS_V1.07_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\planning-to-ics.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "startmenuicon"; Description: "Créer un raccourci dans le menu Démarrer"; GroupDescription: "Raccourcis :"
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "..\dist\Planning to ICS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}{code:GetShortcutSuffix}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}{code:GetShortcutSuffix}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  ExistingCount: Integer;
  ExistingSummary: String;
  ExistingUninstallCommands: array of String;
  InstallMode: Integer;

procedure AddExistingInstall(DisplayName, DisplayVersion, InstallLocation, UninstallCommand: String);
var
  LabelText: String;
begin
  SetArrayLength(ExistingUninstallCommands, ExistingCount + 1);
  ExistingUninstallCommands[ExistingCount] := UninstallCommand;
  ExistingCount := ExistingCount + 1;

  LabelText := DisplayName;
  if DisplayVersion <> '' then
    LabelText := LabelText + ' ' + DisplayVersion;
  if InstallLocation <> '' then
    LabelText := LabelText + ' - ' + InstallLocation;

  ExistingSummary := ExistingSummary + '- ' + LabelText + #13#10;
end;

function IsKnownPlanningToICS(DisplayName: String): Boolean;
begin
  Result :=
    (Pos('Planning To ICS', DisplayName) = 1) or
    (Pos('Planning to ICS', DisplayName) = 1);
end;

procedure ScanUninstallRoot(RootKey: Integer);
var
  Subkeys: TArrayOfString;
  I: Integer;
  Key: String;
  DisplayName: String;
  DisplayVersion: String;
  InstallLocation: String;
  QuietUninstallString: String;
  UninstallString: String;
  UninstallCommand: String;
begin
  if not RegGetSubkeyNames(RootKey, 'Software\Microsoft\Windows\CurrentVersion\Uninstall', Subkeys) then
    exit;

  for I := 0 to GetArrayLength(Subkeys) - 1 do
  begin
    Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + Subkeys[I];
    DisplayName := '';
    DisplayVersion := '';
    InstallLocation := '';
    QuietUninstallString := '';
    UninstallString := '';
    UninstallCommand := '';

    if RegQueryStringValue(RootKey, Key, 'DisplayName', DisplayName) then
    begin
      if IsKnownPlanningToICS(DisplayName) then
      begin
        RegQueryStringValue(RootKey, Key, 'DisplayVersion', DisplayVersion);
        RegQueryStringValue(RootKey, Key, 'InstallLocation', InstallLocation);

        if RegQueryStringValue(RootKey, Key, 'QuietUninstallString', QuietUninstallString) then
          UninstallCommand := QuietUninstallString
        else if RegQueryStringValue(RootKey, Key, 'UninstallString', UninstallString) then
          UninstallCommand := UninstallString + ' /VERYSILENT /SUPPRESSMSGBOXES /NORESTART';

        AddExistingInstall(DisplayName, DisplayVersion, InstallLocation, UninstallCommand);
      end;
    end;
  end;
end;

procedure DeleteLegacyShortcuts();
begin
  DeleteFile(ExpandConstant('{userprograms}\PDF to ICS.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Planning To ICS.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Planning to ICS.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Planning To ICS\PDF to ICS.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Planning To ICS\Planning To ICS.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Planning To ICS\Planning to ICS.lnk'));
  RemoveDir(ExpandConstant('{userprograms}\Planning To ICS'));
  DeleteFile(ExpandConstant('{autodesktop}\PDF to ICS.lnk'));
  DeleteFile(ExpandConstant('{autodesktop}\Planning To ICS.lnk'));
  DeleteFile(ExpandConstant('{userdesktop}\PDF to ICS.lnk'));
  DeleteFile(ExpandConstant('{userdesktop}\Planning To ICS.lnk'));
end;

procedure ScanExistingInstalls();
begin
  ExistingCount := 0;
  ExistingSummary := '';
  SetArrayLength(ExistingUninstallCommands, 0);
  ScanUninstallRoot(HKCU);
  ScanUninstallRoot(HKLM);
end;

function InitializeSetup(): Boolean;
var
  Choice: Integer;
begin
  Result := True;
  InstallMode := 0;
  ScanExistingInstalls();

  if ExistingCount > 0 then
  begin
    if WizardSilent() then
      exit;

    Choice := MsgBox(
      '{#MyAppName} est déjà installé :' + #13#10 + #13#10 +
      ExistingSummary + #13#10 +
      'Oui : remplacer la version existante.' + #13#10 +
      'Non : installer cette version en plus, dans un autre dossier.' + #13#10 +
      'Annuler : arrêter l''installation.',
      mbConfirmation,
      MB_YESNOCANCEL
    );

    if Choice = IDYES then
      InstallMode := 0
    else if Choice = IDNO then
      InstallMode := 1
    else
      Result := False;
  end;
end;

procedure InitializeWizard();
begin
  if InstallMode = 1 then
  begin
    WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Programs\{#MyAppName} {#MyAppVersion}');
    WizardForm.GroupEdit.Text := '{#MyAppName} {#MyAppVersion}';
  end;
end;

function GetShortcutSuffix(Param: String): String;
begin
  if InstallMode = 1 then
    Result := ' {#MyAppVersion}'
  else
    Result := '';
end;

procedure UninstallExistingInstalls();
var
  I: Integer;
  ResultCode: Integer;
begin
  for I := 0 to ExistingCount - 1 do
  begin
    if ExistingUninstallCommands[I] <> '' then
      Exec(ExpandConstant('{cmd}'), '/C "' + ExistingUninstallCommands[I] + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) and (InstallMode = 0) and (ExistingCount > 0) then
  begin
    UninstallExistingInstalls();
    DeleteLegacyShortcuts();
  end;
end;
