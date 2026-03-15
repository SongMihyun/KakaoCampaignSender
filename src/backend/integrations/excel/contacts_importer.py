from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from openpyxl import load_workbook


PreviewRow = Tuple[str, str, str, str, str]  # (emp_id, name, phone, agency, branch)


_HEADER_ALIASES: dict[str, set[str]] = {
    "emp_id": {"사번", "사원번호", "empid", "emp_id", "employeeid", "employee_id", "id"},
    "name": {"이름", "성명", "name"},
    "phone": {"전화번호", "전화", "휴대폰", "휴대전화", "연락처", "phone", "mobile", "tel"},
    "agency": {"대리점명", "대리점", "agency"},
    "branch": {"지사명", "지사", "branch"},
}

_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
_SUPPORTED_EXTS = {".xlsx", ".xlsm", ".docx", ".txt", ".csv", ".tsv"}


@dataclass
class ImportResult:
    rows: List[PreviewRow]
    skipped: int
    errors: List[str]


def supported_contact_import_exts() -> set[str]:
    return set(_SUPPORTED_EXTS)


def is_supported_contact_import_file(path: str) -> bool:
    return Path(path).suffix.lower() in _SUPPORTED_EXTS


def import_contacts_file(path: str) -> ImportResult:
    ext = Path(path).suffix.lower()

    try:
        if ext in {".xlsx", ".xlsm"}:
            raw_rows = _read_xlsx_rows(path)
        elif ext == ".docx":
            raw_rows = _read_docx_rows(path)
        elif ext in {".txt", ".csv", ".tsv"}:
            raw_rows = _read_text_rows(path)
        else:
            return ImportResult(
                rows=[],
                skipped=0,
                errors=["지원하지 않는 파일 형식입니다. 지원 확장자: .xlsx, .xlsm, .docx, .txt, .csv, .tsv"],
            )
    except Exception as e:
        return ImportResult(rows=[], skipped=0, errors=[f"파일 파싱 실패: {e}"])

    return _build_import_result(raw_rows)


def import_contacts_text(text: str) -> ImportResult:
    try:
        raw_rows = _rows_from_text_blob(text)
    except Exception as e:
        return ImportResult(rows=[], skipped=0, errors=[f"붙여넣기 파싱 실패: {e}"])
    return _build_import_result(raw_rows)


# 하위 호환용

def import_contacts_xlsx(path: str) -> ImportResult:
    return import_contacts_file(path)


def _read_xlsx_rows(path: str) -> list[list[str]]:
    wb = load_workbook(filename=path, data_only=True)
    ws = wb.active

    rows: list[list[str]] = []
    for row in ws.iter_rows(values_only=True):
        rows.append([_normalize_cell(v) for v in row])
    return rows


def _read_text_rows(path: str) -> list[list[str]]:
    text = _read_text_file(path)
    return _rows_from_text_blob(text)


