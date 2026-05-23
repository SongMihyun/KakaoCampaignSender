# kakao-pc-driver

Lightweight KakaoTalk PC automation for sending a self-chat notification or a
single contact message from another Python project such as FaxSender.

## Install From This Monorepo

```toml
# pyproject.toml
kakao-pc-driver = { path = "../KakaoCampaignSender/packages/kakao_pc_driver", develop = true }
```

```powershell
poetry install
```

## Quick Use

```python
from kakao_pc_driver import send_self_message

result = send_self_message("Fax complete: 3 received", my_name="Your Name")
if not result.ok:
    raise RuntimeError(result.reason)
```

## CLI

```powershell
poetry run kakao-send-self send-self -m "Fax complete"
poetry run kakao-send-self list
poetry run kakao-send-self send-to -n "Your Name" -m "Hello"
```

## Requirements

- Windows
- KakaoTalk PC running and signed in
- `kakao-win32`, `pywinauto`, and `pillow`

This package does not depend on PySide6, SQLite, campaign data, or the
KakaoCampaignSender desktop UI.
