from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta

from app.version import __version__
from backend.core.app_settings import get_setting
from backend.domains.auth.access_policy import AccessPolicy
from backend.domains.auth.auth_api_client import AuthApiClient, AuthApiClientError, get_or_create_device_id
from backend.domains.auth.auth_messages import AuthFailureMessage, message_for_auth_result, service_unavailable_message, unknown_error_message
from backend.domains.auth.beta_password import create_beta_session, verify_beta_password
from backend.domains.auth.config import AuthConfig
from backend.domains.auth.kakao_provider import KakaoAuthProvider
from backend.domains.auth.models import AuthSession, utc_now
from backend.domains.auth.no_db_access_policy import NoDbAccessPolicy
from backend.domains.auth.provider import AuthProvider
from backend.domains.auth.session_store import SessionStore


log = logging.getLogger(__name__)


class AuthError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        title: str = "로그인 실패",
        result: str | None = None,
        reason: str | None = None,
        user_uuid: str | None = None,
        project_code: str | None = None,
        device_id: str | None = None,
        app_version: str | None = None,
        signup_token: str | None = None,
        requires_invite_code: bool = False,
        display_name: str | None = None,
    ) -> None:
        self.title = title
        self.message = message
        self.result = result
        self.reason = reason
        self.user_uuid = user_uuid
        self.project_code = project_code
        self.device_id = device_id
        self.app_version = app_version
        self.signup_token = signup_token
        self.requires_invite_code = requires_invite_code
        self.display_name = display_name
        super().__init__(self.full_text())

    @classmethod
    def from_failure(cls, failure: AuthFailureMessage) -> "AuthError":
        return cls(
            failure.message,
            title=failure.title,
            result=failure.result,
            reason=failure.reason,
            user_uuid=failure.user_uuid,
            project_code=failure.project_code,
            device_id=failure.device_id,
            app_version=failure.app_version,
            signup_token=failure.signup_token,
            requires_invite_code=failure.requires_invite_code,
            display_name=failure.display_name,
        )

    def full_text(self) -> str:
        details = []
        if self.result:
            details.append(f"result={self.result}")
        if self.reason:
            details.append(f"reason={self.reason}")
        if self.project_code:
            details.append(f"project={self.project_code}")
        if not details:
            return self.message
        return f"{self.message}\n\n({', '.join(details)})"


