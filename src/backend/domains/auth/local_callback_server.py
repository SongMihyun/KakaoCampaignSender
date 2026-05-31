from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class CallbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    error_description: str | None = None


class LocalCallbackServer:
    def __init__(self, redirect_uri: str) -> None:
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname != "localhost":
            raise ValueError("Redirect URI는 http://localhost 주소여야 합니다.")
        if not parsed.port:
            raise ValueError("Redirect URI에는 localhost 포트가 포함되어야 합니다.")
        self.redirect_uri = redirect_uri
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path or "/"
        self._event = threading.Event()
        self._result: CallbackResult | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != outer.path:
                    self.send_response(404)
                    self.end_headers()
                    return
                query = parse_qs(parsed.query)
                outer._result = CallbackResult(
                    code=_first(query.get("code")),
                    state=_first(query.get("state")),
                    error=_first(query.get("error")),
                    error_description=_first(query.get("error_description")),
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<!doctype html><meta charset='utf-8'>"
                    "<title>카센더 로그인</title>"
                    "<body style='font-family:system-ui,sans-serif;padding:40px'>"
                    "<h2>카센더 로그인 처리가 완료되었습니다.</h2>"
                    "<p>이 창을 닫고 카센더로 돌아가 주세요.</p>"
                    "</body>".encode("utf-8")
                )
                outer._event.set()

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def wait(self, timeout_sec: int) -> CallbackResult:
        if not self._event.wait(timeout_sec):
            raise TimeoutError("카카오 로그인 응답 시간이 초과되었습니다.")
        return self._result or CallbackResult(error="empty_callback")

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def _first(values: list[str] | None) -> str | None:
    if not values:
        return None
    return values[0]
