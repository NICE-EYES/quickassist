"""Глобальные горячие клавиши.

Windows: WinAPI RegisterHotKey — не требует прав администратора и низкоуровневых
хуков клавиатуры; если сочетание занято другой программой, регистрация честно
возвращает ошибку, и пользователь может выбрать другое.
Другие ОС: заглушка (окно открывается из трея). Интерфейс общий — HotkeyBackend.
"""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "ctl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "meta": MOD_WIN, "super": MOD_WIN,
}
_MOD_ORDER = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))

_NAMED_KEYS = {
    "space": (0x20, "Space"), "enter": (0x0D, "Enter"), "return": (0x0D, "Enter"),
    "tab": (0x09, "Tab"), "backspace": (0x08, "Backspace"), "insert": (0x2D, "Insert"), "ins": (0x2D, "Insert"),
    "delete": (0x2E, "Delete"), "del": (0x2E, "Delete"), "home": (0x24, "Home"), "end": (0x23, "End"),
    "pageup": (0x21, "PgUp"), "pgup": (0x21, "PgUp"), "pagedown": (0x22, "PgDown"), "pgdown": (0x22, "PgDown"),
    "left": (0x25, "Left"), "up": (0x26, "Up"), "right": (0x27, "Right"), "down": (0x28, "Down"),
    "`": (0xC0, "`"), "~": (0xC0, "`"), "-": (0xBD, "-"), "=": (0xBB, "="), "[": (0xDB, "["), "]": (0xDD, "]"),
    ";": (0xBA, ";"), "'": (0xDE, "'"), ",": (0xBC, ","), ".": (0xBE, "."), "/": (0xBF, "/"), "\\": (0xDC, "\\"),
    "pause": (0x13, "Pause"), "scrolllock": (0x91, "ScrollLock"),
}


class HotkeyParseError(ValueError):
    pass


def parse_hotkey(text: str) -> tuple[int, int, str]:
    """'ctrl + alt + q' → (модификаторы, виртуальный код клавиши, 'Ctrl+Alt+Q')."""
    raw = (text or "").strip()
    if not raw:
        raise HotkeyParseError("Пустое сочетание.")
    # '+' как клавиша не поддерживается; разбиваем по '+'
    parts = [p.strip() for p in raw.split("+")]
    if any(not p for p in parts):
        raise HotkeyParseError("Неверный формат. Пример: Ctrl+Alt+Space")
    *mods_raw, key_raw = parts
    mods = 0
    for m in mods_raw:
        flag = _MODIFIERS.get(m.lower())
        if flag is None:
            raise HotkeyParseError(f"Неизвестный модификатор: {m}")
        mods |= flag
    k = key_raw.lower()
    if k in _MODIFIERS:
        raise HotkeyParseError("Сочетание должно заканчиваться обычной клавишей.")
    if len(k) == 1 and ("a" <= k <= "z" or "0" <= k <= "9"):
        vk, key_name = ord(k.upper()), k.upper()
    elif k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        vk, key_name = 0x70 + int(k[1:]) - 1, f"F{int(k[1:])}"
    elif k in _NAMED_KEYS:
        vk, key_name = _NAMED_KEYS[k]
    else:
        raise HotkeyParseError(f"Неподдерживаемая клавиша: {key_raw}")
    if mods == 0 and not key_name.startswith("F"):
        raise HotkeyParseError("Добавьте модификатор (Ctrl, Alt, Shift или Win).")
    if mods == MOD_SHIFT and not key_name.startswith("F"):
        raise HotkeyParseError("Одного Shift недостаточно — это помешает набору текста.")
    canonical = "+".join([name for flag, name in _MOD_ORDER if mods & flag] + [key_name])
    return mods, vk, canonical


class HotkeyBackend(QObject):
    activated = Signal()
    supported = False

    def register(self, text: str) -> str:
        """Регистрирует сочетание, возвращает каноническую запись. Бросает HotkeyError."""
        raise HotkeyError("Глобальные горячие клавиши в этой ОС пока не поддерживаются — используйте значок в трее.")

    def unregister(self) -> None:
        pass

    @property
    def current(self) -> str:
        return ""


class HotkeyError(Exception):
    pass


class _WinFilter(QAbstractNativeEventFilter):
    def __init__(self, backend: "WindowsHotkey"):
        super().__init__()
        self._backend = backend

    def nativeEventFilter(self, event_type, message):
        try:
            etype = bytes(event_type.data()) if hasattr(event_type, "data") else bytes(event_type)
        except Exception:
            etype = b""
        if etype == b"windows_generic_MSG":
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._backend.HOTKEY_ID:
                self._backend.activated.emit()
                return True, 0
        return False, 0


class WindowsHotkey(HotkeyBackend):
    supported = True
    HOTKEY_ID = 0xB001

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        import ctypes
        from ctypes import wintypes

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._ctypes = ctypes
        self._filter = _WinFilter(self)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._registered = ""

    @property
    def current(self) -> str:
        return self._registered

    def register(self, text: str) -> str:
        try:
            mods, vk, canonical = parse_hotkey(text)
        except HotkeyParseError as exc:
            raise HotkeyError(str(exc)) from None
        self.unregister()
        # hwnd=NULL: WM_HOTKEY приходит в очередь главного потока (там работает цикл Qt).
        if not self._user32.RegisterHotKey(None, self.HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            err = self._ctypes.get_last_error()
            log.warning("RegisterHotKey failed for %s (winerror=%s)", canonical, err)
            if err == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                raise HotkeyError(f"Сочетание {canonical} уже занято другой программой. Выберите другое.")
            raise HotkeyError(f"Не удалось зарегистрировать {canonical} (код {err}).")
        self._registered = canonical
        log.info("hotkey registered: %s", canonical)
        return canonical

    def unregister(self) -> None:
        if self._registered:
            self._user32.UnregisterHotKey(None, self.HOTKEY_ID)
            log.info("hotkey unregistered")
            self._registered = ""


def create_hotkey_backend(parent: QObject | None = None) -> HotkeyBackend:
    if sys.platform == "win32":
        return WindowsHotkey(parent)
    return HotkeyBackend(parent)
