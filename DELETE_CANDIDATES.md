# DELETE_CANDIDATES.md

구조 정리 이력 및 추가 점검 메모입니다.

## 2026-05 정리 완료

### 삭제된 미사용 모듈

| 파일 | 사유 |
|------|------|
| `src/app/kakao_launch.py` | import 0건 |
| `src/app/startup_args.py` | main 미연결 |
| `src/backend/integrations/kakaotalk/image_dib_cache.py` | driver 내부 캐시로 대체 |
| `src/backend/integrations/kakaotalk/speed_profiles.py` | driver.py 인라인 정의 사용 |
| `src/backend/integrations/windows/win_clipboard.py` | win32_core 사용 |
| `src/backend/integrations/windows/task_scheduler_service.py` | 미연결 |
| `src/backend/integrations/windows/kakaotalk_window.py` | 개발용 CLI만 |
| `src/backend/core/lifecycle/uninstall.py` | MainWindow + uninstall.ps1 사용 |
| `src/backend/updates/updater_legacy.py` | updater.py로 통합 |
| `src/backend/updates/update_config.py` | placeholder, 미사용 |
| `src/frontend/app/update_service.py` | 메뉴 미연결 |
| `src/frontend/dialogs/update_dialog.py` | 위와 함께 미사용 |

### 삭제된 루트 잡파일

- `kakao_fix.patch` — 리팩터 이전 경로 기준 패치
- `kakao_not_found_recipients.csv` — 디버그 샘플

### 수정

- `main.py`: 시작 시 업데이트 확인을 `backend.updates.updater`로 연결 (기존 splash import 오류로 무음 실패하던 문제 수정)
- `README.md`: 현재 `src/backend` + `src/frontend` 구조 반영

---

## 추가 점검 후보 (유지 중)

### `pyproject.toml`의 `docx` 패키지

Word 연동은 `python-docx`만 사용합니다. PyPI `docx` 패키지는 중복·혼동 가능성이 있어 제거 검토.

### scheduled_sends DB의 `task_name` / `task_path`

Windows 작업 스케줄러 연동 코드 삭제 후, 컬럼이 실제로 쓰이는지 확인 후 스키마 정리 가능.

---

## 삭제 전 필수 검증

```powershell
py -m compileall src
poetry run python .\src\app\main.py
```

기능 회귀: [REGRESSION_CHECKLIST.md](REGRESSION_CHECKLIST.md)
