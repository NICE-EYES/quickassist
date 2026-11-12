"""Получение выделенного текста из активного окна Windows (любое приложение, включая браузер).

Как работает:
1. Ждём, пока пользователь отпустит модификаторы горячей клавиши (иначе Alt+Ctrl+C).
2. Сохраняем содержимое буфера обмена (все форматы, которые можно скопировать как память).
3. Посылаем активному окну Ctrl+C и ждём изменения номера последовательности буфера.
4. Читаем текст и восстанавливаем прежнее содержимое буфера.

Ограничения (описаны и в README):
* Форматы-дескрипторы GDI (CF_BITMAP, метафайлы и т.п.) не копируются; Windows обычно
  синтезирует CF_BITMAP из CF_DIB, поэтому картинки, как правило, восстанавливаются.
* Журнал буфера обмена Windows (Win+V) и сторонние менеджеры буфера могут увидеть
  временную копию выделения — запретить это приложению-источнику мы не можем.
* Если буфер больше лимита, захват пропускается, чтобы не потерять данные.
* В терминалах Ctrl+C прерывает процесс, поэтому окна консолей пропускаются.
* Некоторые программы при пустом выделении копируют целую строку (например, VS Code).
"""
from __future__ import annotations

import ctypes
import logging
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL, VK_C = 0x11, 0x43
VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x12, 0x5B, 0x5C
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

MAX_SAVED_BYTES = 64 * 1024 * 1024
# Дескрипторы, которые нельзя скопировать как блок памяти (GDI-объекты, owner-display и т.п.)
_NON_MEMORY_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}

TERMINAL_CLASSES = {
    "consolewindowclass", "cascadia_hosting_window_class", "mintty", "putty", "virtualconsoleclass",
    "kitty", "pseudoconsolewindow",
}
TERMINAL_PROCESSES = {
    "windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe", "openconsole.exe",
    "mintty.exe", "putty.exe", "kitty.exe", "conemu.exe", "conemu64.exe", "alacritty.exe",
    "wezterm-gui.exe", "tabby.exe", "hyper.exe", "wsl.exe", "bash.exe",
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


@dataclass
class SelectionResult:
    text: str | None
    reason: str = ""   # ok | no_selection | terminal | own_window | clipboard_busy | too_large | failed


def _window_info(hwnd) -> tuple[str, str, int]:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        try:
            size = wintypes.DWORD(1024)
            path = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                exe = os.path.basename(path.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    return buf.value.lower(), exe, pid.value


def _open_clipboard(retries: int = 10) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _snapshot() -> list[tuple[int, bytes]] | None:
    """Копия всех форматов буфера, которые являются блоками памяти. None — слишком большой."""
    items: list[tuple[int, bytes]] = []
    total = 0
    fmt = user32.EnumClipboardFormats(0)
    while fmt:
        if fmt not in _NON_MEMORY_FORMATS and not (0x0200 <= fmt <= 0x03FF):
            handle = user32.GetClipboardData(fmt)
            if handle:
                size = kernel32.GlobalSize(handle)
                if size:
                    total += size
                    if total > MAX_SAVED_BYTES:
                        return None
                    ptr = kernel32.GlobalLock(handle)
                    if ptr:
                        try:
                            items.append((fmt, ctypes.string_at(ptr, size)))
                        finally:
                            kernel32.GlobalUnlock(handle)
        fmt = user32.EnumClipboardFormats(fmt)
    return items


def _set_bytes(fmt: int, data: bytes) -> None:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not handle:
        return
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        return
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(fmt, handle):
        kernel32.GlobalFree(handle)  # при успехе памятью владеет система


def _restore(items: list[tuple[int, bytes]]) -> bool:
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        for fmt, data in items:
            _set_bytes(fmt, data)
        # Не дублировать восстановленное содержимое в журнале буфера Windows (Win+V).
        hist = user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
        if hist and items:
            _set_bytes(hist, (0).to_bytes(4, "little"))
        return True
    finally:
        user32.CloseClipboard()


def _read_unicode_text() -> str | None:
    if not _open_clipboard():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _wait_modifiers_released(timeout: float = 0.6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_CONTROL, VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN)):
            return
        time.sleep(0.01)


def _send_ctrl_c() -> None:
    seq = [(VK_CONTROL, 0), (VK_C, 0), (VK_C, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP)]
    arr = (INPUT * len(seq))()
    for i, (vk, flags) in enumerate(seq):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def capture_selection(wait_timeout: float = 0.45) -> SelectionResult:
    """Блокирующая функция: вызывать в рабочем потоке ДО показа панели."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return SelectionResult(None, "no_selection")
    cls, exe, pid = _window_info(hwnd)
    if pid == os.getpid():
        return SelectionResult(None, "own_window")
    if cls in TERMINAL_CLASSES or exe in TERMINAL_PROCESSES:
        return SelectionResult(None, "terminal")

    _wait_modifiers_released()
    if not _open_clipboard():
        return SelectionResult(None, "clipboard_busy")
    try:
        saved = _snapshot()
    finally:
        user32.CloseClipboard()
    if saved is None:
        return SelectionResult(None, "too_large")

    before = user32.GetClipboardSequenceNumber()
    _send_ctrl_c()
    deadline = time.monotonic() + wait_timeout
    changed = False
    while time.monotonic() < deadline:
        if user32.GetClipboardSequenceNumber() != before:
            changed = True
            time.sleep(0.03)  # даём приложению дописать все форматы
            break
        time.sleep(0.01)
    if not changed:
        return SelectionResult(None, "no_selection")  # буфер не тронут

    text = _read_unicode_text()
    if not _restore(saved):
        log.warning("clipboard restore failed (clipboard busy)")
    if not text or not text.strip():
        return SelectionResult(None, "no_selection")
    return SelectionResult(text, "ok")
