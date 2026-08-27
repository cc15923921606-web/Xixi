from __future__ import annotations

import logging

from .config import Config
try:
    from .tts_bus import TtsBus
except Exception as exc:
    TtsBus = None  # type: ignore[assignment]

logger = logging.getLogger("mouth")


class Mouth:
    def __init__(self, cfg: Config, translator: object = None) -> None:
        self.available = TtsBus is not None
        if self.available:
            self.tts = TtsBus(cfg, translator=translator)  # type: ignore[misc]
            self.tts.start()
        else:
            self.tts = None  # type: ignore[assignment]
        logger.info("mouth started=%s", self.available)

    def speak(self, text: str, *, reply_language: str = "zh") -> None:
        if not text or not text.strip():
            return
        if not self.available or not self.tts:
            return
        self.tts.inbox.put((text, reply_language))

    def stop(self) -> None:
        if not self.available or not self.tts:
            return
        self.tts.stop()
