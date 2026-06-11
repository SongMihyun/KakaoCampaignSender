from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import (
    legacy_backup_marker_path,
    legacy_contacts_db_path,
    orphan_backups_dir,
    user_contacts_db_path,
)


@dataclass(frozen=True)
class OrphanBackup:
    backup_path: Path
    meta_path: Path
    created_at: str
    source_path: str
    source_size: int
    claimed: bool = False

    @property
    def label(self) -> str:
        return f"{self.created_at} | {self.backup_path.name}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _marker_matches(marker: dict[str, Any], source: Path, source_sha256: str) -> bool:
    if not marker.get("backup_created"):
        return False
    if marker.get("source_sha256") != source_sha256:
        return False
    backup_path = Path(str(marker.get("backup_path") or ""))
    return backup_path.exists()


def backup_legacy_db_if_needed(*, app_version: str | None = None) -> OrphanBackup | None:
    source = legacy_contacts_db_path()
    if not source.exists() or source.stat().st_size <= 0:
        return None

    source_sha256 = _sha256_file(source)
    marker_path = legacy_backup_marker_path()
    marker = _read_json(marker_path)
    if marker and _marker_matches(marker, source, source_sha256):
        backup_path = Path(str(marker["backup_path"]))
        meta_path = backup_path.with_suffix(backup_path.suffix + ".meta.json")
        meta = _read_json(meta_path) or {}
        return OrphanBackup(
            backup_path=backup_path,
            meta_path=meta_path,
            created_at=str(meta.get("created_at") or marker.get("created_at") or ""),
            source_path=str(source),
            source_size=int(marker.get("source_size") or source.stat().st_size),
            claimed=bool(meta.get("claimed")),
        )

    backup_dir = orphan_backups_dir()
    backup_path = backup_dir / f"kasender_legacy_{_timestamp()}.sqlite3"
    shutil.copy2(source, backup_path)

    meta_path = backup_path.with_suffix(backup_path.suffix + ".meta.json")
    source_stat = source.stat()
    created_at = _now_iso()
    meta = {
        "type": "legacy_single_db_orphan_backup",
        "source_path": str(source),
        "backup_path": str(backup_path),
        "created_at": created_at,
        "app_version": app_version or "",
        "source_size": source_stat.st_size,
        "source_mtime": source_stat.st_mtime,
        "source_sha256": source_sha256,
        "claimed": False,
        "claimed_by_user_uuid": None,
        "claimed_at": None,
    }
    _write_json(meta_path, meta)
    _write_json(
        marker_path,
        {
            "legacy_db_detected": True,
            "backup_created": True,
            "backup_path": str(backup_path),
            "created_at": created_at,
            "app_version": app_version or "",
            "source_size": source_stat.st_size,
            "source_mtime": source_stat.st_mtime,
            "source_sha256": source_sha256,
        },
    )

    return OrphanBackup(
        backup_path=backup_path,
        meta_path=meta_path,
        created_at=created_at,
        source_path=str(source),
        source_size=source_stat.st_size,
    )


def list_unclaimed_orphan_backups() -> list[OrphanBackup]:
    backups: list[OrphanBackup] = []
    for meta_path in orphan_backups_dir().glob("*.meta.json"):
        meta = _read_json(meta_path) or {}
        if meta.get("claimed"):
            continue
        backup_path = Path(str(meta.get("backup_path") or ""))
        if not backup_path.exists():
            backup_path = Path(str(meta_path).removesuffix(".meta.json"))
        if not backup_path.exists():
            continue
        backups.append(
            OrphanBackup(
                backup_path=backup_path,
                meta_path=meta_path,
                created_at=str(meta.get("created_at") or ""),
                source_path=str(meta.get("source_path") or ""),
                source_size=int(meta.get("source_size") or backup_path.stat().st_size),
                claimed=False,
            )
        )
    return sorted(backups, key=lambda item: item.created_at, reverse=True)


def _table_row_count(conn: sqlite3.Connection, table: str) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (table,),
    ).fetchone()
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0])


def is_user_db_empty(db_path: Path) -> bool:
    if not db_path.exists() or db_path.stat().st_size <= 0:
        return True
    conn = sqlite3.connect(db_path)
    try:
        for table in ("contacts", "groups", "campaigns", "send_lists", "send_logs"):
            if _table_row_count(conn, table) > 0:
                return False
        return True
    finally:
        conn.close()


def _validate_sqlite_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check;").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {result[0] if result else 'no result'}")
    finally:
        conn.close()


def claim_orphan_backup_for_user(backup: OrphanBackup, *, user_uuid: str) -> Path:
    target = user_contacts_db_path(user_uuid)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not is_user_db_empty(target):
        raise RuntimeError("현재 로그인 계정의 DB가 비어 있지 않아 백업을 가져올 수 없습니다.")

    _validate_sqlite_db(backup.backup_path)
    if target.exists():
        target.unlink()
    shutil.copy2(backup.backup_path, target)
    _validate_sqlite_db(target)

    claimed_dir = orphan_backups_dir() / "claimed"
    claimed_dir.mkdir(parents=True, exist_ok=True)
    claimed_at = _now_iso()
    meta = _read_json(backup.meta_path) or {}
    meta.update(
        {
            "claimed": True,
            "claimed_by_user_uuid": user_uuid,
            "claimed_at": claimed_at,
            "restored_to": str(target),
        }
    )
    _write_json(backup.meta_path, meta)

    claimed_backup_path = claimed_dir / backup.backup_path.name
    claimed_meta_path = claimed_dir / backup.meta_path.name
    if claimed_backup_path.exists():
        claimed_backup_path = claimed_dir / f"{backup.backup_path.stem}_{_timestamp()}{backup.backup_path.suffix}"
    if claimed_meta_path.exists():
        claimed_meta_path = claimed_dir / f"{backup.meta_path.stem}_{_timestamp()}{backup.meta_path.suffix}"
    shutil.move(str(backup.backup_path), str(claimed_backup_path))
    shutil.move(str(backup.meta_path), str(claimed_meta_path))
    return target
