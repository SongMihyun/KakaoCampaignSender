# src/ui/pages/send_page.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, List, Any

from PySide6.QtCore import Qt, QThread, Signal, QAbstractNativeEventFilter
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QFrame, QListWidget, QListWidgetItem, QTableView, QAbstractItemView,
    QProgressBar, QComboBox, QToolButton, QApplication
)

from app.data.contacts_repo import ContactsRepo
from app.data.groups_repo import GroupsRepo
from app.data.campaigns_repo import CampaignsRepo
from app.data.send_lists_repo import SendListsRepo

from ui.pages.campaign_preview_dialog import CampaignPreviewDialog

from app.sender.kakao_pc_driver import KakaoSenderDriver, KakaoPcDriver
from app.system.send_run_logger import SendRunLogger

from app.paths import user_data_dir
from app.system.send_report import SendReportWriter

# ✅ "검색 결과 0건"을 NOT_FOUND로 기록하기 위해 사용
from app.sender.kakao_pc_hooks import ChatNotFound


# ----------------------------
# Global Hotkey (Windows) - F11 강제중지
# ----------------------------
class GlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey: Callable[[int], None]) -> None:
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, eventType, message):  # type: ignore[override]
        try:
            if eventType != "windows_generic_MSG":
                return False, 0

            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            WM_HOTKEY = 0x0312
            if msg.message == WM_HOTKEY:
                hotkey_id = int(msg.wParam)
                try:
                    self._on_hotkey(hotkey_id)
                except Exception:
                    pass
                return True, 0
        except Exception:
            pass

        return False, 0


class GlobalHotkeyManager:
    def __init__(self, app: QApplication, on_hotkey: Callable[[int], None]) -> None:
        self._app = app
        self._filter = GlobalHotkeyFilter(on_hotkey)
        self._registered_ids: set[int] = set()
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._app.installNativeEventFilter(self._filter)
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        try:
            self._app.removeNativeEventFilter(self._filter)
        except Exception:
            pass
        self._installed = False

    def register_f11(self, hotkey_id: int = 1001) -> bool:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            MOD_NOREPEAT = 0x4000
            VK_F11 = 0x7A
            self.install()
            ok = bool(user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, VK_F11))
            if ok:
                self._registered_ids.add(hotkey_id)
            return ok
        except Exception:
            return False

    def unregister_all(self) -> None:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            for hid in list(self._registered_ids):
                try:
                    user32.UnregisterHotKey(None, hid)
                except Exception:
                    pass
            self._registered_ids.clear()
        finally:
            self.uninstall()


# ----------------------------
# Worker Data Models
# ----------------------------
@dataclass
class Recipient:
    emp_id: str
    name: str
    phone: str
    agency: str
    branch: str


@dataclass
class SendJob:
    send_list_id: int
    title: str
    group_name: str
    campaign_id: int
    campaign_name: str
    recipients: List[Recipient]
    campaign_items: List[Any]


