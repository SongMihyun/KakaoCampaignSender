# v1.0.14 Beta Release Notes

## 발송 실패 디버깅 강화

- 이미지/파일 첨부 실패 원인을 `4201` 하나로 묶지 않고 `4210~4218` 세부 코드로 분리했습니다.
- 발송 리포트 JSON에 대상자별 `debug_steps`를 저장합니다.
- 리포트 상세 화면에서 마지막 성공 단계, 실패 단계, 재시도 가능 여부, 단계별 디버그 로그를 확인할 수 있습니다.

## 추가 상태코드

- `4210 FILE_NOT_FOUND`
- `4211 FILE_DIALOG_NOT_OPENED`
- `4212 FILE_DIALOG_PATH_INPUT_FAILED`
- `4213 FILE_DIALOG_OPEN_BUTTON_FAILED`
- `4214 KAKAO_UPLOAD_NOT_STARTED`
- `4215 KAKAO_UPLOAD_TIMEOUT`
- `4216 KAKAO_WINDOW_FOCUS_LOST`
- `4217 IMAGE_PATH_CLIPBOARD_SET_FAILED`
- `4218 FILE_DIALOG_UNKNOWN_STATE`

## 발송 완료 UX

- 발송 완료 팝업에 `로그/리포트 보기` 버튼을 추가했습니다.
- 실패가 있는 경우 로그 화면의 `실패 대상 추출` 기능을 안내합니다.
