# ✅ FILE: src/ui/utils/contact_edit.py

from __future__ import annotations

from typing import Optional, Any, Dict

from PySide6.QtWidgets import QMessageBox

from ui.app_events import app_events
from ui.pages.contacts_dialog import ContactDialog


def edit_contact_by_emp_id(parent, *, contacts_repo, emp_id: str) -> bool:
    """
    emp_id 기준으로 DB에서 1건 로드 -> ContactDialog로 편집 -> 저장 -> contacts_changed emit
    return: 저장 성공 여부
    """
    emp_id = (emp_id or "").strip()
    if not emp_id:
        QMessageBox.information(parent, "안내", "사번(emp_id)이 비어있어 수정할 대상을 찾을 수 없습니다.")
        return False

    try:
        # ✅ repo에 맞게 조정: 아래 중 하나로 맞추면 됨
        # row = contacts_repo.get_by_emp_id(emp_id)
        # row = contacts_repo.find_one(emp_id=emp_id)
        row = contacts_repo.get_contact_by_emp_id(emp_id)  # 너 코드에 맞게 하나로 고정
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"대상자 로드 실패\n{e}")
        return False

    if not row:
        QMessageBox.information(parent, "안내", f"대상자를 찾지 못했습니다.\nemp_id={emp_id}")
        return False

    dlg = ContactDialog(parent=parent, initial=row)  # ✅ ContactDialog 시그니처에 맞춰 조정
    ok = dlg.exec()
    if not ok:
        return False

    try:
        updated = dlg.get_result()  # ✅ ContactDialog 결과 반환 메서드에 맞춰 조정
        contacts_repo.upsert_contact(updated)  # ✅ repo 저장 메서드명 맞추기 (update/replace/upsert)
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"대상자 저장 실패\n{e}")
        return False

    try:
        app_events.contacts_changed.emit()
    except Exception:
        pass
    return True