def _rows_from_text_blob(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            rows.append([])
            continue
        rows.append(_split_text_line(line))
    return rows


def _read_text_file(path: str) -> str:
    last_error: Exception | None = None
    for enc in _TEXT_ENCODINGS:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError as e:
            last_error = e
            continue

    if last_error is not None:
        raise last_error

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_docx_rows(path: str) -> list[list[str]]:
    with zipfile.ZipFile(path) as zf:
        try:
            xml_bytes = zf.read("word/document.xml")
        except KeyError as e:
            raise ValueError("Word 문서에서 본문(word/document.xml)을 찾을 수 없습니다.") from e

    root = ET.fromstring(xml_bytes)
    body = root.find("w:body", _DOCX_NS)
    if body is None:
        return []

    rows: list[list[str]] = []
    for child in list(body):
        tag = _local_name(child.tag)
        if tag == "tbl":
            rows.extend(_extract_docx_table_rows(child))
        elif tag == "p":
            text = _extract_docx_paragraph_text(child)
            if text:
                rows.append(_split_text_line(text))
    return rows


def _extract_docx_table_rows(tbl_el: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in tbl_el.findall("w:tr", _DOCX_NS):
        cells: list[str] = []
        for tc in tr.findall("w:tc", _DOCX_NS):
            parts = [t.text or "" for t in tc.findall(".//w:t", _DOCX_NS)]
            cell_text = _cleanup_text("".join(parts))
            cells.append(cell_text)
        rows.append(cells)
    return rows


def _extract_docx_paragraph_text(p_el: ET.Element) -> str:
    parts = [t.text or "" for t in p_el.findall(".//w:t", _DOCX_NS)]
    return _cleanup_text("".join(parts))


def _build_import_result(raw_rows: Sequence[Sequence[str]]) -> ImportResult:
    cleaned_rows = [_trim_row(row) for row in raw_rows]
    cleaned_rows = [row for row in cleaned_rows if row]

    if not cleaned_rows:
        return ImportResult(rows=[], skipped=0, errors=[])

    rows: list[PreviewRow] = []
    skipped = 0
    active_header_map: dict[str, int] | None = None

    for raw in cleaned_rows:
        detected_header = _detect_header_map(raw)
        if detected_header:
            active_header_map = detected_header
            continue

        rec = _row_to_record(raw, active_header_map)
        name = _cleanup_name(rec["name"])
        if not name:
            skipped += 1
            continue

        rows.append(
            (
                rec["emp_id"],
                name,
                rec["phone"],
                rec["agency"],
                rec["branch"],
            )
        )

    return ImportResult(rows=rows, skipped=skipped, errors=[])


def _detect_header_map(row: Sequence[str]) -> dict[str, int] | None:
    mapped: dict[str, int] = {}

    for idx, cell in enumerate(row):
        key = _map_header(cell)
        if key and key not in mapped:
            mapped[key] = idx

    if not mapped:
        return None

    if "name" in mapped or len(mapped) >= 2:
        return mapped
    return None


def _row_to_record(row: Sequence[str], header_map: dict[str, int] | None) -> dict[str, str]:
    if header_map:
        return {
            "emp_id": _get_cell(row, header_map.get("emp_id")),
            "name": _get_cell(row, header_map.get("name")),
            "phone": _get_cell(row, header_map.get("phone")),
            "agency": _get_cell(row, header_map.get("agency")),
            "branch": _get_cell(row, header_map.get("branch")),
        }

    values = [_cleanup_text(v) for v in row if _cleanup_text(v)]
    if not values:
        return {"emp_id": "", "name": "", "phone": "", "agency": "", "branch": ""}

    if len(values) == 1:
        return {"emp_id": "", "name": values[0], "phone": "", "agency": "", "branch": ""}

    starts_with_emp_id = _looks_like_emp_id(values[0]) and len(values) >= 2 and _looks_like_nameish(values[1])
    if starts_with_emp_id:
        return {
            "emp_id": values[0],
            "name": values[1] if len(values) >= 2 else "",
            "phone": values[2] if len(values) >= 3 else "",
            "agency": values[3] if len(values) >= 4 else "",
            "branch": values[4] if len(values) >= 5 else "",
        }

    if len(values) == 2 and _looks_like_phone(values[1]):
        return {"emp_id": "", "name": values[0], "phone": values[1], "agency": "", "branch": ""}

    return {
        "emp_id": "",
        "name": values[0],
        "phone": values[1] if len(values) >= 2 else "",
        "agency": values[2] if len(values) >= 3 else "",
        "branch": values[3] if len(values) >= 4 else "",
    }


def _split_text_line(line: str) -> list[str]:
    raw = (line or "").rstrip("\r\n")
    if not raw.strip():
        return []

    delimiters = ("\t", "|", ";", ",")
    for delim in delimiters:
        if delim in raw:
            row = next(csv.reader(io.StringIO(raw), delimiter=delim))
            return [_cleanup_text(cell) for cell in row]

    return [_cleanup_name(raw)]


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return len(digits) >= 8


def _looks_like_emp_id(value: str) -> bool:
    x = (value or "").strip()
    if not x:
        return False
    if _looks_like_phone(x):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{2,20}", x))


def _looks_like_nameish(value: str) -> bool:
    x = _cleanup_text(value)
    if not x:
        return False
    if _looks_like_phone(x):
        return False
    return bool(re.search(r"[A-Za-z가-힣]", x))


def _map_header(cell: str) -> str | None:
    key = _normalize_header(cell)
    if not key:
        return None

    for field, aliases in _HEADER_ALIASES.items():
        if key in aliases:
            return field
    return None


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).casefold()


def _normalize_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value)).strip()
    return str(value).strip()


def _cleanup_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _cleanup_name(value: str) -> str:
    x = _cleanup_text(value)
    x = re.sub(r"^[\u2022\-\*•·]+\s*", "", x)
    x = re.sub(r"^\d+[\.)]\s*", "", x)
    return x.strip("\"'").strip()


def _trim_row(row: Sequence[str]) -> list[str]:
    values = [_cleanup_text(v) for v in row]
    while values and not values[-1]:
        values.pop()
    return values


def _get_cell(row: Sequence[str], idx: int | None) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return _cleanup_text(row[idx])


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag
