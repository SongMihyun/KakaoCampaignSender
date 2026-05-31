from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.domains.auth.models import AuthSession


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str = ""


class AccessPolicy(Protocol):
    def evaluate(self, session: AuthSession) -> AccessDecision:
        ...


class DbAccessPolicy(Protocol):
    def evaluate(self, session: AuthSession) -> AccessDecision:
        """Future DB/server-backed policy placeholder."""
        ...
