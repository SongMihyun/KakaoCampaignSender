from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from frontend.app.app_events import app_events
from frontend.pages.contacts.dialog import ContactDialog


def edit_contact_by_emp_id(parent, *, contacts_repo, emp_id: str) -> bool:
    emp_id = (emp_id or "").strip()
    if not emp_id:
        QMessageBox.information(parent, "안내", "사번(emp_id)이 비어있어 수정할 대상을 찾을 수 없습니다.")
        return False

    try:
        row = contacts_repo.get_contact_by_emp_id(emp_id)
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"대상자 로드 실패\n{e}")
        return False

    if not row:
        QMessageBox.information(parent, "안내", f"대상자를 찾지 못했습니다.\nemp_id={emp_id}")
        return False

    dlg = ContactDialog("대상자 수정", preset=row, parent=parent)
    if dlg.exec() != ContactDialog.Accepted:
        return False

    data = dlg.get_contact()

    try:
        contacts_repo.update(
            row_id=int(getattr(row, "id")),
            emp_id=(data.get("emp_id") or "").strip(),
            name=(data.get("name") or "").strip(),
            phone=(data.get("phone") or "").strip(),
            agency=(data.get("agency") or "").strip(),
            branch=(data.get("branch") or "").strip(),
        )
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"대상자 저장 실패\n{e}")
        return False

    try:
        app_events.contacts_changed.emit()
    except Exception:
        pass

    return True