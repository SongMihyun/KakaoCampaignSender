from __future__ import annotations

import argparse
import sys

from kakao_pc_driver.api import list_kakao_targets, send_self_message, send_to_contact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KakaoTalk PC lightweight send helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_self = sub.add_parser("send-self", help="Send a message to self chat")
    p_self.add_argument("-m", "--message", required=True)
    p_self.add_argument("--my-name", default="", help="Display name for search fallback")

    p_to = sub.add_parser("send-to", help="Send a message to a contact by name")
    p_to.add_argument("-n", "--name", required=True)
    p_to.add_argument("-m", "--message", required=True)

    sub.add_parser("list", help="List Kakao main window targets")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        for target in list_kakao_targets():
            print(f"{target.handle}\t{target.title}")
        return 0

    if args.cmd == "send-self":
        result = send_self_message(args.message, my_name=args.my_name)
    else:
        result = send_to_contact(args.name, args.message)

    if result.ok:
        print("OK")
        return 0
    print(f"FAIL: {result.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
