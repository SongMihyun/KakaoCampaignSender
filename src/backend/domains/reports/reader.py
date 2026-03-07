# FILE: src/backend/domains/reports/reader.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class SendReportReader:
    """
    발송 리포트(JSON) 파싱 전담.
    UI는 이 클래스를 직접 다루기보다 LogsService를 통해 사용하는 것을 권장한다.
    """

    def load_json(self, path: str | Path) -> Dict[str, Any]:
        p = Path(path)
        return json.loads(p.read_text(encoding="utf-8"))

    def build_rows(self, obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        started_at = str(obj.get("started_at", "") or obj.get("created_at", "") or "")
        ended_at = str(obj.get("ended_at", "") or "")
        ts_base = ended_at or started_at

        lists = obj.get("lists", []) or []
        if not isinstance(lists, list):
            return rows

        for lst in lists:
            if not isinstance(lst, dict):
                continue

            title = str(lst.get("title", "") or "")
            send_list_id = lst.get("send_list_id", "")
            group_name = str(lst.get("group_name", "") or "")
            campaign_id = lst.get("campaign_id", "")
            campaign_name = str(lst.get("campaign_name", "") or "")

            items = lst.get("campaign_items", []) or lst.get("items", []) or []
            if not isinstance(items, list):
                items = []

            message_len = self._calc_message_len(items)
            image_count = self._calc_image_count(items)

            batch_id = (
                f"send_list:{send_list_id}"
                if send_list_id != ""
                else str(obj.get("run_id", "") or "")
            )

            recipients = lst.get("recipients", []) or lst.get("results", []) or []
            if not isinstance(recipients, list):
                recipients = []

            list_meta = {
                "title": title,
                "send_list_id": send_list_id,
                "group_name": group_name,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "campaign_items": items,
            }

            for r in recipients:
                if not isinstance(r, dict):
                    continue

                rows.append(
                    self._build_recipient_row(
                        recipient_obj=r,
                        ts_base=ts_base,
                        campaign_id=campaign_id,
                        batch_id=batch_id,
                        group_name=group_name,
                        title=title,
                        campaign_name=campaign_name,
                        message_len=message_len,
                        image_count=image_count,
                        list_meta=list_meta,
                    )
                )

        return rows

    def filter_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        status: str | None = None,
        keyword: str = "",
    ) -> List[Dict[str, Any]]:
        status_norm = str(status or "").strip().upper()
        keyword_norm = str(keyword or "").strip().lower()

        if not status_norm and not keyword_norm:
            return list(rows)

        filtered: List[Dict[str, Any]] = []
        for row in rows:
            row_status = str(row.get("status", "") or "").upper()
            if status_norm and not row_status.startswith(status_norm):
                continue

            if keyword_norm:
                hay = " ".join(
                    [
                        str(row.get("channel", "") or ""),
                        str(row.get("recipient", "") or ""),
                        str(row.get("reason", "") or ""),
                        str(row.get("_list_title", "") or ""),
                        str(row.get("_campaign_name", "") or ""),
                        str(row.get("_group_name", "") or ""),
                    ]
                ).lower()
                if keyword_norm not in hay:
                    continue

            filtered.append(row)

        return filtered

    def build_retry_targets(
        self,
        rows: List[Dict[str, Any]],
        *,
        fail_prefix: str = "FAIL",
    ) -> List[str]:
        prefix = str(fail_prefix or "FAIL").upper()
        targets: List[str] = []

        for row in rows:
            status = str(row.get("status", "") or "").upper()
            if not status.startswith(prefix):
                continue
            recipient = str(row.get("recipient", "") or "")
            reason = str(row.get("reason", "") or "")
            targets.append(f"{recipient} | {reason}")

        return targets

    def _calc_message_len(self, items: List[Any]) -> int:
        total = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("item_type", "")).upper() == "TEXT":
                total += len(str(item.get("text", "") or ""))
        return total

    def _calc_image_count(self, items: List[Any]) -> int:
        count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("item_type", "")).upper() == "IMAGE":
                count += 1
        return count

    def _build_recipient_row(
        self,
        *,
        recipient_obj: Dict[str, Any],
        ts_base: str,
        campaign_id: Any,
        batch_id: str,
        group_name: str,
        title: str,
        campaign_name: str,
        message_len: int,
        image_count: int,
        list_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        name = str(recipient_obj.get("name", "") or "")
        emp_id = str(recipient_obj.get("emp_id", "") or "")
        phone = str(recipient_obj.get("phone", "") or "")

        recipient = name
        if emp_id or phone:
            recipient = f"{name} ({emp_id}/{phone})".strip()

        status = str(recipient_obj.get("status", "") or "").upper()
        reason = str(recipient_obj.get("reason", "") or "")
        attempt = int(recipient_obj.get("attempt", 0) or 0)
        ts = str(recipient_obj.get("ts", "") or ts_base)
        channel = group_name or title or campaign_name

        return {
            "id": "",
            "ts": ts,
            "campaign_id": campaign_id,
            "batch_id": batch_id,
            "channel": channel,
            "recipient": recipient,
            "status": status,
            "reason": reason,
            "attempt": attempt,
            "message_len": message_len,
            "image_count": image_count,
            "_list_title": title,
            "_campaign_name": campaign_name,
            "_group_name": group_name,
            "_list_meta": list_meta,
        }