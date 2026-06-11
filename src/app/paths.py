from __future__ import annotations

import os
import re
from pathlib import Path

APP_NAME = "kakao_campaign_sender"
_ACTIVE_USER_UUID: str | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / "AppData" / "Local" / APP_NAME

    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_contacts_db_path() -> Path:
    return user_data_dir() / "contacts.sqlite3"


def sanitize_user_uuid(user_uuid: str) -> str:
    value = (user_uuid or "").strip()
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value or "unknown_user"


def set_active_user_uuid(user_uuid: str | None) -> None:
    global _ACTIVE_USER_UUID
    _ACTIVE_USER_UUID = sanitize_user_uuid(user_uuid) if user_uuid else None


def active_user_uuid() -> str | None:
    return _ACTIVE_USER_UUID


def user_db_dir(user_uuid: str) -> Path:
    path = user_data_dir() / "users" / sanitize_user_uuid(user_uuid)
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_contacts_db_path(user_uuid: str) -> Path:
    return user_db_dir(user_uuid) / "contacts.sqlite3"


def contacts_db_path() -> Path:
    if _ACTIVE_USER_UUID:
        return user_contacts_db_path(_ACTIVE_USER_UUID)
    return legacy_contacts_db_path()


def orphan_backups_dir() -> Path:
    path = user_data_dir() / "orphan_backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_backup_marker_path() -> Path:
    return user_data_dir() / "legacy_backup_marker.json"
