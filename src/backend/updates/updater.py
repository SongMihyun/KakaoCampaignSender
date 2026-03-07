# FILE: src/backend/updates/updater.py
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from app.version import __version__, __app_name__


def _version_tuple(v: str) -> tuple[int, int, int]:
    v = (v or "").strip().lstrip("v").strip()
    parts = v.split(".")
    nums = []
    for i in range(3):
        try:
            nums.append(int(parts[i]))
        except Exception:
            nums.append(0)
    return tuple(nums)  # type: ignore[return-value]


def is_newer(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class LatestManifest:
    version: str
    url: str
    sha256: str
    notes: str = ""
    published_at: str = ""


class DownloadCancelled(RuntimeError):
    pass


class Updater:
    """
    온라인 업데이트 전담.

    기존 역할:
    - 최신 manifest 조회
    - 설치파일 다운로드
    - 해시 검증
    - silent install 실행

    추가 역할:
    - 종료 후 설치가 필요할 때 pending installer marker 기록
    """

    def __init__(self, latest_json_url: str, *, timeout_sec: float = 5.0) -> None:
        self._latest_json_url = latest_json_url
        self._timeout_sec = float(timeout_sec)

    def fetch_latest_manifest(self) -> Optional[LatestManifest]:
        try:
            r = requests.get(
                self._latest_json_url,
                timeout=self._timeout_sec,
                headers={"User-Agent": __app_name__},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            return LatestManifest(
                version=str(data.get("version", "")).strip(),
                url=str(data.get("url", "")).strip(),
                sha256=str(data.get("sha256", "")).strip().lower(),
                notes=str(data.get("notes", "") or ""),
                published_at=str(data.get("published_at", "") or ""),
            )
        except Exception:
            return None

    def needs_update(self, manifest: LatestManifest) -> bool:
        if not manifest.version or not manifest.url:
            return False
        return is_newer(manifest.version, __version__)

    def download_installer(
        self,
        url: str,
        *,
        on_progress=None,  # callable(downloaded:int,total:int)->None
        cancel_flag=None,  # callable()->bool
    ) -> str:
        tmp = tempfile.gettempdir()
        filename = os.path.basename(url.split("?")[0]) or "setup.exe"
        dest = os.path.join(tmp, filename)

        with requests.get(url, stream=True, timeout=20, headers={"User-Agent": __app_name__}) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            downloaded = 0

            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if cancel_flag and bool(cancel_flag()):
                        raise DownloadCancelled("user cancelled")
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total)

        return dest

    def verify_sha256(self, path: str, want_sha256: str) -> bool:
        if not want_sha256:
            return True
        got = sha256_file(path).lower()
        return got == want_sha256.lower().strip()

    def run_silent_install(self, installer_path: str) -> None:
        args = [
            installer_path,
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
        ]
        subprocess.Popen(args, close_fds=True)

    def mark_installer_for_after_close(self, installer_path: str) -> Path:
        """
        앱이 실행 중이라 즉시 설치 대신 '종료 후 설치'가 필요한 경우 사용.
        marker 파일을 남기고, 실제 실행은 finalize_update_on_app_close()가 담당한다.
        """
        return write_pending_installer_marker(installer_path)


def _pending_marker_path(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir) if base_dir else Path(sys.executable).resolve().parent
    return root / "pending_installer.json"


def write_pending_installer_marker(installer_path: str, *, base_dir: Optional[Path] = None) -> Path:
    """
    종료 후 실행할 installer 경로를 marker 파일로 기록한다.
    """
    marker = _pending_marker_path(base_dir)
    payload = {
        "installer_path": str(Path(installer_path).resolve()),
    }
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker


def read_pending_installer_marker(*, base_dir: Optional[Path] = None) -> Optional[Path]:
    """
    pending_installer.json을 읽어 installer 경로를 반환한다.
    """
    marker = _pending_marker_path(base_dir)
    try:
        if not marker.exists():
            return None

        data = json.loads(marker.read_text(encoding="utf-8"))
        raw = str(data.get("installer_path", "") or "").strip()
        if not raw:
            return None

        path = Path(raw)
        if not path.is_absolute():
            root = Path(base_dir) if base_dir else Path(sys.executable).resolve().parent
            path = (root / path).resolve()

        if not path.exists() or not path.is_file():
            return None

        return path
    except Exception:
        return None


def clear_pending_installer_marker(*, base_dir: Optional[Path] = None) -> None:
    marker = _pending_marker_path(base_dir)
    try:
        marker.unlink(missing_ok=True)
    except Exception:
        pass


def finalize_update_on_app_close(*, base_dir: Optional[Path] = None) -> bool:
    """
    앱 종료 시 호출되는 최종 업데이트 후처리 진입점.

    동작:
    1. pending installer marker 확인
    2. 있으면 silent install 실행
    3. 실행 시도 후 marker 제거

    반환:
    - 실행 시도 성공: True
    - 실행 대상 없음 / 실패: False
    """
    installer = read_pending_installer_marker(base_dir=base_dir)
    if installer is None:
        return False

    args = [
        str(installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
    ]

    try:
        subprocess.Popen(args, close_fds=True)
        clear_pending_installer_marker(base_dir=base_dir)
        return True
    except Exception:
        return False