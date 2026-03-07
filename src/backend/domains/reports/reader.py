from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class SendReportReader:
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

            message_len = 0
            image_count = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                if str(it.get("item_type", "")).upper() == "TEXT":
                    message_len += len(str(it.get("text", "") or ""))
                elif str(it.get("item_type", "")).upper() == "IMAGE":
                    image_count += 1

            batch_id = f"send_list:{send_list_id}" if send_list_id != "" else str(obj.get("run_id", "") or "")

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

                name = str(r.get("name", "") or "")
                emp_id = str(r.get("emp_id", "") or "")
                phone = str(r.get("phone", "") or "")
                recipient = name
                if emp_id or phone:
                    recipient = f"{name} ({emp_id}/{phone})".strip()

                status = str(r.get("status", "") or "").upper()
                reason = str(r.get("reason", "") or "")
                attempt = int(r.get("attempt", 0) or 0)

                channel = group_name or title or campaign_name
                ts = str(r.get("ts", "") or ts_base)

                rows.append(
                    {
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
                )

        return rows