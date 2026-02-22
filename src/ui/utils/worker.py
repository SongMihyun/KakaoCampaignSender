# src/ui/utils/worker.py
from __future__ import annotations

import traceback
from typing import Any, Callable, Optional, Set

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


# ----------------------------
# ✅ GC 방지용 keep-alive pool
# ----------------------------
_KEEP_ALIVE: Set[int] = set()
_KEEP_REF: dict[int, "_Worker"] = {}


def _keep(worker: "_Worker") -> None:
    wid = id(worker)
    _KEEP_ALIVE.add(wid)
    _KEEP_REF[wid] = worker


def _release(worker: "_Worker") -> None:
    wid = id(worker)
    _KEEP_ALIVE.discard(wid)
    _KEEP_REF.pop(wid, None)


class _WorkerSignals(QObject):
    done = Signal(object)     # result
    error = Signal(str)       # traceback string
    finished = Signal()       # always emitted


class _Worker(QRunnable):
    def __init__(
        self,
        fn: Callable[[], Any],
        *,
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _WorkerSignals()

        # ✅ 완료/에러와 상관없이 끝나면 keep 해제
        self.signals.finished.connect(lambda: _release(self))

        # ✅ Qt Signal 연결 -> 수신자(QObject)가 UI thread면 QueuedConnection으로 UI에서 실행됨
        if on_done:
            self.signals.done.connect(on_done)   # type: ignore[arg-type]
        if on_error:
            self.signals.error.connect(on_error) # type: ignore[arg-type]

    @Slot()
    def run(self) -> None:
        try:
            res = self.fn()
        except Exception:
            tb = traceback.format_exc()
            self.signals.error.emit(tb)
            self.signals.finished.emit()
            return

        self.signals.done.emit(res)
        self.signals.finished.emit()


def run_bg(
    fn: Callable[[], Any],
    *,
    on_done: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """
    ✅ 백그라운드 실행 + UI 안전 콜백
    - fn: ThreadPool에서 실행
    - on_done/on_error: Qt Signal로 UI thread에서 실행(정상적인 경우)
    - ✅ Worker를 keep-alive 해서 팝업/저장 콜백 누락 방지
    """
    worker = _Worker(fn, on_done=on_done, on_error=on_error)
    _keep(worker)
    QThreadPool.globalInstance().start(worker)
