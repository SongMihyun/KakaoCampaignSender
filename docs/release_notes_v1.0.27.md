# v1.0.27 Beta Release Notes

- Windows 다중 파일 경고창의 `확인` 버튼에 포커스가 잡혔지만 클릭 동작이 실행되지 않는 PC 대응
- 경고창 감지 시 포커스된 버튼에 `Enter`를 먼저 입력하고, 실패 시 기존 `BM_CLICK`/`WM_COMMAND`/좌표 클릭을 순차 시도
- 마지막 fallback으로 `Space`와 `Enter` 재시도를 추가
- 성공한 확인 방식은 `debug_steps`의 `confirm_method`로 기록
