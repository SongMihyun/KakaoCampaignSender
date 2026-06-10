from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.paths import project_root


DEFAULT_KAKAO_CLIENT_ID = "85aecf352ab2bbdf6fcdaffb812212c9"
DEFAULT_KAKAO_REDIRECT_URI = "http://localhost:8765/auth/kakao/callback"
DEFAULT_KAKAO_LOGIN_PROMPT = "login"
DEFAULT_BETA_LOGIN_PASSWORD_SALT = "DjVaJxCA78z7rmmQrvjrpA=="
DEFAULT_BETA_LOGIN_PASSWORD_HASH = "h2RLhrxXBsG3PPfKc2lj0SZNdU1AKk7PoFPkIM+AvLg="


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class AuthConfig:
    kakao_client_id: str = DEFAULT_KAKAO_CLIENT_ID
    kakao_redirect_uri: str = DEFAULT_KAKAO_REDIRECT_URI
    kakao_client_secret: str = ""
    kakao_login_prompt: str = DEFAULT_KAKAO_LOGIN_PROMPT
    auth_mode: str = "no_db"
    auth_provider: str = "kakao"
    persist_session: bool = False
    callback_timeout_sec: int = 180
    beta_password_login_enabled: bool = True
    beta_login_id: str = "test"
    beta_login_password_hash: str = DEFAULT_BETA_LOGIN_PASSWORD_HASH
    beta_login_password_salt: str = DEFAULT_BETA_LOGIN_PASSWORD_SALT

    @classmethod
    def load(cls) -> "AuthConfig":
        env_file = _load_dotenv(project_root() / ".env")
        if getattr(sys, "frozen", False):
            env_file = {
                **env_file,
                **_load_dotenv(Path(sys.executable).resolve().parent / ".env"),
            }

        def get(name: str, default: str = "") -> str:
            return str(os.environ.get(name) or env_file.get(name) or default).strip()

        def get_bool(name: str, default: bool = False) -> bool:
            value = get(name, "true" if default else "false").lower()
            return value in {"1", "true", "yes", "y", "on"}

        return cls(
            kakao_client_id=get("KAKAO_CLIENT_ID", DEFAULT_KAKAO_CLIENT_ID),
            kakao_redirect_uri=get("KAKAO_REDIRECT_URI", DEFAULT_KAKAO_REDIRECT_URI),
            kakao_client_secret=get("KAKAO_CLIENT_SECRET"),
            kakao_login_prompt=get("KAKAO_LOGIN_PROMPT", DEFAULT_KAKAO_LOGIN_PROMPT),
            auth_mode=get("AUTH_MODE", "no_db").lower(),
            auth_provider=get("AUTH_PROVIDER", "kakao").lower(),
            persist_session=get_bool("AUTH_PERSIST_SESSION", False),
            callback_timeout_sec=int(get("AUTH_CALLBACK_TIMEOUT_SEC", "180") or "180"),
            beta_password_login_enabled=get_bool("BETA_PASSWORD_LOGIN_ENABLED", True),
            beta_login_id=get("BETA_LOGIN_ID", "test"),
            beta_login_password_hash=get("BETA_LOGIN_PASSWORD_HASH", DEFAULT_BETA_LOGIN_PASSWORD_HASH),
            beta_login_password_salt=get("BETA_LOGIN_PASSWORD_SALT", DEFAULT_BETA_LOGIN_PASSWORD_SALT),
        )

    def validate_for_kakao(self) -> None:
        if not self.kakao_client_id:
            raise ValueError("KAKAO_CLIENT_ID가 설정되지 않았습니다.")
        if not self.kakao_redirect_uri:
            raise ValueError("KAKAO_REDIRECT_URI가 설정되지 않았습니다.")
        if not self.kakao_redirect_uri.startswith("http://localhost:"):
            raise ValueError("KAKAO_REDIRECT_URI는 http://localhost 기반 callback 주소여야 합니다.")
