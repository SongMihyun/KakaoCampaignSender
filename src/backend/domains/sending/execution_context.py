# FILE: src/backend/domains/sending/execution_context.py
from __future__ import annotations

from dataclasses import dataclass

from backend.core.error_report.reporter import ErrorReporter
from backend.core.logging.trace_logger import TraceConfig, TraceLogger
from backend.core.logging.send_run_logger import SendRunLogger
from backend.domains.sending.executor import SendExecutor


@dataclass(slots=True)
class ExecutionBundle:
    run_logger: SendRunLogger
    trace_logger: TraceLogger
    error_reporter: ErrorReporter
    executor: SendExecutor


def build_send_executor(
    *,
    driver,
    jobs,
    delay_ms: int,
    max_retry: int,
    retry_sleep_ms: int,
    report_writer=None,
    run_logger=None,
    is_stop_requested=None,
    status_cb=None,
    progress_cb=None,
    list_changed_cb=None,
    recover_driver_cb=None,
    stop_driver_cb=None,
    debug_log: bool = False,
    trace_log_prefix: str = "kakao_pc_driver",
) -> ExecutionBundle:
    """
    발송 실행에 필요한 run_logger / trace_logger / error_reporter / executor를 한 번에 구성.
    외부에서 run_logger를 주면 재사용하고, 없으면 새로 생성한다.
    """
    actual_run_logger = run_logger or SendRunLogger.new_run()

    trace_logger = TraceLogger(
        TraceConfig(
            debug_log=bool(debug_log),
            log_prefix=str(trace_log_prefix or "kakao_pc_driver"),
            run_id=actual_run_logger.run_id,
            file_enabled=True,
        )
    )

    error_reporter = ErrorReporter(run_logger=actual_run_logger)

    executor = SendExecutor(
        driver=driver,
        jobs=jobs,
        delay_ms=delay_ms,
        max_retry=max_retry,
        retry_sleep_ms=retry_sleep_ms,
        run_logger=actual_run_logger,
        report_writer=report_writer,
        error_reporter=error_reporter,
        trace_log_path=trace_logger.file_path_str(),
        is_stop_requested=is_stop_requested,
        status_cb=status_cb,
        progress_cb=progress_cb,
        list_changed_cb=list_changed_cb,
        recover_driver_cb=recover_driver_cb,
        stop_driver_cb=stop_driver_cb,
    )

    try:
        actual_run_logger.log_event(
            "EXECUTION_CONTEXT_READY",
            run_id=actual_run_logger.run_id,
            run_log_path=actual_run_logger.path_str(),
            trace_log_path=trace_logger.file_path_str(),
            jobs=len(list(jobs or [])),
            max_retry=int(max_retry),
            delay_ms=int(delay_ms),
            retry_sleep_ms=int(retry_sleep_ms),
        )
    except Exception:
        pass

    return ExecutionBundle(
        run_logger=actual_run_logger,
        trace_logger=trace_logger,
        error_reporter=error_reporter,
        executor=executor,
    )