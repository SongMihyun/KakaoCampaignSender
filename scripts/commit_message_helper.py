# FILE: scripts/commit_message_helper.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TYPES: list[tuple[str, str]] = [
    ("feat", "기능 추가"),
    ("fix", "버그 수정"),
    ("refactor", "구조 개선 / 로직 정리"),
    ("perf", "성능 개선"),
    ("docs", "문서 변경"),
    ("test", "테스트 추가/수정"),
    ("chore", "기타 유지보수"),
    ("build", "빌드 설정"),
    ("ci", "CI/CD 설정"),
    ("style", "포맷/스타일 정리"),
    ("revert", "되돌리기"),
]

SCOPES: list[str] = [
    "contacts",
    "groups",
    "campaigns",
    "sending",
    "logs",
    "reports",
    "updates",
    "frontend",
    "backend",
    "ui",
    "excel",
    "windows",
    "core",
    "db",
    "app",
    "infra",
]

SCOPE_RULES: list[tuple[str, str]] = [
    ("src/frontend/pages/contacts/", "contacts"),
    ("src/backend/domains/contacts/", "contacts"),
    ("src/frontend/pages/groups/", "groups"),
    ("src/backend/domains/groups/", "groups"),
    ("src/frontend/pages/campaigns/", "campaigns"),
    ("src/backend/domains/campaigns/", "campaigns"),
    ("src/frontend/pages/sending/", "sending"),
    ("src/backend/domains/sending/", "sending"),
    ("src/backend/domains/send_lists/", "sending"),
    ("src/frontend/pages/logs/", "logs"),
    ("src/backend/domains/logs/", "logs"),
    ("src/backend/domains/reports/", "reports"),
    ("src/backend/updates/", "updates"),
    ("src/backend/database/", "db"),
    ("src/backend/integrations/excel/", "excel"),
    ("src/backend/integrations/windows/", "windows"),
    ("src/backend/core/", "core"),
    ("src/frontend/", "frontend"),
    ("src/backend/", "backend"),
    ("src/app/", "app"),
    ("scripts/", "infra"),
    (".githooks/", "infra"),
    (".github/", "ci"),
]

TYPE_RULES: list[tuple[str, str]] = [
    ("docs/", "docs"),
    (".github/", "ci"),
    ("scripts/", "chore"),
    (".githooks/", "chore"),
]

