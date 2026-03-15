# FILE: src/backend/core/lifecycle/apply_settings_bundle.py
from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Sequence

from app.paths import contacts_db_path, user_data_dir


CREATE_NO_WINDOW = 0x08000000


def _ps_quote(text: str) -> str:
    return str(text).replace("`", "``").replace('"', '`"')


def _ps_array(values: Sequence[str]) -> str:
    return "@(" + ", ".join(f'"{_ps_quote(v)}"' for v in values) + ")"


def schedule_apply_settings_bundle_after_exit(
    *,
    bundle_path: str | Path,
    wait_pid: int,
    relaunch_executable: str,
    relaunch_args: Sequence[str],
) -> Path:
    """
    현재 앱 프로세스가 완전히 종료된 뒤 설정 번들을 오프라인으로 적용하고,
    적용 완료 후 앱을 재실행하도록 별도 PowerShell 프로세스를 예약한다.
    """
    src_bundle = Path(bundle_path).resolve()
    if not src_bundle.exists() or not src_bundle.is_file():
        raise FileNotFoundError(f"설정 번들 파일을 찾을 수 없습니다: {src_bundle}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = Path(tempfile.gettempdir())
    staged_bundle = temp_dir / f"kcsbundle_stage_{ts}.zip"
    log_file = temp_dir / f"kcsbundle_apply_{ts}.log"
    extract_root = temp_dir / f"kcsbundle_extract_{ts}"
    backup_root = temp_dir / f"kcsbundle_backup_{ts}"

    shutil.copy2(src_bundle, staged_bundle)

    base_dir = user_data_dir().resolve()
    db_path = contacts_db_path().resolve()

    ps = rf'''
$ErrorActionPreference = "Stop"

$waitPid = {int(wait_pid)}
$bundle = "{_ps_quote(str(staged_bundle))}"
$log = "{_ps_quote(str(log_file))}"
$extract = "{_ps_quote(str(extract_root))}"
$backup = "{_ps_quote(str(backup_root))}"
$base = "{_ps_quote(str(base_dir))}"
$db = "{_ps_quote(str(db_path))}"
$assetsDir = Join-Path $base "campaign_assets"
$reportsDir = Join-Path $base "Reports"
$logsDir = Join-Path $base "logs"
$exe = "{_ps_quote(str(relaunch_executable))}"
$args = {_ps_array(list(relaunch_args))}

function Write-Log([string]$message) {{
    ((Get-Date).ToString("s") + " | " + $message) | Out-File -FilePath $log -Encoding utf8 -Append
}}

function Remove-PathSafe([string]$path) {{
    if (Test-Path -LiteralPath $path) {{
        Remove-Item -LiteralPath $path -Recurse -Force
    }}
}}

function Replace-FileWithRetry([string]$src, [string]$dst) {{
    if (!(Test-Path -LiteralPath $src)) {{
        throw "복원할 파일이 없습니다: $src"
    }}

    $dstDir = Split-Path -Parent $dst
    if ($dstDir -and !(Test-Path -LiteralPath $dstDir)) {{
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    }}

    $incoming = "$dst.incoming"
    if (Test-Path -LiteralPath $incoming) {{
        Remove-Item -LiteralPath $incoming -Force
    }}
    Copy-Item -LiteralPath $src -Destination $incoming -Force

    for ($i = 1; $i -le 40; $i++) {{
        try {{
            if (Test-Path -LiteralPath $dst) {{
                Remove-Item -LiteralPath $dst -Force
            }}
            Move-Item -LiteralPath $incoming -Destination $dst -Force
            return
        }} catch {{
            if ($i -ge 40) {{
                throw
            }}
            Start-Sleep -Milliseconds 500
        }}
    }}
}}

function Replace-Dir([string]$src, [string]$dst) {{
    if (Test-Path -LiteralPath $dst) {{
        Remove-Item -LiteralPath $dst -Recurse -Force
    }}
    if (Test-Path -LiteralPath $src) {{
        Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
    }}
}}

function Restore-FileIfExists([string]$backupFile, [string]$dst) {{
    if (!(Test-Path -LiteralPath $backupFile)) {{
        return
    }}
    if (Test-Path -LiteralPath $dst) {{
        Remove-Item -LiteralPath $dst -Force
    }}
    Copy-Item -LiteralPath $backupFile -Destination $dst -Force
}}

function Restore-DirIfExists([string]$backupDir, [string]$dst) {{
    if (Test-Path -LiteralPath $dst) {{
        Remove-Item -LiteralPath $dst -Recurse -Force
    }}
    if (Test-Path -LiteralPath $backupDir) {{
        Copy-Item -LiteralPath $backupDir -Destination $dst -Recurse -Force
    }}
}}

Write-Log "START bundle=$bundle"

for ($i = 1; $i -le 120; $i++) {{
    try {{
        $null = Get-Process -Id $waitPid -ErrorAction Stop
        Write-Log "WAIT process_alive try=$i pid=$waitPid"
        Start-Sleep -Milliseconds 500
    }} catch {{
        Write-Log "WAIT process_closed pid=$waitPid"
        break
    }}
}}

Start-Sleep -Seconds 1

try {{
    Remove-PathSafe $extract
    Remove-PathSafe $backup
    New-Item -ItemType Directory -Path $extract -Force | Out-Null
    New-Item -ItemType Directory -Path $backup -Force | Out-Null

    Expand-Archive -LiteralPath $bundle -DestinationPath $extract -Force

    $manifest = Join-Path $extract "manifest.json"
    $incomingDb = Join-Path $extract "data\contacts.sqlite3"
    $incomingAssets = Join-Path $extract "data\campaign_assets"
    $incomingReports = Join-Path $extract "data\Reports"
    $incomingLogs = Join-Path $extract "data\logs"

    if (!(Test-Path -LiteralPath $manifest)) {{
        throw "설정 번들 manifest.json이 없습니다."
    }}
    if (!(Test-Path -LiteralPath $incomingDb)) {{
        throw "설정 번들 DB(data\\contacts.sqlite3)가 없습니다."
    }}

    $backupDb = Join-Path $backup "contacts.sqlite3"
    $backupAssets = Join-Path $backup "campaign_assets"
    $backupReports = Join-Path $backup "Reports"
    $backupLogs = Join-Path $backup "logs"

    if (Test-Path -LiteralPath $db) {{
        Copy-Item -LiteralPath $db -Destination $backupDb -Force
    }}
    if (Test-Path -LiteralPath $assetsDir) {{
        Copy-Item -LiteralPath $assetsDir -Destination $backupAssets -Recurse -Force
    }}
    if (Test-Path -LiteralPath $reportsDir) {{
        Copy-Item -LiteralPath $reportsDir -Destination $backupReports -Recurse -Force
    }}
    if (Test-Path -LiteralPath $logsDir) {{
        Copy-Item -LiteralPath $logsDir -Destination $backupLogs -Recurse -Force
    }}

    try {{
        Replace-FileWithRetry $incomingDb $db
        Replace-Dir $incomingAssets $assetsDir
        Replace-Dir $incomingReports $reportsDir
        Replace-Dir $incomingLogs $logsDir
        Write-Log "APPLY done"
    }} catch {{
        Write-Log ("APPLY failed, restoring backup: " + $_.Exception.Message)
        Restore-FileIfExists $backupDb $db
        Restore-DirIfExists $backupAssets $assetsDir
        Restore-DirIfExists $backupReports $reportsDir
        Restore-DirIfExists $backupLogs $logsDir
        throw
    }}

    Start-Sleep -Milliseconds 700
    Write-Log "RELAUNCH start"
    Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory (Split-Path -Parent $exe)
    Write-Log "DONE"
}} catch {{
    Write-Log ("FAIL " + $_.Exception.Message)
}}
'''

    subprocess.Popen(
        [
            'powershell.exe',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-WindowStyle',
            'Hidden',
            '-Command',
            ps,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )

    return log_file
