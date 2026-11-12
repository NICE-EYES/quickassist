"""Диагностические логи.

Правило проекта: в логи пишутся только события и типы ошибок. Выделенный текст,
содержимое страниц, изображения, запросы пользователя и секреты НЕ логируются.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(directory: Path, debug: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            directory / "quickassist.log", maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    # Сторонние HTTP-библиотеки на уровне DEBUG могут печатать URL с текстом запроса.
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
