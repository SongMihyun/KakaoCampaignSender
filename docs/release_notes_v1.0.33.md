# v1.0.33 Beta Release Notes

- Ctrl+T 묶음 첨부 후 카카오톡 `파일 전송` 창 탐지 강화
- 제목이 비어 있는 `EVA_Window_Dblclk` 파일 전송 패널도 후보로 인식
- `N개 전송` 버튼 UIA 탐지 실패 시 전송창 하단 버튼 영역을 직접 좌표 클릭
- 버튼 객체를 찾은 경우에도 닫힘 확인 실패 시 전송창 하단 영역 클릭 fallback 수행
- `KAKAO_FILE_TRANSFER_DIALOG_DETECTED` fallback 진단 정보 보강

## 개선 대상

- 파일 선택창은 닫히고 카카오톡 `파일 전송` 창은 떠 있지만 `N개 전송` 버튼이 눌리지 않는 PC
- 화면에는 `3개 전송` 버튼이 보이는데 리포트에는 `KAKAO_FILE_TRANSFER_DIALOG_NOT_FOUND`로 기록되는 환경
