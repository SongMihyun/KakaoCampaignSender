from __future__ import annotations

import json
import platform
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.paths import contacts_db_path, user_data_dir
from app.version import __version__
from backend.core.app_settings import load_settings
from backend.core.error_summary import build_error_summary


@dataclass(frozen=True)
class SupportPackageResult:
    zip_path: Path
    summary_path: Path
    summary_message: str


def support_packages_dir() -> Path:
    path = user_data_dir() / "support_packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_support_packages() -> int:
    count = 0
    root = support_packages_dir()
    for path in list(root.glob("support_package_*.zip")) + list(root.glob("support_package_*")):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            count += 1
        except Exception:
            pass
    return count


def _add_if_exists(zf: zipfile.ZipFile, path: Path, arcname: str | None = None) -> None:
    if path.exists() and path.is_file():
        zf.write(path, arcname or path.name)


def _add_dir(zf: zipfile.ZipFile, path: Path, prefix: str) -> None:
    if not path.exists():
        return
    for child in path.rglob("*"):
        if child.is_file():
            try:
                zf.write(child, f"{prefix}/{child.relative_to(path)}")
            except Exception:
                pass


def build_support_package(*, include_db: bool = False) -> SupportPackageResult:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = support_packages_dir()
    work = root / f"support_package_{ts}"
    work.mkdir(parents=True, exist_ok=True)
    package_name = f"support_package_{ts}.zip"

    summary = build_error_summary(include_db=include_db, package_name=package_name)
    summary_path = work / "error_summary.txt"
    summary_path.write_text(summary.text, encoding="utf-8")
    (work / "version.txt").write_text(str(__version__), encoding="utf-8")
    (work / "system_info.txt").write_text(
        "\n".join(
            [
                f"PC: {platform.node()}",
                f"OS: {platform.platform()}",
                f"Python: {platform.python_version()}",
                f"Data dir: {user_data_dir()}",
            ]
        ),
        encoding="utf-8",
    )
    (work / "settings_summary.txt").write_text(
        json.dumps(load_settings(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    zip_path = root / package_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _add_if_exists(zf, summary_path, "error_summary.txt")
        _add_if_exists(zf, work / "version.txt", "version.txt")
        _add_if_exists(zf, work / "system_info.txt", "system_info.txt")
        _add_if_exists(zf, work / "settings_summary.txt", "settings_summary.txt")
        _add_dir(zf, user_data_dir() / "logs", "logs")
        _add_dir(zf, user_data_dir() / "reports", "send_report")
        _add_dir(zf, user_data_dir() / "error_reports", "error_report")
        if include_db:
            _add_if_exists(zf, contacts_db_path(), "data/contacts.sqlite3")

    return SupportPackageResult(
        zip_path=zip_path,
        summary_path=summary_path,
        summary_message=summary.message,
    )
