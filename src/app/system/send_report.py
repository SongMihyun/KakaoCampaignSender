# src/app/system/send_report.py
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


@dataclass
class ReportRecipient:
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""
    status: str = ""        # SUCCESS / FAIL / NOT_FOUND / SKIP / TAIL_RETRY_SCHEDULED / SUCCESS(TAIL_RETRY) ...
    reason: str = ""
    attempt: int = 0


@dataclass
class ReportItem:
    item_type: str = ""     # TEXT / IMAGE
    text: str = ""          # TEXT 내용
    image_name: str = ""    # IMAGE 이름(있으면)
    image_bytes_len: int = 0  # IMAGE 원본 bytes 길이만 기록(파일에 bytes 저장 금지)


@dataclass
class ReportList:
    send_list_id: int = 0
    title: str = ""
    group_name: str = ""
    campaign_id: int = 0
    campaign_name: str = ""
    total_recipients: int = 0
    recipients: List[ReportRecipient] = field(default_factory=list)
    campaign_items: List[ReportItem] = field(default_factory=list)


@dataclass
class SendReport:
    run_id: str
    started_at: str = field(default_factory=_now_ts)
    ended_at: str = ""
    total_lists: int = 0
    total_targets: int = 0
    list_done: int = 0
    success: int = 0
    fail: int = 0
    stopped: bool = False
    lists: List[ReportList] = field(default_factory=list)


class SendReportWriter:
    """
    발송 1회(RUN) 단위로 리포트를 누적/저장한다.
    - thread-safe: Worker thread에서 기록해도 안전
    - 저장 위치: base_dir/reports/send_report_{run_id}.json
    """

    def __init__(self, *, base_dir: Path, run_id: str) -> None:
        self._lock = threading.Lock()

        self._base_dir = Path(base_dir)
        self._reports_dir = self._base_dir / "reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        self._run_id = str(run_id)
        self._path = self._reports_dir / f"send_report_{self._run_id}.json"

        self._report = SendReport(run_id=self._run_id)

        # list_index -> index in report.lists
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
        campaign_items: List[Any],
    ) -> None:
        """
        리스트 시작 시 1회 호출
        campaign_items는 원본 객체(list of DraftItem 등)여도 됨.
        이미지 bytes는 저장하지 않고 길이만 기록
        """
        with self._lock:
            rl = ReportList(
                send_list_id=_safe_int(send_list_id),
                title=str(title or ""),
                group_name=str(group_name or ""),
                campaign_id=_safe_int(campaign_id),
                campaign_name=str(campaign_name or ""),
                total_recipients=_safe_int(recipients_total),
                recipients=[],
                campaign_items=[],
            )

            for it in (campaign_items or []):
                # 객체/딕트 혼용 방어
                if isinstance(it, dict):
                    typ = str(it.get("item_type", "") or "").upper().strip()
                    if typ == "TEXT":
                        text = str(it.get("text", "") or "").strip()
                        rl.campaign_items.append(ReportItem(item_type="TEXT", text=text))
                    else:
                        image_name = str(it.get("image_name", "") or "")
                        b = it.get("image_bytes", b"") or b""
                        rl.campaign_items.append(
                            ReportItem(item_type="IMAGE", image_name=image_name, image_bytes_len=len(b))
                        )
                else:
                    typ = str(getattr(it, "item_type", "") or "").upper().strip()
                    if typ == "TEXT":
                        text = str(getattr(it, "text", "") or "").strip()
                        rl.campaign_items.append(ReportItem(item_type="TEXT", text=text))
                    else:
                        image_name = str(getattr(it, "image_name", "") or "")
                        b = getattr(it, "image_bytes", b"") or b""
                        rl.campaign_items.append(
                            ReportItem(item_type="IMAGE", image_name=image_name, image_bytes_len=len(b))
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
