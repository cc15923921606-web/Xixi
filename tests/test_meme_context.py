from __future__ import annotations

import unittest
from pathlib import Path

from app.meme_context import MemeInterpreter


class MemeInterpreterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        lexicon = Path(__file__).resolve().parents[1] / "meme_lexicon.json"
        cls.interpreter = MemeInterpreter(lexicon)

    def test_recognizes_known_homophone_meme(self) -> None:
        context = self.interpreter.context_for("这剧情真是蚌埠住了")

        self.assertIn("绷不住了", context)
        self.assertIn("beng bu zhu le", context)
        self.assertIn("自然接住", context)

    def test_provides_pinyin_for_unlisted_wordplay(self) -> None:
        context = self.interpreter.context_for("宫廷玉液酒")

        self.assertIn("gong ting yu ye jiu", context)

    def test_explains_only_when_meaning_is_requested(self) -> None:
        context = self.interpreter.context_for("蚌埠住了是什么梗")

        self.assertIn("正在询问含义", context)

    def test_english_without_known_meme_needs_no_hint(self) -> None:
        self.assertEqual(self.interpreter.context_for("hello world"), "")


if __name__ == "__main__":
    unittest.main()
