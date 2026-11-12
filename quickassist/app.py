"""Точка входа и связка модулей: трей, горячая клавиша, панель, настройки, мост браузера."""
from __future__ import annotations

import getpass
import logging
import sys

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from quickassist import APP_NAME, APP_TITLE, __version__
from quickassist.bridge.server import BridgeServer
from quickassist.config import FALLBACK_HOTKEY, SettingsStore, log_dir
from quickassist.context import AppContext
from quickassist.logging_setup import setup_logging
from quickassist.platform import autostart
from quickassist.platform.hotkey import HotkeyError, create_hotkey_backend
from quickassist.platform.selection import SELECTION_HINTS, capture_selection
from quickassist.secrets_store import SecretStore
from quickassist.services.hub import ServiceHub
from quickassist.tasks import TaskRunner
from quickassist.ui.icons import make_app_icon
from quickassist.ui.panel import Panel
from quickassist.ui.settings_dialog import SettingsDialog
from quickassist.ui.theme import apply_theme

log = logging.getLogger(__name__)


class SingleInstance(QObject):
    """Второй запуск не создаёт копию, а просит первую показать панель."""

    def __init__(self, on_show, parent=None):
        super().__init__(parent)
        self.name = f"{APP_NAME}-{getpass.getuser()}"
        self._on_show = on_show
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)  # устаревший сокет после сбоя (не Windows)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(self.name):
            log.warning("single-instance server failed to listen")
        return True

    def _on_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return

        def read():
            if conn.readAll().data().startswith(b"show"):
                self._on_show()
            conn.disconnectFromServer()

        conn.readyRead.connect(read)


