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
