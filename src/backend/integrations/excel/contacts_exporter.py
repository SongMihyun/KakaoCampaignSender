from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Iterable, Tuple

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter


ContactRow = Tuple[str, str, str, str, str]
HEADERS = ["사번", "이름", "전화번호", "대리점명", "지사명"]


def _apply_sheet_style(ws) -> None:
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5597")
    header_align = Alignment(horizontal="center", vertical="center")

    ws.append(HEADERS)
    ws.freeze_panes = "A2"

    for col in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    ws.row_dimensions[1].height = 20

    widths = [12, 12, 18, 18, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _atomic_save_workbook(wb: Workbook, path: str) -> None:
    path = os.path.abspath(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".__tmp_", suffix=".xlsx", dir=folder)
    os.close(fd)

    try:
        wb.save(tmp_path)
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def _atomic_save_docx(doc: Document, path: str) -> None:
    path = os.path.abspath(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".__tmp_", suffix=".docx", dir=folder)
    os.close(fd)

    try:
        doc.save(tmp_path)
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def _atomic_write_text(path: str, text: str, encoding: str = "utf-8-sig") -> None:
    path = os.path.abspath(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".__tmp_", suffix=os.path.splitext(path)[1] or ".txt", dir=folder)
    os.close(fd)

    try:
        with open(tmp_path, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def create_template_xlsx(path: str) -> None:
    wb = Workbook()

    ws = wb.active
    ws.title = "대상자"
    _apply_sheet_style(ws)

    ws.append(["1001", "홍길동", "01011112222", "강남대리점", "서울"])
    ws.append(["", "김영희", "", "", ""])

    ws2 = wb.create_sheet("안내")
    ws2["A1"] = "입력 규칙"
    ws2["A1"].font = Font(bold=True)
    ws2["A3"] = "1) 이름만 있어도 등록 가능합니다."
    ws2["A4"] = "2) 권장 헤더: 사번 / 이름 / 전화번호 / 대리점명 / 지사명"
    ws2["A5"] = "3) 빈 사번/전화번호는 허용됩니다."
    ws2["A6"] = f"4) 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    _atomic_save_workbook(wb, path)


def create_template_docx(path: str) -> None:
    doc = Document()

    table = doc.add_table(rows=1, cols=len(HEADERS))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"

    hdr = table.rows[0].cells
    for i, h in enumerate(HEADERS):
        hdr[i].text = h

    samples = [
        ("1001", "홍길동", "01011112222", "강남대리점", "서울"),
        ("", "김영희", "", "", ""),
    ]
    for row in samples:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v or "")

    _atomic_save_docx(doc, path)


def create_template_txt(path: str) -> None:
    lines = [
        "사번\t이름\t전화번호\t대리점명\t지사명",
        "1001\t홍길동\t01011112222\t강남대리점\t서울",
        "\t김영희\t\t\t",
        "박민수",
        "최지은",
    ]
    _atomic_write_text(path, "\n".join(lines))


def export_contacts_xlsx(path: str, rows: Iterable[ContactRow]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "대상자"
    _apply_sheet_style(ws)

    for r in rows:
        ws.append(list(r))

    _atomic_save_workbook(wb, path)


def export_contacts_docx(path: str, rows: Iterable[ContactRow]) -> None:
    doc = Document()
    title = doc.add_heading("대상자 내보내기", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    info = doc.add_paragraph(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if info.runs:
        info.runs[0].font.size = Pt(10)

    table = doc.add_table(rows=1, cols=len(HEADERS))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT

    hdr = table.rows[0].cells
    for i, h in enumerate(HEADERS):
        hdr[i].text = h

    for row in rows:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v or "")

    _atomic_save_docx(doc, path)


def export_contacts_txt(path: str, rows: Iterable[ContactRow]) -> None:
    lines = ["\t".join(HEADERS)]
    for row in rows:
        lines.append("\t".join([str(v or "") for v in row]))
    _atomic_write_text(path, "\n".join(lines))
