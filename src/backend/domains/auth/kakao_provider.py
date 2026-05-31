from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from urllib.parse import urlencode
import webbrowser

import requests

from backend.domains.auth.config import AuthConfig
from backend.domains.auth.local_callback_server import LocalCallbackServer
from backend.domains.auth.models import AuthSession, utc_now
from backend.domains.auth.pkce import code_challenge_s256, new_code_verifier, new_state
from backend.domains.auth.provider import AuthProvider


log = logging.getLogger(__name__)


class KakaoAuthProvider(AuthProvider):
    AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    USER_ME_URL = "https://kapi.kakao.com/v2/user/me"

    def __init__(self, config: AuthConfig) -> None:
        self.config = config

    def login(self) -> AuthSession:
        self.config.validate_for_kakao()
        verifier = new_code_verifier()
        state = new_state()
        log.info(
            "KAKAO_OAUTH_AUTHORIZE CLIENT_ID=%s REDIRECT_URI=%s AUTH_URL=%s CODE_VERIFIER_SHA256=%s CLIENT_SECRET_CONFIGURED=%s",
            self.config.kakao_client_id,
            self.config.kakao_redirect_uri,
            self.AUTH_URL,
            _sha256_hex(verifier),
            bool(self.config.kakao_client_secret),
        )
        server = LocalCallbackServer(self.config.kakao_redirect_uri)
        server.start()
        try:
            auth_url = self._build_authorize_url(verifier=verifier, state=state)
            if not webbrowser.open(auth_url):
                raise RuntimeError("기본 브라우저를 열 수 없습니다.")
            callback = server.wait(self.config.callback_timeout_sec)
        finally:
            server.stop()

        if callback.error:
            raise RuntimeError(_friendly_oauth_error(callback.error, callback.error_description))
        if not callback.code:
            raise RuntimeError("카카오 인증 코드를 받지 못했습니다.")
        if callback.state != state:
            raise RuntimeError("카카오 인증 응답 검증에 실패했습니다.")

        token = self._exchange_code(callback.code, verifier)
        access_token = str(token.get("access_token") or "")
        if not access_token:
            raise RuntimeError("카카오 인증 토큰을 받지 못했습니다.")

        user = self._fetch_user(access_token)
        provider_user_id = str(user.get("id") or "")
        if not provider_user_id:
            raise RuntimeError("카카오 사용자 식별 정보를 확인할 수 없습니다.")

        account = user.get("kakao_account") if isinstance(user.get("kakao_account"), dict) else {}
        profile = account.get("profile") if isinstance(account.get("profile"), dict) else {}
        nickname = profile.get("nickname") if isinstance(profile, dict) else None
        email = account.get("email") if isinstance(account, dict) else None
        expires_in = int(token.get("expires_in") or 0)
        now = utc_now()
        expires_at = now + timedelta(seconds=max(1, expires_in))

        return AuthSession(
            provider="KAKAO",
            provider_user_id=provider_user_id,
            nickname=str(nickname) if nickname else None,
            email=str(email) if email else None,
            access_token=access_token,
            refresh_token=str(token.get("refresh_token") or "") or None,
            expires_at=expires_at,
            login_at=now,
        )

    def _build_authorize_url(self, *, verifier: str, state: str) -> str:
        self.config.validate_for_kakao()
        params = {
            "response_type": "code",
            "client_id": self.config.kakao_client_id,
            "redirect_uri": self.config.kakao_redirect_uri,
            "code_challenge": code_challenge_s256(verifier),
            "code_challenge_method": "S256",
            "state": state,
        }
        prompt = (self.config.kakao_login_prompt or "").strip()
        if prompt:
            params["prompt"] = prompt
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def _exchange_code(self, code: str, verifier: str) -> dict:
        self.config.validate_for_kakao()
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.config.kakao_client_id,
            "redirect_uri": self.config.kakao_redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
        if self.config.kakao_client_secret:
            payload["client_secret"] = self.config.kakao_client_secret
        log.info("KAKAO_OAUTH CLIENT_ID=%s", self.config.kakao_client_id)
        log.info("KAKAO_OAUTH REDIRECT_URI=%s", self.config.kakao_redirect_uri)
        log.info("KAKAO_OAUTH TOKEN_URL=%s", self.TOKEN_URL)
        log.info(
            "KAKAO_OAUTH TOKEN_PAYLOAD=%s",
            json.dumps(_safe_payload_for_log(payload), ensure_ascii=False),
        )
        resp = requests.post(
            self.TOKEN_URL,
            data=payload,
            timeout=15,
        )
        log.info("KAKAO_OAUTH TOKEN_RESPONSE status=%s body=%s", resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise RuntimeError(f"카카오 토큰 요청에 실패했습니다. ({resp.status_code})\n{resp.text}")
        return resp.json()

    def _fetch_user(self, access_token: str) -> dict:
        resp = requests.get(
            self.USER_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"카카오 사용자 정보 조회에 실패했습니다. ({resp.status_code})")
        return resp.json()


def _friendly_oauth_error(error: str, description: str | None) -> str:
    if error in {"access_denied", "user_cancel"}:
        return "로그인이 취소되었습니다."
    if description:
        return f"카카오 인증에 실패했습니다. ({description})"
    return "카카오 인증에 실패했습니다."


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_payload_for_log(payload: dict[str, str]) -> dict[str, str]:
    data = dict(payload)
    if "client_secret" in data:
        data["client_secret"] = "<configured>"
    return data
