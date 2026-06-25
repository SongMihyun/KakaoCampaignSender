from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from backend.domains.sender_profiles.models import SenderProfile


class SenderProfileDialog(QDialog):
    def __init__(self, profile: SenderProfile, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("내 발신자 정보")
        self.setMinimumWidth(520)
        self._profile_id = int(profile.id or 0)
        self._created_at = profile.created_at
        self._updated_at = profile.updated_at

        root = QVBoxLayout(self)
        root.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.profile_name = QLineEdit(profile.profile_name or "기본 발신자")
        self.sender_name = QLineEdit(profile.sender_name or "")
        self.sender_position = QLineEdit(profile.sender_position or "")
        self.sender_company = QLineEdit(profile.sender_company or "")
        self.sender_branch = QLineEdit(profile.sender_branch or "")
        self.sender_phone = QLineEdit(profile.sender_phone or "")
        self.default_signature = QTextEdit(profile.default_signature or "")
        self.default_signature.setMinimumHeight(96)

        rows = [
            ("프로필명", self.profile_name),
            ("이름", self.sender_name),
            ("직책", self.sender_position),
            ("회사", self.sender_company),
            ("지사", self.sender_branch),
            ("연락처", self.sender_phone),
            ("기본 서명", self.default_signature),
        ]
        for row, (label, widget) in enumerate(rows):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)

        root.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("취소")
        self.btn_save = QPushButton("저장")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.accept)
        self.btn_save.setDefault(True)
        self.btn_save.setAutoDefault(True)

    def get_profile(self) -> SenderProfile:
        return SenderProfile(
            id=self._profile_id,
            profile_name=self.profile_name.text().strip() or "기본 발신자",
            sender_name=self.sender_name.text().strip(),
            sender_position=self.sender_position.text().strip(),
            sender_company=self.sender_company.text().strip(),
            sender_branch=self.sender_branch.text().strip(),
            sender_phone=self.sender_phone.text().strip(),
            default_signature=self.default_signature.toPlainText().strip(),
            is_default=1,
            is_active=1,
            created_at=self._created_at,
            updated_at=self._updated_at,
        )