# ----------------------------
# Worker Thread
# ----------------------------
class MultiSendWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    list_changed = Signal(str, int, int)
    finished_ok = Signal(int, int, int)  # (list_done, success, fail)

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
        report_writer: Optional[SendReportWriter] = None,
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

    def _emit_stopped(self, reason: str = "F11") -> None:
        self.status.emit("발송 강제 중지됨(F11)")
        try:
            if self._run_logger:
                self._run_logger.log_event("FORCE_STOPPED", reason=reason)
        except Exception:
            pass

    def _recover_driver(self) -> None:
        fn = getattr(self._driver, "recover", None)
        if callable(fn):
            fn()
        else:
            self._driver.start()

    def run(self) -> None:
        StopNow = None
        TransferAbortedByClose = None
        try:
            from app.sender.kakao_pc_driver import StopNow as _StopNow, TransferAbortedByClose as _TransferAbortedByClose  # type: ignore
            StopNow = _StopNow
            TransferAbortedByClose = _TransferAbortedByClose
        except Exception:
            StopNow = None
            TransferAbortedByClose = None

        list_done = 0
        success = 0
        fail = 0

        if not self._jobs:
            self.status.emit("발송할 발송리스트가 없습니다.")
            self.progress.emit(0)
            self.finished_ok.emit(0, 0, 0)
            try:
                if self._run_logger:
                    self._run_logger.log_event("RUN_EMPTY")
            except Exception:
                pass
            try:
                if self._report_writer:
                    self._report_writer.finish(list_done=0, success=0, fail=0, stopped=False)
                    self._report_writer.save()
            except Exception:
                pass
            return

        total_lists = len(self._jobs)

        try:
            if self._run_logger:
                self._run_logger.log_event(
                    "RUN_START",
                    total_lists=total_lists,
                    max_retry=self._max_retry,
                    delay_ms=self._delay_ms,
                    retry_sleep_ms=self._retry_sleep_ms,
                )
        except Exception:
            pass

        try:
            self.status.emit("발송 준비 중...")
            self._driver.start()

            # ✅ 캠페인 이미지 사전 전처리(런 시작 1회)
            self.status.emit("캠페인 이미지 전처리 중...")
            for job in self._jobs:
                for item in job.campaign_items:
                    typ = str(getattr(item, "item_type", "")).upper().strip()
                    if typ == "IMG":
                        png = getattr(item, "image_bytes", b"") or b""
                        if png and hasattr(self._driver, "_png_to_dib_bytes"):
                            self._driver._png_to_dib_bytes(png)
            try:
                if self._run_logger:
                    self._run_logger.log_event("DRIVER_START_OK")
            except Exception:
                pass
        except Exception as e:
            self.status.emit(f"발송 준비 실패: {e}")
            try:
                if self._run_logger:
                    self._run_logger.log_event("DRIVER_START_FAIL", error=str(e))
            except Exception:
                pass
            self.finished_ok.emit(0, 0, 0)
            try:
                if self._report_writer:
                    self._report_writer.finish(list_done=0, success=0, fail=0, stopped=False)
                    self._report_writer.save()
            except Exception:
                pass
            return

        def _rk(x: Recipient) -> str:
            return f"{x.emp_id}|{x.name}|{x.phone}"

        try:
            for li, job in enumerate(self._jobs, start=1):
                if self._stop:
                    self._emit_stopped("STOP_FLAG_BEFORE_LIST")
                    break

                try:
                    if self._run_logger:
                        self._run_logger.log_event(
                            "LIST_START",
                            list_index=li,
                            total_lists=total_lists,
                            title=job.title,
                            recipients=len(job.recipients),
                        )
                except Exception:
                    pass

                # ✅ report: list meta + campaign content snapshot
                try:
                    if self._report_writer:
                        self._report_writer.add_list(
                            list_index=li,
                            send_list_id=int(job.send_list_id),
                            title=str(job.title or ""),
                            group_name=str(job.group_name or ""),
                            campaign_id=int(job.campaign_id),
                            campaign_name=str(job.campaign_name or ""),
                            recipients_total=len(job.recipients),
                            campaign_items=job.campaign_items,
                        )
                except Exception:
                    pass

                self.list_changed.emit(job.title, li, total_lists)
                self.progress.emit(0)

                # 리스트 단위 복구
                try:
                    self._recover_driver()
                    try:
                        if self._run_logger:
                            self._run_logger.log_event(
                                "DRIVER_RESTART_OK",
                                list_index=li,
                                title=job.title,
                            )
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        if self._run_logger:
                            self._run_logger.log_event(
                                "DRIVER_RESTART_FAIL",
                                list_index=li,
                                title=job.title,
                                error=str(e),
                            )
                    except Exception:
                        pass

                total = len(job.recipients)
                if total == 0:
                    self.status.emit(f"스킵(대상 0명) | {job.title}")
                    list_done += 1
                    try:
                        if self._run_logger:
                            self._run_logger.log_event(
                                "LIST_SKIP_EMPTY",
                                list_index=li,
                                title=job.title,
                            )
                    except Exception:
                        pass
                    continue

                # ✅ 리스트 말미 재시도 큐(확정 실패 아님)
                tail_retry: List[Recipient] = []
                tail_retry_keys: set[str] = set()

                for ri, r in enumerate(job.recipients, start=1):
                    if self._stop:
                        self._emit_stopped("STOP_FLAG_IN_LIST")
                        break

                    self.status.emit(f"[{li}/{total_lists}] {job.title} | {ri}/{total} | {r.name}")

                    try:
                        if self._run_logger:
                            self._run_logger.log_event(
                                "RECIPIENT_START",
                                list_index=li,
                                total_lists=total_lists,
                                title=job.title,
                                recipient_index=ri,
                                total_recipients=total,
                                name=r.name,
                                emp_id=r.emp_id,
                                phone=r.phone,
                                agency=r.agency,
                                branch=r.branch,
                            )
                    except Exception:
                        pass

                    ok = False
                    last_err: Optional[Exception] = None
                    used_attempt = 0

                    for attempt in range(0, self._max_retry + 1):
                        if self._stop:
                            break

                        used_attempt = attempt + 1

                        try:
                            if self._run_logger:
                                self._run_logger.log_event(
                                    "SEND_ATTEMPT",
                                    list_index=li,
                                    title=job.title,
                                    recipient_index=ri,
                                    name=r.name,
                                    attempt=used_attempt,
                                    attempt_max=self._max_retry + 1,
                                )
                        except Exception:
                            pass

                        try:
                            raw_name = r.name
                            name = (raw_name or "").strip().replace("\u200b", "").replace("\ufeff", "")
                            if not name:
                                self.status.emit(f"스킵(이름 비어있음) | {job.title} | emp_id={r.emp_id}")
                                ok = True

                                # ✅ report: SKIP
                                try:
                                    if self._report_writer:
                                        self._report_writer.add_recipient_result(
                                            list_index=li,
                                            emp_id=r.emp_id, name=r.name, phone=r.phone,
                                            agency=r.agency, branch=r.branch,
                                            status="SKIP",
                                            reason="EMPTY_NAME",
                                            attempt=used_attempt,
                                        )
                                except Exception:
                                    pass
                                break

                            # ✅ 발송
                            self._driver.send_campaign_items(name, job.campaign_items)

                            ok = True

                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "RECIPIENT_SUCCESS",
                                        list_index=li,
                                        title=job.title,
                                        recipient_index=ri,
                                        name=r.name,
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass

                            # ✅ report: SUCCESS
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=r.emp_id, name=r.name, phone=r.phone,
                                        agency=r.agency, branch=r.branch,
                                        status="SUCCESS",
                                        reason="",
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass

                            break

                        # =====================================================
                        # ✅ 핵심: 검색 결과 0건 → NOT_FOUND로 확정
                        #    (ChatNotFound는 hooks/driver에서 raise되어야 함)
                        # =====================================================
                        except ChatNotFound as e_nf:
                            ok = False
                            last_err = e_nf

                            self.status.emit(f"대화방 없음(NOT_FOUND) | {job.title} | {r.name}")

                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "RECIPIENT_NOT_FOUND",
                                        list_index=li,
                                        title=job.title,
                                        recipient_index=ri,
                                        name=r.name,
                                        reason=str(e_nf),
                                    )
                            except Exception:
                                pass

                            # ✅ report: NOT_FOUND
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=r.emp_id, name=r.name, phone=r.phone,
                                        agency=r.agency, branch=r.branch,
                                        status="NOT_FOUND",
                                        reason=str(e_nf) or "CHAT_NOT_FOUND",
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass

                            # NOT_FOUND는 재시도 의미 없음 -> 즉시 attempt 루프 종료
                            break

                        except Exception as e:
                            if StopNow is not None and isinstance(e, StopNow):
                                self._stop = True
                                self._emit_stopped("StopNow")
                                break

                            if TransferAbortedByClose is not None and isinstance(e, TransferAbortedByClose):
                                k = _rk(r)
                                if k not in tail_retry_keys:
                                    tail_retry_keys.add(k)
                                    tail_retry.append(r)

                                self.status.emit(f"전송 취소 감지 → 리스트 마지막에 1회 재전송 예약 | {job.title} | {r.name}")
                                try:
                                    if self._run_logger:
                                        self._run_logger.log_event(
                                            "RECIPIENT_TAIL_RETRY_SCHEDULED",
                                            list_index=li,
                                            title=job.title,
                                            recipient_index=ri,
                                            name=r.name,
                                            reason=str(e),
                                        )
                                except Exception:
                                    pass

                                # ✅ report: TAIL_RETRY_SCHEDULED
                                try:
                                    if self._report_writer:
                                        self._report_writer.add_recipient_result(
                                            list_index=li,
                                            emp_id=r.emp_id, name=r.name, phone=r.phone,
                                            agency=r.agency, branch=r.branch,
                                            status="TAIL_RETRY_SCHEDULED",
                                            reason=str(e),
                                            attempt=used_attempt,
                                        )
                                except Exception:
                                    pass

                                ok = True
                                last_err = e
                                break

                            last_err = e

                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "SEND_ATTEMPT_FAIL",
                                        list_index=li,
                                        title=job.title,
                                        recipient_index=ri,
                                        name=r.name,
                                        attempt=used_attempt,
                                        attempt_max=self._max_retry + 1,
                                        error=str(e),
                                    )
                            except Exception:
                                pass

                            self.status.emit(
                                f"재시도({used_attempt}/{self._max_retry+1}) 실패 | {job.title} | {r.name} | {e}"
                            )

                            if self._retry_sleep_ms > 0:
                                self.msleep(self._retry_sleep_ms)

                            try:
                                self._recover_driver()
                            except Exception:
                                pass

                    if self._stop:
                        break

                    # ✅ fail 확정은 "일반 실패"만.
                    #    TransferAbortedByClose는 tail_retry로 넘어가므로 fail 확정하지 않음.
                    if ok:
                        if not (TransferAbortedByClose is not None and isinstance(last_err, TransferAbortedByClose)):
                            if last_err is None:
                                success += 1
                            else:
                                success += 1
                    else:
                        fail += 1

                        # ✅ NOT_FOUND는 이미 위에서 report 기록 완료
                        if isinstance(last_err, ChatNotFound):
                            # 메시지도 위에서 출력됨
                            pass
                        else:
                            self.status.emit(
                                f"최종 실패 | [{li}/{total_lists}] {job.title} | {ri}/{total} | {r.name} | {last_err}"
                            )
                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "RECIPIENT_FINAL_FAIL",
                                        list_index=li,
                                        total_lists=total_lists,
                                        title=job.title,
                                        recipient_index=ri,
                                        total_recipients=total,
                                        name=r.name,
                                        error=str(last_err),
                                    )
                            except Exception:
                                pass

                            # ✅ report: FAIL
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=r.emp_id, name=r.name, phone=r.phone,
                                        agency=r.agency, branch=r.branch,
                                        status="FAIL",
                                        reason=str(last_err),
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass

                    self.progress.emit(int(ri * 100 / total))

                    if self._delay_ms > 0:
                        remain = int(self._delay_ms)
                        step = 50
                        while remain > 0:
                            if self._stop:
                                break
                            self.msleep(min(step, remain))
                            remain -= step

                if self._stop:
                    break

                # ---------------------------------------------------------
                # ✅ 리스트 말미 재전송(1회만)
                # ---------------------------------------------------------
                if tail_retry and (not self._stop):
                    self.status.emit(f"[{li}/{total_lists}] {job.title} | 말미 재전송 {len(tail_retry)}건 시작")
                    try:
                        if self._run_logger:
                            self._run_logger.log_event(
                                "TAIL_RETRY_START",
                                list_index=li,
                                title=job.title,
                                count=len(tail_retry),
                            )
                    except Exception:
                        pass

                    for rr in tail_retry:
                        if self._stop:
                            break

                        self.status.emit(f"[{li}/{total_lists}] {job.title} | 말미 재전송 | {rr.name}")

                        final_ok = False
                        last_err2: Optional[Exception] = None
                        used_attempt2 = 0

                        for attempt2 in range(0, self._max_retry + 1):
                            if self._stop:
                                break
                            used_attempt2 = attempt2 + 1
                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "TAIL_RETRY_ATTEMPT",
                                        list_index=li,
                                        title=job.title,
                                        name=rr.name,
                                        attempt=used_attempt2,
                                        attempt_max=self._max_retry + 1,
                                    )
                                self._driver.send_campaign_items(rr.name, job.campaign_items)
                                final_ok = True
                                break
                            except Exception as e2:
                                if StopNow is not None and isinstance(e2, StopNow):
                                    self._stop = True
                                    self._emit_stopped("StopNow")
                                    break
                                last_err2 = e2

                                if self._retry_sleep_ms > 0:
                                    self.msleep(self._retry_sleep_ms)

                                try:
                                    self._recover_driver()
                                except Exception:
                                    pass

                        if final_ok:
                            success += 1
                            self.status.emit(f"말미 재전송 성공 | {job.title} | {rr.name}")
                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "TAIL_RETRY_SUCCESS",
                                        list_index=li,
                                        title=job.title,
                                        name=rr.name,
                                    )
                            except Exception:
                                pass

                            # ✅ report: SUCCESS(TAIL_RETRY)
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=rr.emp_id, name=rr.name, phone=rr.phone,
                                        agency=rr.agency, branch=rr.branch,
                                        status="SUCCESS(TAIL_RETRY)",
                                        reason="",
                                        attempt=used_attempt2,
                                    )
                            except Exception:
                                pass
                        else:
                            fail += 1
                            self.status.emit(f"말미 재전송 최종 실패 | {job.title} | {rr.name} | {last_err2}")
                            try:
                                if self._run_logger:
                                    self._run_logger.log_event(
                                        "TAIL_RETRY_FINAL_FAIL",
                                        list_index=li,
                                        title=job.title,
                                        name=rr.name,
                                        error=str(last_err2),
                                    )
                            except Exception:
                                pass

                            # ✅ report: FAIL(TAIL_RETRY)
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=rr.emp_id, name=rr.name, phone=rr.phone,
                                        agency=rr.agency, branch=rr.branch,
                                        status="FAIL(TAIL_RETRY)",
                                        reason=str(last_err2),
                                        attempt=used_attempt2,
                                    )
                            except Exception:
                                pass

                list_done += 1
                try:
                    if self._run_logger:
                        self._run_logger.log_event(
                            "LIST_DONE",
                            list_index=li,
                            title=job.title,
                        )
                except Exception:
                    pass

        finally:
            try:
                if self._run_logger:
                    self._run_logger.log_event(
                        "RUN_END",
                        list_done=list_done,
                        success=success,
                        fail=fail,
                        stopped=bool(self._stop),
                    )
            except Exception:
                pass

            try:
                if self._report_writer:
                    self._report_writer.finish(
                        list_done=list_done,
                        success=success,
                        fail=fail,
                        stopped=bool(self._stop),
                    )
                    self._report_writer.save()
            except Exception:
                pass

            self.finished_ok.emit(list_done, success, fail)


