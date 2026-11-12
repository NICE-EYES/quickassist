"""Общий HTTP-клиент для сторонних API (кроме Anthropic, у которого свой SDK).

TLS-проверка всегда включена (поведение httpx2 по умолчанию), тайм-ауты обязательны.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx2

from quickassist import __version__
from quickassist.services.errors import ServiceError

log = logging.getLogger(__name__)

USER_AGENT = f"QuickAssist/{__version__}"


def make_client(timeout: float, transport: httpx2.BaseTransport | None = None) -> httpx2.Client:
    return httpx2.Client(
        timeout=httpx2.Timeout(timeout, connect=min(10.0, timeout)),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        transport=transport,
    )


def request_json(
    client: httpx2.Client,
    method: str,
    url: str,
    service: str,
    **kwargs: Any,
) -> Any:
    """Выполняет запрос и возвращает JSON; сетевые ошибки превращает в ServiceError."""
    try:
        response = client.request(method, url, **kwargs)
    except httpx2.TimeoutException:
        raise ServiceError(f"{service}: превышено время ожидания ответа.") from None
    except httpx2.ConnectError:
        raise ServiceError(f"{service}: не удалось подключиться. Проверьте интернет и адрес сервиса.") from None
    except httpx2.RequestError as exc:
        raise ServiceError(f"{service}: сетевая ошибка ({type(exc).__name__}).") from None

    if response.status_code >= 400:
        log.info("%s returned HTTP %s", service, response.status_code)
        raise ServiceError(describe_status(service, response.status_code))
    try:
        return response.json()
    except ValueError:
        raise ServiceError(f"{service}: сервис вернул некорректный ответ.") from None


def describe_status(service: str, status: int) -> str:
    if status in (401, 403):
        return f"{service}: ключ API отклонён (HTTP {status}). Проверьте ключ в настройках."
    if status == 404:
        return f"{service}: адрес или модель не найдены (HTTP 404). Проверьте настройки."
    if status == 429:
        return f"{service}: слишком много запросов, повторите позже (HTTP 429)."
    if status == 456:
        return f"{service}: исчерпан лимит символов тарифа (HTTP 456)."
    if 500 <= status < 600:
        return f"{service}: ошибка на стороне сервиса (HTTP {status}). Повторите позже."
    return f"{service}: запрос отклонён (HTTP {status})."
