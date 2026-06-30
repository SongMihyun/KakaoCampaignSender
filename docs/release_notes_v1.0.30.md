# v1.0.30 Beta Release Notes

- 카카오톡 `파일 전송` 창의 `N개 전송` 버튼 클릭 안정화
- 버튼 클릭 호출 성공 여부가 아니라 전송창/버튼이 실제로 사라졌는지를 기준으로 클릭 성공 판정
- `invoke`, `click_input`, 좌표 클릭, 포커스 후 `Enter`, 포커스 후 `Space`, 기존 UIA 클릭 순서로 재시도
- `debug_steps`에 `KAKAO_FILE_TRANSFER_SEND_BUTTON_FOUND`, `KAKAO_FILE_TRANSFER_SEND_BUTTON_CLICKED`, `click_method` 기록
- 전송 버튼이 눌리지 않아 다음 대상 창이 계속 쌓이는 문제 개선
