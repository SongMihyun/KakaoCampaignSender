# v1.0.34 Beta Release Notes

- Ctrl+T 묶음 첨부 후 카카오톡 `N개 전송` 버튼 fallback 조건 완화
- 파일 선택 직후 foreground가 제목 없는 작은 `EVA_Window_Dblclk` 창이면 파일 전송창으로 인정
- UIA 텍스트에서 `파일 전송` / `N개 전송` 문구가 수집되지 않는 PC에서도 하단 전송 버튼 영역 직접 클릭
- fallback 진단값에 `assumed_textless_small_eva` 기록

## 개선 대상

- 화면에는 `2개 전송` 버튼이 보이지만 리포트에는 `KAKAO_FILE_TRANSFER_DIALOG_NOT_FOUND`로 기록되는 환경
- 카카오톡 파일 전송 패널의 UIA 텍스트가 비어 있어 버튼 탐지가 실패하는 PC
