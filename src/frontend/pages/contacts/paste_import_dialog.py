# FILE: src/frontend/pages/contacts/paste_import_dialog.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)


class PasteImportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("붙여넣기 업로드")
        self.resize(760, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("엑셀/워드/메모장에서 복사한 대상자 목록을 그대로 붙여넣으세요.")
        title.setStyleSheet("font-size:14px; font-weight:700;")
        root.addWidget(title)

        guide = QLabel(
            "지원 예시\n"
            "- 이름만 한 줄씩: 홍길동\n"
            "- 엑셀 복사: 사번/이름/전화/대리점/지사 탭 구분\n"
            "- 워드 표/문단, 메모장 목록도 가능\n"
            "- 이름만 있어도 등록됩니다."
        )
        guide.setStyleSheet("color:#6b7280;")
        root.addWidget(guide)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText(
            "여기에 Ctrl+V로 붙여넣으세요.\n\n"
            "예시 1)\n홍길동\n김영희\n\n"
            "예시 2)\n1001\t홍길동\t010-1111-2222\t강남대리점\t서울지사"
        )
        self.editor.setAcceptRichText(False)
        root.addWidget(self.editor, 1)

        btns = QHBoxLayout()
        self.btn_from_clipboard = QPushButton("현재 클립보드 불러오기")
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("미리보기")
        btns.addWidget(self.btn_from_clipboard)
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_from_clipboard.clicked.connect(self._load_from_clipboard)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept_if_valid)

        self.editor.setFocus()

    def _load_from_clipboard(self) -> None:
        text = QApplication.clipboard().text() or ""
        if not text.strip():
            QMessageBox.information(self, "안내", "클립보드에 텍스트가 없습니다.")
            return
        self.editor.setPlainText(text)
        self.editor.setFocus()

    def _accept_if_valid(self) -> None:
        if not self.get_text().strip():
            QMessageBox.information(self, "안내", "붙여넣은 내용이 없습니다.")
            return
        self.accept()

    def get_text(self) -> str:
        return self.editor.toPlainText()
