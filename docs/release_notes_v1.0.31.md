# v1.0.31 Beta Release Notes

- Ctrl+T 묶음 첨부 파일 선택창 입력 방식을 `navigate_then_names`로 변경
- 파일 선택창이 어느 폴더에서 열리더라도 먼저 `temp_attachments` 폴더로 이동한 뒤 파일명만 입력
- 일부 PC에서 `"temp_attachments" "파일명"` 입력이 `temp_attachments` 파일 검색으로 오해되던 문제 개선
- 기존 설정 파일에 남아 있는 `folder_and_names` 값을 새 기본 방식으로 자동 승격
- `FILE_DIALOG_NAVIGATE_FOLDER`, `FILE_DIALOG_NAVIGATE_FOLDER_DONE`, `FILE_DIALOG_INPUT_STRATEGY_FALLBACK` debug_steps 추가

## 기대 효과

- 파일 선택창 시작 위치가 OneDrive, 문서, 바탕화면 등으로 달라도 묶음 첨부 파일을 안정적으로 찾음
- 같은 폴더의 여러 이미지 선택 시 Windows 파일 선택창 버전별 해석 차이를 줄임
- 폴더 이동 실패 시 절대경로 입력 방식으로 fallback
