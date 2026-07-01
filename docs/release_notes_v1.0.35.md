# v1.0.35 Beta Release Notes

- Ctrl+T 묶음 첨부 파일 선택 속도 개선
- `temp_attachments` 폴더 이동 후 파일 목록 선택보다 파일 이름 입력칸 직접 입력을 우선 수행
- 파일 이름 입력칸에 `"파일1" "파일2"` 형식으로 넣고 `열기` 실행
- 파일 이름 입력 실패 시 Windows 오류 팝업을 자동 확인한 뒤 기존 파일 목록 선택 fallback 수행
- `FILE_DIALOG_FILENAME_EDIT_FASTPATH`, `FILE_DIALOG_ERROR_POPUP_DETECTED`, `FILE_DIALOG_ERROR_POPUP_DISMISSED` debug_steps 추가

## 개선 대상

- `temp_attachments` 폴더에 파일이 많아 썸네일/목록 로딩이 느린 PC
- 파일 선택창에서 이미지 목록을 직접 선택하는 동안 업로드 단계가 늦어지는 환경
