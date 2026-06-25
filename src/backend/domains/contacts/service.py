# FILE: src/backend/domains/contacts/service.py
from __future__ import annotations

from backend.domains.contacts.dto import ContactCreateDTO, ContactUpdateDTO
from backend.domains.contacts.models import Contact
from backend.domains.contacts.validators import normalize_create, normalize_update


class ContactsService:
    def __init__(self, *, repo, store) -> None:
        self.repo = repo
        self.store = store

    def list_all(self) -> list[Contact]:
        rows = self.repo.search_contacts("")
        return [self._to_model(r) for r in rows]

    def search(self, keyword: str) -> list[Contact]:
        rows = self.repo.search_contacts(keyword or "")
        return [self._to_model(r) for r in rows]

    def get_contact_by_id(self, row_id: int) -> Contact | None:
        row = self.repo.get_by_id(int(row_id))
        if not row:
            return None
        return self._to_model(row)

    def reload_store_from_db(self) -> int:
        rows = self.repo.search_contacts("")
        self.store.load_rows(rows)
        return len(rows)

    def create_contact(self, dto: ContactCreateDTO) -> int:
        dto = normalize_create(dto)
        row_id = self.repo.insert(
            emp_id=dto.emp_id,
            name=dto.name,
            customer_name=dto.customer_name,
            customer_honorific=dto.customer_honorific,
            customer_position=dto.customer_position,
            phone=dto.phone,
            agency=dto.agency,
            branch=dto.branch,
            customer_status=dto.customer_status,
            tags=dto.tags,
            memo2=dto.memo2,
        )
        self.store.upsert(
            type(
                "ContactMemLike",
                (),
                {
                    "id": int(row_id),
                    "emp_id": dto.emp_id,
                    "name": dto.name,
                    "customer_name": dto.customer_name,
                    "customer_honorific": dto.customer_honorific,
                    "customer_position": dto.customer_position,
                    "phone": dto.phone,
                    "agency": dto.agency,
                    "branch": dto.branch,
                    "customer_status": dto.customer_status,
                    "tags": dto.tags,
                    "memo2": dto.memo2,
                    "last_assigned_code": dto.last_assigned_code,
                    "last_assigned_label": dto.last_assigned_label,
                    "last_assigned_at": dto.last_assigned_at,
                },
            )()
        )
        return int(row_id)

    def update_contact(self, dto: ContactUpdateDTO) -> None:
        dto = normalize_update(dto)
        self.repo.update(
            row_id=dto.row_id,
            emp_id=dto.emp_id,
            name=dto.name,
            customer_name=dto.customer_name,
            customer_honorific=dto.customer_honorific,
            customer_position=dto.customer_position,
            phone=dto.phone,
            agency=dto.agency,
            branch=dto.branch,
            customer_status=dto.customer_status,
            tags=dto.tags,
            memo2=dto.memo2,
            last_assigned_code=dto.last_assigned_code,
            last_assigned_label=dto.last_assigned_label,
            last_assigned_at=dto.last_assigned_at,
        )
        self.store.update(
            contact_id=dto.row_id,
            emp_id=dto.emp_id,
            name=dto.name,
            customer_name=dto.customer_name,
            customer_honorific=dto.customer_honorific,
            customer_position=dto.customer_position,
            phone=dto.phone,
            agency=dto.agency,
            branch=dto.branch,
            customer_status=dto.customer_status,
            tags=dto.tags,
            memo2=dto.memo2,
        )

    def delete_contacts(self, ids: list[int]) -> None:
        ids = [int(x) for x in ids or []]
        if not ids:
            return

        if hasattr(self.repo, "delete_many"):
            self.repo.delete_many(ids)
        else:
            for cid in ids:
                self.repo.delete(int(cid))

        self.store.delete_many(ids)

    @staticmethod
    def _to_model(row) -> Contact:
        return Contact(
            id=int(getattr(row, "id")),
            emp_id=str(getattr(row, "emp_id", "") or ""),
            name=str(getattr(row, "name", "") or ""),
            customer_name=str(getattr(row, "customer_name", "") or getattr(row, "name", "") or ""),
            customer_honorific=str(getattr(row, "customer_honorific", "") or "고객님"),
            customer_position=str(getattr(row, "customer_position", "") or ""),
            phone=str(getattr(row, "phone", "") or ""),
            agency=str(getattr(row, "agency", "") or ""),
            branch=str(getattr(row, "branch", "") or ""),
            customer_status=str(getattr(row, "customer_status", "") or ""),
            tags=str(getattr(row, "tags", "") or ""),
            memo2=str(getattr(row, "memo2", "") or ""),
            last_assigned_code=getattr(row, "last_assigned_code", None),
            last_assigned_label=getattr(row, "last_assigned_label", None),
            last_assigned_at=getattr(row, "last_assigned_at", None),
        )
