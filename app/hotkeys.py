from __future__ import annotations

import logging
from typing import Callable

from pynput import keyboard

logger = logging.getLogger("hotkeys")


def install_hotkey(hotkey: str, callback: Callable[[], None]) -> None:
    parts = {p.strip().lower() for p in hotkey.split("+") if p.strip()}
    target_key = parts - {"ctrl", "shift", "alt"}
    target = target_key.pop() if target_key else "q"

    def _normalize(name: str) -> str:
        name = name.replace("left", "").replace("right", "")
        return name

    pressed = set()

    def _on_press(key):
        try:
            name = getattr(key, "char", None) or getattr(key, "name", None) or str(key)
        except Exception:
            name = str(key)
        pressed.add(_normalize(name))
        need_ctrl = "ctrl" in parts
        need_shift = "shift" in parts
        need_alt = "alt" in parts
        if _normalize(target) in pressed:
            ctrl_ok = (keyboard.Key.ctrl_l in pressed or keyboard.Key.ctrl_r in pressed) if need_ctrl else True
            shift_ok = (keyboard.Key.shift in pressed) if need_shift else True
            alt_ok = (keyboard.Key.alt_l in pressed or keyboard.Key.alt_r in pressed) if need_alt else True
            if ctrl_ok and shift_ok and alt_ok:
                logger.info("hotkey triggered")
                callback()

    def _on_release(key):
        try:
            name = getattr(key, "char", None) or getattr(key, "name", None) or str(key)
        except Exception:
            name = str(key)
        pressed.discard(_normalize(name))

    logger.info("installing stop hotkey: %s", hotkey)
    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()
