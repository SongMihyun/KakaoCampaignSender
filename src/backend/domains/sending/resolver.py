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
        last_assigned_code = getattr(m, "last_assigned_code", None)
        last_assigned_label = getattr(m, "last_assigned_label", None)
        last_assigned_at = getattr(m, "last_assigned_at", None)

        recipients.append(
            Recipient(
                contact_id=contact_id,
                emp_id=emp_id,
                name=name,
                phone=phone,
                agency=agency,
                branch=branch,
                last_assigned_code=last_assigned_code,
                last_assigned_label=last_assigned_label,
                last_assigned_at=last_assigned_at,
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
                "last_assigned_code": last_assigned_code,
                "last_assigned_label": last_assigned_label,
                "last_assigned_at": last_assigned_at,
                # TODO: When per-recipient message values are implemented, fill these
                # from message_value_pools/message_value_items assignment results.
                "assigned_value": None,
                "assigned_value_label": None,
                "assigned_value_pool_id": None,
                "assigned_value_item_id": None,
            }
        )

    return recipients, snapshot
