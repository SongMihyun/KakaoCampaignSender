from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def dt_to_str(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuthSession:
    provider: str
    provider_user_id: str
    nickname: str | None
    email: str | None
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    login_at: datetime
    user_uuid: str | None = None
    project_code: str | None = None
    auth_result: str | None = None
    auth_reason: str | None = None
    device_id: str | None = None
    app_version: str | None = None

    def is_expired(self, *, now: datetime | None = None, skew_seconds: int = 60) -> bool:
        now = now or utc_now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return (expires_at.timestamp() - now.timestamp()) <= skew_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_user_id": self.provider_user_id,
            "nickname": self.nickname,
            "email": self.email,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": dt_to_str(self.expires_at),
            "login_at": dt_to_str(self.login_at),
            "user_uuid": self.user_uuid,
            "project_code": self.project_code,
            "auth_result": self.auth_result,
            "auth_reason": self.auth_reason,
            "device_id": self.device_id,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthSession":
        expires_at = parse_dt(str(data.get("expires_at") or ""))
        login_at = parse_dt(str(data.get("login_at") or ""))
        if expires_at is None or login_at is None:
            raise ValueError("invalid auth session timestamps")
        return cls(
            provider=str(data.get("provider") or ""),
            provider_user_id=str(data.get("provider_user_id") or ""),
            nickname=data.get("nickname") or None,
            email=data.get("email") or None,
            access_token=str(data.get("access_token") or ""),
            refresh_token=data.get("refresh_token") or None,
            expires_at=expires_at,
            login_at=login_at,
            user_uuid=data.get("user_uuid") or None,
            project_code=data.get("project_code") or None,
            auth_result=data.get("auth_result") or None,
            auth_reason=data.get("auth_reason") or None,
            device_id=data.get("device_id") or None,
            app_version=data.get("app_version") or None,
        )
