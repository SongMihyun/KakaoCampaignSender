from __future__ import annotations

import json
import platform
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.paths import user_data_dir
from app.version import __version__
from backend.core.status_codes import get_status_info, status_from_result


@dataclass(frozen=True)
class ErrorSummary:
    text: str
    message: str
    latest_code: int
    latest_message: str


def _reports_dir() -> Path:
    return user_data_dir() / "reports"


def _latest_reports(limit: int = 5) -> list[Path]:
    root = _reports_dir()
    if not root.exists():
        return []
    return sorted(root.glob("send_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def _iter_recipients() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _latest_reports():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for list_row in data.get("lists", []) or []:
            for rec in list_row.get("recipients", []) or []:
                row = dict(rec)
                row["campaign_name"] = list_row.get("campaign_name", "")
                row["group_name"] = list_row.get("group_name", "")
                row["report"] = path.name
                rows.append(row)
    return rows


def build_error_summary(*, include_db: bool, package_name: str = "") -> ErrorSummary:
    rows = _iter_recipients()
    failures = [r for r in rows if not str(r.get("status", "")).upper().startswith("SUCCESS")]
    latest = failures[0] if failures else {}
    code_counts: Counter[int] = Counter()
    for row in failures:
        code = int(row.get("status_code") or status_from_result(row.get("status", ""), row.get("reason", "")).code)
        code_counts[code] += 1

    latest_code = int(latest.get("status_code") or (code_counts.most_common(1)[0][0] if code_counts else 1000))
    latest_info = get_status_info(latest_code)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    top_lines = [f"- {code}: {get_status_info(code).message} ({count}건)" for code, count in code_counts.most_common(10)]

    text = "\n".join(
        [
            "카센더 오류 요약",
            "",
            f"앱 버전: {__version__}",
            f"생성 시각: {now}",
            f"PC 이름: {platform.node()}",
            f"Windows 버전: {platform.platform()}",
            f"최근 실패 건수: {len(failures)}",
            "",
            "실패 TOP 10:",
            *(top_lines or ["- 최근 실패 없음"]),
            "",
            f"최근 오류 상태코드: {latest_code}",
            f"최근 오류 메시지: {latest.get('reason', '') or latest_info.message}",
            f"최근 실패 STEP: {latest.get('step', '') or latest_info.step}",
            f"최근 캠페인: {latest.get('campaign_name', '')}",
            f"최근 그룹: {latest.get('group_name', '')}",
            f"최근 대상자 수: {len(rows)}",
            f"DB 포함 여부: {'포함' if include_db else '제외'}",
        ]
    )

    message = "\n".join(
        [
            "[카센더 오류 신고]",
            "",
            f"버전: {__version__}",
            f"발생시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"최근 실패: {len(failures)}건",
            "",
            f"대표 오류: {latest_code}",
            "",
            f"설명: {latest.get('reason', '') or latest_info.message}",
            "",
            f"패키지: {package_name}",
        ]
    )
    return ErrorSummary(text=text, message=message, latest_code=latest_code, latest_message=latest_info.message)
