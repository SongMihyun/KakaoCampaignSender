

# ✅ FILE: src/app/sender/trace_logger.py
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TraceConfig:
    debug_log: bool = False
    log_prefix: str = "kakao_pc_driver"


class TraceLogger:
    def __init__(self, cfg: TraceConfig) -> None:
        self._cfg = cfg
        self._logger = logging.getLogger(str(cfg.log_prefix or "kakao_pc_driver"))

        env_trace = str(os.getenv("KAKAO_TRACE", "")).strip().lower() in ("1", "true", "on", "yes")
        want_info = bool(cfg.debug_log) or env_trace

        self._logger.setLevel(logging.INFO if want_info else logging.WARNING)

        if want_info:
            fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
            if not self._logger.handlers:
                h = logging.StreamHandler(sys.stdout)
                h.setLevel(logging.INFO)
                h.setFormatter(fmt)
                self._logger.addHandler(h)
            self._logger.propagate = False

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def trace_on(self) -> bool:
        if self._cfg.debug_log:
            return True
        return str(os.getenv("KAKAO_TRACE", "")).strip().lower() in ("1", "true", "on", "yes")

    def log(self, msg: str) -> None:
        try:
            self._logger.info(msg)
        except Exception:
            print(msg)

    def trace(self, label: str, **kv: Any) -> None:
        if not self.trace_on():
            return
        try:
            ts = time.perf_counter()
            extra = " ".join([f"{k}={repr(v)}" for k, v in kv.items()])
            self._logger.info(f"[TRACE {ts:.6f}] {label} {extra}".rstrip())
            if not self._logger.handlers:
                print(f"[TRACE {ts:.6f}] {label} {extra}".rstrip())
        except Exception:
            pass