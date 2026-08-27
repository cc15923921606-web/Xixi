from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_initialized = False


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)

    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(ch)
