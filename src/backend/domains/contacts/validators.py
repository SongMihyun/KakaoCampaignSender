from __future__ import annotations
from backend.domains.contacts.dto import ContactCreateDTO, ContactUpdateDTO


def normalize_optional(v: str | None) -> str:
    return (v or "").strip()


def normalize_required(v: str | None, field_name: str) -> str:
    x = (v or "").strip()
    if not x:
        raise ValueError(f"{field_name}은(는) 필수입니다.")
    return x


def normalize_create(dto: ContactCreateDTO) -> ContactCreateDTO:
    return ContactCreateDTO(
        emp_id=normalize_optional(dto.emp_id),
        name=normalize_required(dto.name, "이름"),
        phone=normalize_optional(dto.phone),
        agency=normalize_optional(dto.agency),
        branch=normalize_optional(dto.branch),
    )


def normalize_update(dto: ContactUpdateDTO) -> ContactUpdateDTO:
    if int(dto.row_id or 0) <= 0:
        raise ValueError("유효한 row_id가 필요합니다.")

    return ContactUpdateDTO(
        row_id=int(dto.row_id),
        emp_id=normalize_optional(dto.emp_id),
        name=normalize_required(dto.name, "이름"),
        phone=normalize_optional(dto.phone),
        agency=normalize_optional(dto.agency),
        branch=normalize_optional(dto.branch),
    )