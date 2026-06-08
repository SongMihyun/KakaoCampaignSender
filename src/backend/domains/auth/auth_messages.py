from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.domains.auth.auth_api_client import AuthLoginResult


@dataclass(frozen=True)
class AuthFailureMessage:
    title: str
    message: str
    result: str | None = None
    reason: str | None = None
    user_uuid: str | None = None
    project_code: str | None = None
    device_id: str | None = None
    app_version: str | None = None
    signup_token: str | None = None
    requires_invite_code: bool = False
    display_name: str | None = None

    def full_text(self) -> str:
        detail = []
        if self.result:
            detail.append(f"result={self.result}")
        if self.reason:
            detail.append(f"reason={self.reason}")
        if self.project_code:
            detail.append(f"project={self.project_code}")
        if not detail:
            return self.message
        return f"{self.message}\n\n({', '.join(detail)})"


def message_for_auth_result(
    result: AuthLoginResult,
    *,
    device_id: str | None = None,
    app_version: str | None = None,
) -> AuthFailureMessage:
    reason = result.reason or ""
    mapping: dict[str, tuple[str, str]] = {
        "USER_PENDING": ("승인 대기 중입니다", "현재 계정이 승인 대기 상태입니다. 운영자 승인 후 이용할 수 있습니다."),
        "USER_BLOCKED": ("차단된 계정입니다", "현재 계정이 차단되었습니다. 운영자에게 문의해 주세요."),
        "USER_EXPIRED": ("사용 기간이 만료되었습니다", "계정 사용 기간이 만료되었습니다. 운영자에게 연장 요청을 해주세요."),
        "PROJECT_PENDING": ("카센더 권한 승인 대기 중입니다", "카센더 사용 권한이 승인 대기 중입니다. 운영자 승인 후 이용할 수 있습니다."),
        "PROJECT_BLOCKED": ("카센더 권한이 차단되었습니다", "카센더 사용 권한이 차단되었습니다. 운영자에게 문의해 주세요."),
        "PROJECT_EXPIRED": ("카센더 권한이 만료되었습니다", "카센더 사용 권한이 만료되었습니다. 운영자에게 연장 요청을 해주세요."),
        "PROJECT_NOT_ALLOWED": ("카센더 권한이 없습니다", "카센더 사용 권한이 없습니다. 운영자에게 권한 부여를 요청해 주세요."),
    }
    if result.result == "SIGNUP_REQUIRED":
        title = "베타 초대 코드 입력"
        message = result.message or "카센더 베타 초대 코드가 필요합니다.\n운영자에게 받은 초대 코드를 입력해 주세요."
    else:
        title, message = mapping.get(reason, ("로그인 권한 확인에 실패했습니다", "로그인 권한을 확인할 수 없습니다. 운영자에게 문의해 주세요."))

    return AuthFailureMessage(
        title=title,
        message=message,
        result=result.result,
        reason=result.reason,
        user_uuid=result.user_uuid,
        project_code=result.project_code,
        device_id=device_id,
        app_version=app_version,
        signup_token=result.signup_token,
        requires_invite_code=result.requires_invite_code,
        display_name=result.display_name,
    )


def service_unavailable_message(message: str) -> AuthFailureMessage:
    return AuthFailureMessage(
        title="인증 서버에 연결할 수 없습니다",
        message=message,
        result="ERROR",
        reason="AUTH_API_UNAVAILABLE",
    )


def unknown_error_message(message: str) -> AuthFailureMessage:
    return AuthFailureMessage(
        title="로그인에 실패했습니다",
        message=message or "네트워크 상태를 확인해 주세요.",
        result="ERROR",
        reason="UNKNOWN_ERROR",
    )
