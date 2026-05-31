from __future__ import annotations

import webbrowser
from dataclasses import dataclass

from backend.core.app_settings import get_setting


@dataclass(frozen=True)
class SupportSendResult:
    ok: bool
    reason: str = ""


def send_summary_to_operator(message: str) -> SupportSendResult:
    chat_name = str(get_setting("support_chat_name", "카센더 운영자") or "").strip()
    if not chat_name:
        return SupportSendResult(False, "운영자 채팅방 이름이 설정되지 않았습니다.")

    try:
        from kakao_pc_driver import send_to_contact

        result = send_to_contact(chat_name, message)
        return SupportSendResult(bool(result.ok), str(result.reason or ""))
    except Exception as e:
        return SupportSendResult(False, str(e))


def open_support_chat_url() -> SupportSendResult:
    url = str(get_setting("support_openchat_url", "") or "").strip()
    if not url:
        return SupportSendResult(False, "문의 채널이 아직 설정되지 않았습니다.")
    try:
        webbrowser.open(url)
        return SupportSendResult(True)
    except Exception as e:
        return SupportSendResult(False, str(e))
