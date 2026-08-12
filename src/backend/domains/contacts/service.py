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
            phone=dto.phone,
            agency=dto.agency,
            branch=dto.branch,
            title=dto.title,
            kakao_search_name=dto.kakao_search_name,
        )
        self.store.upsert(
            type(
                "ContactMemLike",
                (),
                {
                    "id": int(row_id),
                    "emp_id": dto.emp_id,
                    "name": dto.name,
                    "phone": dto.phone,
                    "agency": dto.agency,
                    "branch": dto.branch,
                    "title": dto.title,
                    "kakao_search_name": dto.kakao_search_name,
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
            phone=dto.phone,
            agency=dto.agency,
            branch=dto.branch,
            title=dto.title,
            kakao_search_name=dto.kakao_search_name,
        )
        self.store.update(
            contact_id=dto.row_id,
            emp_id=dto.emp_id,
            name=dto.name,
            phone=dto.phone,
            agency=dto.agency,
            branch=dto.branch,
            title=dto.title,
            kakao_search_name=dto.kakao_search_name,
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
            phone=str(getattr(row, "phone", "") or ""),
            agency=str(getattr(row, "agency", "") or ""),
            branch=str(getattr(row, "branch", "") or ""),
            title=str(getattr(row, "title", "") or ""),
            kakao_search_name=str(getattr(row, "kakao_search_name", "") or ""),
        )