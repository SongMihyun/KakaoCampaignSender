# FILE: src/backend/domains/sending/worker.py
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import QThread, Signal

from backend.domains.sending.execution_context import build_send_executor
from backend.domains.sending.models import SendJob
from backend.integrations.kakaotalk.driver import KakaoSenderDriver


class MultiSendWorker(QThread):
    """
    Qt thread wrapper 전담.

    책임:
    - stop flag 관리
    - Qt signal bridge
    - executor 생성/실행
    - driver stop / recover adapter 제공
    - run_logger / trace_logger / error_reporter 묶음 실행
    """

    progress = Signal(int)
    status = Signal(str)
    list_changed = Signal(str, int, int)
    finished_ok = Signal(int, int, int)

    def __init__(
        self,
        driver: KakaoSenderDriver,
        jobs: List[SendJob],
        parent=None,
        delay_ms: int = 400,
        max_retry: int = 2,
        retry_sleep_ms: int = 250,
        *,
        run_logger=None,
        report_writer=None,
    ) -> None:
        super().__init__(parent)
        self._driver = driver
        self._jobs = list(jobs or [])
        self._delay_ms = max(0, int(delay_ms))
        self._stop = False
        self._max_retry = max(0, int(max_retry))
        self._retry_sleep_ms = max(0, int(retry_sleep_ms))
        self._run_logger = run_logger
        self._report_writer = report_writer

        self._trace_logger = None
        self._error_reporter = None

    def request_stop(self) -> None:
        self._stop = True
        self._safe_stop_driver()
        self._safe_log_force_stop()

    def run(self) -> None:
        bundle = self._build_execution_bundle()

        self._run_logger = bundle.run_logger
        self._trace_logger = bundle.trace_logger
        self._error_reporter = bundle.error_reporter

        result = bundle.executor.execute()
        self.finished_ok.emit(result.list_done, result.success, result.fail)

    def _build_execution_bundle(self):
        debug_log = self._is_trace_enabled()

        return build_send_executor(
            driver=self._driver,
            jobs=self._jobs,
            delay_ms=self._delay_ms,
            max_retry=self._max_retry,
            retry_sleep_ms=self._retry_sleep_ms,
            report_writer=self._report_writer,
            run_logger=self._run_logger,
            is_stop_requested=self._is_stop_requested,
            status_cb=self.status.emit,
            progress_cb=self.progress.emit,
            list_changed_cb=self.list_changed.emit,
            recover_driver_cb=self._recover_driver,
            stop_driver_cb=self._safe_stop_driver,
            debug_log=debug_log,
            trace_log_prefix="kakao_pc_driver",
        )

    def _is_trace_enabled(self) -> bool:
        v = str(os.getenv("KAKAO_TRACE", "")).strip().lower()
        return v in ("1", "true", "on", "yes")

    def _is_stop_requested(self) -> bool:
        return bool(self._stop)

    def _recover_driver(self) -> None:
        recover_fn = getattr(self._driver, "recover", None)
        if callable(recover_fn):
            recover_fn()
        else:
            self._driver.start()

    def _safe_stop_driver(self) -> None:
        try:
            self._driver.stop()
        except Exception:
            pass

    def _safe_log_force_stop(self) -> None:
        try:
            if self._run_logger:
                self._run_logger.log_event("FORCE_STOP_REQUESTED", via="UI_OR_HOTKEY")
        except Exception:
            pass