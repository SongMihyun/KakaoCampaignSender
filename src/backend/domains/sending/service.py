# FILE: src/backend/domains/sending/service.py
from __future__ import annotations


class SendingService:
    """
    Sending 도메인 orchestration 계층.
    - SendPage가 기대하는 API 이름으로 감싸고
    - 실제 send_lists_service / job_builder / worker_factory에 위임한다.
    """

    def __init__(
        self,
        *,
        job_builder,
        worker_factory=None,
        send_lists_service=None,
        groups_repo=None,
        contacts_store=None,
        campaigns_service=None,
    ) -> None:
        self.job_builder = job_builder
        self.worker_factory = worker_factory

        self.send_lists_service = send_lists_service or getattr(job_builder, "send_lists_service", None)
        self.groups_repo = groups_repo or getattr(job_builder, "groups_repo", None)
        self.contacts_store = contacts_store or getattr(job_builder, "contacts_store", None)
        self.campaigns_service = campaigns_service or getattr(job_builder, "campaigns_service", None)

    # -----------------------------
    # source 조회
    # -----------------------------
    def list_groups(self):
        if self.groups_repo is None:
            return []
        try:
            return self.groups_repo.list_groups()
        except Exception:
            return []

    def list_send_lists(self):
        if self.send_lists_service is None:
            return []
        try:
            return self.send_lists_service.list_send_lists()
        except Exception:
            return []

    # -----------------------------
    # 발송리스트 CRUD
    # -----------------------------
    def create_or_replace_send_list(self, dto) -> tuple[int, int]:
        """
        SendPage 호환용.
        반환:
        - send_list_id
        - target_count(현재 기준 대상자 수)
        """
        if self.send_lists_service is None:
            raise RuntimeError("send_lists_service가 설정되지 않았습니다.")

        send_list_id = int(self.send_lists_service.create_or_replace(dto))

        rows, _title = self.build_preview_rows(send_list_id)
        target_count = len(rows)
        return send_list_id, target_count

    def delete_send_list(self, send_list_id: int) -> None:
        if self.send_lists_service is None:
            raise RuntimeError("send_lists_service가 설정되지 않았습니다.")
        self.send_lists_service.delete_send_list(int(send_list_id))

    def update_send_list_orders(self, ordered_ids: list[int]) -> None:
        if self.send_lists_service is None:
            raise RuntimeError("send_lists_service가 설정되지 않았습니다.")
        self.send_lists_service.update_orders([int(x) for x in ordered_ids or []])

    # -----------------------------
    # preview
    # -----------------------------
    def build_preview_rows(self, send_list_id: int) -> tuple[list[dict], str]:
        if self.send_lists_service is None:
            return [], ""

        meta = self.send_lists_service.get_meta(int(send_list_id))
        if not meta:
            return [], ""

        target_mode = str(getattr(meta, "target_mode", "") or "")
        group_id = getattr(meta, "group_id", None)

        from backend.domains.sending.resolver import (
            resolve_contacts_for_send_list_meta,
            build_recipients_and_snapshot,
        )

        contacts_mem = resolve_contacts_for_send_list_meta(
            contacts_store=self.contacts_store,
            groups_repo=self.groups_repo,
            target_mode=target_mode,
            group_id=group_id,
        )
        recipients, _recipients_snapshot = build_recipients_and_snapshot(contacts_mem)

        rows: list[dict] = []
        for idx, r in enumerate(recipients, start=1):
            rows.append(
                {
                    "no": idx,
                    "contact_id": int(getattr(r, "contact_id", 0) or 0),
                    "emp_id": str(getattr(r, "emp_id", "") or ""),
                    "name": str(getattr(r, "name", "") or ""),
                    "phone": str(getattr(r, "phone", "") or ""),
                    "agency": str(getattr(r, "agency", "") or ""),
                    "branch": str(getattr(r, "branch", "") or ""),
                }
            )

        group_name = str(getattr(meta, "group_name", "") or "")
        campaign_name = str(getattr(meta, "campaign_name", "") or "")
        title = f"{group_name} + {campaign_name}".strip(" +")
        return rows, title

    # -----------------------------
    # job build
    # -----------------------------
    def build_jobs(self, send_list_rows: list[dict]):
        return self.job_builder.build_all_jobs(send_list_rows)

    # -----------------------------
    # worker 생성
    # -----------------------------
    def create_worker(
        self,
        *,
        driver,
        jobs,
        parent=None,
        delay_ms: int = 500,
        max_retry: int = 2,
        retry_sleep_ms: int = 250,
        run_logger=None,
        report_writer=None,
    ):
        factory = self.worker_factory

        if factory is None:
            from backend.domains.sending.worker import MultiSendWorker
            factory = MultiSendWorker

        if hasattr(factory, "create") and callable(factory.create):
            return factory.create(
                driver=driver,
                jobs=jobs,
                parent=parent,
                delay_ms=delay_ms,
                max_retry=max_retry,
                retry_sleep_ms=retry_sleep_ms,
                run_logger=run_logger,
                report_writer=report_writer,
            )

        return factory(
            driver=driver,
            jobs=jobs,
            parent=parent,
            delay_ms=delay_ms,
            max_retry=max_retry,
            retry_sleep_ms=retry_sleep_ms,
            run_logger=run_logger,
            report_writer=report_writer,
        )