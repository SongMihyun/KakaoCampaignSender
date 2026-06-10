from __future__ import annotations

from backend.domains.sending.models import Recipient


def resolve_contacts_for_send_list_meta(
    *,
    contacts_store,
    groups_repo,
    target_mode: str,
    group_id,
):
    tm = str(target_mode or "").upper().strip()
    if tm == "ALL" or group_id is None:
        return list(contacts_store.list_all() or [])

    member_ids = groups_repo.list_group_member_ids(int(group_id))
    return list(contacts_store.get_many(member_ids) or [])


def build_recipients_and_snapshot(contacts_mem) -> tuple[list[Recipient], list[dict]]:
    recipients: list[Recipient] = []
    snapshot: list[dict] = []

    for m in contacts_mem or []:
        raw_name = str(getattr(m, "name", "") or "")
        name = raw_name.strip().replace("\u200b", "").replace("\ufeff", "")
        if not name:
            continue

        contact_id = int(getattr(m, "id", 0) or 0)
        emp_id = str(getattr(m, "emp_id", "") or "").strip()
        phone = str(getattr(m, "phone", "") or "").strip()
        agency = str(getattr(m, "agency", "") or "").strip()
        branch = str(getattr(m, "branch", "") or "").strip()

        recipients.append(
            Recipient(
                contact_id=contact_id,
                emp_id=emp_id,
                name=name,
                phone=phone,
                agency=agency,
                branch=branch,
            )
        )

        snapshot.append(
            {
                "contact_id": contact_id,
                "emp_id": emp_id,
                "name": name,
                "phone": phone,
                "agency": agency,
                "branch": branch,
            }
        )

    return recipients, snapshot