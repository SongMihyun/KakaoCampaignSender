"""Example: send a KakaoTalk PC self-chat notification.

Run:
  poetry install
  poetry run python examples/send_self.py "fax complete"
"""
from __future__ import annotations

import sys

from kakao_pc_driver import list_kakao_targets, send_self_message


def main() -> int:
    msg = " ".join(sys.argv[1:]).strip() or "Kakao/FaxSender integration test"
    targets = list_kakao_targets()
    if not targets:
        print("KakaoTalk PC window not found. Please run and sign in to KakaoTalk PC.")
        return 1
    print(f"Target: {targets[0].title} (hwnd={targets[0].handle})")
    result = send_self_message(msg, my_name="")
    if result.ok:
        print("Sent")
        return 0
    print(f"Failed: {result.reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
