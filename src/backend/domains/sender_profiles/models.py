from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SenderProfile:
    id: int = 0
    profile_name: str = "기본 발신자"
    sender_name: str = ""
    sender_position: str = ""
    sender_company: str = ""
    sender_branch: str = ""
    sender_phone: str = ""
    default_signature: str = ""
    is_default: int = 1
    is_active: int = 1
    created_at: str = ""
    updated_at: str = ""
