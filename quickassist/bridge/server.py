"""Локальный мост «расширение браузера → приложение».

Безопасность:
* слушаем только 127.0.0.1 (не 0.0.0.0) — из локальной сети недоступно;
* каждый запрос должен нести `Authorization: Bearer <токен>` (токен в системном
  хранилище, вводится в настройках расширения при сопряжении);
* заголовок Host обязан быть 127.0.0.1:<порт>/localhost:<порт> — защита от DNS rebinding;
* если есть заголовок Origin, он обязан быть chrome-extension://… (обычные сайты
  отсекаются), а при заданном ID расширения — совпадать с ним точно;
* CORS-заголовки не выдаются, preflight (OPTIONS) отклоняется;
* размер тела ограничен, JSON проверяется по схеме;
* содержимое запросов не логируется.
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Mapping

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 2_000_000
MAX_TEXT_CHARS = 200_000
MAX_URL_CHARS = 4_096
MAX_TITLE_CHARS = 1_000
KINDS = ("selection", "page", "tab")


@dataclass
class BrowserContext:
    kind: str           # selection | page | tab
    url: str
    title: str
    text: str = ""
    truncated: bool = False


class RequestRejected(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def check_headers(headers: Mapping[str, str], token: str, port: int, allowed_extension_id: str = "") -> None:
    """Проверка заголовков. Бросает RequestRejected при нарушении."""
    host = (headers.get("Host") or "").strip().lower()
    if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
        raise RequestRejected(421, "bad host")

    origin = (headers.get("Origin") or "").strip().lower()
    if origin:
        if not origin.startswith("chrome-extension://"):
            raise RequestRejected(403, "origin not allowed")
        if allowed_extension_id and origin != f"chrome-extension://{allowed_extension_id}":
            raise RequestRejected(403, "extension id not allowed")
    elif allowed_extension_id:
        raise RequestRejected(403, "origin required")

    auth = headers.get("Authorization") or ""
    if not token or not auth.startswith("Bearer "):
        raise RequestRejected(401, "missing token")
    if not hmac.compare_digest(auth[len("Bearer "):].strip().encode(), token.encode()):
        raise RequestRejected(401, "bad token")


def parse_context(body: bytes) -> BrowserContext:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise RequestRejected(400, "invalid json") from None
    if not isinstance(data, dict):
        raise RequestRejected(400, "object expected")
    if data.get("version") != 1:
        raise RequestRejected(400, "unsupported version")
    kind = data.get("kind")
    if kind not in KINDS:
        raise RequestRejected(400, "bad kind")
    url, title, text = data.get("url", ""), data.get("title", ""), data.get("text", "")
    if not all(isinstance(v, str) for v in (url, title, text)):
        raise RequestRejected(400, "string fields expected")
    if len(url) > MAX_URL_CHARS or len(title) > MAX_TITLE_CHARS:
        raise RequestRejected(413, "field too long")
    truncated = bool(data.get("truncated", False))
    if len(text) > MAX_TEXT_CHARS:
        text, truncated = text[:MAX_TEXT_CHARS], True
    if kind in ("selection", "page") and not text.strip():
        raise RequestRejected(422, "empty text")
    return BrowserContext(kind=kind, url=url, title=title.strip(), text=text, truncated=truncated)


class BridgeServer(QObject):
    """HTTP-сервер в фоновом потоке; принятые данные доставляются сигналом в главный поток."""

    contextReceived = Signal(object)  # BrowserContext
    statusChanged = Signal(str)

    def __init__(self, token_getter: Callable[[], str], parent: QObject | None = None):
        super().__init__(parent)
        self._token_getter = token_getter
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0
        self.allowed_extension_id = ""
        self.status = "Мост выключен"

    def start(self, port: int, allowed_extension_id: str = "") -> bool:
        self.stop()
        self.port = port
        self.allowed_extension_id = allowed_extension_id
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "QuickAssist"
            sys_version = ""

            def log_message(self, fmt, *args):  # не пишем адреса/тела запросов
                return

            def _reply(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self._reply(403, {"ok": False, "error": "forbidden"})

            def do_GET(self):
                self._reply(405, {"ok": False, "error": "method not allowed"})

            def do_POST(self):
                try:
                    check_headers(self.headers, bridge._token_getter(), bridge.port, bridge.allowed_extension_id)
                    if self.path == "/v1/ping":
                        self._reply(200, {"ok": True, "app": "QuickAssist"})
                        return
                    if self.path != "/v1/context":
                        raise RequestRejected(404, "not found")
                    ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    if ctype != "application/json":
                        raise RequestRejected(415, "json required")
                    try:
                        length = int(self.headers.get("Content-Length") or "0")
                    except ValueError:
                        raise RequestRejected(411, "length required") from None
                    if length <= 0 or length > MAX_BODY_BYTES:
                        raise RequestRejected(413, "body too large")
                    ctx = parse_context(self.rfile.read(length))
                except RequestRejected as exc:
                    log.info("bridge request rejected: %s (%s)", exc.status, exc.reason)
                    self._reply(exc.status, {"ok": False, "error": exc.reason})
                    return
                log.info("bridge context received: kind=%s", ctx.kind)
                bridge.contextReceived.emit(ctx)
                self._reply(200, {"ok": True})

        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            self._set_status(f"Порт {port} занят или недоступен ({exc.strerror or type(exc).__name__}). Выберите другой порт.")
            log.warning("bridge failed to bind port %s", port)
            return False
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="bridge", daemon=True)
        self._thread.start()
        self._set_status(f"Мост работает: 127.0.0.1:{port}")
        log.info("bridge listening on 127.0.0.1:%s", port)
        return True

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            self._set_status("Мост выключен")

    def _set_status(self, text: str) -> None:
        self.status = text
        self.statusChanged.emit(text)
