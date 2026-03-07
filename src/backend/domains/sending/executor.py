from __future__ import annotations

from typing import Optional, List

from backend.domains.sending.result import SendRunResult
from backend.integrations.kakaotalk.hooks import ChatNotFound


class SendExecutor:
    def __init__(
        self,
        *,
        driver,
        jobs,
        delay_ms: int,
        max_retry: int,
        retry_sleep_ms: int,
        run_logger=None,
        report_writer=None,
        is_stop_requested=None,
        status_cb=None,
        progress_cb=None,
        list_changed_cb=None,
        recover_driver_cb=None,
        stop_driver_cb=None,
    ) -> None:
        self._driver = driver
        self._jobs = jobs
        self._delay_ms = max(0, int(delay_ms))
        self._max_retry = max(0, int(max_retry))
        self._retry_sleep_ms = max(0, int(retry_sleep_ms))
        self._run_logger = run_logger
        self._report_writer = report_writer

        self._is_stop_requested = is_stop_requested or (lambda: False)
        self._status_cb = status_cb or (lambda _msg: None)
        self._progress_cb = progress_cb or (lambda _v: None)
        self._list_changed_cb = list_changed_cb or (lambda _title, _i, _t: None)

        self._recover_driver_cb = recover_driver_cb or (lambda: None)
        self._stop_driver_cb = stop_driver_cb or (lambda: None)

    def execute(self) -> SendRunResult:
        StopNow = None
        TransferAbortedByClose = None
        try:
            from backend.integrations.kakaotalk.driver import (
                StopNow as _StopNow,
                TransferAbortedByClose as _TransferAbortedByClose,
            )
            StopNow = _StopNow
            TransferAbortedByClose = _TransferAbortedByClose
        except Exception:
            StopNow = None
            TransferAbortedByClose = None

        list_done = 0
        success = 0
        fail = 0
        stopped = False

        if not self._jobs:
            self._status_cb("발송할 발송리스트가 없습니다.")
            self._progress_cb(0)
            return SendRunResult(list_done=0, success=0, fail=0, stopped=False)

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
            self._status_cb("발송 준비 중...")
            self._driver.start()

            self._status_cb("캠페인 이미지 전처리 중...")
            for job in self._jobs:
                for item in job.campaign_items:
                    typ = str(getattr(item, "item_type", "")).upper().strip()
                    if typ in ("IMG", "IMAGE"):
                        png = getattr(item, "image_bytes", b"") or b""
                        if png and hasattr(self._driver, "_png_to_dib_bytes"):
                            self._driver._png_to_dib_bytes(png)

            try:
                if self._run_logger:
                    self._run_logger.log_event("DRIVER_START_OK")
            except Exception:
                pass
        except Exception as e:
            self._status_cb(f"발송 준비 실패: {e}")
            try:
                if self._run_logger:
                    self._run_logger.log_event("DRIVER_START_FAIL", error=str(e))
            except Exception:
                pass
            return SendRunResult(list_done=0, success=0, fail=0, stopped=False)

        def _rk(x) -> str:
            return f"{x.emp_id}|{x.name}|{x.phone}"

        try:
            for li, job in enumerate(self._jobs, start=1):
                if self._is_stop_requested():
                    stopped = True
                    self._status_cb("발송 강제 중지됨(F11)")
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
                            recipients_snapshot=list(job.recipients_snapshot or []),
                        )
                except Exception:
                    pass

                self._list_changed_cb(job.title, li, total_lists)
                self._progress_cb(0)

                try:
                    self._recover_driver_cb()
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
                    self._status_cb(f"스킵(대상 0명) | {job.title}")
                    list_done += 1
                    continue

                tail_retry: List = []
                tail_retry_keys: set[str] = set()

                for ri, r in enumerate(job.recipients, start=1):
                    if self._is_stop_requested():
                        stopped = True
                        self._status_cb("발송 강제 중지됨(F11)")
                        break

                    self._status_cb(f"[{li}/{total_lists}] {job.title} | {ri}/{total} | {r.name}")

                    ok = False
                    last_err: Optional[Exception] = None
                    used_attempt = 0

                    for attempt in range(0, self._max_retry + 1):
                        if self._is_stop_requested():
                            stopped = True
                            break

                        used_attempt = attempt + 1

                        try:
                            raw_name = r.name
                            name = (raw_name or "").strip().replace("\u200b", "").replace("\ufeff", "")
                            if not name:
                                self._status_cb(f"스킵(이름 비어있음) | {job.title} | emp_id={r.emp_id}")
                                ok = True
                                try:
                                    if self._report_writer:
                                        self._report_writer.add_recipient_result(
                                            list_index=li,
                                            emp_id=r.emp_id,
                                            name=r.name,
                                            phone=r.phone,
                                            agency=r.agency,
                                            branch=r.branch,
                                            status="SKIP",
                                            reason="EMPTY_NAME",
                                            attempt=used_attempt,
                                        )
                                except Exception:
                                    pass
                                break

                            self._driver.send_campaign_items(name, job.campaign_items)
                            ok = True
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=r.emp_id,
                                        name=r.name,
                                        phone=r.phone,
                                        agency=r.agency,
                                        branch=r.branch,
                                        status="SUCCESS",
                                        reason="",
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass
                            break

                        except ChatNotFound as e_nf:
                            ok = False
                            last_err = e_nf
                            self._status_cb(f"대화방 없음(NOT_FOUND) | {job.title} | {r.name}")
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=r.emp_id,
                                        name=r.name,
                                        phone=r.phone,
                                        agency=r.agency,
                                        branch=r.branch,
                                        status="NOT_FOUND",
                                        reason=str(e_nf) or "CHAT_NOT_FOUND",
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass
                            break

                        except Exception as e:
                            if StopNow is not None and isinstance(e, StopNow):
                                stopped = True
                                break

                            if TransferAbortedByClose is not None and isinstance(e, TransferAbortedByClose):
                                k = _rk(r)
                                if k not in tail_retry_keys:
                                    tail_retry_keys.add(k)
                                    tail_retry.append(r)

                                self._status_cb(f"전송 취소 감지 → 리스트 마지막에 1회 재전송 예약 | {job.title} | {r.name}")

                                try:
                                    if self._report_writer:
                                        self._report_writer.add_recipient_result(
                                            list_index=li,
                                            emp_id=r.emp_id,
                                            name=r.name,
                                            phone=r.phone,
                                            agency=r.agency,
                                            branch=r.branch,
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
                            self._status_cb(
                                f"재시도({used_attempt}/{self._max_retry + 1}) 실패 | {job.title} | {r.name} | {e}"
                            )

                            if self._retry_sleep_ms > 0:
                                import time
                                time.sleep(self._retry_sleep_ms / 1000.0)

                            try:
                                self._recover_driver_cb()
                            except Exception:
                                pass

                    if stopped:
                        break

                    if ok:
                        if not (TransferAbortedByClose is not None and isinstance(last_err, TransferAbortedByClose)):
                            success += 1
                    else:
                        fail += 1
                        if not isinstance(last_err, ChatNotFound):
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=r.emp_id,
                                        name=r.name,
                                        phone=r.phone,
                                        agency=r.agency,
                                        branch=r.branch,
                                        status="FAIL",
                                        reason=str(last_err),
                                        attempt=used_attempt,
                                    )
                            except Exception:
                                pass

                    self._progress_cb(int(ri * 100 / total))

                    if self._delay_ms > 0:
                        import time
                        remain = int(self._delay_ms)
                        step = 50
                        while remain > 0:
                            if self._is_stop_requested():
                                stopped = True
                                break
                            sleep_ms = min(step, remain)
                            time.sleep(sleep_ms / 1000.0)
                            remain -= sleep_ms

                if stopped:
                    break

                if tail_retry and (not stopped):
                    self._status_cb(f"[{li}/{total_lists}] {job.title} | 말미 재전송 {len(tail_retry)}건 시작")

                    for rr in tail_retry:
                        if self._is_stop_requested():
                            stopped = True
                            break

                        self._status_cb(f"[{li}/{total_lists}] {job.title} | 말미 재전송 | {rr.name}")

                        final_ok = False
                        last_err2: Optional[Exception] = None
                        used_attempt2 = 0

                        for attempt2 in range(0, self._max_retry + 1):
                            if self._is_stop_requested():
                                stopped = True
                                break

                            used_attempt2 = attempt2 + 1
                            try:
                                self._driver.send_campaign_items(rr.name, job.campaign_items)
                                final_ok = True
                                break
                            except Exception as e2:
                                if StopNow is not None and isinstance(e2, StopNow):
                                    stopped = True
                                    break

                                last_err2 = e2
                                if self._retry_sleep_ms > 0:
                                    import time
                                    time.sleep(self._retry_sleep_ms / 1000.0)

                                try:
                                    self._recover_driver_cb()
                                except Exception:
                                    pass

                        if final_ok:
                            success += 1
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=rr.emp_id,
                                        name=rr.name,
                                        phone=rr.phone,
                                        agency=rr.agency,
                                        branch=rr.branch,
                                        status="SUCCESS(TAIL_RETRY)",
                                        reason="",
                                        attempt=used_attempt2,
                                    )
                            except Exception:
                                pass
                        else:
                            fail += 1
                            try:
                                if self._report_writer:
                                    self._report_writer.add_recipient_result(
                                        list_index=li,
                                        emp_id=rr.emp_id,
                                        name=rr.name,
                                        phone=rr.phone,
                                        agency=rr.agency,
                                        branch=rr.branch,
                                        status="FAIL(TAIL_RETRY)",
                                        reason=str(last_err2),
                                        attempt=used_attempt2,
                                    )
                            except Exception:
                                pass

                list_done += 1

        finally:
            try:
                if self._report_writer:
                    self._report_writer.finish(
                        list_done=list_done,
                        success=success,
                        fail=fail,
                        stopped=stopped,
                    )
                    self._report_writer.save()
            except Exception:
                pass

        return SendRunResult(
            list_done=list_done,
            success=success,
            fail=fail,
            stopped=stopped,
        )