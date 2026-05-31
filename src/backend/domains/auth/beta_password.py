from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import timedelta

from backend.domains.auth.config import AuthConfig
from backend.domains.auth.models import AuthSession, utc_now


PBKDF2_ITERATIONS = 200_000


def verify_beta_password(config: AuthConfig, user_id: str, password: str) -> bool:
    if not config.beta_password_login_enabled:
        return False
    if not hmac.compare_digest((user_id or "").strip(), config.beta_login_id):
        return False
    if not password:
        return False
    try:
        salt = base64.b64decode(config.beta_login_password_salt)
        expected = base64.b64decode(config.beta_login_password_hash)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return hmac.compare_digest(actual, expected)


def create_beta_session() -> AuthSession:
    now = utc_now()
    return AuthSession(
        provider="BETA_PASSWORD",
        provider_user_id="beta_test_user",
        nickname="베타 비상 사용자",
        email=None,
        access_token="beta-password-session",
        refresh_token=None,
        expires_at=now + timedelta(hours=24),
        login_at=now,
    )
