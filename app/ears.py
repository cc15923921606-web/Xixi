from __future__ import annotations

import logging

from .asr_bus import AsrBus
from .config import Config

logger = logging.getLogger("ears")


class Ears:
    def __init__(self, cfg: Config) -> None:
        self.asr = AsrBus(cfg)
        self.asr.start()
        logger.info("ears started")

    def stop(self) -> None:
        self.asr.stop()
