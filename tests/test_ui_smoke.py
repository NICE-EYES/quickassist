"""Smoke-тест интерфейса в offscreen-режиме: окна создаются, режимы переключаются, поиск строит URL."""
from PySide6.QtGui import QDesktopServices, QImage, Qt
from PySide6.QtWidgets import QApplication

from quickassist.bridge.server import BrowserContext
from quickassist.config import Settings, SettingsStore
from quickassist.context import AppContext
from quickassist.secrets_store import SecretStore
from quickassist.services.hub import ServiceHub
from quickassist.tasks import TaskRunner
from tests.test_services import DictKeyring


def make_ctx(tmp_path):
    app = QApplication.instance() or QApplication([])
    s = Settings()
    secrets = SecretStore("T", backend=DictKeyring())
    return app, AppContext(s, SettingsStore(tmp_path / "s.json"), secrets, ServiceHub(s, secrets), TaskRunner())


def test_panel_and_settings(tmp_path, monkeypatch):
    from quickassist.ui.panel import Panel
    from quickassist.ui.settings_dialog import SettingsDialog
    from quickassist.ui.theme import apply_theme

    app, ctx = make_ctx(tmp_path)
    apply_theme(app, "dark")
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)

    panel = Panel(ctx)
    panel.show_panel("hello world")
    assert panel.query.toPlainText() == "hello world"
    for mode in ("search", "image", "ask", "translate"):
        panel.set_mode(mode)
    # перевод без ключа → открывается браузер
    panel.action_translate()
    assert opened and opened[-1].startswith("https://translate.google.com/")
    panel.set_mode("search")
    panel.action_search()
    assert "google.com/search?q=hello" in opened[-1]
    assert not panel._web_answer_btn.isEnabled()   # ИИ не настроен
    # изображение
    img = QImage(40, 20, QImage.Format_ARGB32)
    img.fill(Qt.red)
    panel.set_image(img)
    assert panel._mode == "image" and all(b.isEnabled() for b in panel._img_actions)
    from quickassist.ui.panel import bgra_bytes, png_bytes
    data, w, h = bgra_bytes(img, 4096)
    assert len(data) == w * h * 4 and png_bytes(img, 10).startswith(b"\x89PNG")
    # контекст браузера
    panel.set_browser_context(BrowserContext("page", "https://ex.com", "Пример", "Текст страницы"))
    assert panel._page_text() == "Текст страницы"
    panel.clear_context()
    assert panel._page_text() is None
    # ошибка «не настроено» при вопросе к ИИ
    panel.set_mode("ask")
    panel.query.setPlainText("вопрос")
    panel.action_ask()
    assert "Не настроено" in panel._status.text()

    dlg = SettingsDialog(ctx, "Мост выключен")
    got = []
    dlg.applyRequested.connect(lambda s, sec: got.append((s, sec)))
    dlg.hotkey.setCurrentText("ctrl+alt+q")
    dlg.deepl_key.edit.setText("abc:fx")
    dlg._on_save()
    assert got and got[0][0].hotkey == "Ctrl+Alt+Q" and got[0][1] == {"deepl_api_key": "abc:fx"}
    assert SettingsStore(tmp_path / "s.json").load().last_mode == "ask"
