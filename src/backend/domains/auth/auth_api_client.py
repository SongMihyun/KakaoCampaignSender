from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app.paths import user_data_dir


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthLoginResult:
    result: str
    reason: str | None
    user_uuid: str | None
    project_code: str
    provider: str | None = None
    signup_token: str | None = None
    requires_invite_code: bool = False
    message: str | None = None
    role: str | None = None
    expires_at: str | None = None
    display_name: str | None = None

    @property
    def allowed(self) -> bool:
        return self.result == "ALLOWED"

    @property
    def signup_required(self) -> bool:
        return self.result == "SIGNUP_REQUIRED"


class AuthApiClientError(RuntimeError):
    pass


class AuthApiClient:
    def __init__(self, *, base_url: str, timeout_sec: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def health_check(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/admin/health", timeout=self.timeout_sec)
            if response.status_code >= 400:
                return False
            body = response.json()
            return bool(body.get("ok"))
        except Exception:
            return False

    def login_with_kakao(
        self,
        *,
        provider_user_id: str,
        device_id: str,
        app_version: str,
        project_code: str = "kasender",
        pc_type: str = "public",
        auth_flow: str = "kakao_login",
    ) -> AuthLoginResult:
        provider_user_id_hash = _sha256_hex(provider_user_id)
        payload = {
            "provider": "kakao",
            "provider_user_id_hash": provider_user_id_hash,
            "device_id": device_id,
            "app_version": app_version,
            "pc_type": pc_type,
            "auth_flow": auth_flow,
        }
        log.info(
            "AUTH_API_LOGIN_REQUEST base_url=%s endpoint=/api/auth/check provider=kakao provider_user_id_hash=%s device_id=%s app_version=%s pc_type=%s project_code=%s",
            self.base_url,
            _mask(provider_user_id_hash),
            device_id,
            app_version,
            pc_type,
            project_code,
        )
        body = self._post_json("/api/auth/check", payload, log_prefix="AUTH_API_LOGIN_RESPONSE")
        result = _result_from_body(body, project_code=project_code)
        log.info(
            "AUTH_API_LOGIN_RESPONSE provider=kakao provider_user_id_hash=%s result=%s reason=%s user_uuid=%s project_code=%s signup_required=%s requires_invite_code=%s",
            _mask(provider_user_id_hash),
            result.result,
            result.reason,
            result.user_uuid,
            result.project_code,
            result.signup_required,
            result.requires_invite_code,
        )
        return result

    def complete_signup(
        self,
        *,
        signup_token: str,
        display_name: str,
        invite_code: str,
        device_id: str,
        app_version: str,
        pc_type: str = "public",
        project_code: str = "kasender",
    ) -> AuthLoginResult:
        payload = {
            "signup_token": signup_token,
            "display_name": display_name,
            "invite_code": invite_code,
            "device_id": device_id,
            "app_version": app_version,
            "pc_type": pc_type,
        }
        log.info(
            "AUTH_API_SIGNUP_COMPLETE_REQUEST base_url=%s endpoint=/api/auth/signup/complete signup_token_present=%s invite_code_present=%s device_id=%s app_version=%s pc_type=%s project_code=%s",
            self.base_url,
            bool(signup_token),
            bool(invite_code),
            device_id,
            app_version,
            pc_type,
            project_code,
        )
        body = self._post_json("/api/auth/signup/complete", payload, log_prefix="AUTH_API_SIGNUP_COMPLETE_RESPONSE")
        result = _result_from_body(body, project_code=project_code)
        log.info(
            "AUTH_API_SIGNUP_COMPLETE_RESPONSE result=%s reason=%s user_uuid=%s project_code=%s role=%s",
            result.result,
            result.reason,
            result.user_uuid,
            result.project_code,
            result.role,
        )
        return result

    def _post_json(self, path: str, payload: dict[str, Any], *, log_prefix: str) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}{path}",
                json=payload,
                timeout=self.timeout_sec,
            )
        except requests.RequestException as exc:
            raise AuthApiClientError(_connection_error_message(self.base_url)) from exc

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            log.warning("%s status=%s body_preview=%s", log_prefix, response.status_code, _preview_body(response.text))
            raise AuthApiClientError("인증 서버 응답을 해석할 수 없습니다.") from exc

        if response.status_code >= 400:
            log.warning("%s status=%s body=%s", log_prefix, response.status_code, _safe_body_for_log(body))
            raise AuthApiClientError(_server_error_message(body) or f"인증 서버 요청이 실패했습니다. ({response.status_code})")
        return body


