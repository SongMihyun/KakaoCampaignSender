from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.paths import user_data_dir


DEFAULT_SETTINGS: dict[str, Any] = {
    "pc_environment": "public",
    "support_chat_name": "카센더 운영자",
    "support_openchat_url": "",
    "kakao_ctrl_t_multi_attach_input_mode": "navigate_then_names",
}


def settings_path() -> Path:
    path = user_data_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_settings() -> dict[str, Any]:
    path = settings_path()
    data = dict(DEFAULT_SETTINGS)
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
    except Exception:
        pass
    return data


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    data = load_settings()
    data.update(values or {})
    settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_setting(key: str, default: Any = None) -> Any:
    return load_settings().get(key, default)


def set_setting(key: str, value: Any) -> None:
    save_settings({key: value})
