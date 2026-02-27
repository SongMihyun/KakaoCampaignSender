; installer/KakaoCampaignSender.iss
; ------------------------------------------------------------
; KakaoCampaignSender Installer (Inno Setup 6)
; ------------------------------------------------------------

#define MyAppName "KakaoCampaignSender"
#define MyAppExeName "KakaoCampaignSender.exe"

; ✅ 사용자 노출용 바로가기 이름
#define MyShortcutName "카센더"

; ✅ CI에서 /DMyAppDistDir 로 주입. 로컬 빌드용 기본값도 제공.
#ifndef MyAppDistDir
  #define RepoRoot     "{#SourcePath}\.."
  #define MyAppDistDir "{#RepoRoot}\dist\app\KakaoCampaignSender"
#endif

; ✅ CI에서 /DOutputDir 로 주입. 로컬 빌드용 기본값도 제공.
#ifndef OutputDir
  #define OutputDir "{#SourcePath}\..\dist\installer"
#endif

; ✅ 아이콘(컴파일 시점)
#ifndef MyAppIconSource
  #define MyAppIconSource "{#SourcePath}\KakaoSender.ico"
#endif
#define MyAppIconName   "KakaoSender.ico"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{7F6C5D7B-9B6D-4F7A-9F2A-1A1C2C3D4E5F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=YourCompany

DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

OutputDir={#OutputDir}
OutputBaseFilename={#MyAppName}Setup_{#MyAppVersion}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

SetupIconFile={#MyAppIconSource}
UninstallDisplayIcon={app}\{#MyAppExeName}

ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 생성"; GroupDescription: "추가 작업:"; Flags: unchecked

[Files]
; ✅ PyInstaller 결과물을 통째로 설치
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ✅ 아이콘 설치 폴더에 복사(바로가기용)
Source: "{#MyAppIconSource}"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[Icons]
; ✅ 사용자 노출 이름은 "카센더"
Name: "{autoprograms}\{#MyShortcutName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"
Name: "{autodesktop}\{#MyShortcutName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppIconName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyShortcutName} 실행"; Flags: nowait postinstall skipifsilent