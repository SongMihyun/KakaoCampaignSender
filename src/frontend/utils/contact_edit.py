# FILE: src/frontend/utils/contact_edit.py
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtWidgets import QMessageBox

from backend.domains.contacts.dto import ContactUpdateDTO
from backend.domains.contacts.service import ContactsService
from frontend.app.app_events import app_events
from frontend.pages.contacts.dialog import ContactDialog


def _make_fallback_preset(fallback_preset: Any):
    if fallback_preset is None:
        return None

    if isinstance(fallback_preset, dict):
        return type(
            "TmpContactPreset",
            (),
            {
                "emp_id": (fallback_preset.get("emp_id") or "").strip(),
                "name": (fallback_preset.get("name") or "").strip(),
                "phone": (fallback_preset.get("phone") or "").strip(),
                "agency": (fallback_preset.get("agency") or "").strip(),
                "branch": (fallback_preset.get("branch") or "").strip(),
            },
        )()

    return fallback_preset


def edit_contact_by_id(
    parent,
    *,
    contacts_service: ContactsService,
    contact_id: int,
    fallback_preset: Any = None,
    on_saved: Optional[Callable[[], None]] = None,
    emit_event: bool = True,
) -> bool:
    try:
        cid = int(contact_id)
    except Exception:
        cid = 0

    if cid <= 0:
        QMessageBox.information(parent, "안내", "수정할 대상자 ID(contact_id)를 확인할 수 없습니다.")
        return False

    preset = None
    try:
        preset = contacts_service.get_contact_by_id(cid)
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"대상자 로드 실패\n{e}")
        return False

    if preset is None:
        preset = _make_fallback_preset(fallback_preset)

    if preset is None:
        QMessageBox.information(parent, "안내", f"대상자를 찾지 못했습니다.\ncontact_id={cid}")
        return False

    dlg = ContactDialog("대상자 수정", preset=preset, parent=parent)
    if dlg.exec() != ContactDialog.Accepted:
        return False

    data = dlg.get_contact()
    new_emp_id = (data.get("emp_id") or "").strip()
    new_name = (data.get("name") or "").strip()
    new_phone = (data.get("phone") or "").strip()
    new_agency = (data.get("agency") or "").strip()
    new_branch = (data.get("branch") or "").strip()

    if not new_name:
        QMessageBox.warning(parent, "입력 오류", "이름은 필수입니다.")
        return False

    try:
        contacts_service.update_contact(
            ContactUpdateDTO(
                row_id=cid,
                emp_id=new_emp_id,
                name=new_name,
                phone=new_phone,
                agency=new_agency,
                branch=new_branch,
            )
        )
    except ValueError as e:
        QMessageBox.warning(parent, "중복 오류", str(e))
        return False
    except Exception as e:
        QMessageBox.critical(parent, "오류", f"대상자 저장 실패\n{e}")
        return False

    if emit_event:
        try:
            app_events.contacts_changed.emit()
        except Exception:
            pass

    if on_saved is not None:
        try:
            on_saved()
        except Exception:
            pass

    return True