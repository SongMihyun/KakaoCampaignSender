# v1.0.32 Beta Release Notes

- Ctrl+T 묶음 첨부에서 파일명 텍스트 입력보다 파일 목록 직접 선택을 우선 수행
- `temp_attachments` 폴더 이동 후 `F5` 새로고침을 수행해 방금 복사된 첨부 파일 목록 반영 보강
- 파일 선택창 목록의 이미지 항목을 UIA/좌표 클릭으로 다중 선택한 뒤 `열기` 실행
- 확장자가 숨겨진 Windows 파일 탐색기에서도 파일명 stem 기준으로 대상 파일을 매칭
- `FILE_DIALOG_LIST_SELECT_ATTEMPT`, `FILE_DIALOG_LIST_SELECT_ITEM`, `FILE_DIALOG_LIST_SELECT_SUBMIT` debug_steps 추가

## 개선 대상

- 여러 파일명을 `"a.jpg" "b.jpg" "c.jpg"` 형태로 입력했을 때 `파일 이름이 올바르지 않습니다` 오류가 뜨는 PC
- 파일 선택창은 `temp_attachments`까지 이동하지만 텍스트 기반 다중 파일 선택이 막히는 Windows 환경
