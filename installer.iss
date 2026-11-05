; مثبّت AeroGrab (Inno Setup 6.3+).  بيتبني تلقائي من GitHub Actions، أو يدوي:
;   python build_release.py        (بيبني البرنامج ثم المثبّت لو Inno Setup متسطّب)
; المتغيرات بتتبعت من سطر الأوامر:  /DAppVersion=4.2  /DArch=x64|x86
#ifndef AppVersion
  #define AppVersion "0.0"
#endif
#ifndef Arch
  #define Arch "x64"
#endif
#define AppName "AeroGrab"
#define AppExe "AeroGrab.exe"

[Setup]
; AppId ثابت: بيخلي كل إصدار جديد يتثبّت فوق القديم ويظهر كبرنامج واحد في Apps & features. ما تغيّروش أبداً.
AppId={{6B0E4C3A-5D2F-4F7B-9A1E-AE20A6C0DA11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; تثبيت لمستخدم واحد من غير صلاحيات أدمن: التحديث التلقائي بيقدر يكتب في المجلد
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=AeroGrab-{#AppVersion}-{#Arch}-Setup
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
#if Arch == "x64"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\AeroGrab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; تثبيت عادي: خيار "Launch AeroGrab" في آخر الويزارد
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; تحديث تلقائي (صامت): البرنامج بيتفتح تاني لوحده
Filename: "{app}\{#AppExe}"; Parameters: "--restarted"; Flags: nowait; Check: WizardSilent

[Code]
// عند الإزالة: نسأل لو عايز يمسح الإعدادات وسجل التحميلات (مجلد .aerograb). التحميلات نفسها عمرها ما بتتمسح.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    DataDir := ExpandConstant('{%USERPROFILE}\.aerograb');
    if DirExists(DataDir) then
      if MsgBox('Also delete AeroGrab settings and download history?' + #13#10 +
                'Your downloaded files are not touched.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
