from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SendRunResult:
    list_done: int
    success: int
    fail: int
    stopped: bool = False