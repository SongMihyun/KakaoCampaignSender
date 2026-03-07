from __future__ import annotations

from backend.domains.sending.job_builder import SendJobBuilder
from backend.domains.sending.worker import MultiSendWorker


class SendingService:
    def __init__(self, *, job_builder) -> None:
        self.job_builder = job_builder

    def build_jobs(self, send_list_rows: list[dict]):
        return self.job_builder.build_all_jobs(send_list_rows)

    def create_worker(self, **kwargs):
        return MultiSendWorker(**kwargs)