# FILE: src/backend/domains/sending/executor.py
from __future__ import annotations

import time
from typing import Callable, Optional

from backend.domains.sending.result import SendRunResult
from backend.integrations.kakaotalk.hooks import ChatNotFound


class SendExecutor:
    """
    실제 발송 실행 전담.

    책임:
    - driver start / recover / stop orchestration
    - job loop / recipient loop
    - retry / tail-retry 처리
    - run_logger / report_writer 반영
    - error_reporter 반영
    - 최종 SendRunResult 반환
    """

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
        error_reporter=None,
        trace_log_path: str = "",
        is_stop_requested: Optional[Callable[[], bool]] = None,
        status_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int], None]] = None,
        list_changed_cb: Optional[Callable[[str, int, int], None]] = None,
        recover_driver_cb: Optional[Callable[[], None]] = None,
        stop_driver_cb: Optional[Callable[[], None]] = None,
    ) -> None:
        self._driver = driver
        self._jobs = list(jobs or [])
        self._delay_ms = max(0, int(delay_ms))
        self._max_retry = max(0, int(max_retry))
        self._retry_sleep_ms = max(0, int(retry_sleep_ms))
        self._run_logger = run_logger
        self._report_writer = report_writer
        self._error_reporter = error_reporter
        self._trace_log_path = str(trace_log_path or "")

        self._is_stop_requested = is_stop_requested or (lambda: False)
        self._status_cb = status_cb or (lambda _msg: None)
        self._progress_cb = progress_cb or (lambda _v: None)
        self._list_changed_cb = list_changed_cb or (lambda _title, _i, _t: None)
        self._recover_driver_cb = recover_driver_cb or (lambda: None)
        self._stop_driver_cb = stop_driver_cb or (lambda: None)

        self._StopNow = None
        self._TransferAbortedByClose = None
        self._load_driver_exceptions()

    def execute(self) -> SendRunResult:
        result = SendRunResult(list_done=0, success=0, fail=0, stopped=False)

        if not self._jobs:
            self._status_cb("발송할 발송리스트가 없습니다.")
            self._progress_cb(0)
            return result

        total_lists = len(self._jobs)
        self._log_run_start(total_lists)

        if not self._prepare_driver():
            return result

        try:
            for list_index, job in enumerate(self._jobs, start=1):
                if self._check_stop(result, "발송 강제 중지됨(F11)"):
                    break

                self._log_list_start(job=job, list_index=list_index, total_lists=total_lists)
                self._report_add_list(job=job, list_index=list_index)

                self._list_changed_cb(job.title, list_index, total_lists)
                self._progress_cb(0)

                self._safe_recover_driver(list_index=list_index, title=job.title)

                total_recipients = len(job.recipients)
                if total_recipients == 0:
                    self._status_cb(f"스킵(대상 0명) | {job.title}")
                    result.list_done += 1
                    continue

                tail_retry, stopped_during_main = self._execute_main_recipients(
                    job=job,
                    list_index=list_index,
                    total_lists=total_lists,
                    result=result,
                )
                if stopped_during_main:
                    result.stopped = True
                    break

                stopped_during_tail = self._execute_tail_retry(
                    job=job,
                    list_index=list_index,
                    total_lists=total_lists,
                    tail_retry=tail_retry,
                    result=result,
                )
                if stopped_during_tail:
                    result.stopped = True
                    break

                result.list_done += 1

        finally:
            self._finalize_report(result)

        return result

    def _load_driver_exceptions(self) -> None:
        try:
            from backend.integrations.kakaotalk.driver import (
                StopNow as _StopNow,
                TransferAbortedByClose as _TransferAbortedByClose,
            )
            self._StopNow = _StopNow
            self._TransferAbortedByClose = _TransferAbortedByClose
        except Exception:
            self._StopNow = None
            self._TransferAbortedByClose = None

    def _prepare_driver(self) -> bool:
        try:
            self._status_cb("발송 준비 중...")
            self._driver.start()

            self._status_cb("캠페인 이미지 전처리 중...")
            for job in self._jobs:
                for item in job.campaign_items:
                    item_type = str(getattr(item, "item_type", "") or "").upper().strip()
                    if item_type not in ("IMG", "IMAGE"):
                        continue

                    png = getattr(item, "image_bytes", b"") or b""
                    if png and hasattr(self._driver, "_png_to_dib_bytes"):
                        self._driver._png_to_dib_bytes(png)

            self._safe_log_event("DRIVER_START_OK")
            return True

        except Exception as e:
            self._status_cb(f"발송 준비 실패: {e}")
            self._safe_log_event("DRIVER_START_FAIL", error=str(e))

            self._maybe_report_error(
                exc=e,
                stage="DRIVER_START_FAIL",
                attempt=0,
                job=None,
                recipient=None,
                extra={},
            )
            return False

    def _execute_main_recipients(
        self,
        *,
        job,
        list_index: int,
        total_lists: int,
        result: SendRunResult,
    ) -> tuple[list, bool]:
        total = len(job.recipients)
        tail_retry: list = []
        tail_retry_keys: set[str] = set()

        for recipient_index, recipient in enumerate(job.recipients, start=1):
            if self._check_stop(result, "발송 강제 중지됨(F11)"):
                return tail_retry, True

            self._status_cb(
                f"[{list_index}/{total_lists}] {job.title} | {recipient_index}/{total} | {recipient.name}"
            )

            send_outcome = self._send_single_recipient(
                job=job,
                recipient=recipient,
                list_index=list_index,
            )

            if send_outcome["stopped"]:
                return tail_retry, True

            if send_outcome["tail_retry_scheduled"]:
                retry_key = self._recipient_key(recipient)
                if retry_key not in tail_retry_keys:
                    tail_retry_keys.add(retry_key)
                    tail_retry.append(recipient)
            elif send_outcome["ok"]:
                result.success += 1
            else:
                result.fail += 1

            self._progress_cb(int(recipient_index * 100 / total))
            if self._sleep_with_stop(self._delay_ms, result):
                return tail_retry, True

        return tail_retry, False

    def _send_single_recipient(self, *, job, recipient, list_index: int) -> dict:
        last_err: Optional[Exception] = None
        used_attempt = 0

        for attempt in range(0, self._max_retry + 1):
            if self._is_stop_requested():
                return {
                    "ok": False,
                    "stopped": True,
                    "tail_retry_scheduled": False,
                    "attempt": used_attempt,
                    "last_err": last_err,
                }

            used_attempt = attempt + 1

            try:
                raw_name = str(getattr(recipient, "name", "") or "")
                name = raw_name.strip().replace("\u200b", "").replace("\ufeff", "")
                if not name:
                    self._status_cb(f"스킵(이름 비어있음) | {job.title} | emp_id={recipient.emp_id}")
                    self._report_add_recipient_result(
                        list_index=list_index,
                        recipient=recipient,
                        status="SKIP",
                        reason="EMPTY_NAME",
                        attempt=used_attempt,
                    )
                    return {
                        "ok": True,
                        "stopped": False,
                        "tail_retry_scheduled": False,
                        "attempt": used_attempt,
                        "last_err": None,
                    }

                self._driver.send_campaign_items(
                    name,
                    job.campaign_items,
                    send_mode=str(getattr(job, "send_mode", "clipboard") or "clipboard"),
                )
                self._report_add_recipient_result(
                    list_index=list_index,
                    recipient=recipient,
                    status="SUCCESS",
                    reason="",
                    attempt=used_attempt,
                )
                return {
                    "ok": True,
                    "stopped": False,
                    "tail_retry_scheduled": False,
                    "attempt": used_attempt,
                    "last_err": None,
                }

            except ChatNotFound as e_nf:
                self._status_cb(f"대화방 없음(NOT_FOUND) | {job.title} | {recipient.name}")
                self._report_add_recipient_result(
                    list_index=list_index,
                    recipient=recipient,
                    status="NOT_FOUND",
                    reason=str(e_nf) or "CHAT_NOT_FOUND",
                    attempt=used_attempt,
                )
                return {
                    "ok": False,
                    "stopped": False,
                    "tail_retry_scheduled": False,
                    "attempt": used_attempt,
                    "last_err": e_nf,
                }

            except Exception as e:
                msg = str(e)

                if self._StopNow is not None and isinstance(e, self._StopNow):
                    return {
                        "ok": False,
                        "stopped": True,
                        "tail_retry_scheduled": False,
                        "attempt": used_attempt,
                        "last_err": e,
                    }

                if self._TransferAbortedByClose is not None and isinstance(e, self._TransferAbortedByClose):
                    self._status_cb(
                        f"전송 취소 감지 → 리스트 마지막에 1회 재전송 예약 | {job.title} | {recipient.name}"
                    )
                    self._report_add_recipient_result(
                        list_index=list_index,
                        recipient=recipient,
                        status="TAIL_RETRY_SCHEDULED",
                        reason=str(e),
                        attempt=used_attempt,
                    )
                    return {
                        "ok": False,
                        "stopped": False,
                        "tail_retry_scheduled": True,
                        "attempt": used_attempt,
                        "last_err": e,
                    }

                lowered = msg.lower()

                if ("파일 열기" in msg) or ("경로가 없습니다" in msg) or ("bing" in lowered) or ("open" in lowered):
                    self._status_cb(
                        f"첨부창 잔류/경로 꼬임 복구 재시도 | {job.title} | {recipient.name} | {msg}"
                    )
                else:
                    self._status_cb(
                        f"재시도({used_attempt}/{self._max_retry + 1}) 실패 | {job.title} | {recipient.name} | {e}"
                    )

                last_err = e

                if self._retry_sleep_ms > 0:
                    time.sleep(self._retry_sleep_ms / 1000.0)

                try:
                    self._recover_driver_cb()
                except Exception:
                    pass

        self._report_add_recipient_result(
            list_index=list_index,
            recipient=recipient,
            status="FAIL",
            reason=str(last_err),
            attempt=used_attempt,
        )

        if last_err is not None:
            self._maybe_report_error(
                exc=last_err,
                stage="SEND_SINGLE_RECIPIENT_FINAL_FAIL",
                attempt=used_attempt,
                job=job,
                recipient=recipient,
                extra={
                    "list_index": list_index,
                    "max_retry": self._max_retry,
                    "send_mode": str(getattr(job, "send_mode", "") or ""),
                },
            )

        return {
            "ok": False,
            "stopped": False,
            "tail_retry_scheduled": False,
            "attempt": used_attempt,
            "last_err": last_err,
        }

    def _execute_tail_retry(
        self,
        *,
        job,
        list_index: int,
        total_lists: int,
        tail_retry: list,
        result: SendRunResult,
    ) -> bool:
        if not tail_retry:
            return False

        self._status_cb(f"[{list_index}/{total_lists}] {job.title} | 말미 재전송 {len(tail_retry)}건 시작")

        for recipient in tail_retry:
            if self._check_stop(result, "발송 강제 중지됨(F11)"):
                return True

            self._status_cb(f"[{list_index}/{total_lists}] {job.title} | 말미 재전송 | {recipient.name}")

            final_ok = False
            last_err: Optional[Exception] = None
            used_attempt = 0

            for attempt in range(0, self._max_retry + 1):
                if self._is_stop_requested():
                    result.stopped = True
                    return True

                used_attempt = attempt + 1

                try:
                    self._driver.send_campaign_items(
                        recipient.name,
                        job.campaign_items,
                        send_mode=str(getattr(job, "send_mode", "clipboard") or "clipboard"),
                    )
                    final_ok = True
                    break

                except Exception as e:
                    if self._StopNow is not None and isinstance(e, self._StopNow):
                        result.stopped = True
                        return True

                    last_err = e
                    if self._retry_sleep_ms > 0:
                        time.sleep(self._retry_sleep_ms / 1000.0)

                    try:
                        self._recover_driver_cb()
                    except Exception:
                        pass

            if final_ok:
                result.success += 1
                self._report_add_recipient_result(
                    list_index=list_index,
                    recipient=recipient,
                    status="SUCCESS(TAIL_RETRY)",
                    reason="",
                    attempt=used_attempt,
                )
            else:
                result.fail += 1
                self._report_add_recipient_result(
                    list_index=list_index,
                    recipient=recipient,
                    status="FAIL(TAIL_RETRY)",
                    reason=str(last_err),
                    attempt=used_attempt,
                )

                if last_err is not None:
                    self._maybe_report_error(
                        exc=last_err,
                        stage="TAIL_RETRY_FINAL_FAIL",
                        attempt=used_attempt,
                        job=job,
                        recipient=recipient,
                        extra={
                            "list_index": list_index,
                            "max_retry": self._max_retry,
                            "send_mode": str(getattr(job, "send_mode", "") or ""),
                        },
                    )

        return False

    def _log_run_start(self, total_lists: int) -> None:
        self._safe_log_event(
            "RUN_START",
            total_lists=total_lists,
            max_retry=self._max_retry,
            delay_ms=self._delay_ms,
            retry_sleep_ms=self._retry_sleep_ms,
        )

    def _log_list_start(self, *, job, list_index: int, total_lists: int) -> None:
        self._safe_log_event(
            "LIST_START",
            list_index=list_index,
            total_lists=total_lists,
            title=job.title,
            recipients=len(job.recipients),
            send_mode=str(getattr(job, "send_mode", "clipboard") or "clipboard"),
        )

    def _safe_recover_driver(self, *, list_index: int, title: str) -> None:
        try:
            self._recover_driver_cb()
        except Exception as e:
            self._safe_log_event(
                "DRIVER_RESTART_FAIL",
                list_index=list_index,
                title=title,
                error=str(e),
            )

    def _report_add_list(self, *, job, list_index: int) -> None:
        if not self._report_writer:
            return

        try:
            self._report_writer.add_list(
                list_index=list_index,
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

    def _report_add_recipient_result(
        self,
        *,
        list_index: int,
        recipient,
        status: str,
        reason: str,
        attempt: int,
    ) -> None:
        if not self._report_writer:
            return

        try:
            self._report_writer.add_recipient_result(
                list_index=list_index,
                emp_id=recipient.emp_id,
                name=recipient.name,
                phone=recipient.phone,
                agency=recipient.agency,
                branch=recipient.branch,
                status=status,
                reason=reason,
                attempt=attempt,
            )
        except Exception:
            pass

    def _finalize_report(self, result: SendRunResult) -> None:
        try:
            if self._report_writer:
                self._report_writer.finish(
                    list_done=result.list_done,
                    success=result.success,
                    fail=result.fail,
                    stopped=result.stopped,
                )
                self._report_writer.save()
        except Exception:
            pass

    def _check_stop(self, result: SendRunResult, message: str) -> bool:
        if not self._is_stop_requested():
            return False
        result.stopped = True
        self._status_cb(message)
        return True

    def _sleep_with_stop(self, total_ms: int, result: SendRunResult) -> bool:
        remain = max(0, int(total_ms))
        if remain <= 0:
            return False

        step = 50
        while remain > 0:
            if self._is_stop_requested():
                result.stopped = True
                return True
            sleep_ms = min(step, remain)
            time.sleep(sleep_ms / 1000.0)
            remain -= sleep_ms
        return False

    def _safe_log_event(self, event_name: str, **kwargs) -> None:
        try:
            if self._run_logger:
                self._run_logger.log_event(event_name, **kwargs)
        except Exception:
            pass

    def _maybe_report_error(
        self,
        *,
        exc: Exception,
        stage: str,
        attempt: int,
        job=None,
        recipient=None,
        extra: Optional[dict] = None,
    ) -> None:
        reporter = self._error_reporter
        if reporter is None:
            return

        try:
            reporter.report_exception(
                exc=exc,
                stage=stage,
                attempt=attempt,
                run_logger=self._run_logger,
                trace_log_path=self._trace_log_path,
                job=job,
                recipient=recipient,
                extra=extra or {},
            )
        except Exception as report_exc:
            self._safe_log_event(
                "ERROR_REPORT_FAIL",
                stage=stage,
                error=str(report_exc),
                error_type=report_exc.__class__.__name__,
            )

    def _recipient_key(self, recipient) -> str:
        return f"{recipient.emp_id}|{recipient.name}|{recipient.phone}"