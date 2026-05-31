from __future__ import annotations

import hashlib
import hmac
import os
import platform
import sqlite3
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.paths import contacts_db_path, user_data_dir
from backend.core.app_settings import get_setting

MAGIC = b"KCSBAK1\n"


@dataclass(frozen=True)
class BackupResult:
    path: Path
    mode: str
    removed: int = 0


def backups_dir() -> Path:
    path = user_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _machine_secret() -> bytes:
    raw = "|".join(
        [
            os.environ.get("USERNAME", ""),
            os.environ.get("USERDOMAIN", ""),
            platform.node(),
            str(user_data_dir()),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).digest()


def _xor_stream(data: bytes, key: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hashlib.sha256(key + counter.to_bytes(8, "little")).digest()
        out.extend(block)
        counter += 1
    return bytes(b ^ k for b, k in zip(data, out))


def _encrypt_bytes(data: bytes) -> bytes:
    key = _machine_secret()
    compressed = zlib.compress(data, level=9)
    cipher = _xor_stream(compressed, key)
    sig = hmac.new(key, cipher, hashlib.sha256).digest()
    return MAGIC + sig + cipher


def create_db_backup(reason: str = "manual", *, mode: str | None = None) -> BackupResult | None:
    db_path = contacts_db_path()
    if not db_path.exists():
        return None

    actual_mode = (mode or str(get_setting("pc_environment", "public"))).strip().lower()
    if actual_mode not in ("personal", "public"):
        actual_mode = "public"

    tmp_snapshot = backups_dir() / "_snapshot.sqlite3"
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(tmp_snapshot))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

        encrypted = _encrypt_bytes(tmp_snapshot.read_bytes())
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = backups_dir() / f"contacts_{ts}_{reason}.ksbak"
        out.write_bytes(encrypted)
    finally:
        try:
            tmp_snapshot.unlink(missing_ok=True)
        except Exception:
            pass

    keep = 7 if actual_mode == "personal" else 1
    removed = prune_backups(keep=keep)
    return BackupResult(path=out, mode=actual_mode, removed=removed)


def prune_backups(*, keep: int) -> int:
    files = sorted(backups_dir().glob("*.ksbak"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for path in files[max(0, int(keep)):]:
        try:
            path.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def delete_backups() -> int:
    count = 0
    for path in backups_dir().glob("*.ksbak"):
        try:
            path.unlink()
            count += 1
        except Exception:
            pass
    return count
