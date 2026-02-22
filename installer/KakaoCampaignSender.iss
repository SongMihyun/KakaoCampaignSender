; installer/KakaoCampaignSender.iss

#define MyAppName "KakaoCampaignSender"
#define MyAppExeName "KakaoCampaignSender.exe"

; iss 파일(=installer 폴더) 기준으로 경로 고정
#define RepoRoot        "{#SourcePath}\.."
#define MyAppDistDir    "{#RepoRoot}\dist\app\KakaoCampaignSender"

; 아이콘도 installer 폴더 기준으로 고정
#define MyAppIconSource "{#SourcePath}\KakaoSender.ico"
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

; Output도 레포 루트 dist로 고정
OutputDir={#OutputDir}
OutputBaseFilename={#MyAppName}Setup_{#MyAppVersion}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

; ✅ 여기서 아이콘을 “무조건” 찾게 됨
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

; ✅ 아이콘을 설치 폴더에 복사(바로가기용)
Source: "{#MyAppIconSource}"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppIconName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent