import unittest

from app.voice_verification import chinese_voice_match


class VoiceVerificationTests(unittest.TestCase):
    def test_rejects_qq_self_intro_with_omitted_middle_content(self) -> None:
        expected = (
            "你好，cc，我是昔夕，也可以叫我小夕。平时我喜欢聊游戏、动漫和各种"
            "有点奇妙的故事，也会慢慢形成自己的想法。以后请多多关照啦。"
        )
        transcript = (
            "你好，谢谢我是昔夕，也可以叫我小夕。动漫，还有那些幻想和日常交织"
            "在一起的故事。唉。"
        )

        accepted, score, metrics = chinese_voice_match(expected, transcript)

        self.assertFalse(accepted)
        self.assertLess(score, 0.8)
        self.assertLess(metrics["character_recall"], 0.9)
        self.assertEqual(metrics["unexpected_terminal_interjection"], 1.0)

    def test_rejects_unintended_terminal_sigh_even_when_rest_is_complete(self) -> None:
        accepted, score, metrics = chinese_voice_match(
            "今天一起聊游戏和动漫吧。",
            "今天一起聊游戏和动漫吧。唉。",
        )

        self.assertFalse(accepted)
        self.assertGreater(score, 0.9)
        self.assertEqual(metrics["unexpected_terminal_interjection"], 1.0)

    def test_keeps_terminal_sigh_when_it_is_present_in_expected_text(self) -> None:
        accepted, _, metrics = chinese_voice_match(
            "真拿你没办法，唉。",
            "真拿你没办法，哎。",
        )

        self.assertTrue(accepted)
        self.assertEqual(metrics["unexpected_terminal_interjection"], 0.0)

    def test_accepts_common_erhua_omitted_by_whisper(self) -> None:
        accepted, score, _ = chinese_voice_match(
            "歇一会儿，我陪着你。",
            "歇一会，我陪着你。",
        )

        self.assertTrue(accepted)
        self.assertEqual(score, 1.0)

    def test_accepts_terminal_particle_confusion_in_evening_greeting(self) -> None:
        accepted, score, metrics = chinese_voice_match(
            "晚上好，希希，终于又见到你啦。",
            "晚上好，昔夕，终于又见到你了。",
        )

        self.assertTrue(accepted)
        self.assertEqual(score, 1.0)
        self.assertEqual(metrics["phonetic_similarity"], 1.0)

    def test_terminal_particle_equivalence_does_not_hide_wrong_middle_word(self) -> None:
        accepted, _, metrics = chinese_voice_match(
            "晚上好，希希，终于又见到你啦。",
            "晚上好，昔夕，终于要见到你了。",
        )

        self.assertFalse(accepted)
        self.assertLess(metrics["character_recall"], 0.94)

    def test_does_not_remove_semantic_er_character(self) -> None:
        accepted, _, metrics = chinese_voice_match(
            "女儿和儿子都在等你。",
            "女和子都在等你。",
        )

        self.assertFalse(accepted)
        self.assertLess(metrics["character_recall"], 0.9)

    def test_accepts_same_sounding_complement_particle_from_asr(self) -> None:
        accepted, score, _ = chinese_voice_match(
            "你说得有道理，我们一步一步来。",
            "你说的有道理，我们一步一步来。",
        )

        self.assertTrue(accepted)
        self.assertEqual(score, 1.0)

    def test_accepts_same_sounding_adverbial_particle_from_asr(self) -> None:
        accepted, score, _ = chinese_voice_match(
            "音乐结束以后，我们再安静地聊一会儿。",
            "音乐结束以后，我们再安静的聊一会。",
        )

        self.assertTrue(accepted)
        self.assertEqual(score, 1.0)

    def test_does_not_merge_semantic_destination_particle(self) -> None:
        accepted, _, metrics = chinese_voice_match(
            "请到目的地等我。",
            "请到目的的等我。",
        )

        self.assertFalse(accepted)
        self.assertLess(metrics["phonetic_similarity"], 1.0)

    def test_does_not_merge_lexical_de_pronunciation(self) -> None:
        accepted, _, metrics = chinese_voice_match(
            "努力以后可以获得奖励。",
            "努力以后可以获的奖励。",
        )

        self.assertFalse(accepted)
        self.assertLess(metrics["phonetic_similarity"], 1.0)


if __name__ == "__main__":
    unittest.main()
