# FILE: src/backend/domains/settings_bundle/service.py
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.paths import contacts_db_path, user_data_dir
from backend.database.db_bootstrap import ensure_db_initialized


@dataclass(slots=True)
class SettingsBundleInfo:
    bundle_path: str
    bundle_version: int
    exported_at: str
    contacts_count: int
    groups_count: int
    campaigns_count: int
    send_lists_count: int
    has_campaign_assets: bool
    has_reports: bool
    has_logs: bool


class SettingsBundleService:
    """
    연락처/그룹/캠페인/발송리스트를 포함한 로컬 운영 데이터를
    단일 번들(.kcsbundle / zip)로 내보내고 검증한다.

    실제 가져오기 적용은 Windows 파일 잠금 이슈를 피하기 위해
    앱 종료 후 오프라인 단계에서 처리한다.
    """

    BUNDLE_VERSION = 1
    MANIFEST_PATH = "manifest.json"
    DB_ENTRY = "data/contacts.sqlite3"
    CAMPAIGN_ASSETS_DIR = "data/campaign_assets"
    REPORTS_DIR = "data/Reports"
    LOGS_DIR = "data/logs"
    REQUIRED_TABLES = (
        "contacts",
        "groups",
        "group_members",
        "campaigns",
        "campaign_items",
        "send_lists",
    )

    def __init__(self) -> None:
        self.base_dir = user_data_dir()
        self.db_path = contacts_db_path()
        self.campaign_assets_dir = self.base_dir / "campaign_assets"
        self.reports_dir = self.base_dir / "Reports"
        self.logs_dir = self.base_dir / "logs"

    def export_bundle(self, output_path: str | Path) -> SettingsBundleInfo:
        ensure_db_initialized()

        out_path = self._normalize_output_path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        counts = self._read_db_counts(self.db_path)
        has_campaign_assets = self._dir_has_files(self.campaign_assets_dir)
        has_reports = self._dir_has_files(self.reports_dir)
        has_logs = self._dir_has_files(self.logs_dir)
        exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        manifest = {
            "bundle_version": self.BUNDLE_VERSION,
            "exported_at": exported_at,
            "app_name": "kakao_campaign_sender",
            "db_entry": self.DB_ENTRY,
            "campaign_assets_dir": self.CAMPAIGN_ASSETS_DIR,
            "reports_dir": self.REPORTS_DIR,
            "logs_dir": self.LOGS_DIR,
            "counts": counts,
            "has_campaign_assets": has_campaign_assets,
            "has_reports": has_reports,
            "has_logs": has_logs,
        }

        tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
        if tmp_out.exists():
            tmp_out.unlink()

        snapshot_db = self._create_db_snapshot(self.db_path)
        try:
            with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    self.MANIFEST_PATH,
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
                zf.write(snapshot_db, self.DB_ENTRY)
                self._write_dir_to_zip(zf, self.campaign_assets_dir, self.CAMPAIGN_ASSETS_DIR)
                self._write_dir_to_zip(zf, self.reports_dir, self.REPORTS_DIR)
                self._write_dir_to_zip(zf, self.logs_dir, self.LOGS_DIR)
        finally:
            try:
                snapshot_db.unlink(missing_ok=True)
            except Exception:
                pass

        if out_path.exists():
            out_path.unlink()
        tmp_out.replace(out_path)

        return SettingsBundleInfo(
            bundle_path=str(out_path),
            bundle_version=int(self.BUNDLE_VERSION),
            exported_at=exported_at,
            contacts_count=int(counts["contacts"]),
            groups_count=int(counts["groups"]),
            campaigns_count=int(counts["campaigns"]),
            send_lists_count=int(counts["send_lists"]),
            has_campaign_assets=has_campaign_assets,
            has_reports=has_reports,
            has_logs=has_logs,
        )

    def inspect_bundle(self, bundle_path: str | Path) -> SettingsBundleInfo:
        bundle_path = Path(bundle_path)
        if not bundle_path.exists() or not bundle_path.is_file():
            raise FileNotFoundError("설정 번들 파일을 찾을 수 없습니다.")

        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = set(zf.namelist())
            if self.MANIFEST_PATH not in names:
                raise ValueError("올바른 설정 번들 파일이 아닙니다. (manifest 누락)")
            if self.DB_ENTRY not in names:
                raise ValueError("올바른 설정 번들 파일이 아닙니다. (DB 누락)")

            manifest = json.loads(zf.read(self.MANIFEST_PATH).decode("utf-8"))
            counts = manifest.get("counts") or {}
            self._validate_bundle_db_from_zip(zf)

            return SettingsBundleInfo(
                bundle_path=str(bundle_path),
                bundle_version=int(manifest.get("bundle_version") or 0),
                exported_at=str(manifest.get("exported_at") or ""),
                contacts_count=int(counts.get("contacts") or 0),
                groups_count=int(counts.get("groups") or 0),
                campaigns_count=int(counts.get("campaigns") or 0),
                send_lists_count=int(counts.get("send_lists") or 0),
                has_campaign_assets=bool(manifest.get("has_campaign_assets")),
                has_reports=bool(manifest.get("has_reports")),
                has_logs=bool(manifest.get("has_logs")),
            )

    def _normalize_output_path(self, output_path: str | Path) -> Path:
        path = Path(output_path)
        suffix = path.suffix.lower()
        if suffix not in (".kcsbundle", ".zip"):
            path = path.with_suffix(".kcsbundle")
        return path

    def _create_db_snapshot(self, db_path: Path) -> Path:
        if not db_path.exists():
            raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {db_path}")

        fd, temp_name = tempfile.mkstemp(prefix="kcsbundle_db_", suffix=".sqlite3")
        try:
            Path(temp_name).unlink(missing_ok=True)
        except Exception:
            pass

        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(temp_name)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            try:
                dst.close()
            except Exception:
                pass
            try:
                src.close()
            except Exception:
                pass
        return Path(temp_name)

    def _read_db_counts(self, db_path: Path) -> dict[str, int]:
        counts = {
            "contacts": 0,
            "groups": 0,
            "campaigns": 0,
            "send_lists": 0,
        }
        if not db_path.exists():
            return counts

        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            for table in ("contacts", "groups", "campaigns", "send_lists"):
                if self._table_exists(conn, table):
                    row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table};").fetchone()
                    counts[table] = int(row["cnt"] or 0) if row is not None else 0
            return counts
        finally:
            conn.close()

    def _validate_bundle_db_from_zip(self, zf: zipfile.ZipFile) -> None:
        fd, temp_name = tempfile.mkstemp(prefix="kcsbundle_check_", suffix=".sqlite3")
        try:
            Path(temp_name).unlink(missing_ok=True)
        except Exception:
            pass
        temp_db = Path(temp_name)
        try:
            with zf.open(self.DB_ENTRY) as src, open(temp_db, "wb") as dst:
                shutil.copyfileobj(src, dst)
            self._validate_import_db(temp_db)
        finally:
            try:
                temp_db.unlink(missing_ok=True)
            except Exception:
                pass

    def _validate_import_db(self, db_path: Path) -> None:
        if not db_path.exists():
            raise ValueError("설정 번들 안에 DB 파일이 없습니다.")

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA quick_check;").fetchone()
            if row and str(row[0]).lower() != "ok":
                raise ValueError(f"설정 번들 DB 무결성 검사 실패: {row[0]}")
            for table in self.REQUIRED_TABLES:
                if not self._table_exists(conn, table):
                    raise ValueError(f"설정 번들 DB에 필수 테이블이 없습니다: {table}")
        finally:
            conn.close()

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
            (table,),
        ).fetchone()
        return row is not None

    def _dir_has_files(self, path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        return any(p.is_file() for p in path.rglob("*"))

    def _write_dir_to_zip(self, zf: zipfile.ZipFile, src_dir: Path, dest_root: str) -> None:
        if not src_dir.exists() or not src_dir.is_dir():
            return
        for file_path in sorted(src_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = f"{dest_root}/{file_path.relative_to(src_dir).as_posix()}"
            zf.write(file_path, arcname)
