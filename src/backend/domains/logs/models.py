from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class SendLog:
    id: int
    ts: str
    campaign_id: int
    batch_id: str
    channel: str
    recipient: str
    status: str
    reason: str
    attempt: int
    message_len: int
    image_count: int