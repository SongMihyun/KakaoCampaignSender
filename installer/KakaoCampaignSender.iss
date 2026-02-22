; installer/KakaoCampaignSender.iss
; ------------------------------------------------------------
; KakaoCampaignSender Installer (Inno Setup 6)
; - CI injects version: ISCC.exe /DMyAppVersion=1.2.3 ...
; - Installs from: dist\app\KakaoCampaignSender\*
; - Desktop + Start menu shortcuts
; - Installs to LocalAppData (minimal UAC)
; ------------------------------------------------------------

#define MyAppName "KakaoCampaignSender"
#define MyAppExeName "KakaoCampaignSender.exe"

; ✅ 중요: iss가 installer 폴더에 있으므로, dist는 한 단계 위(..)에 있음
#define MyAppDistDir "{#SourcePath}\..\dist\app\KakaoCampaignSender"

; ✅ 아이콘도 installer 폴더 기준으로 정확히
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

OutputDir={#SourcePath}\..\dist\installer
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
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 설치 폴더에 아이콘을 고정 파일명으로 복사
Source: "{#MyAppIconSource}"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppIconName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent