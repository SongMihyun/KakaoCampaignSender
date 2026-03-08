from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from app.paths import user_data_dir

from .collector import collect_error_context
from .mailer import send_error_report_email
from .models import EmailReportConfig, ErrorReportContext
from .package_builder import build_error_report_package
from .screenshot import capture_fullscreen_to


def _env_flag(name: str, default: bool = False) -> bool:
    v = str(os.getenv(name, "")).strip().lower()
    if not v:
        return default
    return v in ("1", "true", "on", "yes")


def load_email_report_config_from_env() -> EmailReportConfig:
    return EmailReportConfig(
        enabled=_env_flag("KCS_ERROR_REPORT_ENABLED", False),
        smtp_host=str(os.getenv("KCS_ERROR_REPORT_SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com"),
        smtp_port=int(str(os.getenv("KCS_ERROR_REPORT_SMTP_PORT", "587") or "587")),
        smtp_user=str(os.getenv("KCS_ERROR_REPORT_SMTP_USER", "") or ""),
        smtp_pass=str(os.getenv("KCS_ERROR_REPORT_SMTP_PASS", "") or ""),
        mail_from=str(os.getenv("KCS_ERROR_REPORT_FROM", "") or ""),
        mail_to=str(os.getenv("KCS_ERROR_REPORT_TO", "") or ""),
        subject_prefix=str(os.getenv("KCS_ERROR_REPORT_SUBJECT_PREFIX", "[KCS][ERROR][TEST]") or "[KCS][ERROR][TEST]"),
        max_per_run=int(str(os.getenv("KCS_ERROR_REPORT_MAX_PER_RUN", "5") or "5")),
        cooldown_sec=int(str(os.getenv("KCS_ERROR_REPORT_COOLDOWN_SEC", "60") or "60")),
    )


class ErrorReporter:
    """
    - 절대 원 예외를 덮어쓰지 않는다.
    - 내부 실패는 run_logger에만 남기고 삼킨다.
    - 같은 run 내 과도한 중복 전송을 막는다.
    """

    def __init__(self, *, cfg: Optional[EmailReportConfig] = None, run_logger=None) -> None:
        self._cfg = cfg or load_email_report_config_from_env()
        self._run_logger = run_logger

        self._lock = threading.Lock()
        self._run_sent_count: dict[str, int] = {}
        self._fingerprint_last_sent_mono: dict[tuple[str, str], float] = {}

    def _safe_log_event(self, event: str, **fields) -> None:
        try:
            if self._run_logger:
                self._run_logger.log_event(event, **fields)
        except Exception:
            pass

    def _check_throttle(self, run_id: str, fingerprint: str) -> bool:
        import time

        with self._lock:
            sent_count = self._run_sent_count.get(run_id, 0)
            if sent_count >= max(0, int(self._cfg.max_per_run)):
                return False

            now = time.monotonic()
            key = (run_id, fingerprint)
            last = self._fingerprint_last_sent_mono.get(key, 0.0)
            if last and (now - last) < max(0, int(self._cfg.cooldown_sec)):
                return False

            self._run_sent_count[run_id] = sent_count + 1
            self._fingerprint_last_sent_mono[key] = now
            return True

    def report_exception(
        self,
        *,
        exc: Exception,
        stage: str,
        attempt: int = 0,
        run_logger=None,
        trace_log_path: str = "",
        job=None,
        recipient=None,
        extra: Optional[dict] = None,
    ) -> None:
        try:
            if not self._cfg.enabled:
                return

            actual_run_logger = run_logger or self._run_logger

            ctx = collect_error_context(
                exc=exc,
                stage=stage,
                attempt=attempt,
                run_logger=actual_run_logger,
                trace_log_path=trace_log_path,
                job=job,
                recipient=recipient,
                extra=extra,
            )

            if not self._check_throttle(ctx.run_id or "no_run_id", ctx.fingerprint):
                self._safe_log_event(
                    "ERROR_REPORT_THROTTLED",
                    run_id=ctx.run_id,
                    fingerprint=ctx.fingerprint,
                    stage=ctx.stage,
                    recipient=ctx.recipient_name,
                )
                return

            self._safe_log_event(
                "ERROR_REPORT_TRIGGERED",
                run_id=ctx.run_id,
                fingerprint=ctx.fingerprint,
                stage=ctx.stage,
                recipient=ctx.recipient_name,
                exception_type=ctx.exception_type,
                exception_message=ctx.exception_message,
            )

            screenshot_path = user_data_dir() / "error_reports" / "_tmp" / f"screenshot_{ctx.run_id}_{ctx.fingerprint[:8]}.png"
            shot = capture_fullscreen_to(screenshot_path)
            if shot:
                ctx.screenshot_path = str(shot)
                self._safe_log_event(
                    "ERROR_REPORT_SCREENSHOT_SAVED",
                    run_id=ctx.run_id,
                    screenshot_path=ctx.screenshot_path,
                )

            artifacts = build_error_report_package(ctx)
            ctx.package_dir = str(artifacts.base_dir)
            ctx.extra_json_path = str(artifacts.meta_json_path) if artifacts.meta_json_path else ""
            ctx.zip_path = str(artifacts.zip_path) if artifacts.zip_path else ""

            self._safe_log_event(
                "ERROR_REPORT_PACKAGE_BUILT",
                run_id=ctx.run_id,
                package_dir=ctx.package_dir,
                zip_path=ctx.zip_path,
            )

            ok = send_error_report_email(
                cfg=self._cfg,
                ctx=ctx,
                attachment_path=ctx.zip_path,
            )
            if ok:
                self._safe_log_event(
                    "ERROR_REPORT_EMAIL_SENT",
                    run_id=ctx.run_id,
                    zip_path=ctx.zip_path,
                    to=self._cfg.mail_to,
                )
            else:
                self._safe_log_event(
                    "ERROR_REPORT_EMAIL_FAIL",
                    run_id=ctx.run_id,
                    reason="NOT_READY_OR_FALSE_RETURN",
                )

        except Exception as e:
            self._safe_log_event(
                "ERROR_REPORT_FAIL",
                error=str(e),
                error_type=e.__class__.__name__,
            )