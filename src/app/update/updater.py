# src/app/update/updater.py
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import requests

from app.version import __version__, __app_name__


def _version_tuple(v: str) -> tuple[int, int, int]:
    v = (v or "").strip().lstrip("v").strip()
    parts = v.split(".")
    # 1.2.3 형태 가정. 부족하면 0 채움
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
            # 운영에서는 sha256 필수 권장. 우선은 빈 값이면 통과 처리.
            return True
        got = sha256_file(path).lower()
        return got == want_sha256.lower().strip()

    def run_silent_install(self, installer_path: str) -> None:
        # Inno Setup silent 옵션 (표준)
        args = [
            installer_path,
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
        ]
        # 설치 끝나면 앱 재실행을 원하는 경우:
        # Inno script에 "Run" 섹션으로 실행해도 되고,
        # 여기서 설치 후 별도 재실행도 가능.
        subprocess.Popen(args, close_fds=True)
