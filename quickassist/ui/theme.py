"""Светлая и тёмная темы (Fusion + палитра + немного QSS). Без анимаций."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#f7f7f9", "panel": "#ffffff", "text": "#1d1d1f", "muted": "#6b6b73", "border": "#d7d7de",
    "accent": "#2f6fed", "accent_text": "#ffffff", "input": "#ffffff", "error": "#c62828", "ok": "#2e7d32",
    "chip": "#eef2fd",
}
DARK = {
    "bg": "#1e1f22", "panel": "#26272b", "text": "#e9e9ec", "muted": "#9a9aa3", "border": "#3a3b41",
    "accent": "#5b8cff", "accent_text": "#0d0e10", "input": "#1b1c1f", "error": "#ef6b6b", "ok": "#6fcf73",
    "chip": "#2d3446",
}


def is_dark(theme: str) -> bool:
    if theme == "dark":
        return True
    if theme == "light":
        return False
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return False


def colors(theme: str) -> dict:
    return DARK if is_dark(theme) else LIGHT


def apply_theme(app: QApplication, theme: str) -> dict:
    c = colors(theme)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["input"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["panel"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["panel"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["accent_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.Link, QColor(c["accent"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(f"""
        #PanelFrame {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 12px; }}
        #PanelFrame QPlainTextEdit#Query {{ font-size: 15px; border: 1px solid {c['border']};
            border-radius: 8px; padding: 6px; background: {c['input']}; }}
        #PanelFrame QPlainTextEdit#Query:focus {{ border: 1px solid {c['accent']}; }}
        QPushButton#Mode {{ border: 1px solid transparent; border-radius: 7px; padding: 5px 12px; }}
        QPushButton#Mode:checked {{ background: {c['accent']}; color: {c['accent_text']}; }}
        QPushButton#Mode:hover:!checked {{ border-color: {c['border']}; }}
        QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_text']}; border-radius: 7px;
            padding: 5px 14px; border: none; }}
        QPushButton#Primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}
        QLabel#Muted {{ color: {c['muted']}; }}
        QLabel#Status[kind="error"] {{ color: {c['error']}; }}
        QLabel#Status[kind="ok"] {{ color: {c['ok']}; }}
        QLabel#Status[kind="info"] {{ color: {c['muted']}; }}
        QFrame#Context {{ background: {c['chip']}; border-radius: 8px; }}
        QTextBrowser#Result {{ border: 1px solid {c['border']}; border-radius: 8px; padding: 6px;
            background: {c['input']}; font-size: 14px; }}
        QLabel#Preview {{ border: 1px dashed {c['border']}; border-radius: 8px; }}
    """)
    return c
