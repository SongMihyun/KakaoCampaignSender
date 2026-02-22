from __future__ import annotations

from typing import Optional, TypedDict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)


class ContactForm(TypedDict):
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str


class ContactDialog(QDialog):
    def __init__(self, title: str, preset: Optional[object] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.emp_id = QLineEdit()
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.agency = QLineEdit()
        self.branch = QLineEdit()

        # ✅ 필수: 이름만
        self.emp_id.setPlaceholderText("사번(선택)")
        self.name.setPlaceholderText("이름(필수)")
        self.phone.setPlaceholderText("전화번호(선택, 숫자/하이픈)")
        self.agency.setPlaceholderText("대리점명(선택)")
        self.branch.setPlaceholderText("지사명(선택)")

        layout.addWidget(QLabel("사번(선택)"))
        layout.addWidget(self.emp_id)
        layout.addWidget(QLabel("이름(필수)"))
        layout.addWidget(self.name)
        layout.addWidget(QLabel("전화번호(선택)"))
        layout.addWidget(self.phone)
        layout.addWidget(QLabel("대리점명(선택)"))
        layout.addWidget(self.agency)
        layout.addWidget(QLabel("지사명(선택)"))
        layout.addWidget(self.branch)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("저장")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)

        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        # preset은 Contact든 임시 객체든(emp_id/name/...) 속성만 있으면 동작
        if preset:
            self.emp_id.setText(getattr(preset, "emp_id", "") or "")
            self.name.setText(getattr(preset, "name", "") or "")
            self.phone.setText(getattr(preset, "phone", "") or "")
            self.agency.setText(getattr(preset, "agency", "") or "")
            self.branch.setText(getattr(preset, "branch", "") or "")

    def _on_ok(self) -> None:
        # ✅ 이름만 필수
        if not self.name.text().strip():
            QMessageBox.warning(self, "검증", "이름은 필수입니다.")
            return

        # ✅ 사번/전화/대리점/지사: 비워도 통과
        # (중복/형식 검증은 Repo(DB)에서 최종 처리 권장)
        self.accept()

    def get_contact(self) -> ContactForm:
        return {
            "emp_id": self.emp_id.text().strip(),   # 빈값 허용
            "name": self.name.text().strip(),       # 필수
            "phone": self.phone.text().strip(),
            "agency": self.agency.text().strip(),
            "branch": self.branch.text().strip(),
        }
