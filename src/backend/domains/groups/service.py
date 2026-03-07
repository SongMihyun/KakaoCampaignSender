# FILE: src/backend/domains/groups/service.py
from __future__ import annotations

from backend.domains.groups.dto import GroupCreateDTO, GroupUpdateDTO
from backend.domains.groups.models import Group
from backend.stores.contacts_store import ContactMem


class GroupsService:
    def __init__(self, *, repo, contacts_repo, contacts_store) -> None:
        self.repo = repo
        self.contacts_repo = contacts_repo
        self.contacts_store = contacts_store

    def list_groups(self) -> list[Group]:
        rows = self.repo.list_groups()
        return [
            Group(
                id=int(r.id),
                name=str(r.name),
                memo=str(r.memo or ""),
            )
            for r in rows
        ]

    def create_group(self, dto: GroupCreateDTO) -> int:
        name = (dto.name or "").strip()
        memo = (dto.memo or "").strip()

        if not name:
            raise ValueError("그룹명은 필수입니다.")

        return int(self.repo.create_group(name, memo))

    def update_group(self, dto: GroupUpdateDTO) -> None:
        group_id = int(dto.group_id or 0)
        name = (dto.name or "").strip()
        memo = (dto.memo or "").strip()

        if group_id <= 0:
            raise ValueError("유효한 group_id가 필요합니다.")
        if not name:
            raise ValueError("그룹명은 필수입니다.")

        self.repo.update_group(group_id, name, memo)

    def delete_group(self, group_id: int) -> None:
        self.repo.delete_group(int(group_id))

    def add_members(self, group_id: int, contact_ids: list[int]) -> tuple[int, int]:
        return self.repo.add_members(int(group_id), contact_ids)

    def remove_members(self, group_id: int, contact_ids: list[int]) -> int:
        return int(self.repo.remove_members(int(group_id), contact_ids) or 0)

    def list_member_ids(self, group_id: int) -> list[int]:
        return list(self.repo.list_group_member_ids(int(group_id)) or [])

    def get_member_contacts(self, group_id: int, keyword: str = "") -> list[ContactMem]:
        member_ids = self.list_member_ids(group_id)
        members = list(self.contacts_store.get_many(member_ids) or [])

        kw = (keyword or "").strip().lower()
        if not kw:
            return members

        return [m for m in members if self._matches_contact(m, kw)]

    def search_candidate_contacts(
        self,
        keyword: str = "",
        *,
        exclude_contact_ids: set[int] | None = None,
    ) -> list[ContactMem]:
        rows = list(self.contacts_store.search(keyword) or [])
        if not exclude_contact_ids:
            return rows
        return [m for m in rows if int(m.id) not in exclude_contact_ids]

    def update_contact(
        self,
        *,
        contact_id: int,
        emp_id: str,
        name: str,
        phone: str,
        agency: str,
        branch: str,
    ) -> None:
        cid = int(contact_id)
        new_name = (name or "").strip()
        new_emp_id = (emp_id or "").strip()
        new_phone = (phone or "").strip()
        new_agency = (agency or "").strip()
        new_branch = (branch or "").strip()

        if cid <= 0:
            raise ValueError("유효한 contact_id가 필요합니다.")
        if not new_name:
            raise ValueError("이름은 필수입니다.")

        self.contacts_repo.update(
            row_id=cid,
            emp_id=new_emp_id,
            name=new_name,
            phone=new_phone,
            agency=new_agency,
            branch=new_branch,
        )

        self.contacts_store.update(
            contact_id=cid,
            emp_id=new_emp_id,
            name=new_name,
            phone=new_phone,
            agency=new_agency,
            branch=new_branch,
        )

    def _matches_contact(self, m: ContactMem, keyword_lower: str) -> bool:
        hay = " ".join(
            [
                m.emp_id or "",
                m.name or "",
                m.phone or "",
                m.agency or "",
                m.branch or "",
            ]
        ).lower()
        return keyword_lower in hay