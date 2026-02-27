# src/app/version.py
from __future__ import annotations

__app_name__ = "KakaoCampaignSender"   # 내부 식별자(유지 권장)
__display_name__ = "카센더"            # ✅ UI/바로가기 표기용

__version__ = "__VERSION__"  # CI replaces this token

# ✅ "latest" 릴리즈 기준 latest.json으로 자동 접근 (고정 URL)
LATEST_JSON_URL = "https://github.com/SongMihyun/KakaoCampaignSender/releases/latest/download/latest.json"