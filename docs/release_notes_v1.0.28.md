# v1.0.28 Beta Release Notes

- Windows 다중 파일 경고창의 `확인` 버튼이 포커스만 잡히고 눌리지 않는 PC 대응 강화
- 확인 버튼 HWND에 직접 `Return`/`Space` 키 메시지를 전송
- 확인 버튼 HWND에 직접 마우스 down/up 메시지를 전송
- UI Automation invoke/click fallback을 경고창 확인 버튼에도 적용
- 기존 절대경로 입력과 다중 경고창 자동 확인 흐름은 유지
