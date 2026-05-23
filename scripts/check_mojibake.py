from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_ROOTS = ("src", "packages", "scripts")

# Common UTF-8/CP949 mojibake markers seen in Korean UI text after a bad save.
MOJIBAKE_MARKERS = re.compile(
    r"[諛洹湲臾利덉띾좏由놁誘껜럹鍮쒖넚떆룄낯쓬깮븯젙쫫"
    r"ㅻ덈꾩ㅽ痍醫濡移댁뭅踰뚯쒕곸섏쾲꾨룞젣熬撚嫄媛]"
)
SUSPICIOUS_NO_KOREAN = re.compile(r"[\u4e00-\u9fff\u3130-\u318f]|�|\?{2,}")
KOREAN = re.compile(r"[가-힣]")


def iter_python_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths or list(DEFAULT_ROOTS):
        path = Path(raw)
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.py"))
    return sorted(set(files))


def string_literals(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((node.lineno, node.value))
    return found


def is_suspicious(value: str) -> bool:
    if MOJIBAKE_MARKERS.search(value):
        return True
    return bool(SUSPICIOUS_NO_KOREAN.search(value) and not KOREAN.search(value))


def main(argv: list[str]) -> int:
    bad: list[tuple[Path, int, str]] = []
    self_path = Path(__file__).resolve()
    for path in iter_python_files(argv[1:]):
        if path.resolve() == self_path:
            continue
        try:
            literals = string_literals(path)
        except UnicodeDecodeError as exc:
            bad.append((path, 1, f"file is not valid UTF-8: {exc}"))
            continue
        except SyntaxError:
            continue

        for line_no, value in literals:
            if is_suspicious(value):
                snippet = value.replace("\n", " | ")
                bad.append((path, line_no, snippet[:160]))

    if bad:
        print("Mojibake-looking UI strings found:")
        for path, line_no, snippet in bad:
            print(f"{path}:{line_no}: {snippet}")
        return 1

    print("No mojibake-looking Python string literals found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
