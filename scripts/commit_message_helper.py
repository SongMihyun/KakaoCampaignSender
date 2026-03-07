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
    (".githooks/prepare-commit-msg", "prepare-commit-msg 훅 실행 안정화"),
    ("scripts/commit_message_helper.py", "인터랙티브 커밋 메시지 헬퍼 개선"),
    ("scripts/git_editor_wrapper.py", "커밋 메시지 생성 시 에디터 실행 생략"),
    ("scripts/install_git_hooks.ps1", "윈도우용 git hook 설치 스크립트 안정화"),
    (".gitattributes", "git hook 스크립트 LF 규칙 고정"),
    ("src/frontend/pages/contacts/", "대상자 페이지 수정 흐름 정리"),
    ("src/frontend/pages/groups/", "그룹 멤버 수정 흐름 정리"),
    ("src/frontend/pages/sending/", "발송 미리보기 수정 흐름 정리"),
    ("src/frontend/utils/contact_edit.py", "공통 대상자 수정 유틸 정리"),
    ("src/backend/updates/", "업데이트 종료 후처리 흐름 정리"),
    ("src/frontend/app/main_window.py", "메인 윈도우 조립 및 종료 흐름 정리"),
]

COMBINATION_SUBJECT_RULES: list[dict[str, object]] = [
    {
        "all_of": [
            ".githooks/prepare-commit-msg",
            "scripts/commit_message_helper.py",
            "scripts/git_editor_wrapper.py",
        ],
        "subject": "인터랙티브 git 커밋 헬퍼 흐름 안정화",
    },
    {
        "all_of": [
            ".githooks/prepare-commit-msg",
            "scripts/commit_message_helper.py",
            "scripts/install_git_hooks.ps1",
        ],
        "subject": "git hook 기반 커밋 메시지 흐름 정리",
    },
    {
        "all_of": [
            ".githooks/prepare-commit-msg",
            "scripts/commit_message_helper.py",
            "scripts/git_editor_wrapper.py",
            "scripts/install_git_hooks.ps1",
            ".gitattributes",
        ],
        "subject": "인터랙티브 커밋 메시지 헬퍼 설정 마무리",
    },
    {
        "all_of": [
            "src/frontend/utils/contact_edit.py",
            "src/frontend/pages/contacts/",
            "src/frontend/pages/groups/",
            "src/frontend/pages/sending/",
        ],
        "subject": "대상자 수정 흐름을 공통 모듈로 통합",
    },
    {
        "all_of": [
            "src/frontend/utils/contact_edit.py",
            "src/frontend/pages/contacts/",
        ],
        "subject": "대상자 페이지에 공통 수정 흐름 적용",
    },
    {
        "all_of": [
            "src/frontend/utils/contact_edit.py",
            "src/frontend/pages/groups/",
        ],
        "subject": "그룹 멤버 화면에 공통 수정 흐름 적용",
    },
    {
        "all_of": [
            "src/frontend/utils/contact_edit.py",
            "src/frontend/pages/sending/",
        ],
        "subject": "발송 미리보기에 공통 수정 흐름 적용",
    },
    {
        "all_of": [
            "src/backend/updates/updater.py",
            "src/frontend/app/main_window.py",
        ],
        "subject": "앱 종료 시 업데이트 연동 흐름 마무리",
    },
    {
        "all_of": [
            "src/frontend/pages/contacts/",
            "src/frontend/utils/contact_edit.py",
        ],
        "subject": "대상자 수정창 진입 경로를 공통 유틸로 통일",
    },
    {
        "all_of": [
            "src/frontend/pages/contacts/",
            "src/frontend/pages/groups/",
            "src/frontend/pages/sending/",
        ],
        "subject": "페이지별 대상자 수정 UX를 동일 흐름으로 정리",
    },
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


def any_path_matches(files: list[str], prefix: str) -> bool:
    return any(file_path.startswith(prefix) for file_path in files)


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


def infer_combination_subject_candidates(files: list[str]) -> list[str]:
    results: list[tuple[int, str]] = []

    for rule in COMBINATION_SUBJECT_RULES:
        prefixes = rule.get("all_of", [])
        subject = str(rule.get("subject", "")).strip()
        if not prefixes or not subject:
            continue

        if all(any_path_matches(files, str(prefix)) for prefix in prefixes):
            weight = sum(len(str(prefix)) for prefix in prefixes)
            results.append((weight, subject))

    results.sort(key=lambda x: (-x[0], x[1]))
    ordered: list[str] = []
    for _, subject in results:
        if subject not in ordered:
            ordered.append(subject)
    return ordered


def korean_scope_name(scope: str) -> str:
    mapping = {
        "contacts": "대상자",
        "groups": "그룹",
        "campaigns": "캠페인",
        "sending": "발송",
        "logs": "로그",
        "reports": "리포트",
        "updates": "업데이트",
        "frontend": "프론트엔드",
        "backend": "백엔드",
        "ui": "UI",
        "excel": "엑셀",
        "windows": "윈도우",
        "core": "코어",
        "db": "DB",
        "app": "앱",
        "infra": "인프라",
    }
    return mapping.get(scope, scope)


def generic_subjects(commit_type: str, scope: str) -> list[str]:
    scope_ko = korean_scope_name(scope)

    mapping: dict[str, list[str]] = {
        "feat": [
            f"{scope_ko} 기능 추가",
            f"{scope_ko} 기능 확장",
            f"{scope_ko} 처리 지원 추가",
        ],
        "fix": [
            f"{scope_ko} 동작 오류 수정",
            f"{scope_ko} 예외 케이스 수정",
            f"{scope_ko} 처리 버그 수정",
        ],
        "refactor": [
            f"{scope_ko} 구조 정리",
            f"{scope_ko} 흐름 정리",
            f"{scope_ko} 로직 정리",
        ],
        "perf": [
            f"{scope_ko} 성능 개선",
            f"{scope_ko} 처리 속도 개선",
            f"{scope_ko} 응답성 개선",
        ],
        "docs": [
            f"{scope_ko} 문서 업데이트",
            f"{scope_ko} 사용 방법 문서화",
        ],
        "test": [
            f"{scope_ko} 테스트 추가",
            f"{scope_ko} 테스트 범위 보강",
        ],
        "chore": [
            f"{scope_ko} 설정 정리",
            f"{scope_ko} 유지보수 작업 반영",
            f"{scope_ko} 구성 업데이트",
        ],
        "build": [
            f"{scope_ko} 빌드 설정 업데이트",
        ],
        "ci": [
            f"{scope_ko} CI 설정 업데이트",
        ],
        "style": [
            f"{scope_ko} 포맷 정리",
        ],
        "revert": [
            f"{scope_ko} 변경 롤백",
        ],
    }

    return mapping.get(commit_type, [f"{scope_ko} 변경 반영"])


def infer_subject_candidates(files: list[str], commit_type: str, scope: str) -> list[str]:
    ordered: list[str] = []

    for subject in infer_combination_subject_candidates(files):
        if subject not in ordered:
            ordered.append(subject)

    score: dict[str, int] = {}
    for file_path in files:
        for prefix, subject in SUBJECT_HINT_RULES:
            if file_path.startswith(prefix):
                score[subject] = score.get(subject, 0) + len(prefix)

    ranked = sorted(score.items(), key=lambda x: (-x[1], x[0]))
    for subject, _ in ranked:
        if subject not in ordered:
            ordered.append(subject)

    for subject in generic_subjects(commit_type, scope):
        if subject not in ordered:
            ordered.append(subject)

    return ordered[:7]


def ask_choice(title: str, items: list[tuple[str, str]], default_key: str | None = None) -> str:
    while True:
        print()
        print(title)
        for i, (key, desc) in enumerate(items, start=1):
            suffix = "  [추천]" if default_key == key else ""
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
            suffix = "  [추천]" if scope in recommended[:3] else ""
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
            suffix = "  [추천]" if i == 1 else ""
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
                custom = input("subject 입력: ").strip()
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