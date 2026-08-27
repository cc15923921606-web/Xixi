from __future__ import annotations

import logging
from queue import Empty

from .brain import Brain
from .ears import Ears
from .mouth import Mouth
from .config import Config
from .instruction_frame import analyze_instruction
from .hotkeys import install_hotkey
from .window_manager import focus_window_by_title, pin_window

logger = logging.getLogger("runner")


class Runner:
    def __init__(self, cfg: Config, with_voice: bool = True) -> None:
        self.cfg = cfg
        self.brain = Brain(cfg)
        self.ears = Ears(cfg) if with_voice else None
        self.mouth = (
            Mouth(cfg, translator=self.brain.translate_reply)
            if with_voice
            else None
        )
        self._running = True
        install_hotkey(cfg.hotkey_stop, self._request_stop)
        if cfg.window_title and cfg.use_window_pin:
            focus_window_by_title(cfg.window_title)
            pin_window(cfg.window_title)

    def _request_stop(self) -> None:
        logger.info("stop requested")
        self._running = False

    def run_text_loop(self) -> None:
        greeting = self.brain.think("（系统：用一句话打招呼）")
        print(f"小神经: {greeting}")
        if self.mouth:
            self.mouth.speak(greeting)
        while self._running:
            try:
                msg = input("你: ").strip()
            except EOFError:
                break
            if not msg:
                continue
            if msg.lower() in {"quit", "退出", "再见"}:
                bye = self.brain.think("（系统：玩家要走了，说再见吧）")
                print(f"小神经: {bye}")
                if self.mouth:
                    self.mouth.speak(bye)
                break
            instruction_frame = analyze_instruction(msg)
            reply = self.brain.think(msg, instruction_frame=instruction_frame)
            print(f"小神经: {reply}")
            if self.mouth:
                self.mouth.speak(
                    reply,
                    reply_language=instruction_frame.response_language,
                )

    def run_voice_loop(self) -> None:
        if not self.ears:
            raise RuntimeError("voice loop requires ears")
        greeting = self.brain.think("（系统：玩家刚上线，打个招呼吧）")
        print(f"小神经: {greeting}")
        if self.mouth:
            self.mouth.speak(greeting)
        logger.info("voice loop started")
        while self._running:
            try:
                try:
                    text = self.ears.asr.inbox.get(timeout=0.2)
                except Empty:
                    continue
                if not text:
                    continue
                if "退出" in text or "再见" in text:
                    bye = self.brain.think("（系统：玩家要走了，说再见吧）")
                    print(f"小神经: {bye}")
                    if self.mouth:
                        self.mouth.speak(bye)
                    break
                instruction_frame = analyze_instruction(text)
                reply = self.brain.think(text, instruction_frame=instruction_frame)
                print(f"小神经: {reply}")
                if self.mouth:
                    self.mouth.speak(
                        reply,
                        reply_language=instruction_frame.response_language,
                    )
            except KeyboardInterrupt:
                logger.info("keyboard interrupt")
                break

    def shutdown(self) -> None:
        try:
            if self.ears:
                self.ears.stop()
        except Exception as e:
            logger.warning("ears stop error: %s", e)
        try:
            if self.mouth:
                self.mouth.stop()
        except Exception as e:
            logger.warning("mouth stop error: %s", e)
        logger.info("runner stopped")
