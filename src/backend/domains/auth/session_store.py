from __future__ import annotations

import json
from pathlib import Path

from app.paths import user_data_dir
from backend.domains.auth.crypto import protect_bytes, unprotect_bytes
from backend.domains.auth.models import AuthSession


class SessionStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (user_data_dir() / "auth_session.dat")

    def load(self) -> AuthSession | None:
        if not self.path.exists():
            return None
        try:
            protected = self.path.read_text(encoding="utf-8")
            raw = unprotect_bytes(protected)
            data = json.loads(raw.decode("utf-8"))
            return AuthSession.from_dict(data)
        except Exception:
            return None

    def save(self, session: AuthSession) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(session.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.path.write_text(protect_bytes(raw), encoding="utf-8")

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def clear_session(self) -> None:
        self.clear()

    def delete_session(self) -> None:
        self.clear()
