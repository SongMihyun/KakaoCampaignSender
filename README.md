src/
├─ app/
│  ├─ data/
│  │  ├─ contacts_repo.py
│  │  ├─ groups_repo.py
│  │  └─ campaigns_repo.py
│  └─ io/
│     └─ contacts_excel.py        # ✅ import/export/template 통합
└─ ui/
   ├─ pages/
   │  ├─ contacts_page.py         # ✅ 엑셀 I/O 비동기 처리
   │  ├─ groups_page.py           # ✅ 검색/로드 디바운스 + 비동기
   │  └─ campaign_page.py         # ✅ 이미지 읽기 비동기(다중 파일)
   └─ utils/
      └─ async_job.py             # ✅ 공용 비동기 실행 유틸




src/app/sender/
  ├─ kakao_pc_driver.py              # 드라이버(오케스트레이션)
  ├─ kakao_pc_hooks.py               # 채팅 열기/이미지 다이얼로그 hook
  ├─ kakao_dialog_send.py            # 이미지 전송 다이얼로그 처리(클릭+엔터)
  ├─ win32_core.py                   # Win32 공통(포커스/윈도우/클립보드)
  ├─ speed_profiles.py               # SpeedProfile/Timings
  ├─ trace_logger.py                 # trace/log 설정(중복 제거)
  ├─ image_attach_cache.py           # temp png 파일 캐시(기존 유지, 약간 정리)
  ├─ image_attach_ctrl_t.py          # Ctrl+T attach 전송(캐시 사용)
  └─ image_dib_cache.py              # PNG->DIB 메모리 캐시(신규)



사용법 (핵심)
1) “버전만” 입력해서 자동 Push + Tag
.\release.ps1 -Version 0.1.16
2) “로컬 빌드까지” 같이 하고 Push + Tag
.\release.ps1 -Version 0.1.16 -BuildLocal
3) dist/build 삭제 없이 빌드만 스킵하고 싶으면
.\release.ps1 -Version 0.1.16 -BuildLocal -NoClean


기본(요청하신 3줄과 동일 동작)
.\build_exe.ps1
dist/build 삭제 없이 빌드만(테스트용)
.\build_exe.ps1 -NoClean
spec/출력 경로 바꾸고 싶을 때
.\build_exe.ps1 -Spec "KakaoSender.spec" -DistPath "dist/app"