from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.paths import user_data_dir


@dataclass
class TraceConfig:
    debug_log: bool = False
    log_prefix: str = "kakao_pc_driver"
    run_id: str = ""
    file_enabled: bool = False
    log_dir: Optional[Path] = None


class TraceLogger:
    def __init__(self, cfg: TraceConfig) -> None:
        self._cfg = cfg
        self._logger = logging.getLogger(str(cfg.log_prefix or "kakao_pc_driver"))
        self._file_path: Optional[Path] = None

        env_trace = str(os.getenv("KAKAO_TRACE", "")).strip().lower() in ("1", "true", "on", "yes")
        want_info = bool(cfg.debug_log) or env_trace

        self._logger.setLevel(logging.INFO if want_info else logging.WARNING)
        self._logger.propagate = False

        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

        if want_info:
            self._ensure_stream_handler(fmt)

        if cfg.file_enabled and cfg.run_id:
            self._file_path = self._build_file_path(cfg)
            self._ensure_file_handler(fmt, self._file_path)

    @staticmethod
    def _handler_name(kind: str, key: str) -> str:
        return f"kcs_trace::{kind}::{key}"

    def _ensure_stream_handler(self, fmt: logging.Formatter) -> None:
        key = str(self._cfg.log_prefix or "kakao_pc_driver")
        wanted_name = self._handler_name("stream", key)

        for h in self._logger.handlers:
            if getattr(h, "name", "") == wanted_name:
                return

        h = logging.StreamHandler(sys.stdout)
        h.setLevel(logging.INFO)
        h.setFormatter(fmt)
        h.name = wanted_name
        self._logger.addHandler(h)

    def _ensure_file_handler(self, fmt: logging.Formatter, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        wanted_name = self._handler_name("file", str(path))

        for h in self._logger.handlers:
            if getattr(h, "name", "") == wanted_name:
                return

        fh = logging.FileHandler(str(path), encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        fh.name = wanted_name
        self._logger.addHandler(fh)

    @staticmethod
    def _build_file_path(cfg: TraceConfig) -> Path:
        base = cfg.log_dir or (user_data_dir() / "logs")
        base.mkdir(parents=True, exist_ok=True)
        run_id = str(cfg.run_id or "").strip()
        prefix = str(cfg.log_prefix or "kakao_pc_driver").strip() or "kakao_pc_driver"
        safe_prefix = prefix.replace(" ", "_")
        return base / f"{safe_prefix}_{run_id}.log"

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def file_path(self) -> Optional[Path]:
        return self._file_path

    def file_path_str(self) -> str:
        return str(self._file_path) if self._file_path else ""

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