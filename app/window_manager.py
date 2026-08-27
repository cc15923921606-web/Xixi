from __future__ import annotations

import ctypes
import logging

logger = logging.getLogger("window_manager")

user32 = ctypes.windll.user32


def focus_window_by_title(title: str) -> bool:
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        logger.debug("window not found: %s", title)
        return False
    try:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        logger.info("focused window: %s", title)
        return True
    except Exception as e:
        logger.warning("focus failed: %s", e)
        return False


TOPMOST = -1
NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001


def pin_window(title: str) -> bool:
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    try:
        user32.SetWindowPos(hwnd, TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        logger.info("pinned window: %s", title)
        return True
    except Exception as e:
        logger.warning("pin failed: %s", e)
        return False
