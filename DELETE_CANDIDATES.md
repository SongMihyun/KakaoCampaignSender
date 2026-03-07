# DELETE_CANDIDATES.md

이 문서는 Kakao Campaign Sender 프로젝트에서
구조 리팩토링 이후 삭제 가능하거나 점검이 필요한 파일/폴더를 정리한 문서입니다.

기준:
1. import 0건
2. MainWindow / Page 생성부 참조 0건
3. 실행 경로에서 호출 0건

---

## 1️⃣ 강한 삭제 후보 (우선 점검 대상)

### backend/intergrations/
- 오타 폴더 가능성
- 실제 사용 경로는 backend.integrations/*
- 검색식:
  Get-ChildItem src -Recurse -File -Filter *.py | Select-String -Pattern 'backend\.intergrations'
- 0건이면 삭제 가능

---

### backend/store/
- backend/stores/와 중복 여부 점검
- 검색식:
  Get-ChildItem src -Recurse -File -Filter *.py | Select-String -Pattern 'backend/store'
- 0건이면 삭제 가능

---

## 2️⃣ 조건부 삭제 후보

### updater_legacy.py
현재 closeEvent()에서 사용 중

유지 조건:
- 종료 시 설치파일 자동 실행 기능 필요

삭제 조건:
- closeEvent()에서 import 제거
- 대체 updater 구조 존재
- 검색 0건 확인

---

## 3️⃣ shim / legacy 파일

삭제 조건:
- 단순 re-export
- 새 경로에서만 import
- 검색 0건

---

## 4️⃣ 삭제 전 필수 검증

1. compile 확인
   py -m compileall src

2. 실행 확인
   poetry run python .\src\app\main.py

3. 기능 회귀 테스트 수행
   (REGRESSION_CHECKLIST.md 참고)

---

삭제는 반드시 "기능 검증 후" 수행한다.