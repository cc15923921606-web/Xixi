from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import Config
from .logging_setup import setup_logging
from .runner import Runner

logger = logging.getLogger("app.main")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--text", action="store_true", help="Text chat mode")
    p.add_argument("--qq", action="store_true", help="QQ bot mode")
    p.add_argument("--qq-user", type=int, default=0, help="Your QQ user id")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    cfg = Config.from_env()
    cfg.ensure_dirs()
    setup_logging(cfg.logs_dir)

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.qq:
        _run_qq(cfg, args)
        return

    logger.info("starting app")
    runner = Runner(cfg, with_voice=not args.text)
    try:
        if args.text:
            runner.run_text_loop()
        else:
            runner.run_voice_loop()
    finally:
        runner.shutdown()


def _run_qq(cfg: Config, args: argparse.Namespace) -> None:
    from .brain import Brain
    from .qq_bridge import run_ws_listener

    user_id = args.qq_user or cfg.qq_user_id
    if not user_id:
        print("Error: set --qq-user or QQ_USER_ID env var")
        sys.exit(1)

    brain = Brain(cfg)
    logger.info("QQ bot mode, user_id=%s", user_id)
    asyncio.run(run_ws_listener(cfg, user_id, brain))


if __name__ == "__main__":
    main()