def get_or_create_device_id(path: Path | None = None) -> str:
    device_path = path or (user_data_dir() / "device_id")
    try:
        value = device_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    device_path.parent.mkdir(parents=True, exist_ok=True)
    value = f"WIN-{uuid.uuid4()}"
    device_path.write_text(value, encoding="utf-8")
    return value


def _mask(value: str) -> str:
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _result_from_body(body: dict[str, Any], *, project_code: str) -> AuthLoginResult:
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    normalized = _normalize_auth_response(data, project_code=project_code)
    return AuthLoginResult(
        result=str(normalized.get("result") or ""),
        reason=normalized.get("reason") or None,
        user_uuid=normalized.get("user_uuid") or None,
        project_code=str(normalized.get("project_code") or project_code),
        provider=normalized.get("provider") or None,
        signup_token=normalized.get("signup_token") or None,
        requires_invite_code=bool(normalized.get("requires_invite_code")),
        message=normalized.get("message") or None,
        role=normalized.get("role") or None,
        expires_at=normalized.get("expires_at") or None,
        display_name=normalized.get("display_name") or None,
    )


def _normalize_auth_response(body: dict[str, Any], *, project_code: str) -> dict[str, Any]:
    status = str(body.get("status") or "").strip()
    if body.get("signup_required") is True or status == "signup_required":
        return {
            "result": "SIGNUP_REQUIRED",
            "reason": body.get("reason") or status or "SIGNUP_REQUIRED",
            "user_uuid": body.get("user_uuid") or None,
            "project_code": body.get("project_code") or project_code,
            "provider": body.get("provider") or None,
            "signup_token": body.get("signup_token") or None,
            "requires_invite_code": bool(body.get("requires_invite_code")),
            "message": body.get("message") or None,
            "role": body.get("role") or None,
            "expires_at": body.get("expires_at") or None,
            "display_name": body.get("display_name") or None,
        }
    if body.get("allowed") is True or status == "active":
        return {
            "result": "ALLOWED",
            "reason": body.get("reason") or status or None,
            "user_uuid": body.get("user_uuid") or None,
            "project_code": body.get("project_code") or project_code,
            "provider": body.get("provider") or None,
            "signup_token": body.get("signup_token") or None,
            "requires_invite_code": bool(body.get("requires_invite_code")),
            "message": body.get("message") or None,
            "role": body.get("role") or None,
            "expires_at": body.get("expires_at") or None,
            "display_name": body.get("display_name") or None,
        }
    return {
        "result": str(body.get("result") or "DENIED"),
        "reason": body.get("reason") or status or None,
        "user_uuid": body.get("user_uuid") or None,
        "project_code": body.get("project_code") or project_code,
        "provider": body.get("provider") or None,
        "signup_token": body.get("signup_token") or None,
        "requires_invite_code": bool(body.get("requires_invite_code")),
        "message": body.get("message") or None,
        "role": body.get("role") or None,
        "expires_at": body.get("expires_at") or None,
        "display_name": body.get("display_name") or None,
    }


def _safe_body_for_log(body: dict[str, Any]) -> str:
    redacted = dict(body or {})
    for key in list(redacted.keys()):
        lowered = str(key).lower()
        if "token" in lowered or lowered in {"code", "authorization_code", "code_verifier", "invite_code"}:
            redacted[key] = "<redacted>"
    return str(redacted)


def _preview_body(text: str, limit: int = 240) -> str:
    clean = (text or "").replace("\r", " ").replace("\n", " ").strip()
    return clean[:limit]


def _server_error_message(body: dict[str, Any]) -> str:
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "")
    if isinstance(body.get("message"), str):
        return str(body.get("message") or "")
    return ""


def _connection_error_message(base_url: str) -> str:
    message = "인증 서버에 연결할 수 없습니다.\n네트워크 상태를 확인하거나 잠시 후 다시 시도해 주세요."
    if base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"):
        message += "\n\n로컬 인증 서버가 실행 중인지 확인하세요.\nD:\\01_DEV\\kasender-auth-api 에서 npm run dev를 실행해야 합니다."
    return message
