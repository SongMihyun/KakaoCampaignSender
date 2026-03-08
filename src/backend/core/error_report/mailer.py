from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

from .models import EmailReportConfig, ErrorReportContext


def build_subject(cfg: EmailReportConfig, ctx: ErrorReportContext) -> str:
    who = ctx.recipient_name or "-"
    stage = ctx.stage or "-"
    when = ctx.occurred_at or "-"
    return f"{cfg.subject_prefix} {who} | {stage} | {when}"


def build_body(ctx: ErrorReportContext) -> str:
    lines = [
        f"run_id: {ctx.run_id}",
        f"occurred_at: {ctx.occurred_at}",
        f"stage: {ctx.stage}",
        f"attempt: {ctx.attempt}",
        f"send_list_id: {ctx.send_list_id}",
        f"send_list_title: {ctx.send_list_title}",
        f"campaign_id: {ctx.campaign_id}",
        f"campaign_name: {ctx.campaign_name}",
        f"send_mode: {ctx.send_mode}",
        f"recipient_name: {ctx.recipient_name}",
        f"recipient_emp_id: {ctx.recipient_emp_id}",
        f"recipient_phone: {ctx.recipient_phone}",
        f"exception_type: {ctx.exception_type}",
        f"exception_message: {ctx.exception_message}",
        f"fingerprint: {ctx.fingerprint}",
        "",
        "첨부파일:",
        "- error_meta.json",
        "- screenshot_full.png (있는 경우)",
        "- send_run.jsonl (있는 경우)",
        "- kakao_trace.log (있는 경우)",
    ]
    return "\n".join(lines)


def send_error_report_email(
    *,
    cfg: EmailReportConfig,
    ctx: ErrorReportContext,
    attachment_path: str = "",
) -> bool:
    if not cfg.ready:
        return False

    msg = EmailMessage()
    msg["Subject"] = build_subject(cfg, ctx)
    msg["From"] = cfg.mail_from
    msg["To"] = cfg.mail_to
    msg.set_content(build_body(ctx))

    if attachment_path:
        p = Path(attachment_path)
        if p.exists() and p.is_file():
            ctype, _ = mimetypes.guess_type(str(p))
            if not ctype:
                ctype = "application/zip"
            maintype, subtype = ctype.split("/", 1)
            with p.open("rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=p.name,
                )

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(cfg.smtp_user, cfg.smtp_pass)
        smtp.send_message(msg)

    return True