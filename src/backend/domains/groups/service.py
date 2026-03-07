from __future__ import annotations

from backend.domains.groups.dto import GroupCreateDTO, GroupUpdateDTO
from backend.domains.groups.models import Group


class GroupsService:
    def __init__(self, *, repo, contacts_repo, contacts_store) -> None:
        self.repo = repo
        self.contacts_repo = contacts_repo
        self.contacts_store = contacts_store

    def list_groups(self) -> list[Group]:
        rows = self.repo.list_groups()
        return [Group(id=int(r.id), name=str(r.name), memo=str(r.memo or "")) for r in rows]

    def create_group(self, dto: GroupCreateDTO) -> int:
        name = (dto.name or "").strip()
        memo = (dto.memo or "").strip()
        if not name:
            raise ValueError("그룹명은 필수입니다.")
        return int(self.repo.create_group(name, memo))

    def update_group(self, dto: GroupUpdateDTO) -> None:
        gid = int(dto.group_id or 0)
        name = (dto.name or "").strip()
        memo = (dto.memo or "").strip()
        if gid <= 0:
            raise ValueError("유효한 group_id가 필요합니다.")
        if not name:
            raise ValueError("그룹명은 필수입니다.")
        self.repo.update_group(gid, name, memo)

    def delete_group(self, group_id: int) -> None:
        self.repo.delete_group(int(group_id))

    def add_members(self, group_id: int, contact_ids: list[int]) -> tuple[int, int]:
        return self.repo.add_members(int(group_id), contact_ids)

    def remove_members(self, group_id: int, contact_ids: list[int]) -> None:
        self.repo.remove_members(int(group_id), contact_ids)

    def list_member_ids(self, group_id: int) -> list[int]:
        return list(self.repo.list_group_member_ids(int(group_id)) or [])

    def get_member_contacts(self, group_id: int):
        member_ids = self.list_member_ids(group_id)
        return list(self.contacts_store.get_many(member_ids) or [])