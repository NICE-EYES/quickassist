"""Кроссплатформенная обёртка над получением выделенного текста."""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass
class SelectionResult:
    text: str | None
    reason: str = ""


SELECTION_HINTS = {
    "no_selection": "Выделение не найдено — введите или вставьте текст (Ctrl+V).",
    "terminal": "В терминале выделение не копируется автоматически (Ctrl+C прервал бы программу). Скопируйте текст вручную.",
    "clipboard_busy": "Буфер обмена занят другой программой — вставьте текст вручную.",
    "too_large": "Буфер обмена слишком велик для безопасного восстановления — выделение не захвачено.",
    "failed": "Не удалось получить выделение — вставьте текст вручную.",
    "unsupported": "Автозахват выделения поддерживается только в Windows.",
}


def capture_selection() -> SelectionResult:
    if sys.platform != "win32":
        return SelectionResult(None, "unsupported")
    try:
        from quickassist.platform import selection_win

        r = selection_win.capture_selection()
        return SelectionResult(r.text, r.reason)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("selection capture failed")
        return SelectionResult(None, "failed")
