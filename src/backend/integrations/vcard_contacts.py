from __future__ import annotations

import quopri
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class VCardContact:
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    phone_alt: str = ""
    agency: str = ""
    branch: str = ""
    note: str = ""


def is_supported_vcard_file(path: str | Path) -> bool:
    return str(path or "").lower().endswith((".vcf", ".vcard"))


def load_vcard_contacts(path: str | Path) -> list[VCardContact]:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    cards = _split_cards(_unfold_lines(text))
    return [_parse_card(card) for card in cards if card]


def save_vcard_contacts(path: str | Path, contacts: list[VCardContact]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    chunks = [_format_card(contact) for contact in contacts if (contact.name or contact.phone).strip()]
    p.write_text("".join(chunks), encoding="utf-8", newline="\r\n")


def _unfold_lines(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for line in lines:
        if not line:
            continue
        if unfolded and (line.startswith(" ") or line.startswith("\t")):
            if unfolded[-1].endswith("="):
                unfolded[-1] = unfolded[-1][:-1] + line[1:]
            else:
                unfolded[-1] += line[1:]
        elif unfolded and line.startswith("="):
            if unfolded[-1].endswith("="):
                unfolded[-1] = unfolded[-1][:-1] + line
            else:
                unfolded[-1] += line
        else:
            unfolded.append(line)
    return unfolded


def _split_cards(lines: list[str]) -> list[list[str]]:
    cards: list[list[str]] = []
    current: list[str] = []
    in_card = False
    for line in lines:
        upper = line.upper()
        if upper == "BEGIN:VCARD":
            current = []
            in_card = True
            continue
        if upper == "END:VCARD":
            if in_card:
                cards.append(current)
            current = []
            in_card = False
            continue
        if in_card:
            current.append(line)
    return cards


def _parse_card(lines: list[str]) -> VCardContact:
    fn = ""
    org = ""
    note = ""
    phones: list[str] = []

    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        base = key.split(";", 1)[0].upper()
        decoded = _decode_value(key, value)
        if base == "FN":
            fn = decoded
        elif base == "N" and not fn:
            fn = decoded.replace(";", " ").strip()
        elif base == "ORG":
            org = decoded.replace(";", " ").strip()
        elif base == "NOTE":
            note = decoded
        elif base == "TEL":
            phone = _normalize_phone(decoded)
            if phone:
                phones.append(phone)

    agency = _extract_group_name(note)
    branch = org.strip()
    emp_id, name = _split_display_name(fn, agency=agency, branch=branch)
    return VCardContact(
        emp_id=emp_id,
        name=name or fn.strip(),
        phone=phones[0] if phones else "",
        phone_alt=phones[1] if len(phones) > 1 else "",
        agency=agency,
        branch=branch,
        note=note,
    )


def _decode_value(key: str, value: str) -> str:
    raw = value.strip()
    if "ENCODING=QUOTED-PRINTABLE" in key.upper():
        decoded = quopri.decodestring(raw.encode("ascii", errors="ignore"))
        charset_match = re.search(r"CHARSET=([^;:]+)", key, re.IGNORECASE)
        charset = (charset_match.group(1) if charset_match else "utf-8").strip()
        try:
            return decoded.decode(charset, errors="replace").strip()
        except LookupError:
            return decoded.decode("utf-8", errors="replace").strip()
    return raw


def _normalize_phone(value: str) -> str:
    phone = re.sub(r"[^\d+]", "", value or "")
    if phone.startswith("+82"):
        phone = "0" + phone[3:]
    return phone


def _extract_group_name(note: str) -> str:
    text = (note or "").strip()
    match = re.search(r"그룹명\s*:\s*([^,\n\r]+)", text)
    if match:
        return match.group(1).strip()
    return ""


def _split_display_name(fn: str, *, agency: str, branch: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", (fn or "").strip()) if p]
    if not parts:
        return "", ""

    emp_id = ""
    if re.fullmatch(r"\d{4,}", parts[0]):
        emp_id = parts.pop(0)

    for tail in (branch, agency):
        tail = (tail or "").strip()
        if tail and parts and parts[-1] == tail:
            parts.pop()

    return emp_id, " ".join(parts).strip()


def _format_card(contact: VCardContact) -> str:
    display = " ".join(
        x
        for x in [
            contact.emp_id.strip(),
            contact.name.strip(),
            contact.agency.strip(),
            contact.branch.strip(),
        ]
        if x
    )
    lines = [
        "BEGIN:VCARD",
        "VERSION:2.1",
        f"N;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:;{_qp(display)};;;",
        f"FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:{_qp(display)}",
    ]
    if contact.phone.strip():
        lines.append(f"TEL;CELL:{_normalize_phone(contact.phone)}")
    if contact.phone_alt.strip():
        lines.append(f"TEL;WORK:{_normalize_phone(contact.phone_alt)}")
    if contact.branch.strip():
        lines.append(f"ORG;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:{_qp(contact.branch.strip())}")
    note = contact.note.strip()
    if contact.agency.strip():
        note = f"그룹명:{contact.agency.strip()},,"
    if note:
        lines.append(f"NOTE;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:{_qp(note)}")
    lines.append("END:VCARD")
    return "\n".join(lines) + "\n"


def _qp(value: str) -> str:
    return quopri.encodestring(value.encode("utf-8"), quotetabs=True).decode("ascii").replace("=\n", "")