class AuthService:
    def __init__(
        self,
        *,
        config: AuthConfig | None = None,
        provider: AuthProvider | None = None,
        access_policy: AccessPolicy | None = None,
        session_store: SessionStore | None = None,
        auth_api_client: AuthApiClient | None = None,
    ) -> None:
        self.config = config or AuthConfig.load()
        self.provider = provider or KakaoAuthProvider(self.config)
        self.access_policy = access_policy or NoDbAccessPolicy()
        self.session_store = session_store or SessionStore()
        self.auth_api_client = auth_api_client or AuthApiClient(
            base_url=self.config.effective_auth_api_base_url,
            timeout_sec=self.config.auth_api_timeout_sec,
        )
        self._pending_signup_session: AuthSession | None = None
        self._pending_signup_token: str | None = None
        self._pending_signup_device_id: str | None = None
        self._pending_signup_app_version: str | None = None

    def current_session(self) -> AuthSession | None:
        if not self.should_persist_session():
            self.session_store.clear()
            return None
        session = self.session_store.load()
        if session is None:
            return None
        decision = self.access_policy.evaluate(session)
        if not decision.allowed:
            self.session_store.clear()
            return None
        return session

    def login_with_kakao(self) -> AuthSession:
        try:
            session = self.provider.login()
            session = self._apply_dev_provider_user_id(session)
            decision = self.access_policy.evaluate(session)
            if not decision.allowed:
                raise AuthError(decision.reason or "로그인 권한을 확인할 수 없습니다.")

            device_id = get_or_create_device_id()
            app_version = _app_version()
            auth_result = self.auth_api_client.login_with_kakao(
                provider_user_id=session.provider_user_id,
                device_id=device_id,
                app_version=app_version,
                project_code=self.config.project_code or "kasender",
                pc_type=self.pc_type(),
                auth_flow="kakao_login",
            )
            if not auth_result.allowed:
                if auth_result.signup_required and auth_result.requires_invite_code and auth_result.signup_token:
                    self._pending_signup_session = session
                    self._pending_signup_token = auth_result.signup_token
                    self._pending_signup_device_id = device_id
                    self._pending_signup_app_version = app_version
                failure = message_for_auth_result(auth_result, device_id=device_id, app_version=app_version)
                log.warning(
                    "AUTH_LOGIN_DENIED result=%s reason=%s user_uuid=%s project_code=%s device_id=%s app_version=%s",
                    failure.result,
                    failure.reason,
                    failure.user_uuid,
                    failure.project_code,
                    failure.device_id,
                    failure.app_version,
                )
                raise AuthError.from_failure(failure)

            session = replace(
                session,
                user_uuid=auth_result.user_uuid,
                project_code=auth_result.project_code,
                auth_result=auth_result.result,
                auth_reason=auth_result.reason,
                device_id=device_id,
                app_version=app_version,
            )
            self._save_session_if_needed(session)
            return session
        except AuthError:
            raise
        except AuthApiClientError as e:
            raise AuthError.from_failure(service_unavailable_message(str(e))) from e
        except TimeoutError as e:
            raise AuthError("로그인 시간이 초과되었습니다. 다시 시도해 주세요.") from e
        except ValueError as e:
            raise AuthError.from_failure(service_unavailable_message(str(e))) from e
        except Exception as e:
            message = str(e).strip()
            if not message:
                message = "네트워크 상태를 확인해 주세요."
            raise AuthError.from_failure(unknown_error_message(message)) from e

    def complete_signup_with_invite_code(self, invite_code: str, *, display_name: str | None = None) -> AuthSession:
        pending = self._pending_signup_session
        signup_token = self._pending_signup_token
        device_id = self._pending_signup_device_id or get_or_create_device_id()
        app_version = self._pending_signup_app_version or _app_version()
        if pending is None or not signup_token:
            raise AuthError("가입 요청이 만료되었습니다. 다시 로그인해 주세요.", title="가입 요청 만료")
        invite_code = (invite_code or "").strip()
        if not invite_code:
            raise AuthError("초대 코드를 입력해 주세요.", title="초대 코드 필요")

        try:
            result = self.auth_api_client.complete_signup(
                signup_token=signup_token,
                display_name=(display_name or pending.nickname or "카센더 사용자").strip(),
                invite_code=invite_code,
                device_id=device_id,
                app_version=app_version,
                pc_type=self.pc_type(),
                project_code=self.config.project_code or "kasender",
            )
        except AuthApiClientError as e:
            raise AuthError(str(e), title="초대 코드 확인 실패") from e

        if not result.allowed:
            raise AuthError(result.message or "초대 코드 확인에 실패했습니다.", title="초대 코드 확인 실패", result=result.result, reason=result.reason)

        session = replace(
            pending,
            user_uuid=result.user_uuid,
            project_code=result.project_code,
            auth_result=result.result,
            auth_reason=result.reason,
            device_id=device_id,
            app_version=app_version,
        )
        self._pending_signup_session = None
        self._pending_signup_token = None
        self._pending_signup_device_id = None
        self._pending_signup_app_version = None
        self._save_session_if_needed(session)
        return session

    def login_with_beta_password(self, user_id: str, password: str) -> AuthSession:
        if not self.config.beta_password_login_enabled:
            raise AuthError("비상 로그인이 비활성화되어 있습니다.")
        if not verify_beta_password(self.config, user_id, password):
            raise AuthError("아이디 또는 비밀번호가 올바르지 않습니다.")
        session = create_beta_session()
        decision = self.access_policy.evaluate(session)
        if not decision.allowed:
            raise AuthError(decision.reason or "비상 로그인 권한을 확인할 수 없습니다.")
        self._save_session_if_needed(session)
        return session

    def logout(self) -> None:
        self.session_store.clear()

    def clear_session(self) -> None:
        self.session_store.clear()

    def is_personal_pc(self) -> bool:
        return self.pc_type() == "personal"

    def pc_type(self) -> str:
        return "personal" if str(get_setting("pc_environment", "public") or "public").strip().lower() == "personal" else "public"

    def should_persist_session(self) -> bool:
        return self.is_personal_pc()

    def _save_session_if_needed(self, session: AuthSession) -> None:
        if not self.should_persist_session():
            return
        if self.is_personal_pc():
            session = replace(session, expires_at=utc_now() + timedelta(days=7))
        self.session_store.save(session)

    def _apply_dev_provider_user_id(self, session: AuthSession) -> AuthSession:
        dev_user_id = (self.config.dev_kakao_provider_user_id or "").strip()
        if not dev_user_id:
            return session
        if dev_user_id == "PROJECT_NOT_ALLOWED":
            return session
        if not self.config.effective_auth_api_base_url.startswith(("http://127.0.0.1", "http://localhost")):
            return session
        log.info("AUTH_API_DEV_PROVIDER_USER_ID_OVERRIDE provider_user_id=%s", dev_user_id)
        return replace(session, provider_user_id=dev_user_id)


def _message_for_auth_result(result: AuthLoginResult) -> str:
    reason = result.reason or ""
    if result.result == "SIGNUP_REQUIRED":
        return "등록되지 않은 계정입니다.\n운영자에게 사용 승인을 요청해 주세요.\n\n카카오 계정은 확인되었지만, 카센더 사용 권한이 아직 등록되지 않았습니다."
    if reason == "USER_PENDING":
        return "현재 승인 대기 상태입니다.\n운영자 승인 후 이용할 수 있습니다."
    if reason == "USER_BLOCKED":
        return "차단된 계정입니다.\n운영자에게 문의해 주세요."
    if reason == "USER_EXPIRED":
        return "사용 기간이 만료되었습니다.\n운영자에게 연장 요청을 해주세요."
    if reason == "PROJECT_PENDING":
        return "카센더 사용 권한이 승인 대기 중입니다.\n운영자 승인 후 이용할 수 있습니다."
    if reason == "PROJECT_BLOCKED":
        return "카센더 사용 권한이 차단되었습니다.\n운영자에게 문의해 주세요."
    if reason == "PROJECT_EXPIRED":
        return "카센더 사용 권한이 만료되었습니다.\n운영자에게 연장 요청을 해주세요."
    if reason == "PROJECT_NOT_ALLOWED":
        return "카센더 사용 권한이 없습니다.\n운영자에게 권한 부여를 요청해 주세요."
    return "로그인 권한 확인에 실패했습니다.\n운영자에게 문의해 주세요."


def _app_version() -> str:
    version = str(__version__ or "").strip()
    if not version or version == "__VERSION__":
        return "dev"
    return version
