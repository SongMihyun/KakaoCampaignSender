# KakaoCampaignSender (카센더)

연락처·캠페인·발송 작업을 관리하는 Windows 데스크톱 앱입니다.

## 프로젝트 구조

```
src/
├── app/              # 진입점, 경로, 버전
├── backend/
│   ├── core/         # lifecycle, logging, error_report
│   ├── database/     # SQLite 스키마·부트스트랩
│   ├── domains/      # contacts, campaigns, sending, logs, …
│   ├── integrations/ # kakaotalk, excel, windows
│   ├── stores/       # UI용 in-memory 캐시
│   └── updates/      # 온라인 업데이트
└── frontend/
    ├── app/          # MainWindow, splash
    ├── layout/       # header, navigation, statusbar
    ├── pages/        # 화면별 UI
    ├── dialogs/
    ├── utils/
    └── widgets/
```

레이어 책임·발송 흐름은 [ARCHITECTURE.md](ARCHITECTURE.md)를 참고하세요.

## 재사용 패키지 (팩스센더 등)

| 패키지 | 설명 |
|--------|------|
| `packages/kakao_win32` | Windows HWND·클립보드 |
| `packages/kakao_pc_driver` | 카카오톡 PC 발송 (`send_self_message`) |

팩스센더 `pyproject.toml` 예:

```toml
kakao-pc-driver = { path = "../KakaoCampaignSender/packages/kakao_pc_driver", develop = true }
```

```python
from kakao_pc_driver import send_self_message
send_self_message("팩스 처리 완료", my_name="본인이름")
```

예제: `examples/send_self.py` · 문서: `packages/kakao_pc_driver/README.md`

---

## 로컬 실행

```powershell
poetry install
poetry run python .\src\app\main.py
```

## 빌드

```powershell
# 기본 (dist/build 정리 후 빌드)
.\build_exe.ps1

# 정리 없이 빌드만
.\build_exe.ps1 -NoClean
```

## 릴리스

```powershell
# 버전만 올리고 Push + Tag
.\release.ps1 -Version 0.1.16

# 로컬 빌드까지 포함
.\release.ps1 -Version 0.1.16 -BuildLocal

# dist/build 유지
.\release.ps1 -Version 0.1.16 -BuildLocal -NoClean
```

## 회귀 테스트

기능 변경 후 [REGRESSION_CHECKLIST.md](REGRESSION_CHECKLIST.md) 기준으로 확인합니다.

## Auth API 로그인 연동

KakaoCampaignSender는 카카오 OAuth 성공 후 자체적으로 앱 진입을 허용하지 않고, `kasender-auth-api`의 로그인 판정 endpoint를 호출합니다.

```text
KakaoCampaignSender
↓
POST /auth/kakao/login
↓
kasender-auth-api
↓
local D1 또는 Cloudflare D1
```

로컬 기본값:

```text
AUTH_API_MODE=local
AUTH_API_BASE_URL_LOCAL=http://127.0.0.1:8787
PROJECT_CODE=kasender
```

운영 기본값:

```text
AUTH_API_MODE=production
AUTH_API_BASE_URL_PRODUCTION=https://auth.kasender.com
PROJECT_CODE=kasender
```

요청에는 다음 값이 포함됩니다.

- `provider_user_id`: 카카오 사용자 id
- `device_id`: `%LOCALAPPDATA%\kakao_campaign_sender\device_id`에 저장되는 PC별 UUID
- `app_version`: 앱 버전. 개발 빌드는 `dev`
- `project_code`: `kasender`

판정 결과 처리:

- `ALLOWED`: 앱 진입 허용
- `SIGNUP_REQUIRED`: 등록되지 않은 계정 안내 후 차단
- `DENIED / USER_PENDING`: 승인 대기 안내 후 차단
- `DENIED / USER_BLOCKED`: 차단 계정 안내 후 차단
- `DENIED / USER_EXPIRED`: 사용 기간 만료 안내 후 차단
- `DENIED / PROJECT_PENDING`: 카센더 권한 승인 대기 안내 후 차단
- `DENIED / PROJECT_BLOCKED`: 카센더 권한 차단 안내 후 차단
- `DENIED / PROJECT_EXPIRED`: 카센더 권한 만료 안내 후 차단
- `DENIED / PROJECT_NOT_ALLOWED`: 카센더 사용 권한 없음 안내 후 차단

Auth API 연결 실패 시 자동 허용하지 않습니다. 기존 비상 로그인은 별도 흐름으로 유지됩니다.

로컬 테스트 순서:

```powershell
cd D:\01_DEV\kasender-auth-api
npm run dev
```

그 다음 KakaoCampaignSender를 실행합니다.

```powershell
cd D:\01_DEV\KakaoCampaignSender
poetry run python .\src\app\main.py
```

개발 중 특정 provider id를 강제로 테스트하려면 `.env`에 아래 값을 넣을 수 있습니다. 운영 빌드에서는 사용하지 않습니다.

```text
KASENDER_DEV_KAKAO_PROVIDER_USER_ID=kakao_10001
```

로그인 시도 결과는 Project Portal Admin의 `Membership / Login Logs` 또는 `GET /admin/login-logs`에서 확인합니다.

## Auth API 로그인 실패 메시지

카카오 OAuth 성공 후 `kasender-auth-api`의 `/auth/kakao/login` 판정 결과를 반드시 확인합니다.

실패 메시지는 `src/backend/domains/auth/auth_messages.py`에서 중앙 관리합니다. `AuthError`는 화면 제목과 본문을 분리해서 전달하며, 로그에는 토큰 없이 `result`, `reason`, `user_uuid`, `project_code`, `device_id`, `app_version`만 기록합니다.

대표 결과:

- `SIGNUP_REQUIRED`: 등록되지 않은 계정
- `DENIED / USER_PENDING`: 승인 대기
- `DENIED / USER_BLOCKED`: 계정 차단
- `DENIED / USER_EXPIRED`: 계정 만료
- `DENIED / PROJECT_NOT_ALLOWED`: 카센더 권한 없음
- `DENIED / PROJECT_EXPIRED`: 카센더 권한 만료
