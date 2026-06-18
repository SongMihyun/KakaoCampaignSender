# 설치파일 실행 문제 진단 가이드

대상 버전: `v1.0.17` 이상

이 문서는 `KakaoCampaignSenderSetup_1.0.17.exe`를 실행했을 때 SmartScreen의 "추가 정보 -> 실행" 이후 설치 창이 뜨지 않거나 아무 반응이 없는 경우를 진단하기 위한 안내입니다.

## 현재 배포 구조

- GitHub Actions `Windows Release Build`에서 Windows 설치파일을 생성합니다.
- 빌드 환경은 `windows-latest`와 Python `3.11`입니다.
- 앱 실행 파일은 PyInstaller `onedir` 방식으로 생성됩니다.
- 설치파일은 Inno Setup 6으로 생성됩니다.
- 설치 위치는 기본적으로 현재 사용자 계정의 `%LOCALAPPDATA%\KakaoCampaignSender`입니다.
- 관리자 권한은 기본 요구하지 않습니다. `PrivilegesRequired=lowest`
- 현재 빌드는 64비트 Windows 기준입니다. 32비트 Windows에서는 실행되지 않을 수 있습니다.
- 이 문서가 추가된 이후의 설치파일은 Inno Setup에서 64비트 호환 Windows를 명시적으로 요구합니다.

## 가장 먼저 확인할 것

문제 PC에서 PowerShell을 열고 설치파일이 있는 폴더로 이동합니다. 예를 들어 바탕화면에 있다면:

```powershell
cd $env:USERPROFILE\Desktop
```

아래 3개 결과를 먼저 확인해서 전달해주세요.

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, OSArchitecture

Get-Item .\KakaoCampaignSenderSetup_1.0.17.exe | Select-Object Name, Length, FullName

Get-FileHash .\KakaoCampaignSenderSetup_1.0.17.exe -Algorithm SHA256
```

`v1.0.17` 정상값:

```text
파일명: KakaoCampaignSenderSetup_1.0.17.exe
파일 크기: 56797689 bytes
SHA256: ab17a5701e991effe8271cbc1d198af93f40003c3c1638ecdcc0c67022751f43
```

파일 크기나 SHA256이 다르면 다운로드 손상 가능성이 높습니다. 다시 다운로드하거나 정상 PC에서 받은 파일을 USB로 옮겨 테스트하세요.

## Release 메타데이터 확인

GitHub Release의 설치파일 자산에는 파일 크기와 SHA256 digest가 표시됩니다.

`v1.0.17`의 `latest.json`에는 `sha256`은 있지만 `size` 필드는 없습니다. 이 문서가 추가된 이후의 릴리즈부터 `latest.json`에 아래 필드를 함께 포함합니다.

```json
{
  "version": "1.0.18",
  "filename": "KakaoCampaignSenderSetup_1.0.18.exe",
  "url": "https://github.com/SongMihyun/KakaoCampaignSender/releases/download/v1.0.18/KakaoCampaignSenderSetup_1.0.18.exe",
  "size": 56797689,
  "sha256": "...",
  "notes": "",
  "published_at": "..."
}
```

릴리즈 본문에도 설치파일 이름, 파일 크기, SHA256, `/LOG` 진단 명령이 자동으로 표시됩니다.

## 1. PowerShell에서 직접 실행

더블클릭 대신 PowerShell에서 직접 실행하면 일부 오류 메시지가 창에 남을 수 있습니다.

```powershell
cd $env:USERPROFILE\Desktop
.\KakaoCampaignSenderSetup_1.0.17.exe
```

아무 메시지 없이 종료되면 다음 단계로 진행합니다.

## 2. 차단 해제 후 실행

인터넷에서 받은 실행 파일은 Windows가 차단 표시를 붙일 수 있습니다.

```powershell
cd $env:USERPROFILE\Desktop
Unblock-File .\KakaoCampaignSenderSetup_1.0.17.exe
.\KakaoCampaignSenderSetup_1.0.17.exe
```

파일 우클릭 -> 속성 -> "차단 해제" 체크 -> 적용으로도 같은 처리를 할 수 있습니다.

## 3. 관리자 권한으로 실행

일부 회사 PC나 보안 정책이 있는 환경에서는 사용자 권한 설치도 막힐 수 있습니다.

```powershell
cd $env:USERPROFILE\Desktop
Start-Process .\KakaoCampaignSenderSetup_1.0.17.exe -Verb RunAs
```

관리자 권한 확인 창 이후에도 무반응이면 설치파일 로그를 남겨 확인합니다.

## 4. 설치 로그 생성

Inno Setup 설치파일은 `/LOG` 옵션으로 설치 로그를 만들 수 있습니다.

```powershell
cd $env:USERPROFILE\Desktop
.\KakaoCampaignSenderSetup_1.0.17.exe /LOG="$env:USERPROFILE\Desktop\kasender_setup.log"
```

또는 관리자 권한으로 로그를 남깁니다.

```powershell
cd $env:USERPROFILE\Desktop
Start-Process .\KakaoCampaignSenderSetup_1.0.17.exe -Verb RunAs -ArgumentList "/LOG=$env:USERPROFILE\Desktop\kasender_setup_admin.log" -Wait
```

생성된 로그 파일을 확인합니다.

```powershell
Get-Content .\kasender_setup.log -Tail 80
```

로그 파일 자체가 생성되지 않으면, 설치파일이 Inno Setup 초기화 전에 보안 프로그램이나 Windows 정책에 의해 종료됐을 가능성이 큽니다.

## 5. Windows 64비트 확인

현재 설치파일은 64비트 Windows 기준입니다.

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, OSArchitecture
```

정상 기대값:

```text
64-bit
```

`32-bit`이면 현재 설치파일이 실행되지 않을 수 있으며, 별도 32비트 빌드가 필요합니다.

ARM Windows의 경우 x64 에뮬레이션 환경에서는 동작할 수 있지만, 현재 배포물은 ARM 네이티브 빌드가 아닙니다. 회사 보안 에이전트나 UI 자동화 관련 모듈이 ARM 환경에서 다르게 동작할 수 있습니다.

## 6. Windows 보안 보호 기록 확인

SmartScreen을 통과해도 Windows Defender나 백신이 뒤에서 차단할 수 있습니다.

확인 경로:

```text
Windows 보안
-> 바이러스 및 위협 방지
-> 보호 기록
```

아래 이름이 차단/격리로 표시되는지 확인합니다.

```text
KakaoCampaignSenderSetup_1.0.17.exe
KakaoCampaignSender.exe
```

차단 항목이 있으면 설치파일 자체의 PC별 빌드 문제가 아니라 미서명 베타 실행 파일 차단 가능성이 큽니다.

## 7. 백신/사내 보안 프로그램 확인

아래 환경에서는 실행 직후 무반응 문제가 더 자주 발생할 수 있습니다.

- 회사 데스크탑
- V3, 알약, Windows Defender, 사내 보안 에이전트 설치 PC
- 다운로드 폴더 실행 파일 자동 검사 정책이 있는 PC
- USB나 메신저로 받은 exe 실행 제한 정책이 있는 PC

백신 격리소 또는 보안 프로그램 이벤트 로그에서 `KakaoCampaignSenderSetup_1.0.17.exe`가 차단됐는지 확인하세요.

## 8. 설치 후 앱이 실행되지 않는 경우

설치 창은 뜨고 완료됐지만 앱이 실행되지 않으면 앱 로그를 확인합니다.

```powershell
Get-ChildItem "$env:LOCALAPPDATA\kakao_campaign_sender\logs" -File -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 FullName, Length, LastWriteTime
```

오류 보고 패키지가 있다면 아래도 확인합니다.

```powershell
Get-ChildItem "$env:LOCALAPPDATA\kakao_campaign_sender\support_packages" -File -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 FullName, Length, LastWriteTime
```

## 9. 문제 PC에서 전달받을 최소 정보

아래 결과를 복사해서 전달받으면 원인 범위를 빠르게 줄일 수 있습니다.

```powershell
cd $env:USERPROFILE\Desktop

Get-CimInstance Win32_OperatingSystem | Select-Object Caption, OSArchitecture

Get-Item .\KakaoCampaignSenderSetup_1.0.17.exe | Select-Object Name, Length, FullName

Get-FileHash .\KakaoCampaignSenderSetup_1.0.17.exe -Algorithm SHA256

.\KakaoCampaignSenderSetup_1.0.17.exe /LOG="$env:USERPROFILE\Desktop\kasender_setup.log"

Get-Item .\kasender_setup.log -ErrorAction SilentlyContinue | Select-Object Name, Length, FullName
```

가능하면 아래 화면도 확인합니다.

```text
Windows 보안 -> 바이러스 및 위협 방지 -> 보호 기록
```

## 현재 알려진 개선 후보

- 설치 완료 후 앱 최초 실행 실패 시 사용자에게 로그 위치를 안내하는 별도 도움말을 추가합니다.
- 코드 서명 인증서를 적용해 SmartScreen/백신 오탐 가능성을 줄입니다.
