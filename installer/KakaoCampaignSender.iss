; installer/KakaoCampaignSender.iss
; ------------------------------------------------------------
; KakaoCampaignSender Installer (Inno Setup 6)
; - Version injected by CI: ISCC.exe /DMyAppVersion=1.2.3 ...
; - Installs from PyInstaller output: dist\app\*
; - Creates desktop + start menu shortcuts
; - Uses localappdata install to minimize UAC
; ------------------------------------------------------------

#define MyAppName "KakaoCampaignSender"
#define MyAppExeName "KakaoCampaignSender.exe"

; ✅ PyInstaller dist directory (프로젝트 상황에 맞게 유지)
#define MyAppDistDir "dist\app"

; ✅ 아이콘 파일 (프로젝트에 있는 파일명/경로로 맞추세요)
;    예) assets\KakaoSender.ico or KakaoSender.ico
#define MyAppIconFile "KakaoSender.ico"

; ✅ 빌드 단계에서 /DMyAppVersion=1.2.3 로 주입
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
; ✅ 고정 AppId 권장(업데이트/재설치 식별). GUID 하나 생성해서 고정하세요.
;    기존에 쓰던 AppId가 있으면 그걸 그대로 넣는게 베스트.
AppId={{7F6C5D7B-9B6D-4F7A-9F2A-1A1C2C3D4E5F}}

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=YourCompany

DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; ✅ 출력 위치/파일명 (당신이 선택한 구조 유지)
OutputDir=dist\installer
OutputBaseFilename={#MyAppName}Setup_{#MyAppVersion}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; ✅ UAC 최소화
PrivilegesRequired=lowest

; ✅ 아이콘/언인스톨 아이콘
SetupIconFile={#MyAppIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}

; ✅ 64비트 OS면 64비트 모드(필요없으면 제거 가능)
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
; ✅ 바탕화면 아이콘 (기본 체크 해제: 원하면 unchecked 제거)
Name: "desktopicon"; Description: "바탕화면 바로가기 생성"; GroupDescription: "추가 작업:"; Flags: unchecked

[Files]
; ✅ PyInstaller 결과물을 통째로 설치
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ✅ 아이콘 파일을 설치 폴더에도 복사(바로가기에서 참조)
Source: "{#MyAppIconFile}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; ✅ 시작메뉴
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconFile}"

; ✅ 바탕화면(옵션)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppIconFile}"

[Run]
; ✅ 설치 직후 실행 (사용자가 체크한 경우만 / silent에서는 실행 안 함)
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent