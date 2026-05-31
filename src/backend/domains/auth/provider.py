from __future__ import annotations

from typing import Protocol

from backend.domains.auth.models import AuthSession


class AuthProvider(Protocol):
    def login(self) -> AuthSession:
        ...
