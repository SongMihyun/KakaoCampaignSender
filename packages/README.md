# packages

Reusable Python packages split out from KakaoCampaignSender.

| Package | Purpose |
|---------|---------|
| [kakao_win32](kakao_win32/) | Windows HWND and clipboard helpers |
| [kakao_pc_driver](kakao_pc_driver/) | KakaoTalk PC sending API for FaxSender-style integrations |

The desktop app uses these packages through local path dependencies.

Run `scripts/scaffold_kakao_packages.py` to refresh package implementations
from the original `src/backend/integrations` modules and rewrite imports.
