"""Вспомогательные функции Windows: вывод окна на передний план."""
from __future__ import annotations

import sys


def force_foreground(hwnd: int) -> None:
    """Активирует окно. Windows ограничивает SetForegroundWindow для фоновых процессов,
    поэтому при неудаче временно присоединяемся к потоку ввода активного окна."""
    if sys.platform != "win32" or not hwnd:
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]

    hwnd = wintypes.HWND(hwnd)
    if user32.SetForegroundWindow(hwnd) and user32.GetForegroundWindow() == hwnd.value:
        return
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    our_thread = kernel32.GetCurrentThreadId()
    if fg_thread and fg_thread != our_thread:
        user32.AttachThreadInput(fg_thread, our_thread, True)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            user32.AttachThreadInput(fg_thread, our_thread, False)
