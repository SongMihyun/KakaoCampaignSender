from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "kakao_campaign_sender"  # 원하는 폴더명으로 변경 가능


def project_root() -> Path:
    # src/app/paths.py 기준: .../<project>/src/app/paths.py
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """
    ✅ A안: 사용자 로컬 AppData 경로에 데이터 저장
    예) C:\\Users\\<User>\\AppData\\Local\\kakao_campaign_sender
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        d = Path(base) / APP_NAME
    else:
        d = Path.home() / "AppData" / "Local" / APP_NAME

    d.mkdir(parents=True, exist_ok=True)
    return d


def contacts_db_path() -> Path:
    """
    ✅ DB는 항상 로컬(AppData)에 생성/사용
    """
    return user_data_dir() / "contacts.sqlite3"