SUBJECT_HINT_RULES: list[tuple[str, str]] = [
    (".githooks/prepare-commit-msg", "stabilize prepare-commit-msg hook execution"),
    ("scripts/commit_message_helper.py", "improve interactive commit message helper"),
    ("scripts/git_editor_wrapper.py", "skip editor when commit message is already generated"),
    ("scripts/install_git_hooks.ps1", "stabilize git hook installation on windows"),
    (".gitattributes", "enforce lf for git hook scripts"),
    ("src/frontend/pages/contacts/", "unify contact edit flow"),
    ("src/frontend/pages/groups/", "centralize group contact edit handling"),
    ("src/frontend/pages/sending/", "centralize send preview contact edit handling"),
    ("src/backend/updates/", "finalize update flow cleanup"),
]


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def run_git(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            return ""
        return (completed.stdout or "").strip()
    except Exception:
        return ""


def get_staged_files() -> list[str]:
    out = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    if not out:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def is_effective_commit_message_text(text: str) -> bool:
    if not text:
        return False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        return True
    return False


def read_existing_message(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def infer_scope_candidates(files: list[str]) -> list[str]:
    score: dict[str, int] = {}

    for file_path in files:
        for prefix, scope in SCOPE_RULES:
            if file_path.startswith(prefix):
                score[scope] = score.get(scope, 0) + len(prefix)

    if not score:
        return []

    ranked = sorted(score.items(), key=lambda x: (-x[1], x[0]))
    return [scope for scope, _ in ranked]


def infer_type_candidate(files: list[str]) -> str | None:
    score: dict[str, int] = {}

    for file_path in files:
        matched = False
        for prefix, commit_type in TYPE_RULES:
            if file_path.startswith(prefix):
                score[commit_type] = score.get(commit_type, 0) + len(prefix)
                matched = True
        if matched:
            continue

        if "test" in file_path.lower():
            score["test"] = score.get("test", 0) + 3
        elif "perf" in file_path.lower():
            score["perf"] = score.get("perf", 0) + 3
        elif file_path.endswith(".md"):
            score["docs"] = score.get("docs", 0) + 2
        else:
            score["refactor"] = score.get("refactor", 0) + 1

    if not score:
        return None

    ranked = sorted(score.items(), key=lambda x: (-x[1], x[0]))
    return ranked[0][0]


def infer_subject_candidates(files: list[str], commit_type: str, scope: str) -> list[str]:
    score: dict[str, int] = {}

    for file_path in files:
        for prefix, subject in SUBJECT_HINT_RULES:
            if file_path.startswith(prefix):
                score[subject] = score.get(subject, 0) + len(prefix)

    if not score:
        generic = {
            "feat": f"add {scope} improvements",
            "fix": f"fix {scope} issues",
            "refactor": f"refine {scope} structure",
            "perf": f"optimize {scope} performance",
            "docs": f"update {scope} documentation",
            "test": f"add {scope} tests",
            "chore": f"maintain {scope} setup",
            "build": f"update {scope} build setup",
            "ci": f"update {scope} ci workflow",
            "style": f"clean up {scope} formatting",
            "revert": f"revert {scope} changes",
        }
        return [generic.get(commit_type, f"update {scope}")]

    ranked = sorted(score.items(), key=lambda x: (-x[1], x[0]))
    ordered = [subject for subject, _ in ranked]

    generic = {
        "feat": f"add {scope} improvements",
        "fix": f"fix {scope} issues",
        "refactor": f"refine {scope} structure",
        "perf": f"optimize {scope} performance",
        "docs": f"update {scope} documentation",
        "test": f"add {scope} tests",
        "chore": f"maintain {scope} setup",
        "build": f"update {scope} build setup",
        "ci": f"update {scope} ci workflow",
        "style": f"clean up {scope} formatting",
        "revert": f"revert {scope} changes",
    }
    fallback = generic.get(commit_type, f"update {scope}")
    if fallback not in ordered:
        ordered.append(fallback)

    return ordered[:5]


def ask_choice(title: str, items: list[tuple[str, str]], default_key: str | None = None) -> str:
    while True:
        print()
        print(title)
        for i, (key, desc) in enumerate(items, start=1):
            suffix = "  [recommended]" if default_key == key else ""
            print(f"  {i}. {key:<10} - {desc}{suffix}")

        prompt = "번호를 선택하세요"
        if default_key:
            prompt += " (엔터=추천값)"
        prompt += ": "

        try:
            raw = input(prompt).strip()
        except EOFError:
            return default_key or items[0][0]

        if not raw and default_key:
            return default_key

        try:
            idx = int(raw)
            if 1 <= idx <= len(items):
                return items[idx - 1][0]
        except Exception:
            pass

        print("잘못된 입력입니다. 다시 선택하세요.")


def ask_scope(recommended: list[str]) -> str:
    menu: list[str] = []

    for scope in recommended:
        if scope not in menu:
            menu.append(scope)

    for scope in SCOPES:
        if scope not in menu:
            menu.append(scope)

    while True:
        print()
        print("scope를 선택하세요")
        if recommended:
            print(f"추천 scope: {', '.join(recommended[:3])}")

        for i, scope in enumerate(menu, start=1):
            suffix = "  [recommended]" if scope in recommended[:3] else ""
            print(f"  {i}. {scope}{suffix}")
        print(f"  {len(menu) + 1}. custom")

        try:
            raw = input("번호를 선택하세요 (엔터=첫 추천값): ").strip()
        except EOFError:
            return recommended[0] if recommended else menu[0]

        if not raw and recommended:
            return recommended[0]

        try:
            idx = int(raw)
            if 1 <= idx <= len(menu):
                return menu[idx - 1]
            if idx == len(menu) + 1:
                custom = input("custom scope 입력: ").strip().lower()
                if custom:
                    return custom
        except EOFError:
            return recommended[0] if recommended else menu[0]
        except Exception:
            pass

        print("잘못된 입력입니다. 다시 선택하세요.")


def ask_subject(candidates: list[str]) -> str:
    while True:
        print()
        print("subject를 선택하거나 직접 입력하세요")
        for i, candidate in enumerate(candidates, start=1):
            suffix = "  [recommended]" if i == 1 else ""
            print(f"  {i}. {candidate}{suffix}")
        print(f"  {len(candidates) + 1}. custom")

        try:
            raw = input("번호를 선택하세요 (엔터=첫 추천값): ").strip()
        except EOFError:
            return candidates[0]

        if not raw:
            return candidates[0]

        try:
            idx = int(raw)
            if 1 <= idx <= len(candidates):
                return candidates[idx - 1]
            if idx == len(candidates) + 1:
                custom = input("subject 입력 (영문 권장, 소문자 시작): ").strip()
                custom = " ".join(custom.split())

                if not custom:
                    print("subject는 비어 있을 수 없습니다.")
                    continue

                if custom.endswith("."):
                    custom = custom[:-1].rstrip()

                if len(custom) > 72:
                    print("subject가 너무 깁니다. 72자 이내 권장입니다.")
                    continue

                return custom
        except EOFError:
            return candidates[0]
        except Exception:
            pass

        print("잘못된 입력입니다. 다시 선택하세요.")


def ask_body() -> str:
    print()
    print("body를 입력할까요?")
    print("  1. 없음")
    print("  2. 직접 입력")
    try:
        raw = input("선택 (엔터=없음): ").strip()
    except EOFError:
        return ""

    if raw != "2":
        return ""

    print()
    print("body를 여러 줄로 입력하세요. 빈 줄 2번 입력 시 종료합니다.")
    lines: list[str] = []
    blank_count = 0

    while True:
        try:
            line = input()
        except EOFError:
            break

        if not line.strip():
            blank_count += 1
            if blank_count >= 2:
                break
            lines.append("")
            continue

        blank_count = 0
        lines.append(line.rstrip())

    return "\n".join(lines).strip()


def build_message() -> str:
    staged_files = get_staged_files()
    recommended_scopes = infer_scope_candidates(staged_files)
    recommended_type = infer_type_candidate(staged_files)

    print()
    print("staged files:")
    if staged_files:
        for file_path in staged_files[:30]:
            print(f"  - {file_path}")
        if len(staged_files) > 30:
            print(f"  ... and {len(staged_files) - 30} more")
    else:
        print("  (없음)")

    commit_type = ask_choice("type을 선택하세요", TYPES, default_key=recommended_type)
    scope = ask_scope(recommended_scopes)
    subject_candidates = infer_subject_candidates(staged_files, commit_type, scope)
    subject = ask_subject(subject_candidates)
    body = ask_body()

    header = f"{commit_type}({scope}): {subject}"

    if body:
        return f"{header}\n\n{body}\n"
    return f"{header}\n"


def should_skip(source: str, existing_message: str) -> bool:
    source = (source or "").strip().lower()

    if source == "message":
        return True

    if source in {"merge", "squash"}:
        return True

    if is_effective_commit_message_text(existing_message):
        return True

    return False


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: commit_message_helper.py <commit_msg_file> [source]", file=sys.stderr)
        return 1

    msg_file = Path(sys.argv[1]).resolve()
    source = sys.argv[2] if len(sys.argv) >= 3 else ""

    existing_message = read_existing_message(msg_file)

    if should_skip(source, existing_message):
        return 0

    if not is_interactive():
        return 0

    print()
    print("=" * 72)
    print(" Commit Message Helper")
    print("=" * 72)

    try:
        message = build_message()
    except KeyboardInterrupt:
        print("\n커밋 메시지 입력이 취소되었습니다.")
        return 1

    msg_file.parent.mkdir(parents=True, exist_ok=True)
    msg_file.write_text(message, encoding="utf-8")

    print()
    print("생성된 커밋 메시지:")
    print("-" * 72)
    print(message.rstrip())
    print("-" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())