# ----------------------------
# UI Page
# ----------------------------
class SendPage(QWidget):
    HOTKEY_ID_FORCE_STOP = 1001  # F11

    def __init__(
        self,
        contacts_repo: ContactsRepo,
        groups_repo: GroupsRepo,
        campaigns_repo: CampaignsRepo,
        send_lists_repo: SendListsRepo,
        send_logs_repo=None,  # ✅ MainWindow에서 주입하므로 인자 수용
        on_progress: Optional[Callable[[int], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.setObjectName("Page")

        self.contacts_repo = contacts_repo
        self.groups_repo = groups_repo
        self.campaigns_repo = campaigns_repo
        self.send_lists_repo = send_lists_repo
        self.send_logs_repo = send_logs_repo  # (현 시점 로직에서는 직접 사용하지 않음)
        self._on_progress = on_progress or (lambda _: None)
        self._on_status = on_status or (lambda _: None)

        self.sender_driver: Optional[KakaoSenderDriver] = None
        self._worker: Optional[MultiSendWorker] = None
        self._run_logger: Optional[SendRunLogger] = None

        self._current_sending_title: str = ""

        self._hotkey_mgr: Optional[GlobalHotkeyManager] = None
        self._init_global_hotkey()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # ---- header (좌: 타이틀/설명/경고, 우: 속도 드롭다운) ----
        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        root.addLayout(header_row)

        header_left = QVBoxLayout()
        header_left.setSpacing(6)

        title = QLabel("발송")
        title.setObjectName("PageTitle")
        desc = QLabel("발송리스트(그룹+캠페인)를 생성/관리하고, 리스트를 순차 발송합니다.")
        desc.setObjectName("PageDesc")

        header_left.addWidget(title)
        header_left.addWidget(desc)

        self.lbl_priv = QLabel("")
        self.lbl_priv.setStyleSheet("color:#b45309; font-weight:600;")
        header_left.addWidget(self.lbl_priv)
        self._refresh_priv_label()

        header_row.addLayout(header_left, 1)

        # 우측: 속도 선택
        header_right = QHBoxLayout()
        header_right.setSpacing(8)
        header_right.setAlignment(Qt.AlignTop | Qt.AlignRight)

        lbl_speed = QLabel("속도")
        lbl_speed.setStyleSheet("color:#6b7280; font-weight:600;")

        self.cbo_speed = QComboBox()
        self.cbo_speed.setMinimumWidth(140)
        self.cbo_speed.addItem("SLOW(안정)", "slow")
        self.cbo_speed.addItem("NORMAL(기본)", "normal")
        self.cbo_speed.addItem("FAST(빠름)", "fast")
        self.cbo_speed.setCurrentIndex(1)  # 기본 NORMAL
        self.cbo_speed.setToolTip("발송 자동화 속도 모드 선택\n- SLOW: 안정성 우선\n- NORMAL: 기본\n- FAST: 속도 우선")

        header_right.addWidget(lbl_speed)
        header_right.addWidget(self.cbo_speed)

        header_row.addLayout(header_right)

        self._refresh_priv_label()

        main = QHBoxLayout()
        main.setSpacing(12)
        root.addLayout(main, 1)

        left_card = QFrame()
        left_card.setObjectName("Card")
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(10)

        lv.addWidget(QLabel("발송리스트 생성"))

        form = QHBoxLayout()
        form.setSpacing(8)

        form.addWidget(QLabel("그룹"))
        self.cbo_groups = QComboBox()
        self.cbo_groups.setMinimumWidth(0)
        form.addWidget(self.cbo_groups, 2)

        form.addWidget(QLabel("캠페인"))
        self.cbo_campaigns = QComboBox()
        self.cbo_campaigns.setMinimumWidth(0)
        form.addWidget(self.cbo_campaigns, 3)

        lv.addLayout(form)

        form_btns = QHBoxLayout()
        form_btns.setSpacing(8)
        self.btn_create_send_list = QPushButton("발송리스트 생성")
        self.btn_reload_sources = QPushButton("목록 새로고침")
        form_btns.addWidget(self.btn_create_send_list)
        form_btns.addWidget(self.btn_reload_sources)
        form_btns.addStretch(1)
        lv.addLayout(form_btns)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e5e7eb;")
        lv.addWidget(sep)

        lv.addWidget(QLabel("발송리스트 관리"))

        self.lst_send_lists = QListWidget()
        self.lst_send_lists.setMinimumWidth(380)
        self.lst_send_lists.setDragDropMode(QListWidget.InternalMove)
        self.lst_send_lists.setDefaultDropAction(Qt.MoveAction)
        lv.addWidget(self.lst_send_lists, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_refresh_lists = QPushButton("새로고침")

        self.btn_move_up = QToolButton()
        self.btn_move_up.setText("▲")
        self.btn_move_up.setToolTip("선택한 발송리스트를 위로 이동")

        self.btn_move_down = QToolButton()
        self.btn_move_down.setText("▼")
        self.btn_move_down.setToolTip("선택한 발송리스트를 아래로 이동")

        self.btn_delete_list = QPushButton("삭제")
        self.btn_save_order = QPushButton("순서 저장")

        btn_row.addWidget(self.btn_refresh_lists)
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)
        btn_row.addWidget(self.btn_delete_list)
        btn_row.addWidget(self.btn_save_order)
        btn_row.addStretch(1)
        lv.addLayout(btn_row)

        main.addWidget(left_card, 3)
        left_card.setMaximumWidth(520)

        right_card = QFrame()
        right_card.setObjectName("Card")
        rv = QVBoxLayout(right_card)
        rv.setContentsMargins(12, 12, 12, 12)
        rv.setSpacing(8)

        rv.addWidget(QLabel("발송 대상 리스트(미리보기)"))

        self.tbl_preview = QTableView()
        self.tbl_preview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_preview.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setSortingEnabled(True)

        self.preview_model = QStandardItemModel(0, 6, self)
        self.preview_model.setHorizontalHeaderLabels(["No", "사번", "이름", "전화번호", "대리점명", "지사명"])
        self.tbl_preview.setModel(self.preview_model)

        self.tbl_preview.setColumnWidth(0, 50)
        self.tbl_preview.setColumnWidth(1, 95)
        self.tbl_preview.setColumnWidth(2, 80)
        self.tbl_preview.setColumnWidth(3, 130)
        self.tbl_preview.setColumnWidth(4, 130)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)

        rv.addWidget(self.tbl_preview, 1)

        self.lbl_footer = QLabel("선택된 발송리스트가 없습니다.")
        self.lbl_footer.setStyleSheet("color:#6b7280;")
        rv.addWidget(self.lbl_footer)

        main.addWidget(right_card, 9)

        action = QHBoxLayout()
        action.setSpacing(10)

        self.btn_send_start = QPushButton("발송 시작")
        self.btn_send_stop = QPushButton("중지")
        self.btn_send_stop.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        self.progress.setTextVisible(True)
        self._set_progress_title("")

        action.addWidget(self.btn_send_start)
        action.addWidget(self.btn_send_stop)
        action.addWidget(self.progress, 1)
        root.addLayout(action)

        self.btn_reload_sources.clicked.connect(self.reload_sources)
        self.btn_create_send_list.clicked.connect(self._create_send_list)

        self.btn_refresh_lists.clicked.connect(self.reload_send_lists)
        self.btn_delete_list.clicked.connect(self._delete_selected_send_list)
        self.btn_save_order.clicked.connect(self._save_send_list_order)

        self.btn_move_up.clicked.connect(self._move_selected_send_list_up)
        self.btn_move_down.clicked.connect(self._move_selected_send_list_down)

        self.lst_send_lists.currentRowChanged.connect(self._on_send_list_selected)
        self.lst_send_lists.itemDoubleClicked.connect(self._on_send_list_double_clicked)

        self.btn_send_start.clicked.connect(self._start_send_all_lists)
        self.btn_send_stop.clicked.connect(self._stop_send)

        self.reload_sources()
        self.reload_send_lists()

    # ---- Hotkey ----
    def _init_global_hotkey(self) -> None:
        app = QApplication.instance()
        if app is None:
            return

        self._hotkey_mgr = GlobalHotkeyManager(app, self._on_global_hotkey)
        self._hotkey_mgr.register_f11(self.HOTKEY_ID_FORCE_STOP)

    def _on_global_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id != self.HOTKEY_ID_FORCE_STOP:
            return
        if self._worker and self._worker.isRunning():
            self._force_stop_send()

    def _force_stop_send(self) -> None:
        try:
            if self._worker and self._worker.isRunning():
                self._worker.request_stop()
                self._on_status("⚠️ 강제 중지(F11) 실행됨")
        except Exception:
            pass

    # ---- UI helpers ----
    def _refresh_priv_label(self) -> None:
        self.lbl_priv.setText("강제 중지: F11  |  발송 중 언제든지 즉시 중지됩니다.")

    def _set_progress_title(self, title: str) -> None:
        self._current_sending_title = (title or "").strip()
        if self._current_sending_title:
            self.progress.setFormat(f"발송중: {self._current_sending_title}  %p%")
        else:
            self.progress.setFormat("%p%")

    def _set_sending_ui(self, sending: bool) -> None:
        self.btn_send_start.setEnabled(not sending)
        self.btn_send_stop.setEnabled(sending)

        self.btn_create_send_list.setEnabled(not sending)
        self.btn_reload_sources.setEnabled(not sending)

        self.btn_refresh_lists.setEnabled(not sending)
        self.btn_delete_list.setEnabled(not sending)
        self.btn_save_order.setEnabled(not sending)
        self.lst_send_lists.setEnabled(not sending)

        self.cbo_groups.setEnabled(not sending)
        self.cbo_campaigns.setEnabled(not sending)

        if hasattr(self, "cbo_speed"):
            self.cbo_speed.setEnabled(not sending)

    def _format_title(self, group_name: str, campaign_name: str) -> str:
        group_name = (group_name or "").strip()
        campaign_name = (campaign_name or "").strip()
        return f"{group_name} + {campaign_name}".strip(" +")

    def _refresh_visible_numbers_only(self) -> None:
        for idx in range(self.lst_send_lists.count()):
            it = self.lst_send_lists.item(idx)
            if not it:
                continue
            data = it.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue
            title = data.get("title", "")
            it.setText(f"{idx + 1}. {title}")

    def _current_send_list_data(self) -> Optional[dict]:
        it = self.lst_send_lists.currentItem()
        if not it:
            return None
        data = it.data(Qt.UserRole)
        return data if isinstance(data, dict) else None

    # ---- Kakao target auto resolve ----
    def _pick_best_kakao_target_handle(self) -> Optional[int]:
        targets = KakaoPcDriver.list_targets()
        if not targets:
            return None
        best = None
        best_score = -1
        for t in targets:
            title = str(getattr(t, "title", "") or "")
            hwnd = int(getattr(t, "handle", 0) or 0)
            if hwnd <= 0:
                continue
            score = 0
            if "카카오톡" in title:
                score += 10
            if "kakaotalk" in title.lower():
                score += 9
            if len(title.strip()) >= 3:
                score += 1
            if score > best_score:
                best_score = score
                best = hwnd
        return best

    # ---- Sources ----
    def reload_sources(self) -> None:
        self.cbo_groups.blockSignals(True)
        self.cbo_groups.clear()
        self.cbo_groups.addItem("전체", None)

        groups = self.groups_repo.list_groups()
        for g in (groups or []):
            self.cbo_groups.addItem(str(getattr(g, "name", "")), int(getattr(g, "id")))
        self.cbo_groups.setCurrentIndex(0)
        self.cbo_groups.blockSignals(False)

        self.cbo_campaigns.blockSignals(True)
        self.cbo_campaigns.clear()

        campaigns = self.campaigns_repo.list_campaigns()
        if not campaigns:
            self.cbo_campaigns.addItem("(캠페인 없음)", None)
        else:
            for c in campaigns:
                self.cbo_campaigns.addItem(f"[{c.id}] {c.name}", int(c.id))

        self.cbo_campaigns.setCurrentIndex(0)
        self.cbo_campaigns.blockSignals(False)

        self._on_status("그룹/캠페인 목록 새로고침 완료")

    # ---- Create send list ----
    def _create_send_list(self) -> None:
        group_id = self.cbo_groups.currentData()
        group_name = str(self.cbo_groups.currentText() or "").strip()

        campaign_id = self.cbo_campaigns.currentData()
        if campaign_id is None:
            QMessageBox.information(self, "안내", "캠페인을 선택하세요.")
            return
        campaign_name = str(self.cbo_campaigns.currentText() or "").strip()

        if group_id is None:
            target_mode = "ALL"
            key_group_id = None
            group_name = "전체"
        else:
            target_mode = "GROUP"
            key_group_id = int(group_id)

        try:
            if target_mode == "ALL":
                contacts = self.contacts_repo.search_contacts("")
            else:
                contacts = self.groups_repo.list_group_members(int(key_group_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"대상자 로드 실패\n{e}")
            return

        snapshot: List[dict] = []
        for c in (contacts or []):
            snapshot.append({
                "id": int(getattr(c, "id")),
                "emp_id": str(getattr(c, "emp_id", "") or ""),
                "name": str(getattr(c, "name", "") or ""),
                "phone": str(getattr(c, "phone", "") or ""),
                "agency": str(getattr(c, "agency", "") or ""),
                "branch": str(getattr(c, "branch", "") or ""),
            })

        if not snapshot:
            QMessageBox.information(self, "안내", "대상자가 없습니다.")
            return

        try:
            send_list_id = self.send_lists_repo.create_or_replace_send_list(
                target_mode=target_mode,
                group_id=key_group_id,
                group_name=group_name,
                campaign_id=int(campaign_id),
                campaign_name=campaign_name,
                contacts_snapshot=snapshot,
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"발송리스트 저장 실패\n{e}")
            return

        self._on_status(f"발송리스트 생성/갱신: id={send_list_id}")
        QMessageBox.information(self, "완료", f"발송리스트 저장 완료\n- ID: {send_list_id}\n- 대상: {len(snapshot)}명")
        self.reload_send_lists()

    # ---- list ----
    def reload_send_lists(self) -> None:
        self.lst_send_lists.blockSignals(True)
        self.lst_send_lists.clear()

        try:
            rows = self.send_lists_repo.list_send_lists()
        except Exception as e:
            self.lst_send_lists.blockSignals(False)
            QMessageBox.critical(self, "오류", f"발송리스트 로드 실패\n{e}")
            return

        if not rows:
            it = QListWidgetItem("(저장된 발송리스트 없음)")
            it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.lst_send_lists.addItem(it)

            self.lst_send_lists.blockSignals(False)
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            return

        for idx, r in enumerate(rows, start=1):
            send_list_id = int(getattr(r, "id"))
            group_name = str(getattr(r, "group_name", "") or "")
            campaign_name = str(getattr(r, "campaign_name", "") or "")
            campaign_id = int(getattr(r, "campaign_id"))

            title = self._format_title(group_name, campaign_name)
            visible = f"{idx}. {title}"

            item = QListWidgetItem(visible)
            item.setData(Qt.UserRole, {
                "send_list_id": send_list_id,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "group_name": group_name,
                "title": title,
            })
            self.lst_send_lists.addItem(item)

        self.lst_send_lists.blockSignals(False)
        self.lst_send_lists.setCurrentRow(0)
        self._on_status("발송리스트 새로고침 완료")

    # ---- preview ----
    def _on_send_list_selected(self, row: int) -> None:
        it = self.lst_send_lists.item(row)
        if not it:
            return

        data = it.data(Qt.UserRole)
        if not isinstance(data, dict):
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("선택된 발송리스트가 없습니다.")
            return

        send_list_id = data.get("send_list_id")
        title = data.get("title", "")

        if send_list_id is None:
            return

        try:
            contacts = self.send_lists_repo.get_send_list_contacts(int(send_list_id))
        except Exception as e:
            self.preview_model.setRowCount(0)
            self.lbl_footer.setText("대상자 로드 실패")
            QMessageBox.critical(self, "오류", f"대상자 로드 실패\n{e}")
            return

        self.preview_model.setRowCount(0)
        for i, c in enumerate(contacts, start=1):
            self.preview_model.appendRow([
                QStandardItem(str(i)),
                QStandardItem(str(getattr(c, "emp_id", "") or "")),
                QStandardItem(str(getattr(c, "name", "") or "")),
                QStandardItem(str(getattr(c, "phone", "") or "")),
                QStandardItem(str(getattr(c, "agency", "") or "")),
                QStandardItem(str(getattr(c, "branch", "") or "")),
            ])

        self.lbl_footer.setText(f"대상: {len(contacts)}명 / 발송리스트: {title}")

    # ---- delete ----
    def _delete_selected_send_list(self) -> None:
        data = self._current_send_list_data()
        if not data:
            QMessageBox.information(self, "안내", "삭제할 발송리스트를 선택하세요.")
            return

        send_list_id = data.get("send_list_id")
        if send_list_id is None:
            return

        title = data.get("title", "")

        ok = QMessageBox.question(
            self, "삭제 확인",
            f"발송리스트를 삭제하시겠습니까?\n- {title}",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self.send_lists_repo.delete_send_list(int(send_list_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"삭제 실패\n{e}")
            return

        self._on_status(f"발송리스트 삭제: id={send_list_id}")
        self.reload_send_lists()

    # ---- save order ----
    def _save_send_list_order(self) -> None:
        ordered_ids: List[int] = []
        for i in range(self.lst_send_lists.count()):
            it = self.lst_send_lists.item(i)
            if not it:
                continue
            data = it.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue
            sid = data.get("send_list_id")
            if sid is None:
                continue
            ordered_ids.append(int(sid))

        if not ordered_ids:
            QMessageBox.information(self, "안내", "저장할 발송리스트가 없습니다.")
            return

        try:
            self.send_lists_repo.update_send_list_orders(ordered_ids)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"순서 저장 실패\n{e}")
            return

        self._on_status("발송리스트 순서 저장 완료")
        self.reload_send_lists()

    # ---- double click preview ----
    def _on_send_list_double_clicked(self, it: QListWidgetItem) -> None:
        data = it.data(Qt.UserRole)
        if not isinstance(data, dict):
            return

        campaign_id = data.get("campaign_id")
        title = data.get("title", "")

        if campaign_id is None:
            QMessageBox.information(self, "안내", "캠페인 정보가 없습니다.")
            return

        try:
            items = self.campaigns_repo.get_campaign_items(int(campaign_id))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"캠페인 미리보기 로드 실패\n{e}")
            return

        dlg = CampaignPreviewDialog(campaign_title=title, items=items, parent=self)
        dlg.exec()

    # ---- build jobs ----
    def _build_jobs_from_list_widget(self) -> List[SendJob]:
        jobs: List[SendJob] = []
        for i in range(self.lst_send_lists.count()):
            it = self.lst_send_lists.item(i)
            if not it:
                continue
            if not (it.flags() & Qt.ItemIsEnabled):
                continue

            data = it.data(Qt.UserRole)
            if not isinstance(data, dict):
                continue

            send_list_id = data.get("send_list_id")
            campaign_id = data.get("campaign_id")
            title = data.get("title", "")
            group_name = str(data.get("group_name", "") or "")
            campaign_name = str(data.get("campaign_name", "") or "")

            if send_list_id is None or campaign_id is None:
                continue

            rows = self.send_lists_repo.get_send_list_contacts(int(send_list_id))
            recipients: List[Recipient] = []
            for r in (rows or []):
                raw_name = str(getattr(r, "name", "") or "")
                name = raw_name.strip().replace("\u200b", "").replace("\ufeff", "")

                if not name:
                    continue

                recipients.append(Recipient(
                    emp_id=str(getattr(r, "emp_id", "") or "").strip(),
                    name=name,
                    phone=str(getattr(r, "phone", "") or "").strip(),
                    agency=str(getattr(r, "agency", "") or "").strip(),
                    branch=str(getattr(r, "branch", "") or "").strip(),
                ))

            items = self.campaigns_repo.get_campaign_items(int(campaign_id))

            jobs.append(SendJob(
                send_list_id=int(send_list_id),
                title=str(title),
                group_name=group_name,
                campaign_id=int(campaign_id),
                campaign_name=campaign_name,
                recipients=recipients,
                campaign_items=items,
            ))
        return jobs

    # ---- start send ----
    def _start_send_all_lists(self) -> None:
        self._run_logger = None
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "안내", "이미 발송 중입니다.")
            return

        hwnd = self._pick_best_kakao_target_handle()
        if hwnd is None:
            QMessageBox.information(self, "안내", "카카오톡 창이 없습니다.\n카카오톡 실행/로그인 후 다시 시도하세요.")
            return

        self._refresh_visible_numbers_only()

        try:
            jobs = self._build_jobs_from_list_widget()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"발송 준비(리스트 로드) 실패\n{e}")
            return

        if not jobs:
            QMessageBox.information(self, "안내", "발송할 발송리스트가 없습니다.")
            return

        filtered: List[SendJob] = [j for j in jobs if j.campaign_items]
        if not filtered:
            QMessageBox.information(self, "안내", "발송 가능한 발송리스트가 없습니다. (캠페인 내용 없음)")
            return

        total_targets = sum(len(j.recipients) for j in filtered)

        ok = QMessageBox.question(
            self, "발송 시작",
            f"발송리스트 {len(filtered)}개를 위에서부터 순차 발송합니다.\n"
            f"- 총 대상: {total_targets}명\n\n"
            f"계속 진행하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ok != QMessageBox.Yes:
            return


        try:
            speed_mode = str(self.cbo_speed.currentData() or "normal")
        except Exception:
            speed_mode = "normal"

        self.sender_driver = KakaoPcDriver(
            int(hwnd),
            speed_mode=speed_mode,  # ✅ UI 선택값 반영
            block_input=False,
            use_alt_tab_confirm=False,
            alt_tab_max_steps=0,
        )

        self.progress.setValue(0)
        self._set_progress_title(f"1/{len(filtered)} {filtered[0].title}")
        self._set_sending_ui(True)
        run_logger = SendRunLogger.new_run(prefix="send_run")
        self._run_logger = run_logger
        self._on_status(
            f"발송 시작(카카오톡 자동화) | 속도: {speed_mode.upper()} | 강제중지: F11 | 로그: {run_logger.path_str()}"
        )
        run_id = time.strftime("%Y%m%d_%H%M%S")
        report_writer = SendReportWriter(base_dir=user_data_dir(), run_id=run_id)
        report_writer.set_meta(total_lists=len(filtered), total_targets=total_targets)
        self._on_status(f"리포트 파일 생성: {str(report_writer.path)}")

        self._worker = MultiSendWorker(
            driver=self.sender_driver,
            jobs=filtered,
            parent=self,
            delay_ms=500,
            max_retry=2,
            retry_sleep_ms=250,
            run_logger=run_logger,
            report_writer=report_writer,
        )
        self._worker.list_changed.connect(self._on_worker_list_changed)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished_ok.connect(self._on_send_finished)
        self._worker.start()

    def _on_worker_list_changed(self, title: str, idx: int, total: int) -> None:
        self._set_progress_title(f"{idx}/{total} {title}")
        self.progress.setValue(0)

    def _stop_send(self) -> None:
        if not self._worker or not self._worker.isRunning():
            return
        self._worker.request_stop()
        self._on_status("중지 요청됨")

    def _on_send_finished(self, list_done: int, success: int, fail: int) -> None:
        self._set_sending_ui(False)
        self._set_progress_title("")
        self.progress.setValue(100 if (success + fail) > 0 else 0)

        log_path = ""
        try:
            if self._run_logger:
                log_path = self._run_logger.path_str()
        except Exception:
            log_path = ""

        QMessageBox.information(
            self, "발송 종료",
            f"발송 종료\n- 완료 리스트: {list_done}개\n- 성공: {success}\n- 실패: {fail}"
            + (f"\n\n로그 파일:\n{log_path}" if log_path else "")
        )

        self._on_status(
            f"발송 종료 | 리스트 {list_done}개 완료 | 성공 {success} / 실패 {fail}"
            + (f" | 로그: {log_path}" if log_path else "")
        )

    # ---- move up/down ----
    def _move_selected_send_list_up(self) -> None:
        row = self.lst_send_lists.currentRow()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)

    def _move_selected_send_list_down(self) -> None:
        row = self.lst_send_lists.currentRow()
        if row < 0 or row >= (self.lst_send_lists.count() - 1):
            return
        self._swap_rows(row, row + 1)

    def _swap_rows(self, a: int, b: int) -> None:
        if a == b:
            return
        if a < 0 or b < 0:
            return
        if a >= self.lst_send_lists.count() or b >= self.lst_send_lists.count():
            return

        item_a = self.lst_send_lists.takeItem(a)
        item_b = self.lst_send_lists.takeItem(b if b < a else b - 1)

        self.lst_send_lists.insertItem(a, item_b)
        self.lst_send_lists.insertItem(b, item_a)

        self.lst_send_lists.setCurrentRow(b)
        self._refresh_visible_numbers_only()

    # ---- cleanup ----
    def cleanup(self) -> None:
        try:
            if self._worker and self._worker.isRunning():
                self._worker.request_stop()
                self._worker.wait(1500)
        except Exception:
            pass

        try:
            if self._hotkey_mgr:
                self._hotkey_mgr.unregister_all()
                self._hotkey_mgr = None
        except Exception:
            pass

        self._run_logger = None


__all__ = ["SendPage"]
