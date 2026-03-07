from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.paths import user_data_dir


def schedule_delete_all_local_data() -> Path:
    """
    ✅ 앱 종료 후 AppData\\<APP_NAME> 폴더를 강제 삭제(리트라이 포함)
    - 삭제 성공/실패 로그를 %TEMP%에 남김
    """
    target_dir = user_data_dir()
    target = str(target_dir)

    temp_dir = Path(tempfile.gettempdir())
    log_file = temp_dir / f"{target_dir.name}_wipe.log"

    # PowerShell: 2초 대기 후 0.5초 간격으로 20회 삭제 시도
    # - Force + Recurse
    # - ErrorAction Stop으로 예외 잡고 재시도
    ps = rf"""
$ErrorActionPreference = "Stop"
$target = "{target}"
$log = "{str(log_file)}"

"START  " + (Get-Date).ToString("s") + " target=" + $target | Out-File -FilePath $log -Encoding utf8 -Append

Start-Sleep -Seconds 2

for ($i=1; $i -le 20; $i++) {{
    try {{
        if (Test-Path -LiteralPath $target) {{
            Remove-Item -LiteralPath $target -Recurse -Force
        }}
        "OK     " + (Get-Date).ToString("s") + " try=" + $i | Out-File -FilePath $log -Encoding utf8 -Append
        break
    }} catch {{
        "RETRY  " + (Get-Date).ToString("s") + " try=" + $i + " err=" + $_.Exception.Message | Out-File -FilePath $log -Encoding utf8 -Append
        Start-Sleep -Milliseconds 500
    }}
}}

if (Test-Path -LiteralPath $target) {{
    "FAIL   " + (Get-Date).ToString("s") + " still_exists" | Out-File -FilePath $log -Encoding utf8 -Append
}} else {{
    "DONE   " + (Get-Date).ToString("s") | Out-File -FilePath $log -Encoding utf8 -Append
}}
"""

    # PowerShell을 완전 분리(detached) 실행
    # -WindowStyle Hidden 으로 창 안 뜨게
    creationflags = 0x08000000  # CREATE_NO_WINDOW
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            ps,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )

    # 로그 파일 경로를 반환(문제 시 확인용)
    return log_file
