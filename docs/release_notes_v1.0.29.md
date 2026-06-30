# v1.0.29 Beta Release Notes

- Ctrl+T 묶음 첨부 입력 방식을 PC별 설정값으로 고정할 수 있도록 추가
- 기본 입력 방식을 Windows 다중 선택 표준 형식인 `"폴더경로" "파일1" "파일2"`로 변경
- `settings.json`의 `kakao_ctrl_t_multi_attach_input_mode` 값으로 `folder_and_names`, `absolute_paths`, `same_folder_names` 선택 가능
- 리포트 `debug_steps`에 `FILE_DIALOG_PC_INPUT_MODE`와 실제 `dialog_input_mode` 기록
- 기존 경고창 자동 확인 fallback은 유지
