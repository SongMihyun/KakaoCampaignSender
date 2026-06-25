from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SUPPORTED_VARIABLES: tuple[str, ...] = (
    "카카오톡검색명",
    "고객명",
    "고객호칭",
    "고객직책",
    "고객소속",
    "지사명",
    "연락처",
    "발신자명",
    "발신자직책",
    "발신자소속",
    "발신자지사",
    "발신자연락처",
    "기본서명",
)


def build_variable_values(contact: Any = None, sender_profile: Any = None) -> dict[str, Any]:
    return {
        "카카오톡검색명": _first_value(contact, "name"),
        "고객명": _first_value(contact, "customer_name"),
        "고객호칭": _first_value(contact, "customer_honorific"),
        "고객직책": _first_value(contact, "customer_position"),
        "고객소속": _first_value(contact, "company", "company_name", "agency"),
        "지사명": _first_value(contact, "branch", "branch_name"),
        "연락처": _first_value(contact, "phone"),
        "발신자명": _first_value(sender_profile, "sender_name"),
        "발신자직책": _first_value(sender_profile, "sender_position"),
        "발신자소속": _first_value(sender_profile, "sender_company"),
        "발신자지사": _first_value(sender_profile, "sender_branch"),
        "발신자연락처": _first_value(sender_profile, "sender_phone"),
        "기본서명": _first_value(sender_profile, "default_signature"),
    }


def _first_value(source: Any, *keys: str) -> Any:
    for key in keys:
        value = _get_value(source, key)
        if value is not None:
            return value
    return None


def _get_value(source: Any, key: str) -> Any:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
