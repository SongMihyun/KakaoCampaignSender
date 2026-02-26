# src/app/updater.py
from __future__ import annotations

import json
import os
import re
import time
import hashlib
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple


# ----------------------------
# Data
# ----------------------------
@dataclass
class UpdateInfo:
    version: str
    url: str
    sha256: str
    notes: str = ""
    published_at: str = ""


# ----------------------------
# SemVer compare (v0.1.25 형태 대응)
# ----------------------------
_semver_re = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)\s*$")


def parse_semver(v: str) -> Tuple[int, int, int]:
    m = _semver_re.match(v or "")
    if not m:
        # 파싱 불가면 0.0.0 취급 (원하면 예외로 바꿔도 됨)
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_newer(remote: str, local: str) -> bool:
    return parse_semver(remote) > parse_semver(local)


# ----------------------------
# Network
# ----------------------------
def _http_get_text(url: str, timeout: float = 7.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KakaoCampaignSender-Updater/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return raw.decode("utf-8", errors="replace")


def fetch_latest_json(latest_json_url: str, timeout: float = 7.0) -> UpdateInfo:
    txt = _http_get_text(latest_json_url, timeout=timeout)
    obj = json.loads(txt)

    # 기대 스키마:
    # { version, url, sha256, notes, published_at }
    return UpdateInfo(
        version=str(obj.get("version", "")).strip(),
        url=str(obj.get("url", "")).strip(),
        sha256=str(obj.get("sha256", "")).strip().lower(),
        notes=str(obj.get("notes", "")).strip(),
        published_at=str(obj.get("published_at", "")).strip(),
    )


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def download_installer(url: str, expected_sha256: str, timeout: float = 20.0) -> str:
    """
    설치파일을 임시폴더에 다운로드하고 sha256 검증 후 path 반환.
    검증 실패 시 예외.
    """
    tmp_dir = os.path.join(tempfile.gettempdir(), "kakao_campaign_sender_updates")
    os.makedirs(tmp_dir, exist_ok=True)

    # 파일명 추정
    filename = os.path.basename(url.split("?")[0]) or f"installer_{int(time.time())}.exe"
    dst = os.path.join(tmp_dir, filename)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "KakaoCampaignSender-Updater/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dst, "wb") as f:
        while True:
            buf = resp.read(1024 * 1024)
            if not buf:
                break
            f.write(buf)

    actual = _sha256_file(dst)
    if expected_sha256 and actual != expected_sha256.lower():
        try:
            os.remove(dst)
        except Exception:
            pass
        raise RuntimeError(f"sha256 mismatch: expected={expected_sha256} actual={actual}")

    return dst


# ----------------------------
# High-level API
# ----------------------------
@dataclass
class UpdatePlan:
    available: bool
    latest: Optional[UpdateInfo] = None
    installer_path: Optional[str] = None
    reason: str = ""


def check_and_prepare_update(latest_json_url: str, current_version: str) -> UpdatePlan:
    """
    실행 시 호출:
    - latest.json 조회
    - 버전 비교
    - 새 버전이면 설치파일 다운로드 + 해시 검증
    """
    try:
        latest = fetch_latest_json(latest_json_url)
        if not latest.version or not latest.url:
            return UpdatePlan(False, reason="latest.json invalid")

        if not is_newer(latest.version, current_version):
            return UpdatePlan(False, latest=latest, reason="up_to_date")

        installer_path = download_installer(latest.url, latest.sha256)
        return UpdatePlan(True, latest=latest, installer_path=installer_path, reason="prepared")
    except Exception as e:
        return UpdatePlan(False, reason=f"update_check_failed: {e}")



# ----------------------------
# Pending update (in-memory)
# ----------------------------
_PENDING_PLAN: Optional[UpdatePlan] = None


def set_pending_update(plan: UpdatePlan) -> None:
    global _PENDING_PLAN
    _PENDING_PLAN = plan


def get_pending_update() -> Optional[UpdatePlan]:
    return _PENDING_PLAN


def launch_installer_if_pending() -> bool:
    """
    앱 종료 직전에 호출.
    pending update가 있으면 silent 설치 실행.
    """
    try:
        plan = get_pending_update()
        if not plan or not plan.available:
            return False
        if not plan.installer_path or not os.path.exists(plan.installer_path):
            return False

        import subprocess

        installer = plan.installer_path
        args = [
            installer,
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]
        subprocess.Popen(args, close_fds=True)
        return True
    except Exception:
        return False