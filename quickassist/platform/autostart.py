"""Автозапуск при входе в Windows (HKCU\\...\\Run). Включается только по желанию пользователя."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from quickassist import APP_NAME

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def supported() -> bool:
    return sys.platform == "win32"


def launch_command() -> str:
    if getattr(sys, "frozen", False):  # собранный PyInstaller-exe
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = Path(__file__).resolve().parents[2] / "run.pyw"
    return f'"{exe}" "{script}"'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not supported():
        raise OSError("Автозапуск поддерживается только в Windows")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            log.info("autostart enabled")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            log.info("autostart disabled")
