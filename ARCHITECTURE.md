# ARCHITECTURE.md

## 1. 전체 구조

src/
 ├── backend/
 │    ├── core/
 │    ├── database/
 │    ├── domains/
 │    ├── integrations/
 │    ├── stores/
 │    └── updates/
 │
 └── frontend/
      ├── app/
      ├── layout/
      ├── dialogs/
      ├── pages/
      └── utils/

---

## 2. 레이어 책임

### Repository
- DB 접근 전담
- CRUD
- SQL, schema 의존

### Service
- Business logic
- Validation
- Orchestration
- Repository 호출

### Store
- In-memory cache
- UI 성능 최적화
- DB 직접 접근 없음

### Page (UI)
- 렌더링
- 이벤트 처리
- Service 호출
- Repository 직접 호출 금지

---

## 3. Sending 흐름

SendPage
  ↓
SendingService
  ↓
SendJobBuilder
  ↓
Resolver
  ↓
Executor / Worker
  ↓
SendLogsRepo
  ↓
ReportWriter

UI는 orchestration을 몰라야 한다.
모든 비즈니스 흐름은 backend에서 처리한다.

---

## 4. Logs / Reports 흐름

LogsPage
  ↓
LogsService
  ↓
SendReportReader
  ↓
DTO / Model 변환

JSON flattening은 UI에서 수행하지 않는다.

---

## 5. MainWindow 책임

- Repository 생성
- Service 조립
- Page 주입
- 전역 이벤트 연결
- 구조적 의존만 관리

비즈니스 로직 없음

---

## 6. 최종 목표 구조

UI는 service만 의존
Service는 repository만 의존
Repository는 DB만 의존

frontend ↔ backend는 service 계층으로만 연결