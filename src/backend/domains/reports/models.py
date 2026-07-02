from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ReportRecipient:
    emp_id: str = ""
    name: str = ""
    phone: str = ""
    agency: str = ""
    branch: str = ""
    status: str = ""
    status_code: int = 0
    status_message: str = ""
    step: str = ""
    reason: str = ""
    attempt: int = 0
    retryable: bool = False
    failure_step: str = ""
    last_success_step: str = ""
    debug_steps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReportItem:
    item_type: str = ""
    text: str = ""
    image_name: str = ""
    image_bytes_len: int = 0


@dataclass
class ReportList:
    send_list_id: int = 0
    title: str = ""
    group_name: str = ""
    campaign_id: int = 0
    campaign_name: str = ""
    total_recipients: int = 0
    recipients_snapshot: List[Dict[str, Any]] = field(default_factory=list)
    recipients: List[ReportRecipient] = field(default_factory=list)
    campaign_items: List[ReportItem] = field(default_factory=list)


@dataclass
class SendReport:
    run_id: str
    report_type: str = "send"
    app_version: str = ""
    report_schema: int = 2
    batch_id: str = ""
    source_batch_id: str = ""
    source_report_file: str = ""
    retry_only_failed: bool = False
    retry_created_at: str = ""
    retry_target_count: int = 0
    started_at: str = ""
    ended_at: str = ""
    total_lists: int = 0
    total_targets: int = 0
    list_done: int = 0
    success: int = 0
    fail: int = 0
    stopped: bool = False
    paused: bool = False
    lists: List[ReportList] = field(default_factory=list)
