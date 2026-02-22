; installer/KakaoCampaignSender.iss
; ------------------------------------------------------------
; KakaoCampaignSender Installer (Inno Setup 6)
; - Version injected by CI: ISCC.exe /DMyAppVersion=1.2.3 ...
; - Installs from PyInstaller output: dist\app\KakaoCampaignSender\*
; - Creates desktop + start menu shortcuts
; - Uses localappdata install to minimize UAC
; ------------------------------------------------------------

#define MyAppName "KakaoCampaignSender"
#define MyAppExeName "KakaoCampaignSender.exe"

; ✅ PyInstaller 산출물(최종 폴더명 통일)
#define MyAppDistDir "dist\app\KakaoCampaignSender"

; ✅ 아이콘: 소스 경로(컴파일 시) / 설치 후 파일명 분리
#define MyAppIconSource "KakaoSender.ico"
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

OutputDir=dist\installer
OutputBaseFilename={#MyAppName}Setup_{#MyAppVersion}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

; ✅ 컴파일 시 아이콘 파일 경로
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

; ✅ 아이콘을 설치 폴더에 "KakaoSender.ico" 이름으로 복사
Source: "{#MyAppIconSource}"; DestDir: "{app}"; DestName: "{#MyAppIconName}"; Flags: ignoreversion

[Icons]
; ✅ 시작메뉴
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconName}"

; ✅ 바탕화면(옵션)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppIconName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent