# v1.0.39 Beta - 카카오톡 업로드 완료 대기 안정화

## 변경 사항

- Ctrl+T 묶음 첨부에서 `N개 전송` 버튼 클릭 후 고정 시간 대기 대신 카카오톡 업로드 상태가 끝날 때까지 확인하도록 개선
- 카카오톡 파일 전송창, 전송 버튼, 업로드 진행 텍스트가 사라진 뒤 안정 구간을 확인하고 다음 로직으로 진행
- 첨부 개수와 전체 파일 크기를 기준으로 업로드 완료 대기 timeout을 동적으로 계산
- 업로드가 끝나기 전에 채팅창 닫기 시도가 발생하면 `전송 중인 파일` 팝업에서 확인을 누르지 않고 취소 후 대기
- 업로드 완료 대기 실패 시 `KAKAO_UPLOAD_TIMEOUT`으로 분류되도록 리포트 원인 분류 보강
- debug_steps에 `KAKAO_UPLOAD_COMPLETE_WAIT`, `KAKAO_UPLOAD_COMPLETED`, `KAKAO_UPLOAD_TIMEOUT` 기록 추가

## 검증

- `python -m compileall packages/kakao_pc_driver/src src packages`
- `git diff --check`

## 참고

- 앱 기능/CRM/인증/쿠폰/홈페이지 코드는 변경하지 않음
- 실제 카카오톡 PC 업로드 속도는 환경과 카카오톡 버전에 따라 달라질 수 있으므로, 이번 버전은 고정 sleep 대신 업로드 완료 상태를 기준으로 다음 대상 발송을 시작함
