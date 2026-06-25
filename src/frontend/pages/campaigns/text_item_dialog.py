from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
)

from backend.domains.personalization import render_personalized_text


VARIABLE_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "고객 정보",
        (
            ("고객명", "{{고객명}}"),
            ("고객호칭", "{{고객호칭}}"),
            ("고객직책", "{{고객직책}}"),
            ("고객소속", "{{고객소속}}"),
            ("지사명", "{{지사명}}"),
            ("연락처", "{{연락처}}"),
        ),
    ),
    (
        "발신자 정보",
        (
            ("발신자명", "{{발신자명}}"),
            ("발신자직책", "{{발신자직책}}"),
            ("발신자소속", "{{발신자소속}}"),
            ("발신자지사", "{{발신자지사}}"),
            ("발신자연락처", "{{발신자연락처}}"),
            ("기본서명", "{{기본서명}}"),
        ),
    ),
    (
        "고급 항목",
        (
            ("카카오톡 검색명", "{{카카오톡검색명}}"),
        ),
    ),
)


class TextItemDialog(QDialog):
    def __init__(
        self,
        title: str = "문구",
        text: str = "",
        parent=None,
        *,
        sample_contact: Any = None,
        sender_profile: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(680)
        self.resize(760, 680)
        self._sample_contact = sample_contact
        self._sender_profile = sender_profile

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        root.addWidget(QLabel("문구"))

        guide = QLabel(
            "자동입력 항목은 고객 정보와 내 발신자 정보를 메시지에 넣는 기능입니다.\n"
            "예: {{고객명}} {{고객호칭}}, 안녕하세요"
        )
        guide.setStyleSheet("color:#6b7280;")
        guide.setWordWrap(True)
        root.addWidget(guide)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_variables = QToolButton()
        self.btn_variables.setText("자동입력 항목")
        self.btn_variables.setPopupMode(QToolButton.InstantPopup)
        self.btn_variables.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_variables.setMenu(self._build_variable_menu())
        toolbar.addWidget(self.btn_variables)

        self.btn_preview = QPushButton("미리보기")
        self.btn_preview.clicked.connect(self._render_preview)
        toolbar.addWidget(self.btn_preview)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.ed_text = QTextEdit()
        self.ed_text.setPlaceholderText("캠페인에 넣을 문구를 입력하세요.")
        self.ed_text.setMinimumHeight(220)
        self.ed_text.setPlainText(text or "")
        root.addWidget(self.ed_text, 1)

        preview_card = QFrame()
        preview_card.setStyleSheet(
            """
            QFrame {
                background:#ffffff;
                border:1px solid #e5e7eb;
                border-radius:8px;
            }
            """
        )
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(8)

        preview_title = QLabel("미리보기")
        preview_title.setStyleSheet("font-weight:700;")
        preview_layout.addWidget(preview_title)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(130)
        self.preview_text.setPlaceholderText("미리보기를 누르면 샘플 고객 기준으로 치환 결과가 표시됩니다.")
        preview_layout.addWidget(self.preview_text)

        self.preview_warnings = QLabel("")
        self.preview_warnings.setWordWrap(True)
        self.preview_warnings.setStyleSheet("color:#b45309;")
        preview_layout.addWidget(self.preview_warnings)

        root.addWidget(preview_card)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("확인")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        self.ed_text.setFocus()

    def _build_variable_menu(self) -> QMenu:
        menu = QMenu(self)
        for group_label, items in VARIABLE_GROUPS:
            sub = menu.addMenu(group_label)
            for label, placeholder in items:
                action = sub.addAction(f"{label}  {placeholder}")
                action.triggered.connect(
                    lambda _checked=False, value=placeholder: self._insert_placeholder(value)
                )
        return menu

    def _insert_placeholder(self, placeholder: str) -> None:
        cursor = self.ed_text.textCursor()
        cursor.insertText(placeholder)
        self.ed_text.setTextCursor(cursor)
        self.ed_text.setFocus()

    def _render_preview(self) -> None:
        if self._sample_contact is None:
            self.preview_text.setPlainText(
                "고객이 없어 미리보기를 만들 수 없습니다.\n고객관리에 고객을 먼저 등록해 주세요."
            )
            self.preview_warnings.setText("")
            return

        result = render_personalized_text(
            self.ed_text.toPlainText() or "",
            contact=self._sample_contact,
            sender_profile=self._sender_profile,
        )
        self.preview_text.setPlainText(result.rendered_text)

        warnings: list[str] = []
        if result.missing_variables:
            warnings.append(
                "다음 자동입력 항목은 값이 비어 있습니다.\n"
                + "\n".join(f"- {name}" for name in result.missing_variables)
            )
        if result.unknown_variables:
            warnings.append(
                "지원하지 않는 자동입력 항목이 포함되어 있습니다.\n"
                + "\n".join(f"- {name}" for name in result.unknown_variables)
            )

        self.preview_warnings.setText("\n\n".join(warnings))

    def _on_ok(self) -> None:
        text = (self.ed_text.toPlainText() or "").strip()
        if not text:
            QMessageBox.warning(self, "검증", "문구를 입력하세요.")
            return
        self.accept()

    def get_text(self) -> str:
        return (self.ed_text.toPlainText() or "").strip()
