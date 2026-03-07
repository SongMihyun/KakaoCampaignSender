from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import QThread, Signal

from backend.domains.sending.models import SendJob
from backend.domains.sending.executor import SendExecutor
from backend.integrations.kakaotalk.driver import KakaoSenderDriver


class MultiSendWorker(QThread):
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
        self._jobs = jobs
        self._delay_ms = max(0, int(delay_ms))
        self._stop = False
        self._max_retry = max(0, int(max_retry))
        self._retry_sleep_ms = max(0, int(retry_sleep_ms))
        self._run_logger = run_logger
        self._report_writer = report_writer

    def request_stop(self) -> None:
        self._stop = True
        try:
            self._driver.stop()
        except Exception:
            pass

        try:
            if self._run_logger:
                self._run_logger.log_event("FORCE_STOP_REQUESTED", via="UI_OR_HOTKEY")
        except Exception:
            pass

    def _recover_driver(self) -> None:
        fn = getattr(self._driver, "recover", None)
        if callable(fn):
            fn()
        else:
            self._driver.start()

    def run(self) -> None:
        executor = SendExecutor(
            driver=self._driver,
            jobs=self._jobs,
            delay_ms=self._delay_ms,
            max_retry=self._max_retry,
            retry_sleep_ms=self._retry_sleep_ms,
            run_logger=self._run_logger,
            report_writer=self._report_writer,
            is_stop_requested=lambda: self._stop,
            status_cb=lambda msg: self.status.emit(msg),
            progress_cb=lambda v: self.progress.emit(v),
            list_changed_cb=lambda title, i, t: self.list_changed.emit(title, i, t),
            recover_driver_cb=self._recover_driver,
            stop_driver_cb=lambda: self._driver.stop(),
        )

        result = executor.execute()
        self.finished_ok.emit(result.list_done, result.success, result.fail)