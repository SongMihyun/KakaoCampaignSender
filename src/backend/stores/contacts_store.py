from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable


@dataclass
class ContactMem:
    id: int
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str
    last_assigned_code: str | None = None
    last_assigned_label: str | None = None
    last_assigned_at: str | None = None


class ContactsStore:
    def __init__(self) -> None:
        self._by_id: Dict[int, ContactMem] = {}
        self._loaded: bool = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def clear(self) -> None:
        self._by_id.clear()
        self._loaded = False

    def load_rows(self, rows: Iterable[object]) -> None:
        self._by_id.clear()
        for r in rows or []:
            try:
                cid = int(getattr(r, "id"))
            except Exception:
                continue
            self._by_id[cid] = ContactMem(
                id=cid,
                emp_id=str(getattr(r, "emp_id", "") or ""),
                name=str(getattr(r, "name", "") or ""),
                phone=str(getattr(r, "phone", "") or ""),
                agency=str(getattr(r, "agency", "") or ""),
                branch=str(getattr(r, "branch", "") or ""),
                last_assigned_code=getattr(r, "last_assigned_code", None),
                last_assigned_label=getattr(r, "last_assigned_label", None),
                last_assigned_at=getattr(r, "last_assigned_at", None),
            )
        self._loaded = True

    def upsert(self, m: ContactMem) -> None:
        self._by_id[int(m.id)] = ContactMem(
            id=int(m.id),
            emp_id=(m.emp_id or ""),
            name=(m.name or ""),
            phone=(m.phone or ""),
            agency=(m.agency or ""),
            branch=(m.branch or ""),
            last_assigned_code=getattr(m, "last_assigned_code", None),
            last_assigned_label=getattr(m, "last_assigned_label", None),
            last_assigned_at=getattr(m, "last_assigned_at", None),
        )
        self._loaded = True

    def delete_many(self, ids: Iterable[int]) -> None:
        for cid in ids or []:
            self._by_id.pop(int(cid), None)

    def list_all(self) -> List[ContactMem]:
        return list(self._by_id.values())

    def get(self, contact_id: int) -> Optional[ContactMem]:
        return self._by_id.get(int(contact_id))

    def get_many(self, ids: Iterable[int]) -> List[ContactMem]:
        out: List[ContactMem] = []
        for cid in ids or []:
            m = self._by_id.get(int(cid))
            if m is not None:
                out.append(m)
        return out

    def update(
        self,
        *,
        contact_id: int,
        emp_id: str,
        name: str,
        phone: str,
        agency: str,
        branch: str,
        last_assigned_code: str | None = None,
        last_assigned_label: str | None = None,
        last_assigned_at: str | None = None,
    ) -> None:
        cid = int(contact_id)
        cur = self._by_id.get(cid)
        if cur is None:
            self._by_id[cid] = ContactMem(
                id=cid,
                emp_id=emp_id or "",
                name=name or "",
                phone=phone or "",
                agency=agency or "",
                branch=branch or "",
                last_assigned_code=last_assigned_code,
                last_assigned_label=last_assigned_label,
                last_assigned_at=last_assigned_at,
            )
            self._loaded = True
            return

        existing_last_assigned_code = cur.last_assigned_code
        existing_last_assigned_label = cur.last_assigned_label
        existing_last_assigned_at = cur.last_assigned_at
        cur.emp_id = emp_id or ""
        cur.name = name or ""
        cur.phone = phone or ""
        cur.agency = agency or ""
        cur.branch = branch or ""
        cur.last_assigned_code = (
            last_assigned_code if last_assigned_code is not None else existing_last_assigned_code
        )
        cur.last_assigned_label = (
            last_assigned_label if last_assigned_label is not None else existing_last_assigned_label
        )
        cur.last_assigned_at = (
            last_assigned_at if last_assigned_at is not None else existing_last_assigned_at
        )

    def search(self, keyword: str) -> List[ContactMem]:
        kw = (keyword or "").strip().lower()
        if not kw:
            return sorted(self._by_id.values(), key=lambda x: (x.name, x.emp_id, x.id))

        def hay(m: ContactMem) -> str:
            return " ".join([m.emp_id, m.name, m.phone, m.agency, m.branch]).lower()

        out = [m for m in self._by_id.values() if kw in hay(m)]
        return sorted(out, key=lambda x: (x.name, x.emp_id, x.id))
