from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.domains.reports.models import (
    SendReport,
    ReportList,
    ReportRecipient,
    ReportItem,
)


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


class SendReportWriter:
    def __init__(self, *, base_dir: Path, run_id: str) -> None:
        self._lock = threading.Lock()

        self._base_dir = Path(base_dir)
        self._reports_dir = self._base_dir / "reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        self._run_id = str(run_id)
        self._path = self._reports_dir / f"send_report_{self._run_id}.json"

        self._report = SendReport(run_id=self._run_id, started_at=_now_ts())
        self._list_map: Dict[int, int] = {}

    @property
    def path(self) -> Path:
        return self._path

    @property
    def run_id(self) -> str:
        return self._run_id

    def set_meta(self, *, total_lists: int, total_targets: int) -> None:
        with self._lock:
            self._report.total_lists = _safe_int(total_lists)
            self._report.total_targets = _safe_int(total_targets)

    def add_list(
        self,
        *,
        list_index: int,
        send_list_id: int,
        title: str,
        group_name: str,
        campaign_id: int,
        campaign_name: str,
        recipients_total: int,
        campaign_items: Any,
        recipients_snapshot: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        with self._lock:
            rl = ReportList(
                send_list_id=_safe_int(send_list_id),
                title=str(title or ""),
                group_name=str(group_name or ""),
                campaign_id=_safe_int(campaign_id),
                campaign_name=str(campaign_name or ""),
                total_recipients=_safe_int(recipients_total),
                recipients_snapshot=list(recipients_snapshot or []),
                recipients=[],
                campaign_items=[],
            )

            for it in (campaign_items or []):
                if isinstance(it, dict):
                    typ = str(it.get("item_type", "") or "").upper().strip()
                    if typ == "TEXT":
                        rl.campaign_items.append(
                            ReportItem(item_type="TEXT", text=str(it.get("text", "") or "").strip())
                        )
                    else:
                        b = it.get("image_bytes", b"") or b""
                        rl.campaign_items.append(
                            ReportItem(
                                item_type="IMAGE",
                                image_name=str(it.get("image_name", "") or ""),
                                image_bytes_len=len(b),
                            )
                        )
                else:
                    typ = str(getattr(it, "item_type", "") or "").upper().strip()
                    if typ == "TEXT":
                        rl.campaign_items.append(
                            ReportItem(item_type="TEXT", text=str(getattr(it, "text", "") or "").strip())
                        )
                    else:
                        b = getattr(it, "image_bytes", b"") or b""
                        rl.campaign_items.append(
                            ReportItem(
                                item_type="IMAGE",
                                image_name=str(getattr(it, "image_name", "") or ""),
                                image_bytes_len=len(b),
                            )
                        )

            self._report.lists.append(rl)
            self._list_map[int(list_index)] = len(self._report.lists) - 1

    def add_recipient_result(
        self,
        *,
        list_index: int,
        emp_id: str,
        name: str,
        phone: str,
        agency: str,
        branch: str,
        status: str,
        reason: str = "",
        attempt: int = 0,
    ) -> None:
        with self._lock:
            idx = self._list_map.get(int(list_index))
            if idx is None:
                return

            rr = ReportRecipient(
                emp_id=str(emp_id or ""),
                name=str(name or ""),
                phone=str(phone or ""),
                agency=str(agency or ""),
                branch=str(branch or ""),
                status=str(status or "").upper().strip(),
                reason=str(reason or ""),
                attempt=_safe_int(attempt, 0),
            )
            self._report.lists[idx].recipients.append(rr)

    def finish(self, *, list_done: int, success: int, fail: int, stopped: bool) -> None:
        with self._lock:
            self._report.ended_at = _now_ts()
            self._report.list_done = _safe_int(list_done)
            self._report.success = _safe_int(success)
            self._report.fail = _safe_int(fail)
            self._report.stopped = bool(stopped)

    def save(self) -> Path:
        with self._lock:
            payload = asdict(self._report)

        tmp = str(self._path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        os.replace(tmp, self._path)
        return self._path