# FILE: src/backend/domains/sending/worker.py
from __future__ import annotations

import os
import threading
from typing import List

from PySide6.QtCore import QThread, Signal

from backend.domains.sending.execution_context import build_send_executor
from backend.domains.sending.models import SendJob
from backend.integrations.kakaotalk.driver import KakaoSenderDriver


class MultiSendWorker(QThread):
    """
    Qt thread wrapper 전담.

    책임:
    - stop / pause state 관리
    - Qt signal bridge
    - executor 생성/실행
    - driver stop / recover adapter 제공
    - run_logger / trace_logger / error_reporter 묶음 실행
    """

    progress = Signal(int)
    status = Signal(str)
    list_changed = Signal(str, int, int)
    pause_changed = Signal(bool)
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
        self._max_retry = max(0, int(max_retry))
        self._retry_sleep_ms = max(0, int(retry_sleep_ms))
        self._run_logger = run_logger
        self._report_writer = report_writer

        self._trace_logger = None
        self._error_reporter = None

        self._stop = False
        self._state_lock = threading.Lock()

        self._pause_requested = False
        self._paused = False

        self._resume_event = threading.Event()
        self._resume_event.set()

        self._bind_pause_controller_to_driver()

    def _bind_pause_controller_to_driver(self) -> None:
        try:
            bind_fn = getattr(self._driver, "set_pause_controller", None)
            if callable(bind_fn):
                bind_fn(
                    is_pause_requested=self._is_pause_requested,
                    wait_if_paused=self._wait_if_paused,
                )
        except Exception:
            pass

    def request_stop(self) -> None:
        self._stop = True
        self._resume_event.set()
        self._safe_stop_driver()
        self._safe_log_event("FORCE_STOP_REQUESTED", via="UI_OR_HOTKEY")

    def request_pause(self) -> None:
        with self._state_lock:
            if self._stop or self._paused or self._pause_requested:
                return
            self._pause_requested = True

        self.status.emit("일시정지 요청됨(F9) | 현재 열린 대화 발송을 마친 뒤, 개인창이 닫히는 시점에 안전하게 멈춥니다.")
        self._safe_log_event("PAUSE_REQUESTED", via="UI_OR_HOTKEY")

    def request_resume(self) -> None:
        emit_changed = False
        with self._state_lock:
            if self._pause_requested:
                self._pause_requested = False
                self.status.emit("일시정지 요청 취소됨 | 현재 발송 흐름을 계속 진행합니다.")
                self._safe_log_event("PAUSE_REQUEST_CANCELLED", via="UI_OR_HOTKEY")
                return

            if not self._paused:
                return

            self._paused = False
            self._resume_event.set()
            emit_changed = True

        if emit_changed:
            self.pause_changed.emit(False)
        self.status.emit("발송 재개 요청됨(F9) | 다음 대상자를 카카오톡 메인창 검색부터 다시 시작합니다.")
        self._safe_log_event("RESUME_REQUESTED", via="UI_OR_HOTKEY")

    def toggle_pause(self) -> None:
        if self.is_paused() or self.is_pause_pending():
            self.request_resume()
        else:
            self.request_pause()

    def is_paused(self) -> bool:
        with self._state_lock:
            return bool(self._paused)

    def is_pause_pending(self) -> bool:
        with self._state_lock:
            return bool(self._pause_requested)

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
            is_pause_requested=self._is_pause_requested,
            wait_if_paused=self._wait_if_paused,
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

    def _is_pause_requested(self) -> bool:
        with self._state_lock:
            return bool(self._pause_requested or self._paused)

    def _wait_if_paused(self) -> bool:
        with self._state_lock:
            pause_requested = bool(self._pause_requested)
            already_paused = bool(self._paused)

        if not pause_requested and not already_paused:
            return False

        if pause_requested and not already_paused:
            with self._state_lock:
                self._pause_requested = False
                self._paused = True
                self._resume_event.clear()

            self.pause_changed.emit(True)
            self.status.emit("일시정지됨(F9) | 현재 열린 대화 발송 완료 후 안전 정지되었습니다. 이제 카카오톡 PC를 사용해도 됩니다.")
            self._safe_log_event("PAUSED", mode="SAFE_AFTER_CHAT_CLOSE")

        while True:
            if self._stop:
                return True
            if self._resume_event.wait(0.05):
                break


        self._safe_log_event("RESUME_UNBLOCKED")
        return False

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

    def _safe_log_event(self, event_name: str, **kwargs) -> None:
        try:
            if self._run_logger:
                self._run_logger.log_event(event_name, **kwargs)
        except Exception:
            pass