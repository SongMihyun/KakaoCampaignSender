from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.domains.campaigns.models import CampaignItem
from backend.domains.reports.reader import SendReportReader
from backend.domains.sending.models import Recipient, SendJob


class RetryBuildError(RuntimeError):
    pass


class NoRetryableTargetsError(RetryBuildError):
    pass


class MissingOriginalConditionsError(RetryBuildError):
    pass


class MissingAttachmentError(RetryBuildError):
    def __init__(self, file_path: str) -> None:
        super().__init__(file_path)
        self.file_path = file_path


@dataclass(slots=True)
class RetryBuildResult:
    jobs: list[SendJob]
    retry_target_count: int
    source_batch_id: str
    source_report_file: str
    campaign_name: str
    retry_run_id: str
    retry_batch_id: str
    report_meta: dict[str, Any] = field(default_factory=dict)
    preview_names: list[str] = field(default_factory=list)


class FailedReportRetryBuilder:
    def __init__(self, *, campaigns_service, report_reader: SendReportReader | None = None) -> None:
        self.campaigns_service = campaigns_service
        self.report_reader = report_reader or SendReportReader()

    def build(self, report_path: str | Path) -> RetryBuildResult:
        path = Path(report_path)
        obj = self.report_reader.load_json(path)

        jobs: list[SendJob] = []
        preview_names: list[str] = []
        total_targets = 0

        lists = obj.get("lists", []) or []
        if not isinstance(lists, list):
            lists = []

        for list_obj in lists:
            if not isinstance(list_obj, dict):
                continue

            retry_recipients, retry_snapshot = self._build_retry_recipients(list_obj)
            if not retry_recipients:
                continue

            campaign_id = int(list_obj.get("campaign_id", 0) or 0)
            campaign_name = str(list_obj.get("campaign_name", "") or "")
            campaign_items = self._load_campaign_items(campaign_id, list_obj)
            self._validate_campaign_items(campaign_items)

            campaign = None
            if self.campaigns_service is not None and campaign_id > 0:
                try:
                    campaign = self.campaigns_service.get_campaign(campaign_id)
                except Exception:
                    campaign = None

            send_mode = str(getattr(campaign, "send_mode", "") or "clipboard")
            if send_mode not in ("clipboard", "multi_attach"):
                send_mode = "clipboard"

            jobs.append(
                SendJob(
                    send_list_id=int(list_obj.get("send_list_id", 0) or 0),
                    title=str(list_obj.get("title", "") or ""),
                    group_name=str(list_obj.get("group_name", "") or ""),
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    send_mode=send_mode,
                    recipients=retry_recipients,
                    recipients_snapshot=retry_snapshot,
                    campaign_items=campaign_items,
                )
            )
            total_targets += len(retry_recipients)
            preview_names.extend([r.name for r in retry_recipients if r.name])

        if total_targets <= 0:
            raise NoRetryableTargetsError("재발송 가능한 실패 대상이 없습니다.")

        retry_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_batch_id = self._source_batch_id(obj, lists)
        retry_batch_id = f"retry:{source_batch_id}:{retry_run_id}"
        campaign_label = self._campaign_label(jobs)

        report_meta = {
            "report_type": "retry",
            "batch_id": retry_batch_id,
            "source_batch_id": source_batch_id,
            "source_report_file": path.name,
            "retry_only_failed": True,
            "retry_created_at": datetime.now().isoformat(timespec="seconds"),
            "retry_target_count": total_targets,
        }

        return RetryBuildResult(
            jobs=jobs,
            retry_target_count=total_targets,
            source_batch_id=source_batch_id,
            source_report_file=path.name,
            campaign_name=campaign_label,
            retry_run_id=retry_run_id,
            retry_batch_id=retry_batch_id,
            report_meta=report_meta,
            preview_names=preview_names,
        )

    def _build_retry_recipients(self, list_obj: dict[str, Any]) -> tuple[list[Recipient], list[dict[str, Any]]]:
        recipients = list_obj.get("recipients", []) or list_obj.get("results", []) or []
        if not isinstance(recipients, list):
            recipients = []

        has_retryable_field = any(isinstance(r, dict) and "retryable" in r for r in recipients)
        snapshots = list_obj.get("recipients_snapshot", []) or []
        if not isinstance(snapshots, list):
            snapshots = []

        out: list[Recipient] = []
        out_snapshot: list[dict[str, Any]] = []

        for result in recipients:
            if not isinstance(result, dict):
                continue
            if not self._is_retryable_failed(result, has_retryable_field=has_retryable_field):
                continue

            snap = self._find_snapshot_for_result(result, snapshots)
            data = dict(snap or result)
            name = str(data.get("name", "") or "").strip()
            if not name:
                continue

            recipient = Recipient(
                contact_id=int(data.get("contact_id", 0) or 0),
                emp_id=str(data.get("emp_id", "") or ""),
                name=name,
                phone=str(data.get("phone", "") or ""),
                agency=str(data.get("agency", "") or ""),
                branch=str(data.get("branch", "") or ""),
                last_assigned_code=data.get("last_assigned_code"),
                last_assigned_label=data.get("last_assigned_label"),
                last_assigned_at=data.get("last_assigned_at"),
            )
            out.append(recipient)
            out_snapshot.append(
                {
                    "contact_id": recipient.contact_id,
                    "emp_id": recipient.emp_id,
                    "name": recipient.name,
                    "phone": recipient.phone,
                    "agency": recipient.agency,
                    "branch": recipient.branch,
                    "last_assigned_code": recipient.last_assigned_code,
                    "last_assigned_label": recipient.last_assigned_label,
                    "last_assigned_at": recipient.last_assigned_at,
                    "assigned_value": data.get("assigned_value"),
                    "assigned_value_label": data.get("assigned_value_label"),
                    "assigned_value_pool_id": data.get("assigned_value_pool_id"),
                    "assigned_value_item_id": data.get("assigned_value_item_id"),
                }
            )

        return out, out_snapshot

    def _is_retryable_failed(self, result: dict[str, Any], *, has_retryable_field: bool) -> bool:
        status = str(result.get("status", "") or "").upper().strip()
        if not status.startswith("FAIL"):
            return False
        if has_retryable_field:
            return bool(result.get("retryable", False))
        return True

    def _find_snapshot_for_result(
        self,
        result: dict[str, Any],
        snapshots: list[Any],
    ) -> dict[str, Any] | None:
        keys = (
            str(result.get("contact_id", "") or ""),
            str(result.get("emp_id", "") or ""),
            str(result.get("name", "") or ""),
            str(result.get("phone", "") or ""),
        )
        for snap in snapshots:
            if not isinstance(snap, dict):
                continue
            candidate = (
                str(snap.get("contact_id", "") or ""),
                str(snap.get("emp_id", "") or ""),
                str(snap.get("name", "") or ""),
                str(snap.get("phone", "") or ""),
            )
            if keys[0] and keys[0] == candidate[0]:
                return snap
            if keys[1:] == candidate[1:]:
                return snap
        return None

    def _load_campaign_items(self, campaign_id: int, list_obj: dict[str, Any]) -> list[Any]:
        db_items: list[Any] = []
        if self.campaigns_service is not None and campaign_id > 0:
            try:
                db_items = list(self.campaigns_service.get_campaign_items(campaign_id) or [])
            except Exception:
                db_items = []
        if db_items:
            return db_items

        report_items = list_obj.get("campaign_items", []) or []
        if not isinstance(report_items, list) or not report_items:
            raise MissingOriginalConditionsError(
                "원본 발송 조건을 찾을 수 없어 재발송할 수 없습니다.\n"
                "원본 캠페인 또는 첨부파일이 삭제되었는지 확인해 주세요."
            )

        converted: list[CampaignItem] = []
        for index, item in enumerate(report_items, start=1):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("item_type", "") or "").upper().strip()
            if item_type == "TEXT":
                text = str(item.get("text", "") or "")
                if text.strip():
                    converted.append(
                        CampaignItem(
                            id=0,
                            campaign_id=campaign_id,
                            item_type="TEXT",
                            text=text,
                            sort_order=index,
                        )
                    )
                continue
            raise MissingOriginalConditionsError(
                "원본 발송 조건을 찾을 수 없어 재발송할 수 없습니다.\n"
                "원본 캠페인 또는 첨부파일이 삭제되었는지 확인해 주세요."
            )

        if not converted:
            raise MissingOriginalConditionsError(
                "원본 발송 조건을 찾을 수 없어 재발송할 수 없습니다.\n"
                "원본 캠페인 또는 첨부파일이 삭제되었는지 확인해 주세요."
            )
        return converted

    def _validate_campaign_items(self, items: list[Any]) -> None:
        if not items:
            raise MissingOriginalConditionsError(
                "원본 발송 조건을 찾을 수 없어 재발송할 수 없습니다.\n"
                "원본 캠페인 또는 첨부파일이 삭제되었는지 확인해 주세요."
            )

        for item in items:
            item_type = str(getattr(item, "item_type", "") or "").upper().strip()
            if item_type != "IMAGE":
                continue

            image_path = str(getattr(item, "image_path", "") or "").strip()
            image_bytes = getattr(item, "image_bytes", b"") or b""
            if image_path and not Path(image_path).exists():
                raise MissingAttachmentError(image_path)
            if not image_path and not image_bytes:
                image_name = str(getattr(item, "image_name", "") or "").strip()
                raise MissingAttachmentError(image_name or "(이미지 경로 없음)")

    def _source_batch_id(self, obj: dict[str, Any], lists: list[Any]) -> str:
        batch_id = str(obj.get("batch_id", "") or "").strip()
        if batch_id:
            return batch_id
        for list_obj in lists:
            if not isinstance(list_obj, dict):
                continue
            send_list_id = str(list_obj.get("send_list_id", "") or "").strip()
            if send_list_id:
                return f"send_list:{send_list_id}"
        run_id = str(obj.get("run_id", "") or "").strip()
        return f"run:{run_id}" if run_id else "report"

    def _campaign_label(self, jobs: list[SendJob]) -> str:
        names = []
        for job in jobs:
            name = str(job.campaign_name or "").strip()
            if name and name not in names:
                names.append(name)
        if not names:
            return "(캠페인)"
        if len(names) == 1:
            return names[0]
        return f"{names[0]} 외 {len(names) - 1}개"
