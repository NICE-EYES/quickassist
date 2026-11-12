"""Захват выделенной области экрана: по полупрозрачному оверлею на каждый монитор.

Выделение делается в пределах одного монитора — так корректно учитывается разный
масштаб (DPI) мониторов. Esc или правая кнопка — отмена.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class _Overlay(QWidget):
    def __init__(self, owner: "RegionCapture", screen, pixmap: QPixmap):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._owner = owner
        self._pixmap = pixmap
        self._origin: QPoint | None = None
        self._rect = QRect()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if not self._rect.isNull():
            src = self._source_rect(self._rect)
            p.drawPixmap(self._rect, self._pixmap, src)
            p.setPen(QPen(QColor("#5b8cff"), 2))
            p.drawRect(self._rect.adjusted(0, 0, -1, -1))
            p.setPen(QColor("white"))
            p.drawText(self._rect.topLeft() + QPoint(4, -6), f"{src.width()}×{src.height()}")
        else:
            p.setPen(QColor("white"))
            p.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                       "Выделите область мышью · Esc — отмена")

    def _source_rect(self, r: QRect) -> QRect:
        sx = self._pixmap.width() / max(1, self.width())
        sy = self._pixmap.height() / max(1, self.height())
        return QRect(round(r.x() * sx), round(r.y() * sy), round(r.width() * sx), round(r.height() * sy))

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._owner.cancel()
            return
        self._origin = e.position().toPoint()
        self._rect = QRect(self._origin, self._origin)
        self.update()

    def mouseMoveEvent(self, e):
        if self._origin is not None:
            self._rect = QRect(self._origin, e.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._origin is None:
            return
        rect = self._rect.normalized()
        self._origin = None
        if rect.width() < 5 or rect.height() < 5:
            self._rect = QRect()
            self.update()
            return
        image = self._pixmap.copy(self._source_rect(rect)).toImage()
        self._owner.finish(image)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._owner.cancel()


class RegionCapture(QObject):
    captured = Signal(QImage)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._overlays: list[_Overlay] = []

    def start(self) -> None:
        self._close_all()
        for screen in QGuiApplication.screens():
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                continue
            overlay = _Overlay(self, screen, pixmap)
            self._overlays.append(overlay)
            overlay.showFullScreen()
        if not self._overlays:
            self.cancelled.emit()
            return
        self._overlays[0].activateWindow()

    def finish(self, image: QImage) -> None:
        self._close_all()
        self.captured.emit(image)

    def cancel(self) -> None:
        self._close_all()
        self.cancelled.emit()

    def _close_all(self) -> None:
        for o in self._overlays:
            o.close()
        self._overlays = []
