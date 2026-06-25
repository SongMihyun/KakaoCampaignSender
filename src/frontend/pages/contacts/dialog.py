# FILE: src/frontend/pages/contacts/dialog.py

from __future__ import annotations

from typing import Optional, TypedDict

from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class ContactForm(TypedDict):
    emp_id: str
    name: str
    customer_name: str
    customer_honorific: str
    customer_position: str
    phone: str
    agency: str
    branch: str
    customer_status: str
    tags: str
    memo2: str


class ContactDialog(QDialog):
    def __init__(self, title: str, preset: Optional[object] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.name = QLineEdit()
        self.customer_name = QLineEdit()
        self.customer_honorific = QLineEdit()
        self.customer_position = QLineEdit()
        self.agency = QLineEdit()
        self.branch = QLineEdit()
        self.phone = QLineEdit()
        self.customer_status = QLineEdit()
        self.tags = QLineEdit()
        self.memo2 = QLineEdit()
        self.emp_id = QLineEdit()

        self.name.setPlaceholderText("카카오톡에서 검색할 이름 또는 채팅방명")
        self.customer_name.setPlaceholderText("메시지 개인화에 사용할 고객명")
        self.customer_honorific.setPlaceholderText("고객님")
        self.customer_position.setPlaceholderText("직책/직함")
        self.agency.setPlaceholderText("소속/대리점")
        self.branch.setPlaceholderText("지사")
        self.phone.setPlaceholderText("연락처")
        self.customer_status.setPlaceholderText("예: 신규, 상담중, 계약")
        self.tags.setPlaceholderText("태그")
        self.memo2.setPlaceholderText("메모")
        self.emp_id.setPlaceholderText("사번/외부 ID(선택)")

        rows = [
            ("카카오톡 검색명(필수)", self.name),
            ("고객명", self.customer_name),
            ("호칭", self.customer_honorific),
            ("직책", self.customer_position),
            ("소속/대리점", self.agency),
            ("지사", self.branch),
            ("연락처", self.phone),
            ("상태", self.customer_status),
            ("태그", self.tags),
            ("메모", self.memo2),
            ("사번/외부 ID(선택)", self.emp_id),
        ]
        for row, (label, widget) in enumerate(rows):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("저장")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        for le in (
            self.name,
            self.customer_name,
            self.customer_honorific,
            self.customer_position,
            self.agency,
            self.branch,
            self.phone,
            self.customer_status,
            self.tags,
            self.memo2,
            self.emp_id,
        ):
            le.returnPressed.connect(self._on_ok)

        self.btn_ok.setDefault(True)
        self.btn_ok.setAutoDefault(True)

        if preset:
            self.emp_id.setText(getattr(preset, "emp_id", "") or "")
            self.name.setText(getattr(preset, "name", "") or "")
            self.customer_name.setText(
                getattr(preset, "customer_name", "") or getattr(preset, "name", "") or ""
            )
            self.customer_honorific.setText(getattr(preset, "customer_honorific", "") or "고객님")
            self.customer_position.setText(getattr(preset, "customer_position", "") or "")
            self.phone.setText(getattr(preset, "phone", "") or "")
            self.agency.setText(getattr(preset, "agency", "") or "")
            self.branch.setText(getattr(preset, "branch", "") or "")
            self.customer_status.setText(getattr(preset, "customer_status", "") or "")
            self.tags.setText(getattr(preset, "tags", "") or "")
            self.memo2.setText(getattr(preset, "memo2", "") or "")
        else:
            self.customer_honorific.setText("고객님")

    def _on_ok(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "검증", "카카오톡 검색명은 필수입니다.")
            return
        self.accept()

    def get_contact(self) -> ContactForm:
        name = self.name.text().strip()
        return {
            "emp_id": self.emp_id.text().strip(),
            "name": name,
            "customer_name": self.customer_name.text().strip() or name,
            "customer_honorific": self.customer_honorific.text().strip() or "고객님",
            "customer_position": self.customer_position.text().strip(),
            "phone": self.phone.text().strip(),
            "agency": self.agency.text().strip(),
            "branch": self.branch.text().strip(),
            "customer_status": self.customer_status.text().strip(),
            "tags": self.tags.text().strip(),
            "memo2": self.memo2.text().strip(),
        }
