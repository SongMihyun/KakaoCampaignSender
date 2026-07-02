# v1.0.37 Beta Release Notes

- send_report 최상단에 `app_version`과 `report_schema` 필드 추가
- Ctrl+T 묶음 첨부 임시 복사 단계에 `ATTACHMENT_TEMP_COPY_STRATEGY` debug_steps 추가
- 새 파일 선택창 안정화 로직이 실제 실행 중인지 리포트만으로 판별 가능하도록 개선
- v1.0.36의 발송 1회별 `batch_...` 폴더와 `a001.png` 짧은 파일명 복사 방식 유지

## 확인 방법

다음 테스트 리포트에서 아래 항목이 보여야 새 버전이 실제로 실행된 것입니다.

```json
"app_version": "1.0.37"
```

```text
ATTACHMENT_TEMP_COPY_STRATEGY
strategy: short_per_send_batch_v1
planned_temp_names: a001.png, a002.png ...
```

위 항목 없이 `attach_YYYYMMDD_HHMMSS_001_hash.png` 긴 파일명이 보이면 이전 설치본이 실행 중인 상태입니다.
