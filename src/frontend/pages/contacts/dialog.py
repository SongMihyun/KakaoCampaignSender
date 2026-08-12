# ✅ FILE: src/frontend/pages/contacts/dialog.py

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
    title: str
    kakao_search_name: str


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
        self.title_field = QLineEdit()
        self.kakao_search_name = QLineEdit()

        # ✅ 필수: 이름만
        self.emp_id.setPlaceholderText("사번(선택)")
        self.name.setPlaceholderText("이름(필수)")
        self.phone.setPlaceholderText("전화번호(선택, 숫자/하이픈)")
        self.agency.setPlaceholderText("법인명(선택)")
        self.branch.setPlaceholderText("점포명(선택)")
        self.title_field.setPlaceholderText("호칭(선택)")
        self.kakao_search_name.setPlaceholderText("카카오톡검색명(선택, 비우면 이름으로 검색)")

        layout.addWidget(QLabel("사번(선택)"))
        layout.addWidget(self.emp_id)
        layout.addWidget(QLabel("이름(필수)"))
        layout.addWidget(self.name)
        layout.addWidget(QLabel("전화번호(선택)"))
        layout.addWidget(self.phone)
        layout.addWidget(QLabel("법인명(선택)"))
        layout.addWidget(self.agency)
        layout.addWidget(QLabel("점포명(선택)"))
        layout.addWidget(self.branch)
        layout.addWidget(QLabel("호칭(선택)"))
        layout.addWidget(self.title_field)
        layout.addWidget(QLabel("카카오톡검색명(선택)"))
        layout.addWidget(self.kakao_search_name)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_ok = QPushButton("저장")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)

        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        # ✅ Enter/Return 누르면 저장(_on_ok) -> accept()로 닫힘
        for le in (self.emp_id, self.name, self.phone, self.agency, self.branch, self.title_field, self.kakao_search_name):
            le.returnPressed.connect(self._on_ok)

        # ✅ Enter 기본 버튼 = 저장
        self.btn_ok.setDefault(True)
        self.btn_ok.setAutoDefault(True)

        # preset은 Contact든 임시 객체든(emp_id/name/...) 속성만 있으면 동작
        if preset:
            self.emp_id.setText(getattr(preset, "emp_id", "") or "")
            self.name.setText(getattr(preset, "name", "") or "")
            self.phone.setText(getattr(preset, "phone", "") or "")
            self.agency.setText(getattr(preset, "agency", "") or "")
            self.branch.setText(getattr(preset, "branch", "") or "")
            self.title_field.setText(getattr(preset, "title", "") or "")
            self.kakao_search_name.setText(getattr(preset, "kakao_search_name", "") or "")

    def _on_ok(self) -> None:
        # ✅ 이름만 필수
        if not self.name.text().strip():
            QMessageBox.warning(self, "검증", "이름은 필수입니다.")
            return

        # ✅ 사번/전화/법인/점포/호칭/카카오톡검색명: 비워도 통과
        # (중복/형식 검증은 Repo(DB)에서 최종 처리 권장)
        self.accept()

    def get_contact(self) -> ContactForm:
        return {
            "emp_id": self.emp_id.text().strip(),   # 빈값 허용
            "name": self.name.text().strip(),       # 필수
            "phone": self.phone.text().strip(),
            "agency": self.agency.text().strip(),
            "branch": self.branch.text().strip(),
            "title": self.title_field.text().strip(),
            "kakao_search_name": self.kakao_search_name.text().strip(),
        }
