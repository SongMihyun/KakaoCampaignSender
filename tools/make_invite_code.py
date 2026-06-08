from __future__ import annotations

import argparse
import hashlib
import secrets
import string
from datetime import date


ALPHABET = string.ascii_uppercase + string.digits


def normalize_invite_code(value: str) -> str:
    return "".join(str(value or "").strip().upper().split())


def new_invite_code() -> str:
    part1 = "".join(secrets.choice(ALPHABET) for _ in range(4))
    part2 = "".join(secrets.choice(ALPHABET) for _ in range(4))
    return f"KS-BETA-{part1}-{part2}"


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sql_quote(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Kasender beta invite code hash and D1 insert SQL.")
    parser.add_argument("--code", default="", help="Optional invite code. If omitted, a new code is generated.")
    parser.add_argument("--label", default="카센더 베타 초대 코드")
    parser.add_argument("--role", default="user")
    parser.add_argument("--max-uses", type=int, default=1)
    parser.add_argument("--expires-at", default="2026-12-31")
    parser.add_argument("--created-by", default="admin")
    parser.add_argument("--memo", default="초기 베타 테스트용")
    args = parser.parse_args()

    raw_code = args.code or new_invite_code()
    normalized = normalize_invite_code(raw_code)
    code_hash = sha256_hex(normalized)

    print("초대 코드 원문:")
    print(normalized)
    print()
    print("SHA-256 code_hash:")
    print(code_hash)
    print()
    print("D1 INSERT SQL:")
    print(
        "INSERT INTO invite_codes (\n"
        "    code_hash,\n"
        "    label,\n"
        "    status,\n"
        "    max_uses,\n"
        "    used_count,\n"
        "    role,\n"
        "    expires_at,\n"
        "    created_by,\n"
        "    memo\n"
        ") VALUES (\n"
        f"    {sql_quote(code_hash)},\n"
        f"    {sql_quote(args.label)},\n"
        "    'active',\n"
        f"    {max(1, args.max_uses)},\n"
        "    0,\n"
        f"    {sql_quote(args.role)},\n"
        f"    {sql_quote(args.expires_at or date.today().isoformat())},\n"
        f"    {sql_quote(args.created_by)},\n"
        f"    {sql_quote(args.memo)}\n"
        ");"
    )


if __name__ == "__main__":
    main()
