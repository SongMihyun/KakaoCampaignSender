# FILE: src/backend/integrations/excel/pdf_table_reader.py
from __future__ import annotations

from pathlib import Path

SUPPORTED_PDF_EXTS = {".pdf"}


def is_supported_pdf_file(path: str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_PDF_EXTS


def read_pdf_table_rows(path: str) -> list[list[str]]:
    """
    표 형태 PDF(선/테두리 없는 표 포함)를 행렬(list[list[str]])로 읽는다.

    선 기반 표 인식(pdfplumber의 기본 extract_tables)은 테두리가 없는 표에서
    잘 안 맞는 경우가 많아서, 대신 각 글자의 좌표(x0)를 이용한다:
    - 첫 페이지 첫 줄(헤더로 간주)의 각 단어 x0 위치를 "컬럼 기준선"으로 잡고
    - 이후 모든 줄에서 각 단어를 x0가 가장 가까운 컬럼에 배정한다
    - 같은 컬럼에 배정된 단어가 여러 개면 공백으로 이어붙인다(예: "1차 위촉")
    이렇게 하면 특정 칸이 비어 있거나(컬럼이 밀리지 않음), 값에 공백이
    섞여 있어도(예: "GAK_다온양심보험") 원래 컬럼대로 복원된다.
    페이지마다 헤더가 반복돼도 그대로 두고, 헤더 판별/스킵은 호출 측
    (contacts_importer 등)의 기존 로직에 맡긴다.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError(
            "PDF를 읽으려면 pdfplumber 패키지가 필요합니다. (poetry add pdfplumber)"
        ) from e

    rows: list[list[str]] = []
    col_x0s: list[float] | None = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            if not words:
                continue

            lines = _group_words_into_lines(words)
            if not lines:
                continue

            if col_x0s is None:
                header_words = sorted(lines[0], key=lambda w: w["x0"])
                col_x0s = [w["x0"] for w in header_words]

            for line in lines:
                rows.append(_assign_words_to_columns(line, col_x0s))

    return rows


def _group_words_into_lines(words: list[dict], tolerance: float = 3.0) -> list[list[dict]]:
    """비슷한 top(y) 좌표를 가진 단어들을 한 줄로 묶는다."""
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))

    lines: list[list[dict]] = []
    current: list[dict] = []
    current_top: float | None = None

    for w in words_sorted:
        if current_top is None or abs(w["top"] - current_top) <= tolerance:
            current.append(w)
            if current_top is None:
                current_top = w["top"]
        else:
            lines.append(current)
            current = [w]
            current_top = w["top"]

    if current:
        lines.append(current)

    return lines


def _assign_words_to_columns(line_words: list[dict], col_x0s: list[float]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in col_x0s]

    for w in sorted(line_words, key=lambda w: w["x0"]):
        idx = min(range(len(col_x0s)), key=lambda i: abs(col_x0s[i] - w["x0"]))
        buckets[idx].append(str(w.get("text", "") or ""))

    return [" ".join(b).strip() for b in buckets]
