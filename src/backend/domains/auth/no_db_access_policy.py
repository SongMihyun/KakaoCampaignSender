from __future__ import annotations

from backend.domains.auth.access_policy import AccessDecision, AccessPolicy
from backend.domains.auth.models import AuthSession


class NoDbAccessPolicy(AccessPolicy):
    def evaluate(self, session: AuthSession) -> AccessDecision:
        provider = session.provider.upper()
        if provider not in {"KAKAO", "BETA_PASSWORD"}:
            return AccessDecision(False, "지원하지 않는 인증 제공자입니다.")
        if not session.provider_user_id:
            return AccessDecision(False, "사용자 식별 정보를 확인할 수 없습니다.")
        if provider == "KAKAO" and not session.access_token:
            return AccessDecision(False, "인증 토큰을 확인할 수 없습니다.")
        if session.is_expired():
            return AccessDecision(False, "로그인 세션이 만료되었습니다.")
        return AccessDecision(True, "")
