from __future__ import annotations

import hashlib
import traceback
from datetime import datetime
from typing import Any, Optional

from .models import ErrorReportContext


def _now_local_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _safe_str(v: Any, limit: int = 4000) -> str:
    s = "" if v is None else str(v)
    s = s.replace("\r", " ").strip()
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def build_error_fingerprint(
    *,
    stage: str,
    exc: Exception,
    send_list_id: Any = None,
    recipient_emp_id: Any = None,
) -> str:
    raw = "|".join(
        [
            _safe_str(stage, 200),
            exc.__class__.__name__,
            _safe_str(exc, 500),
            _safe_str(send_list_id, 100),
            _safe_str(recipient_emp_id, 100),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def collect_error_context(
    *,
    exc: Exception,
    stage: str,
    attempt: int,
    run_logger=None,
    trace_log_path: str = "",
    job=None,
    recipient=None,
    extra: Optional[dict] = None,
) -> ErrorReportContext:
    run_id = ""
    run_log_path = ""
    if run_logger is not None:
        try:
            run_id = str(getattr(run_logger, "run_id", "") or "")
        except Exception:
            run_id = ""
        try:
            run_log_path = str(getattr(run_logger, "path_str", lambda: "")() or "")
        except Exception:
            run_log_path = ""

    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    fingerprint = build_error_fingerprint(
        stage=stage,
        exc=exc,
        send_list_id=getattr(job, "send_list_id", None) if job else None,
        recipient_emp_id=getattr(recipient, "emp_id", None) if recipient else None,
    )

    return ErrorReportContext(
        run_id=run_id,
        occurred_at=_now_local_str(),
        stage=_safe_str(stage, 200),
        exception_type=exc.__class__.__name__,
        exception_message=_safe_str(exc, 2000),
        traceback_text=tb_text,
        fingerprint=fingerprint,
        send_list_id=_safe_int(getattr(job, "send_list_id", None) if job else None),
        send_list_title=_safe_str(getattr(job, "title", "") if job else "", 300),
        campaign_id=_safe_int(getattr(job, "campaign_id", None) if job else None),
        campaign_name=_safe_str(getattr(job, "campaign_name", "") if job else "", 300),
        send_mode=_safe_str(getattr(job, "send_mode", "") if job else "", 100),
        recipient_name=_safe_str(getattr(recipient, "name", "") if recipient else "", 300),
        recipient_emp_id=_safe_str(getattr(recipient, "emp_id", "") if recipient else "", 100),
        recipient_phone=_safe_str(getattr(recipient, "phone", "") if recipient else "", 100),
        recipient_agency=_safe_str(getattr(recipient, "agency", "") if recipient else "", 200),
        recipient_branch=_safe_str(getattr(recipient, "branch", "") if recipient else "", 200),
        attempt=max(0, int(attempt or 0)),
        run_log_path=run_log_path,
        trace_log_path=_safe_str(trace_log_path, 1000),
        extra=dict(extra or {}),
    )