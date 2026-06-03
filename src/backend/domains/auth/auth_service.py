from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from backend.core.app_settings import get_setting
from backend.domains.auth.access_policy import AccessPolicy
from backend.domains.auth.beta_password import create_beta_session, verify_beta_password
from backend.domains.auth.config import AuthConfig
from backend.domains.auth.kakao_provider import KakaoAuthProvider
from backend.domains.auth.models import AuthSession, utc_now
from backend.domains.auth.no_db_access_policy import NoDbAccessPolicy
from backend.domains.auth.provider import AuthProvider
from backend.domains.auth.session_store import SessionStore


class AuthError(RuntimeError):
    pass


class AuthService:
    def __init__(
        self,
        *,
        config: AuthConfig | None = None,
        provider: AuthProvider | None = None,
        access_policy: AccessPolicy | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        self.config = config or AuthConfig.load()
        self.provider = provider or KakaoAuthProvider(self.config)
        self.access_policy = access_policy or NoDbAccessPolicy()
        self.session_store = session_store or SessionStore()

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
            decision = self.access_policy.evaluate(session)
            if not decision.allowed:
                raise AuthError(decision.reason or "베타 사용자 권한을 확인할 수 없습니다.")
            self._save_session_if_needed(session)
            return session
        except AuthError:
            raise
        except TimeoutError as e:
            raise AuthError("로그인 시간이 초과되었습니다. 다시 시도해 주세요.") from e
        except ValueError as e:
            raise AuthError(str(e)) from e
        except Exception as e:
            message = str(e).strip()
            if not message:
                message = "네트워크 상태를 확인해 주세요."
            raise AuthError(message) from e

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
        return str(get_setting("pc_environment", "public") or "public").strip().lower() == "personal"

    def should_persist_session(self) -> bool:
        return self.is_personal_pc()

    def _save_session_if_needed(self, session: AuthSession) -> None:
        if not self.should_persist_session():
            return
        if self.is_personal_pc():
            session = replace(session, expires_at=utc_now() + timedelta(days=7))
        self.session_store.save(session)
