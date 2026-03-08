from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.paths import user_data_dir

from .models import ErrorReportArtifacts, ErrorReportContext


def _safe_copy(src: str, dst: Path) -> Optional[Path]:
    try:
        if not src:
            return None
        src_path = Path(src)
        if not src_path.exists() or not src_path.is_file():
            return None
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst)
        return dst
    except Exception:
        return None


def build_error_report_package(ctx: ErrorReportContext) -> ErrorReportArtifacts:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = ctx.run_id or "no_run_id"

    base_dir = user_data_dir() / "error_reports" / f"{ts}_{run_id}_{ctx.fingerprint[:8]}"
    base_dir.mkdir(parents=True, exist_ok=True)

    screenshot_dst = None
    if ctx.screenshot_path:
        screenshot_dst = _safe_copy(ctx.screenshot_path, base_dir / "screenshot_full.png")

    run_log_dst = _safe_copy(ctx.run_log_path, base_dir / "send_run.jsonl")
    trace_log_dst = _safe_copy(ctx.trace_log_path, base_dir / "kakao_trace.log")

    meta_json_path = base_dir / "error_meta.json"
    payload = asdict(ctx)

    payload["copied_run_log_path"] = str(run_log_dst) if run_log_dst else ""
    payload["copied_trace_log_path"] = str(trace_log_dst) if trace_log_dst else ""
    payload["copied_screenshot_path"] = str(screenshot_dst) if screenshot_dst else ""

    with meta_json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    zip_path = base_dir.with_suffix(".zip")
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in base_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=p.relative_to(base_dir))
    except Exception:
        zip_path = None

    return ErrorReportArtifacts(
        base_dir=base_dir,
        screenshot_path=screenshot_dst,
        meta_json_path=meta_json_path,
        zip_path=zip_path,
    )