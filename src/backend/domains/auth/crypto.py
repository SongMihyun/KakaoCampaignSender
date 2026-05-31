from __future__ import annotations

import base64
import os


def protect_bytes(data: bytes) -> str:
    try:
        import win32crypt  # type: ignore

        encrypted = win32crypt.CryptProtectData(data, "KakaoCampaignSender Auth", None, None, None, 0)
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        key = _fallback_key()
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return "xor:" + base64.b64encode(xored).decode("ascii")


def unprotect_bytes(value: str) -> bytes:
    if value.startswith("dpapi:"):
        import win32crypt  # type: ignore

        encrypted = base64.b64decode(value.removeprefix("dpapi:"))
        return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
    if value.startswith("xor:"):
        raw = base64.b64decode(value.removeprefix("xor:"))
        key = _fallback_key()
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return base64.b64decode(value)


def _fallback_key() -> bytes:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    computer = os.environ.get("COMPUTERNAME") or "local"
    seed = f"KakaoCampaignSender:{user}:{computer}".encode("utf-8")
    return seed or b"KakaoCampaignSender"