class AppController(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        store = SettingsStore()
        settings = store.load()
        secrets = SecretStore()
        self.ctx = AppContext(settings, store, secrets, ServiceHub(settings, secrets), TaskRunner(self))
        self._capturing = False
        self._settings_dialog: SettingsDialog | None = None

        apply_theme(app, settings.theme)
        self.icon = make_app_icon()
        app.setWindowIcon(self.icon)

        self.panel = Panel(self.ctx)
        self.panel.setWindowIcon(self.icon)
        self.panel.settingsRequested.connect(self.open_settings)

        self.hotkey = create_hotkey_backend(self)
        self.hotkey.activated.connect(self.on_hotkey)

        self.bridge = BridgeServer(self.ctx.secrets.bridge_token, self)
        self.bridge.contextReceived.connect(self.panel.set_browser_context)
        self.bridge.statusChanged.connect(self._on_bridge_status)

        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip(APP_TITLE)
        menu = QMenu()
        for text, slot in (("Открыть", self.open_panel), ("Настройки", self.open_settings)):
            act = QAction(text, menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        menu.addSeparator()
        quit_act = QAction("Выход", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    # ------------------------------------------------------------ запуск
    def start(self) -> None:
        self.tray.show()
        hotkey_msg = self._register_initial_hotkey()
        if self.ctx.settings.bridge_enabled:
            self.bridge.start(self.ctx.settings.bridge_port, self.ctx.settings.bridge_allowed_extension_id)
        # Синхронизировать флаг автозапуска с реестром (пользователь мог удалить запись вручную).
        if autostart.supported() and autostart.is_enabled() != self.ctx.settings.autostart:
            from dataclasses import replace
            self.ctx.save_settings(replace(self.ctx.settings, autostart=autostart.is_enabled()))
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(APP_TITLE, hotkey_msg, QSystemTrayIcon.Information, 4000)
        else:
            self.open_panel()
        log.info("QuickAssist %s started", __version__)

    def _register_initial_hotkey(self) -> str:
        wanted = self.ctx.settings.hotkey
        if not self.hotkey.supported:
            return "Глобальные клавиши в этой ОС не поддерживаются — откройте панель из трея."
        try:
            key = self.hotkey.register(wanted)
            return f"Работает в фоне. Вызов: {key}"
        except HotkeyError as exc:
            if wanted != FALLBACK_HOTKEY:
                try:
                    key = self.hotkey.register(FALLBACK_HOTKEY)
                    return f"{exc} Временно используется {key}; изменить: Настройки → Общие."
                except HotkeyError:
                    pass
            return f"{exc} Откройте панель из трея и выберите другое сочетание в настройках."

    # ------------------------------------------------------------ вызов панели
    def on_hotkey(self) -> None:
        if self._capturing:
            return
        if self.panel.isVisible() and self.panel.isActiveWindow():
            self.panel.hide()
            return
        if self.ctx.settings.capture_selection and sys.platform == "win32":
            self._capturing = True

            def ok(result):
                self._capturing = False
                hint = SELECTION_HINTS.get(result.reason) if result.reason not in ("ok", "no_selection", "own_window") else None
                self.panel.show_panel(result.text, hint)

            def err(_exc):
                self._capturing = False
                self.panel.show_panel(None, SELECTION_HINTS["failed"])

            self.ctx.tasks.run(capture_selection, ok, err)
        else:
            self.panel.show_panel(None)

    def open_panel(self) -> None:
        self.panel.show_panel(None)

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.panel.isVisible():
                self.panel.hide()
            else:
                self.open_panel()

    # ------------------------------------------------------------ настройки
    def open_settings(self) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dlg = SettingsDialog(self.ctx, self.bridge.status)
        dlg.setWindowIcon(self.icon)
        dlg.applyRequested.connect(self._apply_settings)
        dlg.finished.connect(self._on_settings_closed)
        self._settings_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_settings_closed(self, _code) -> None:
        self._settings_dialog = None
        self.panel.refresh_availability()

    def _apply_settings(self, new, secrets: dict) -> None:
        dlg = self._settings_dialog
        old = self.ctx.settings
        if self.hotkey.supported and new.hotkey != self.hotkey.current:
            try:
                self.hotkey.register(new.hotkey)
            except HotkeyError as exc:
                if self.hotkey.current != old.hotkey:
                    try:
                        self.hotkey.register(old.hotkey)
                    except HotkeyError:
                        pass
                if dlg:
                    dlg.show_error(str(exc))
                return
        if autostart.supported() and new.autostart != autostart.is_enabled():
            try:
                autostart.set_enabled(new.autostart)
            except OSError as exc:
                if dlg:
                    dlg.show_error(f"Не удалось изменить автозапуск: {exc}")
                return
        for name, value in secrets.items():
            self.ctx.secrets.set(name, value)
        self.ctx.save_settings(new)
        apply_theme(self.app, new.theme)
        bridge_changed = (new.bridge_enabled, new.bridge_port, new.bridge_allowed_extension_id) != (
            old.bridge_enabled, old.bridge_port, old.bridge_allowed_extension_id)
        if bridge_changed or (new.bridge_enabled and self.bridge.port == 0):
            self.bridge.stop()
            if new.bridge_enabled and not self.bridge.start(new.bridge_port, new.bridge_allowed_extension_id):
                QMessageBox.warning(dlg, "Мост браузера", self.bridge.status)
        self.panel.refresh_availability()
        log.info("settings saved")
        if dlg:
            dlg.accept()

    def _on_bridge_status(self, text: str) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.set_bridge_status(text)

    # ------------------------------------------------------------ выход
    def quit(self) -> None:
        log.info("quitting")
        self.bridge.stop()
        self.hotkey.unregister()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    setup_logging(log_dir(), debug="--debug" in sys.argv)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)

    holder: dict = {}
    single = SingleInstance(lambda: holder["c"].open_panel() if "c" in holder else None)
    if not single.acquire():
        log.info("another instance is running; asked it to show the panel")
        return 0
    controller = AppController(app)
    holder["c"] = controller
    controller.start()
    return app.exec()
