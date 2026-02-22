from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.paths import user_data_dir


def _now_local_iso() -> str:
    # 로컬 기준 ISO 문자열
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_str(v: Any, limit: int = 2000) -> str:
    s = "" if v is None else str(v)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if len(s) > limit:
        return s[:limit] + "…"
    return s


@dataclass(frozen=True)
class SendRunLogger:
    """
    실행(run) 단위 로그 저장기
    - jsonl: 한 줄 = 한 이벤트(JSON)
    """
    run_id: str
    jsonl_path: Path

    _lock: threading.Lock = threading.Lock()

    @staticmethod
    def new_run(prefix: str = "send_run") -> "SendRunLogger":
        base = user_data_dir() / "logs"
        base.mkdir(parents=True, exist_ok=True)

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = base / f"{prefix}_{run_id}.jsonl"
        return SendRunLogger(run_id=run_id, jsonl_path=path)

    def log_event(self, event: str, **fields: Any) -> None:
        payload = {
            "ts": _now_local_iso(),
            "run_id": self.run_id,
            "event": event,
        }

        # 값 정리(에러 메시지 길이 제한 포함)
        for k, v in (fields or {}).items():
            if isinstance(v, Exception):
                payload[k] = _safe_str(repr(v))
            elif isinstance(v, (dict, list, tuple, int, float, bool)) or v is None:
                payload[k] = v
            else:
                payload[k] = _safe_str(v)

        line = json.dumps(payload, ensure_ascii=False)

        # Thread-safe append
        with self._lock:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def path_str(self) -> str:
        return str(self.jsonl_path)
