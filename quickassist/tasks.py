"""Запуск блокирующих операций (сеть, OCR, буфер обмена) в пуле потоков Qt.

Результат возвращается в главный поток через сигнал, интерфейс не блокируется.
"""
from __future__ import annotations

import itertools
import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)


class _Runnable(QRunnable):
    def __init__(self, runner: "TaskRunner", task_id: int, fn: Callable[[], Any]):
        super().__init__()
        self._runner = runner
        self._task_id = task_id
        self._fn = fn
        self.setAutoDelete(True)

    def run(self) -> None:  # выполняется в рабочем потоке
        try:
            result = self._fn()
        except BaseException as exc:  # noqa: B902 - передаём любую ошибку в UI
            self._runner._done.emit(self._task_id, None, exc)
        else:
            self._runner._done.emit(self._task_id, result, None)


class TaskRunner(QObject):
    _done = Signal(int, object, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._ids = itertools.count(1)
        self._callbacks: dict[int, tuple[Callable, Callable]] = {}
        self._pool = QThreadPool.globalInstance()
        self._done.connect(self._on_done)

    def run(self, fn: Callable[[], Any], on_ok: Callable[[Any], None], on_err: Callable[[BaseException], None]) -> int:
        task_id = next(self._ids)
        self._callbacks[task_id] = (on_ok, on_err)
        self._pool.start(_Runnable(self, task_id, fn))
        return task_id

    def forget(self, task_id: int) -> None:
        """Отменить доставку результата (сама операция завершится по тайм-ауту)."""
        self._callbacks.pop(task_id, None)

    def _on_done(self, task_id: int, result: Any, error: BaseException | None) -> None:
        callbacks = self._callbacks.pop(task_id, None)
        if callbacks is None:
            return
        on_ok, on_err = callbacks
        try:
            if error is None:
                on_ok(result)
            else:
                on_err(error)
        except Exception:
            log.exception("task callback failed")
