from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.integrations.excel.tabular_editor_io import (
    is_supported_text_editor_file,
    is_supported_word_editor_file,
    load_text_grid,
    load_word_grid,
    save_workbook_grid_to_docx,
    save_workbook_grid_to_text,
    suggest_text_save_path,
    suggest_word_save_path,
)
from backend.integrations.vcard_contacts import is_supported_vcard_file, load_vcard_contacts

try:
    from backend.integrations.excel.workbook_editor_io import (
        is_supported_excel_editor_file,
        load_workbook_grid,
    )
except ImportError:
    from backend.integrations.excel.workbook_editor_io import (  # type: ignore
        is_supported_excel_editor_file,
        load_workbook_for_editor as load_workbook_grid,
    )

from backend.integrations.windows.win_file_picker import Filter, pick_open_file
from frontend.pages.contacts.excel_editor_dialog import ExcelEditorDialog
from frontend.pages.contacts.tabular_editor_dialog import TextEditorDialog, WordEditorDialog
from frontend.pages.editor_tools.vcard_editor_dialog import VCardEditorDialog
from frontend.theme import style_button
from frontend.utils.worker import run_bg


class EditorToolsPage(QWidget):
    def __init__(self, on_status: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self.setObjectName("Page")
        self._on_status = on_status or (lambda _: None)
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("편집 도구")
        title.setObjectName("PageTitle")
        desc = QLabel("- 엑셀, 워드, 메모장 파일을 열어 미리보고 편집합니다.")
        desc.setObjectName("PageDesc")
        title_row.addWidget(title)
        title_row.addWidget(desc)
        title_row.addStretch(1)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_excel = style_button(QPushButton("엑셀 편집"), "primary")
        self.btn_word = style_button(QPushButton("워드 편집"), "secondary")
        self.btn_text = style_button(QPushButton("메모장 편집"), "secondary")
        self.btn_vcard = style_button(QPushButton("VCF 연락처 편집"), "accent")
        row.addWidget(self.btn_excel)
        row.addWidget(self.btn_word)
        row.addWidget(self.btn_text)
        row.addWidget(self.btn_vcard)
        row.addStretch(1)

        note = QLabel("대상자 파일을 가져오기 전에 내용을 확인하거나, 형식을 다듬을 때 사용하세요.")
        note.setObjectName("MutedText")

        card_layout.addLayout(row)
        card_layout.addWidget(note)

        layout.addLayout(title_row)
        layout.addWidget(card)
        layout.addStretch(1)

        self.btn_excel.clicked.connect(self._open_excel_editor)
        self.btn_word.clicked.connect(self._open_word_editor)
        self.btn_text.clicked.connect(self._open_text_editor)
        self.btn_vcard.clicked.connect(self._open_vcard_editor)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in [self.btn_excel, self.btn_word, self.btn_text, self.btn_vcard]:
            button.setEnabled(not busy)

    def _show_bg_error(self, tb: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "오류", tb)

    def _open_excel_editor(self) -> None:
        try:
            path = pick_open_file(
                title="엑셀 파일 선택",
                filters=[Filter("Excel Files", "*.xlsx;*.xlsm;*.xltx;*.xltm"), Filter("All Files", "*.*")],
                default_ext="xlsx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패:\n{e}")
            return
        if not path:
            return
        if not is_supported_excel_editor_file(path):
            QMessageBox.warning(self, "지원 형식 아님", "지원 확장자: .xlsx, .xlsm, .xltx, .xltm")
            return
        self._set_busy(True)
        self._on_status("엑셀 편집기 로드 중...")

        def load_job():
            return load_workbook_grid(path)

        def load_done(workbook):
            self._set_busy(False)
            self._on_status(f"엑셀 편집기 열기 완료: {Path(path).name}")
            try:
                dlg = ExcelEditorDialog(workbook, parent=self)
            except TypeError:
                dlg = ExcelEditorDialog(workbook, path, parent=self)
            dlg.exec()

        run_bg(load_job, on_done=load_done, on_error=self._show_bg_error)

    def _open_word_editor(self) -> None:
        try:
            path = pick_open_file(
                title="워드 파일 선택",
                filters=[Filter("Word Files", "*.docx"), Filter("All Files", "*.*")],
                default_ext="docx",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패:\n{e}")
            return
        if not path:
            return
        if not is_supported_word_editor_file(path):
            QMessageBox.warning(self, "지원 형식 아님", "지원 확장자: .docx")
            return
        self._set_busy(True)
        self._on_status("워드 편집기 로드 중...")

        def load_job():
            return load_word_grid(path)

        def load_done(grid):
            self._set_busy(False)
            self._on_status(f"워드 편집기 열기 완료: {Path(path).name}")
            dlg = WordEditorDialog(grid, save_workbook_grid_to_docx, suggest_word_save_path, parent=self)
            dlg.exec()

        run_bg(load_job, on_done=load_done, on_error=self._show_bg_error)

    def _open_text_editor(self) -> None:
        try:
            path = pick_open_file(
                title="메모장 파일 선택",
                filters=[Filter("Text Files", "*.txt;*.csv;*.tsv"), Filter("All Files", "*.*")],
                default_ext="txt",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패:\n{e}")
            return
        if not path:
            return
        if not is_supported_text_editor_file(path):
            QMessageBox.warning(self, "지원 형식 아님", "지원 확장자: .txt, .csv, .tsv")
            return
        self._set_busy(True)
        self._on_status("메모장 편집기 로드 중...")

        def load_job():
            return load_text_grid(path)

        def load_done(grid):
            self._set_busy(False)
            self._on_status(f"메모장 편집기 열기 완료: {Path(path).name}")
            dlg = TextEditorDialog(grid, save_workbook_grid_to_text, suggest_text_save_path, parent=self)
            dlg.exec()

        run_bg(load_job, on_done=load_done, on_error=self._show_bg_error)

    def _open_vcard_editor(self) -> None:
        try:
            path = pick_open_file(
                title="VCF 연락처 파일 선택",
                filters=[Filter("vCard Files", "*.vcf;*.vcard"), Filter("All Files", "*.*")],
                default_ext="vcf",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 선택기 실행 실패:\n{e}")
            return
        if not path:
            return
        if not is_supported_vcard_file(path):
            QMessageBox.warning(self, "지원 형식 아님", "지원 확장자: .vcf, .vcard")
            return
        self._set_busy(True)
        self._on_status("VCF 연락처 읽는 중...")

        def load_job():
            return load_vcard_contacts(path)

        def load_done(contacts):
            self._set_busy(False)
            self._on_status(f"VCF 연락처 편집기 열기 완료: {Path(path).name} ({len(contacts)}건)")
            dlg = VCardEditorDialog(path=path, contacts=contacts, parent=self)
            dlg.exec()

        run_bg(load_job, on_done=load_done, on_error=self._show_bg_error)
