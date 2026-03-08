from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class ErrorReportContext:
    run_id: str
    occurred_at: str

    stage: str
    exception_type: str
    exception_message: str
    traceback_text: str
    fingerprint: str

    send_list_id: Optional[int] = None
    send_list_title: str = ""
    campaign_id: Optional[int] = None
    campaign_name: str = ""
    send_mode: str = ""

    recipient_name: str = ""
    recipient_emp_id: str = ""
    recipient_phone: str = ""
    recipient_agency: str = ""
    recipient_branch: str = ""

    attempt: int = 0

    run_log_path: str = ""
    trace_log_path: str = ""
    screenshot_path: str = ""

    extra_json_path: str = ""
    package_dir: str = ""
    zip_path: str = ""

    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class EmailReportConfig:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    mail_from: str = ""
    mail_to: str = ""
    subject_prefix: str = "[KCS][ERROR][TEST]"
    max_per_run: int = 5
    cooldown_sec: int = 60

    @property
    def ready(self) -> bool:
        return bool(
            self.enabled
            and self.smtp_host
            and self.smtp_port
            and self.smtp_user
            and self.smtp_pass
            and self.mail_from
            and self.mail_to
        )


@dataclass(slots=True)
class ErrorReportArtifacts:
    base_dir: Path
    screenshot_path: Optional[Path] = None
    meta_json_path: Optional[Path] = None
    zip_path: Optional[Path] = None