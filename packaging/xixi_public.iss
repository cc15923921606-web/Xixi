#define MyAppName "昔夕"
#ifndef MyAppVersion
  #define MyAppVersion "0.1"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "Xixi-Setup"
#endif
#ifndef MyDistDir
  #define MyDistDir "dist"
#endif
#ifndef MyAppId
  #define MyAppId "{{92A89E60-B91E-4A9E-89B4-468A91642853}"
#endif
#ifndef MyAppRegistryId
  #define MyAppRegistryId "{92A89E60-B91E-4A9E-89B4-468A91642853}"
#endif
#define MyAppPublisher "Xixi"
#define MyAppExeName "Xixi.exe"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Xixi
DisableDirPage=no
UsePreviousAppDir=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyDistDir}\installer
OutputBaseFilename={#MyOutputBaseFilename}
SetupIconFile=..\studio\assets\xixi-v3.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern light
WizardImageFile=assets\wizard-large.png
WizardSmallImageFile=assets\wizard-small.png
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\程序文件\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
UninstallFilesDir={app}\卸载程序
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=昔夕 AI 伴侣安装程序
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (C) 2026 Xixi

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce
Name: "startup"; Description: "开机后自动启动昔夕"; GroupDescription: "自动启动："; Flags: unchecked

[Messages]
WelcomeLabel1=欢迎安装昔夕
WelcomeLabel2=昔夕会把程序文件、用户数据和卸载程序分别归类保存。聊天、记忆、关系和模型配置会保留在独立的“用户数据”目录中。%n%n安装程序将引导你完成安装。
SelectDirLabel3=安装程序将把昔夕安装到以下文件夹。
FinishedHeadingLabel=昔夕安装完成
FinishedLabel=昔夕已经安装到你的电脑，可以从桌面、开始菜单或安装目录中的“启动昔夕”打开。首次启动会在安装目录内建立“用户数据”，后续升级不会覆盖聊天、记忆和设置。

[Files]
Source: "{#MyDistDir}\Xixi\*"; DestDir: "{app}\程序文件"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "ChineseSimplified.LICENSE.txt"; DestDir: "{app}\程序文件"; Flags: ignoreversion

[InstallDelete]
; Remove the old flat one-folder runtime. User data is only removed from these
; legacy locations after a valid external-data pointer proves migration finished.
Type: files; Name: "{app}\*.pyd"
Type: files; Name: "{app}\*.dll"
Type: files; Name: "{app}\base_library.zip"
Type: files; Name: "{app}\Xixi.exe"
Type: files; Name: "{app}\构建清单.json"
Type: files; Name: "{app}\README.txt"
Type: files; Name: "{app}\ChineseSimplified.LICENSE.txt"
Type: files; Name: "{app}\persona.txt"; Check: LegacyExternalDataExists
Type: files; Name: "{app}\interest_profile.json"; Check: LegacyExternalDataExists
Type: files; Name: "{app}\knowledge.txt"; Check: LegacyExternalDataExists
Type: files; Name: "{app}\learning_sources.json"; Check: LegacyExternalDataExists
Type: files; Name: "{app}\meme_lexicon.json"; Check: LegacyExternalDataExists
Type: filesandordirs; Name: "{app}\_sounddevice_data"
Type: filesandordirs; Name: "{app}\aiohttp"
Type: filesandordirs; Name: "{app}\attrs-26.1.0.dist-info"
Type: filesandordirs; Name: "{app}\av"
Type: filesandordirs; Name: "{app}\av.libs"
Type: filesandordirs; Name: "{app}\certifi"
Type: filesandordirs; Name: "{app}\charset_normalizer"
Type: filesandordirs; Name: "{app}\click-8.4.2.dist-info"
Type: filesandordirs; Name: "{app}\clr_loader"
Type: filesandordirs; Name: "{app}\comtypes"
Type: filesandordirs; Name: "{app}\comtypes-1.4.16.dist-info"
Type: filesandordirs; Name: "{app}\ctranslate2"
Type: filesandordirs; Name: "{app}\ctranslate2-4.8.1.dist-info"
Type: filesandordirs; Name: "{app}\cv2"
Type: filesandordirs; Name: "{app}\dxcam"
Type: filesandordirs; Name: "{app}\dxcam-0.0.5.dist-info"
Type: filesandordirs; Name: "{app}\faster_whisper"
Type: filesandordirs; Name: "{app}\faster_whisper-1.2.1.dist-info"
Type: filesandordirs; Name: "{app}\frozenlist"
Type: filesandordirs; Name: "{app}\hf_xet"
Type: filesandordirs; Name: "{app}\imageio_ffmpeg"
Type: filesandordirs; Name: "{app}\jiter"
Type: filesandordirs; Name: "{app}\keyring-25.7.0.dist-info"
Type: filesandordirs; Name: "{app}\markupsafe"
Type: filesandordirs; Name: "{app}\markupsafe-3.0.3.dist-info"
Type: filesandordirs; Name: "{app}\multidict"
Type: filesandordirs; Name: "{app}\numpy"
Type: filesandordirs; Name: "{app}\numpy-2.4.6.dist-info"
Type: filesandordirs; Name: "{app}\numpy.libs"
Type: filesandordirs; Name: "{app}\ollama-0.6.2.dist-info"
Type: filesandordirs; Name: "{app}\onnxruntime"
Type: filesandordirs; Name: "{app}\opencc"
Type: filesandordirs; Name: "{app}\PIL"
Type: filesandordirs; Name: "{app}\propcache"
Type: filesandordirs; Name: "{app}\pydantic_core"
Type: filesandordirs; Name: "{app}\pydantic-2.13.4.dist-info"
Type: filesandordirs; Name: "{app}\pygame"
Type: filesandordirs; Name: "{app}\pygame-2.6.1.dist-info"
Type: filesandordirs; Name: "{app}\pypinyin"
Type: filesandordirs; Name: "{app}\pythonnet"
Type: filesandordirs; Name: "{app}\setuptools"
Type: filesandordirs; Name: "{app}\sounddevice-0.5.5.dist-info"
Type: filesandordirs; Name: "{app}\studio"
Type: filesandordirs; Name: "{app}\tokenizers"
Type: filesandordirs; Name: "{app}\tqdm-4.70.0.dist-info"
Type: filesandordirs; Name: "{app}\websockets"
Type: filesandordirs; Name: "{app}\websockets-17.0.1.dist-info"
Type: filesandordirs; Name: "{app}\webview"
Type: filesandordirs; Name: "{app}\whisper-small-full"
Type: filesandordirs; Name: "{app}\yaml"
Type: filesandordirs; Name: "{app}\yarl"
Type: filesandordirs; Name: "{app}\data"; Check: LegacyExternalDataExists
Type: filesandordirs; Name: "{app}\logs"; Check: LegacyExternalDataExists
Type: filesandordirs; Name: "{app}\runtime"; Check: LegacyExternalDataExists
; Remove shortcuts created by public preview installers that used the old name.
; The personal-edition shortcut has a different explicit name and is untouched.
Type: files; Name: "{group}\昔夕（公开版）.lnk"
Type: files; Name: "{autodesktop}\昔夕（公开版）.lnk"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\用户数据"; Check: ShouldDeleteUserData

[Icons]
Name: "{app}\启动昔夕"; Filename: "{app}\程序文件\{#MyAppExeName}"; WorkingDir: "{app}\程序文件"
Name: "{group}\昔夕"; Filename: "{app}\程序文件\{#MyAppExeName}"; WorkingDir: "{app}\程序文件"
Name: "{autodesktop}\昔夕"; Filename: "{app}\程序文件\{#MyAppExeName}"; WorkingDir: "{app}\程序文件"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "XixiStudioPublic"; ValueData: """{app}\程序文件\{#MyAppExeName}"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\程序文件\{#MyAppExeName}"; WorkingDir: "{app}\程序文件"; Description: "启动昔夕"; Flags: nowait postinstall skipifsilent

[Code]
const
  PublicUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppRegistryId}_is1';

var
  ExistingInstallDir: String;
  DeleteUserDataOnUninstall: Boolean;

function ShouldDeleteUserData(): Boolean;
begin
  Result := DeleteUserDataOnUninstall;
end;

function InitializeUninstall(): Boolean;
begin
  DeleteUserDataOnUninstall :=
    SuppressibleMsgBox(
      '是否同时删除昔夕的用户数据？' + #13#10#13#10 +
      '选择“是”会永久删除聊天、记忆、关系、模型配置和本地组件。' + #13#10 +
      '选择“否”只删除程序，之后重新安装仍可继续使用原数据。',
      mbConfirmation,
      MB_YESNO,
      IDNO
    ) = IDYES;
  Result := True;
end;

function NormalizeInstallDir(Path: String): String;
begin
  Result := Lowercase(RemoveBackslashUnlessRoot(ExpandFileName(Path)));
end;

function RegisteredInstallExists(Path: String): Boolean;
var
  NormalizedPath: String;
begin
  NormalizedPath := RemoveBackslashUnlessRoot(Path);
  Result :=
    (NormalizedPath <> '') and
    DirExists(NormalizedPath) and
    (
      FileExists(AddBackslash(NormalizedPath) + '{#MyAppExeName}') or
      FileExists(AddBackslash(NormalizedPath) + '程序文件\{#MyAppExeName}') or
      FileExists(AddBackslash(NormalizedPath) + 'unins000.exe')
      or FileExists(AddBackslash(NormalizedPath) + '卸载程序\unins000.exe')
    );
end;

function LegacyExternalDataExists(): Boolean;
begin
  Result := FileExists(AddBackslash(WizardDirValue()) + '数据目录.txt');
end;

procedure ClearStaleInstallRegistration();
begin
  RegDeleteKeyIncludingSubkeys(HKCU64, PublicUninstallKey);
  RegDeleteKeyIncludingSubkeys(HKCU32, PublicUninstallKey);
  ExistingInstallDir := '';
end;

function LoadExistingInstallDir(): Boolean;
begin
  if ExistingInstallDir = '' then
  begin
    if not RegQueryStringValue(HKCU64, PublicUninstallKey, 'InstallLocation', ExistingInstallDir) then
      RegQueryStringValue(HKCU32, PublicUninstallKey, 'InstallLocation', ExistingInstallDir);
  end;
  ExistingInstallDir := RemoveBackslashUnlessRoot(ExistingInstallDir);
  if (ExistingInstallDir <> '') and not RegisteredInstallExists(ExistingInstallDir) then
    ClearStaleInstallRegistration();
  Result := ExistingInstallDir <> '';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpSelectDir) and LoadExistingInstallDir();
end;

procedure InitializeWizard();
begin
  if LoadExistingInstallDir() then
    WizardForm.DirEdit.Text := ExistingInstallDir;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if LoadExistingInstallDir() and
     (NormalizeInstallDir(WizardDirValue()) <> NormalizeInstallDir(ExistingInstallDir)) then
  begin
    WizardForm.DirEdit.Text := ExistingInstallDir;
    SuppressibleMsgBox(
      '检测到昔夕已经安装在：' + #13#10 + ExistingInstallDir + #13#10#13#10 +
      '本次将只覆盖升级原目录，不会在其他位置重复安装。若要更换安装位置，请先从 Windows 设置中卸载现有安装，再重新安装。',
      mbInformation,
      MB_OK,
      IDOK
    );
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OldPointer: String;
  NewPointer: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  OldPointer := ExpandConstant('{app}\数据目录.txt');
  NewPointer := ExpandConstant('{app}\程序文件\数据目录.txt');
  if FileExists(OldPointer) then
  begin
    ForceDirectories(ExtractFileDir(NewPointer));
    if not CopyFile(OldPointer, NewPointer, False) then
      RaiseException('无法迁移原有数据目录配置：' + OldPointer);
    DeleteFile(OldPointer);
  end;

  if FileExists(ExpandConstant('{app}\卸载程序\unins000.exe')) then
  begin
    DeleteFile(ExpandConstant('{app}\unins000.dat'));
    DeleteFile(ExpandConstant('{app}\unins000.msg'));
    DeleteFile(ExpandConstant('{app}\unins000.exe'));
  end;
end;
