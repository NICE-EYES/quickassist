"""Иконка приложения рисуется кодом — без бинарных файлов в репозитории."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2f6fed"))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        pen = QPen(QColor("white"), max(1.5, size * 0.1))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        r = size * 0.22
        c = QPointF(size * 0.44, size * 0.44)
        p.drawEllipse(c, r, r)
        p.drawLine(QPointF(size * 0.6, size * 0.6), QPointF(size * 0.78, size * 0.78))
        p.end()
        icon.addPixmap(pm)
    return icon
