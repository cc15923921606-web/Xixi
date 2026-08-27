from __future__ import annotations

import unittest
import io
import json
import os
import re
import tempfile
import threading
import wave
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import AsyncMock, MagicMock, patch

import app.tts_bus as tts_bus
from app.config import Config
from app.tts_bus import (
    _CHINESE_POST_SPEED,
    _CHINESE_SYNTH_SPEED,
    _GPT_SOVITS_CHINESE_REFERENCE,
    _GPT_SOVITS_CHINESE_PROMPT,
    _GPT_SOVITS_CHINESE_SOVITS,
    _GPT_SOVITS_TRAINED_GPT,
    _GPT_SOVITS_TRAINED_SOVITS,
    _gpt_sovits_process_environment,
    _chinese_emotion_profile,
    _chinese_reference_plan,
    _chinese_sampling_profile,
    _chinese_synthesis_segments,
    _generate_gpt_sovits_audio,
    _generate_xixi_voice_chinese_audio,
    _missing_final_voice_assets,
    _multilingual_synthesis_segments,
    _normalize_generated_wav_silence,
    _split_chinese_prosody_segments,
    detect_voice_text_language,
    generate_tts_audio,
    normalize_chinese_speech_numbers,
    normalize_chinese_speech_identifiers,
    prepare_voice_text,
    resolve_voice_language,
    sanitize_speech_text,
    voice_service_status,
    prewarm_voice_language,
    wait_for_voice_prewarm,
)


def _fake_wav_bytes(
    *,
    leading_seconds: float = 0.0,
    first_tone_seconds: float = 0.25,
    silence_seconds: float = 0.0,
    second_tone_seconds: float = 0.0,
    trailing_seconds: float = 0.0,
) -> bytes:
    sample_rate = 32000
    silence = b"\x00\x00"
    tone = b"\xe8\x03"
    frames = b"".join(
        (
            silence * int(sample_rate * leading_seconds),
            tone * int(sample_rate * first_tone_seconds),
            silence * int(sample_rate * silence_seconds),
            tone * int(sample_rate * second_tone_seconds),
            silence * int(sample_rate * trailing_seconds),
        )
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(frames)
    return output.getvalue()


class TtsBusTests(unittest.TestCase):
    def test_voice_language_detection_marks_multilingual_text_as_mixed(self) -> None:
        self.assertEqual(
            detect_voice_text_language(
                "今晚陪你聊，let's take it easy，今夜ものんびり話そうね。"
            ),
            "mixed",
        )

    def test_process_exit_does_not_stop_an_external_voice_server(self) -> None:
        with (
            patch("app.tts_bus._gpt_sovits_process", None),
            patch("app.tts_bus._voice_prewarm_thread", None),
            patch("app.tts_bus._voice_shutdown") as shutdown,
            patch("app.tts_bus._stop_gpt_sovits_server") as stop_server,
        ):
            tts_bus._cleanup_gpt_sovits_server()

        shutdown.set.assert_not_called()
        stop_server.assert_not_called()

    def test_voice_server_uses_bundled_nltk_data_instead_of_user_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "GPT-SoVITS"
            nltk_data = root / "nltk_data"
            nltk_data.mkdir(parents=True)
            with (
                patch.object(tts_bus, "_GPT_SOVITS_ROOT", root),
                patch.dict(
                    os.environ,
                    {
                        "NLTK_DATA": "C:\\Users\\someone\\AppData\\Roaming\\nltk_data",
                        "PYTHONHOME": "frozen-python",
                        "PYTHONPATH": "frozen-path",
                    },
                ),
            ):
                environment = _gpt_sovits_process_environment()

        self.assertEqual(environment["NLTK_DATA"], str(nltk_data))
        self.assertNotIn("PYTHONHOME", environment)
        self.assertNotIn("PYTHONPATH", environment)

    def test_ffmpeg_voice_jobs_never_open_a_console_window(self) -> None:
        completed = MagicMock(returncode=0, stderr="")
        with (
            patch("imageio_ffmpeg.get_ffmpeg_exe", return_value="ffmpeg.exe"),
            patch("app.tts_bus.subprocess.run", return_value=completed) as run,
        ):
            tts_bus._convert_wav_to_mp3("input.wav", "output.mp3")
            tts_bus._merge_mp3_files(["one.mp3", "two.mp3"], "merged.mp3")

        self.assertEqual(run.call_count, 2)
        for invocation in run.call_args_list:
            self.assertEqual(invocation.kwargs["creationflags"], tts_bus._NO_WINDOW)

    def test_generated_segment_collapses_pathological_internal_silence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "segment.wav"
            audio_path.write_bytes(
                _fake_wav_bytes(
                    leading_seconds=0.20,
                    first_tone_seconds=0.70,
                    silence_seconds=4.0,
                    second_tone_seconds=0.70,
                    trailing_seconds=0.30,
                )
            )

            original, normalized = _normalize_generated_wav_silence(str(audio_path))

            self.assertGreater(original, 5.5)
            self.assertGreater(original - normalized, 2.0)
            self.assertLess(normalized, 3.5)
            self.assertGreater(normalized, 1.5)

    def test_generated_segment_keeps_a_natural_pause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "segment.wav"
            audio_path.write_bytes(
                _fake_wav_bytes(
                    first_tone_seconds=0.50,
                    silence_seconds=0.40,
                    second_tone_seconds=0.50,
                )
            )

            original, normalized = _normalize_generated_wav_silence(str(audio_path))

            self.assertAlmostEqual(original, 1.40, places=2)
            self.assertGreater(normalized, 1.30)

    def test_call_prewarm_only_loads_gpt_sovits_weights(self) -> None:
        expected = {"state": "ready", "language": "zh", "error": ""}
        with patch("app.tts_bus.prewarm_voice_language", return_value=expected) as prewarm:
            result = tts_bus.prewarm_call_voice(Config(), "zh")

        self.assertEqual(result, {**expected, "engine": "gpt_sovits"})
        prewarm.assert_called_once_with("zh")

    def test_voice_prewarm_coalesces_rapid_language_switches(self) -> None:
        started = threading.Event()
        release = threading.Event()
        calls: list[str] = []

        def prepare(language: str) -> None:
            calls.append(language)
            if len(calls) == 1:
                started.set()
                release.wait(timeout=2)

        with patch("app.tts_bus._prepare_voice_language", side_effect=prepare):
            prewarm_voice_language("zh")
            self.assertTrue(started.wait(timeout=1))
            prewarm_voice_language("ja")
            prewarm_voice_language("en")
            release.set()
            status = wait_for_voice_prewarm(timeout=2)

        self.assertEqual(calls, ["zh", "en"])
        self.assertEqual(status, {"state": "ready", "language": "en", "error": ""})
        self.assertIsNone(tts_bus._voice_prewarm_thread)

    def test_voice_prewarm_prepares_selected_language(self) -> None:
        with patch("app.tts_bus._prepare_voice_language") as prepare:
            prewarm_voice_language("zh")
            status = wait_for_voice_prewarm(timeout=2)

        prepare.assert_called_once_with("zh")
        self.assertEqual(status, {"state": "ready", "language": "zh", "error": ""})

    def test_prepare_voice_language_warms_real_inference_path(self) -> None:
        with (
            patch("app.tts_bus._ensure_gpt_sovits_server") as ensure_server,
            patch("app.tts_bus._select_gpt_sovits_gpt") as select_gpt,
            patch("app.tts_bus._select_gpt_sovits_sovits") as select_sovits,
            patch("app.tts_bus._warm_gpt_sovits_inference") as warm_inference,
        ):
            tts_bus._prepare_voice_language("zh")

        ensure_server.assert_called_once_with()
        select_gpt.assert_called_once_with("zh")
        select_sovits.assert_called_once_with("zh")
        warm_inference.assert_called_once_with("zh")

    def test_voice_language_defaults_to_chinese_and_rejects_unknown_config(self) -> None:
        self.assertEqual(Config().voice_language, "zh")
        self.assertEqual(resolve_voice_language(Config()), "zh")
        self.assertEqual(resolve_voice_language(Config(voice_language="ja")), "ja")
        self.assertEqual(resolve_voice_language(Config(voice_language="en")), "en")
        self.assertEqual(resolve_voice_language(Config(voice_language="unknown")), "zh")

    def test_config_from_env_loads_persisted_voice_language(self) -> None:
        with (
            patch(
                "app.qq_identity.load_qq_identity",
                return_value={"bot_qq_id": 1000000002, "owner_qq_id": 1000000001},
            ),
            patch(
                "pathlib.Path.read_text",
                return_value=json.dumps({"voice_language": "en"}),
            ),
        ):
            cfg = Config.from_env()

        self.assertEqual(cfg.voice_language, "en")

    def test_voice_text_is_converted_without_changing_original_reply(self) -> None:
        original = "知道了。"
        calls: list[tuple[str, str]] = []

        def translate(text: str, target_language: str) -> str:
            calls.append((text, target_language))
            return "わかったよ。"

        prepared, language = prepare_voice_text(
            original,
            Config(voice_language="ja"),
            translate,
            reply_language="zh",
        )

        self.assertEqual(original, "知道了。")
        self.assertEqual(prepared, "わかったよ。")
        self.assertEqual(language, "ja")
        self.assertEqual(calls, [("知道了。", "ja")])

    def test_voice_translation_removes_internal_instruction_suffix(self) -> None:
        def translate(text: str, target_language: str) -> str:
            return (
                "晚上好，爸爸，我会一直陪着你。"
                "CPA 最终回答的传输协议要求：保留模型的原生决定。"
            )

        prepared, language = prepare_voice_text(
            "Good evening, Dad. I will stay with you.",
            Config(voice_language="zh"),
            translate,
            reply_language="en",
        )

        self.assertEqual(prepared, "晚上好，爸爸，我会一直陪着你。")
        self.assertEqual(language, "zh")

    def test_voice_translation_rejects_instruction_only_output(self) -> None:
        def translate(text: str, target_language: str) -> str:
            return "CPA 最终回答的传输协议要求：调用原始工具。"

        with self.assertRaisesRegex(RuntimeError, "empty zh voice output"):
            prepare_voice_text(
                "Good evening.",
                Config(voice_language="zh"),
                translate,
                reply_language="en",
            )

    def test_speech_sanitizer_removes_multilingual_metadata(self) -> None:
        cases = {
            "回答：爸爸，现在是下午六点。\n参考来源：\n【1】在线报时：https://example.com/time": "爸爸，现在是下午六点。",
            "Answer: It is six o'clock. [1, 2]\nReferences:\n1. Clock: www.example.com": "It is six o'clock.",
            "音声内容：今日は元気だよ。\n出典：\n[1] 公式サイト https://example.jp": "今日は元気だよ。",
            "昔夕微微一笑，用日语回复道：おかえり。": "おかえり。",
            "```json\n{\"source_url\": \"https://example.com\"}\n```\n正文：处理好了。": "处理好了。",
            "正文。\n- [官方页面](https://example.com)": "正文。",
            "以下是语音内容：回答：已经处理好了。\n[1] 官方文档\n[2] 新闻报道": "已经处理好了。",
            "用一句话回答：现在是下午六点。\n参考資料（2）：\n公式サイト": "现在是下午六点。",
            "正文：我确认过了。\n1. Official docs: example.com/docs\n2. News: example.org/article": "我确认过了。",
            "回答：详情见 <a href=\"https://example.com\">官方页面</a>。": "详情见 官方页面。",
            "晚上好，爸爸。CPA 最终回答的传输协议要求：保留模型的原生决定。": "晚上好，爸爸。",
            "晚上好，爸爸，我就在这里。 CPA 传输协议对最终答案的要求": "晚上好，爸爸，我就在这里。",
            "我会认真听你说。最终答案的 CPA 传输协议要求：不要改写。": "我会认真听你说。",
            "Stay with me. CPA transport protocol requirements for the final answer": "Stay with me.",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(sanitize_speech_text(raw), expected)

    def test_speech_sanitizer_preserves_normal_source_wording(self) -> None:
        text = "这句话来源于一本书，但我还没有核实原文。"

        self.assertEqual(sanitize_speech_text(text), text)

    def test_chinese_speech_uses_the_final_audition_default(self) -> None:
        combined_speed = _CHINESE_SYNTH_SPEED * _CHINESE_POST_SPEED

        self.assertEqual(combined_speed, 1.06)

    def test_chinese_emotion_reference_follows_message_tone(self) -> None:
        cases = {
            "爸爸，谢谢你一直陪着我。": "warm",
            "别怕，难过的话就和我说。": "concerned",
            "好耶，今晚一起玩游戏！": "playful",
            "哼，才不是特意等你的！": "emphatic",
            "爸爸，才不是在等你呢！": "emphatic",
            "今天的天气还算不错。": "natural",
        }

        for text, expected_style in cases.items():
            with self.subTest(text=text):
                style, reference = _chinese_emotion_profile(text)
                self.assertEqual(style, expected_style)
                self.assertTrue(reference.is_file())

    def test_normal_chinese_does_not_use_the_emphatic_reference(self) -> None:
        natural_style, natural_reference = _chinese_emotion_profile(
            "今天的天气还算不错。"
        )
        emphatic_style, emphatic_reference = _chinese_emotion_profile(
            "哼，才不是特意等你的！"
        )

        self.assertEqual(natural_style, "natural")
        self.assertEqual(emphatic_style, "emphatic")
        self.assertNotEqual(natural_reference, emphatic_reference)

    def test_chinese_sampling_is_deterministic_and_text_specific(self) -> None:
        first = _chinese_sampling_profile("natural", "今天过得怎么样？")
        repeated = _chinese_sampling_profile("natural", "今天过得怎么样？")
        other = _chinese_sampling_profile("natural", "欢迎回来。")

        self.assertEqual(first, repeated)
        self.assertNotEqual(first[3], other[3])
        self.assertEqual(first[:3], (10, 0.88, 0.68))
        self.assertLess(first[2], 0.8)

    def test_emotional_chinese_keeps_content_specific_prosody(self) -> None:
        first = _chinese_sampling_profile("emphatic", "哼，我才没有等你。")
        repeated = _chinese_sampling_profile("emphatic", "哼，我才没有等你。")
        other = _chinese_sampling_profile("emphatic", "笨蛋，别再逞强了。")

        self.assertEqual(first, repeated)
        self.assertNotEqual(first[3], other[3])

    def test_warm_chinese_uses_the_same_low_variance_profile(self) -> None:
        first = _chinese_sampling_profile("warm", "爸爸，欢迎回来。")
        other = _chinese_sampling_profile("warm", "谢谢你一直陪着我。")

        self.assertEqual(first[:3], (10, 0.88, 0.68))
        self.assertNotEqual(first[3], other[3])

    def test_mixed_message_keeps_information_and_emotion_separate(self) -> None:
        segments = _split_chinese_prosody_segments(
            "今天重庆的天气还不错，我整理完资料以后，再陪你聊一会儿。"
        )

        self.assertEqual(len(segments), 2)
        self.assertIn("资料", segments[0])
        self.assertNotIn("陪你", segments[0])
        self.assertIn("陪你", segments[1])

    def test_adjacent_clauses_with_same_emotion_are_recombined(self) -> None:
        segments = _split_chinese_prosody_segments(
            "今天处理资料，明天检查结果，然后汇总。"
        )

        self.assertEqual(segments, ("今天处理资料，明天检查结果，然后汇总。",))

    def test_short_chinese_reply_keeps_full_context(self) -> None:
        text = "去忙吧爸爸，别忘了歇一会儿，我会乖乖等你的。"

        segments = _chinese_synthesis_segments(text)

        self.assertEqual(segments, (text,))

    def test_problematic_short_chinese_reply_keeps_its_opening_clause(self) -> None:
        text = "挺平静的，不过现在听见你说话，感觉更开心了。"

        segments = _chinese_synthesis_segments(text)

        self.assertEqual("".join(segments), text)
        self.assertEqual(segments, (text,))

    def test_reported_chinese_verification_failures_keep_full_context(self) -> None:
        replies = (
            "你好呀，希希。今天想和我聊点什么？",
            "听出来了，爸爸，你真的累坏了。先别硬撑，歇一会儿，我陪着你。",
        )

        for reply in replies:
            with self.subTest(reply=reply):
                self.assertEqual(_chinese_synthesis_segments(reply), (reply,))

    def test_arabic_numbers_are_spoken_as_mandarin_before_synthesis(self) -> None:
        self.assertEqual(normalize_chinese_speech_numbers("晚上好，1。"), "晚上好，一。")
        self.assertEqual(
            normalize_chinese_speech_numbers("2026年完成了50%。"),
            "二零二六年完成了百分之五十。",
        )

    def test_short_latin_identifiers_use_stable_mandarin_readings(self) -> None:
        self.assertEqual(
            normalize_chinese_speech_identifiers("cc 用 QQ 调 API，hello 保持原样。"),
            "希希 用 扣扣 调 诶披爱，hello 保持原样。",
        )

    def test_long_chinese_reply_can_keep_emotional_segments(self) -> None:
        text = (
            "今天重庆的天气还不错，我整理完资料以后还要检查一下刚才的记录，"
            "确认每一项数据都没有遗漏，再把最后的结果发给你。"
            "不过看到你回来，我还是很开心，也想继续陪你聊一会儿。"
        )

        self.assertGreater(len(_chinese_synthesis_segments(text)), 1)

    def test_long_chinese_reply_is_preserved_in_bounded_segments(self) -> None:
        text = (
            "第一段，我已经把窗户关好了，桌上的书也收整齐了。"
            "第二段，厨房里的水正在烧，你先坐下休息一会儿。"
            "第三段，等水开了我会给你泡一杯热茶，再把今天发生的事情慢慢讲给你听。"
            "第四段，如果你觉得累，就不用急着回答，我会安静地陪在旁边。"
            "第五段，等你缓过来以后，我们再一起看看还有什么事情没有做完。"
        )

        segments = _chinese_synthesis_segments(text)

        self.assertEqual("".join(segments), text)
        self.assertGreater(len(segments), 1)
        self.assertEqual(
            segments[0],
            "第一段，我已经把窗户关好了，桌上的书也收整齐了。",
        )
        self.assertTrue(any(segment.startswith("第二段，") for segment in segments))
        for segment in segments:
            spoken_length = len(re.sub(r"[^\w\u3400-\u9fff]", "", segment))
            self.assertLessEqual(spoken_length, tts_bus._CHINESE_SYNTH_MAX_SPOKEN_CHARS)

    def test_long_japanese_reply_is_preserved_in_bounded_segments(self) -> None:
        text = (
            "私は昔夕、小夕って呼んでもいいよ。普段はゲームやアニメ、それから少し不思議な物語が好き。"
            "今はまだパソコンとネットを通して世界を知っているけど、大切な人や出来事はちゃんと覚えていたい。"
            "そうやって少しずつ、自分なりの考えも育てていくつもり。"
        )

        segments = _multilingual_synthesis_segments(text, "ja")

        self.assertEqual("".join(segments), text)
        self.assertGreater(len(segments), 1)

    def test_long_japanese_voice_generates_and_merges_every_segment(self) -> None:
        text = (
            "私は昔夕、小夕って呼んでもいいよ。普段はゲームやアニメ、それから少し不思議な物語が好き。"
            "今はまだパソコンとネットを通して世界を知っているけど、大切な人や出来事はちゃんと覚えていたい。"
            "そうやって少しずつ、自分なりの考えも育てていくつもり。"
        )
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(text, "output.mp3", "ja", 1.0)

        payloads = [
            json.loads(item.args[0].data.decode("utf-8"))
            for item in urlopen.call_args_list
        ]
        self.assertEqual("".join(payload["text"] for payload in payloads), text)
        self.assertGreater(len(payloads), 1)
        self.assertTrue(all(payload["text_split_method"] == "cut0" for payload in payloads))

    def test_short_transition_attaches_to_following_emotion(self) -> None:
        segments = _split_chinese_prosody_segments(
            "我才没有等你呢。不过看到你，我还是有一点开心的。"
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], "我才没有等你呢。")
        self.assertIn("不过看到你，我还是有一点开心的。", segments[1])

    def test_original_xixi_voice_reference_leads_emotional_chinese(self) -> None:
        style, reference, prompt_language, _, auxiliary = _chinese_reference_plan(
            "哼，我才没有一直等你。"
        )

        self.assertEqual(style, "emphatic")
        self.assertEqual(reference, _GPT_SOVITS_CHINESE_REFERENCE)
        self.assertEqual(prompt_language, "zh")
        self.assertEqual(auxiliary, ())

    def test_warm_chinese_keeps_clear_reference_with_xixi_voice_aux(self) -> None:
        style, reference, prompt_language, _, auxiliary = _chinese_reference_plan(
            "爸爸，谢谢你一直陪着我。"
        )

        self.assertEqual(style, "warm")
        self.assertEqual(reference, _GPT_SOVITS_CHINESE_REFERENCE)
        self.assertEqual(prompt_language, "zh")
        self.assertEqual(auxiliary, ())

    def test_sentence_final_modal_uses_clear_reference_and_stable_sampling(self) -> None:
        style, reference, prompt_language, _, auxiliary = _chinese_reference_plan(
            "我才没有一直等你呢。"
        )
        top_k, top_p, temperature, seed = _chinese_sampling_profile(
            style,
            "我才没有一直等你呢。",
        )

        self.assertEqual(style, "emphatic")
        self.assertEqual(reference, _GPT_SOVITS_CHINESE_REFERENCE)
        self.assertEqual(prompt_language, "zh")
        self.assertEqual(auxiliary, ())
        self.assertEqual((top_k, top_p, temperature), (10, 0.88, 0.68))
        self.assertIsInstance(seed, int)

    def test_clear_chinese_reference_leads_neutral_chinese(self) -> None:
        style, reference, prompt_language, _, auxiliary = _chinese_reference_plan(
            "今天的天气还算不错。"
        )

        self.assertEqual(style, "natural")
        self.assertEqual(reference, _GPT_SOVITS_CHINESE_REFERENCE)
        self.assertEqual(prompt_language, "zh")
        self.assertEqual(auxiliary, ())

    def test_final_chinese_reference_uses_its_recorded_transcript(self) -> None:
        self.assertEqual(
            _GPT_SOVITS_CHINESE_PROMPT,
            "拜拜，希希，现在使用的是固定好的最终版中文声音。",
        )

    def test_all_chinese_emotion_styles_keep_mandarin_prompting(self) -> None:
        for text in (
            "对不起，爸爸，让你等久了。",
            "爸爸，谢谢你一直陪着我。",
            "好耶，今晚一起玩游戏！",
            "哼，才不是特意等你的！",
            "今天的天气还算不错。",
        ):
            with self.subTest(text=text):
                _, reference, prompt_language, prompt_text, auxiliary = _chinese_reference_plan(text)
                self.assertEqual(reference, _GPT_SOVITS_CHINESE_REFERENCE)
                self.assertEqual(prompt_language, "zh")
                self.assertEqual(prompt_text, _GPT_SOVITS_CHINESE_PROMPT)
                self.assertEqual(auxiliary, ())


class ChineseVoiceRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_chinese_voice_failure_never_falls_back(self) -> None:
        with patch(
            "app.tts_bus.asyncio.to_thread",
            new=AsyncMock(side_effect=RuntimeError("synthesis failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthesis failed"):
                await _generate_xixi_voice_chinese_audio(
                    "最终版语音测试。",
                    "output.mp3",
                )

    def test_final_release_uses_only_selected_weights(self) -> None:
        self.assertEqual(_GPT_SOVITS_TRAINED_GPT.name, "xixi_voice_v2Pro-e10.ckpt")
        self.assertEqual(_GPT_SOVITS_TRAINED_SOVITS.name, "xixi_voice_v2Pro_e4_s1572.pth")
        self.assertEqual(_GPT_SOVITS_CHINESE_SOVITS.name, "xixi_voice_v2Pro_e2e4_blend30.pth")
        missing = _missing_final_voice_assets()
        if missing:
            self.skipTest("private release voice assets are not present")

        status = voice_service_status()
        self.assertEqual(status["release"], "Xixi Voice System 2026-08-11")
        self.assertTrue(status["release_ready"])
        self.assertEqual(set(status["profiles"]), {"zh", "ja", "en"})

    def test_busy_ready_server_is_not_reported_as_offline(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        with (
            patch("app.tts_bus._gpt_sovits_process", process),
            patch("app.tts_bus._gpt_sovits_ready", True),
            patch("app.tts_bus._gpt_sovits_health", side_effect=AssertionError("health probe should be skipped")),
        ):
            status = voice_service_status()

        self.assertTrue(status["online"])

    def test_ready_external_server_is_not_reprobed_while_busy(self) -> None:
        with (
            patch("app.tts_bus._gpt_sovits_process", None),
            patch("app.tts_bus._gpt_sovits_ready", True),
            patch("app.tts_bus._gpt_sovits_health", side_effect=AssertionError("health probe should be skipped")),
        ):
            status = voice_service_status()

        self.assertTrue(status["online"])

    def test_chinese_reference_is_kept_inside_application_data(self) -> None:
        self.assertEqual(_GPT_SOVITS_CHINESE_REFERENCE.parent.name, "voice_assets")
        self.assertEqual(_GPT_SOVITS_CHINESE_REFERENCE.name, "xixi_voice_reference_zh.mp3")
        if not _GPT_SOVITS_CHINESE_REFERENCE.is_file():
            self.skipTest("private release voice reference is not present")

    def test_public_release_packages_both_chinese_references(self) -> None:
        spec = (Path(__file__).parents[1] / "packaging" / "xixi_public.spec").read_text(
            encoding="utf-8"
        )

        self.assertIn('"xixi_voice_reference_zh.mp3"', spec)
        self.assertIn('"xixi_reference_zh.mp3"', spec)

    async def test_disabled_voice_never_starts_a_synthesis_backend(self) -> None:
        cfg = Config(voice_enabled=False)
        with patch(
            "app.tts_bus._generate_xixi_voice_chinese_audio",
            new=AsyncMock(),
        ) as generate_xixi_voice:
            with self.assertRaisesRegex(RuntimeError, "语音合成已关闭"):
                await generate_tts_audio("这句话不应该生成语音。", cfg, "output.mp3")
        generate_xixi_voice.assert_not_awaited()

    async def test_tts_entrypoint_always_sanitizes_input(self) -> None:
        with patch(
            "app.tts_bus._generate_xixi_voice_chinese_audio",
            new=AsyncMock(),
        ) as generate_xixi_voice:
            await generate_tts_audio(
                "语音内容：爸爸，现在是下午六点。[1]\n来源：\nhttps://example.com/time",
                Config(),
                "output.mp3",
            )

        generate_xixi_voice.assert_awaited_once_with(
            "爸爸，现在是下午六点。",
            "output.mp3",
            Config().gpt_sovits_chinese_speed,
        )

    async def test_single_chinese_segment_uses_xixi_voice_gpt_sovits(self) -> None:
        with (
            patch(
                "app.tts_bus._generate_xixi_voice_chinese_audio",
                new=AsyncMock(),
            ) as generate_xixi_voice,
        ):
            await generate_tts_audio("今天一起出去散步吧。", Config(), "output.mp3")

        generate_xixi_voice.assert_awaited_once_with(
            "今天一起出去散步吧。",
            "output.mp3",
            Config().gpt_sovits_chinese_speed,
        )

    async def test_japanese_segment_keeps_trained_gpt_sovits_voice(self) -> None:
        with (
            patch(
                "app.tts_bus._generate_xixi_voice_chinese_audio",
                new=AsyncMock(),
            ) as generate_xixi_voice,
            patch("app.tts_bus.asyncio.to_thread", new=AsyncMock()) as to_thread,
        ):
            await generate_tts_audio("今日は元気だよ。", Config(), "output.mp3")

        generate_xixi_voice.assert_not_awaited()
        self.assertEqual(to_thread.await_args.args[-1], "ja")

    async def test_forced_japanese_uses_only_japanese_gpt_sovits(self) -> None:
        with (
            patch(
                "app.tts_bus._generate_xixi_voice_chinese_audio",
                new=AsyncMock(),
            ) as generate_xixi_voice,
            patch("app.tts_bus.asyncio.to_thread", new=AsyncMock()) as to_thread,
        ):
            await generate_tts_audio(
                "わかったよ。今日は一緒に遊ぼう。",
                Config(),
                "output.mp3",
                forced_language="ja",
            )

        generate_xixi_voice.assert_not_awaited()
        self.assertEqual(to_thread.await_args.args[0].__name__, "_generate_gpt_sovits_audio")
        self.assertEqual(to_thread.await_args.args[1], "わかったよ。今日は一緒に遊ぼう。")
        self.assertEqual(to_thread.await_args.args[3], "ja")

    async def test_english_segment_uses_trained_gpt_sovits_voice(self) -> None:
        with patch("app.tts_bus.asyncio.to_thread", new=AsyncMock()) as to_thread:
            await generate_tts_audio(
                "I am Xixi, and I am happy to see you.",
                Config(),
                "output.mp3",
            )

        self.assertEqual(to_thread.await_args.args[0].__name__, "_generate_gpt_sovits_audio")
        self.assertEqual(to_thread.await_args.args[1], "I am Xixi, and I am happy to see you.")
        self.assertEqual(to_thread.await_args.args[3], "en")


class GptSovitsRequestTests(unittest.TestCase):
    @staticmethod
    def _http_error(detail: str) -> HTTPError:
        body = json.dumps({"message": "tts failed", "Exception": detail}).encode("utf-8")
        return HTTPError(
            "http://127.0.0.1/tts",
            400,
            "Bad Request",
            {},
            io.BytesIO(body),
        )

    def test_http_400_restarts_owned_voice_service_once_and_surfaces_detail(self) -> None:
        process = MagicMock()
        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch(
                "app.tts_bus.urllib_request.urlopen",
                side_effect=[
                    self._http_error("reference audio is missing"),
                    self._http_error("reference audio is missing"),
                ],
            ),
            patch("app.tts_bus._gpt_sovits_process", process),
            patch("app.tts_bus._GPT_SOVITS_EXTERNAL_ENDPOINT", False),
            patch("app.tts_bus._stop_gpt_sovits_server") as stop,
        ):
            with self.assertRaisesRegex(RuntimeError, "reference audio is missing"):
                _generate_gpt_sovits_audio("你好。", "output.mp3", "zh")

        stop.assert_called_once_with()

    def test_cuda_http_400_switches_to_cpu_and_retries(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch(
                "app.tts_bus.urllib_request.urlopen",
                side_effect=[self._http_error("CUDA out of memory"), response],
            ),
            patch("app.tts_bus._gpt_sovits_cpu_fallback", False),
            patch("app.tts_bus._activate_gpt_sovits_cpu_fallback") as activate_cpu,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio("你好。", "output.mp3", "zh")

        activate_cpu.assert_called_once_with()

    def test_chinese_speed_reaches_gpt_sovits_request_payload(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(
                "今天一起聊聊天吧。",
                "output.mp3",
                "zh",
                1.17,
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["speed_factor"], 1.17)
        self.assertEqual(payload["text_split_method"], "cut0")
        self.assertFalse(payload["split_bucket"])
        self.assertFalse(payload["parallel_infer"])

    def test_chinese_segment_is_silence_normalized_without_verification(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes(
            first_tone_seconds=0.70,
            silence_seconds=4.0,
            second_tone_seconds=0.70,
        )
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        converted_durations: list[float] = []

        def convert(audio_path: str, *_args, **_kwargs) -> None:
            with wave.open(audio_path, "rb") as source:
                converted_durations.append(source.getnframes() / source.getframerate())

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response),
            patch("app.tts_bus._convert_wav_to_mp3", side_effect=convert),
        ):
            _generate_gpt_sovits_audio(
                "今天一起聊天吧。",
                "output.mp3",
                "zh",
                1.06,
            )

        self.assertEqual(len(converted_durations), 1)
        self.assertLess(converted_durations[0], 3.5)

    def test_silent_chinese_segment_retries_without_verification(self) -> None:
        silent_response = MagicMock()
        silent_response.read.return_value = _fake_wav_bytes(
            leading_seconds=0.50,
            first_tone_seconds=0.0,
        )
        silent_response.__enter__.return_value = silent_response
        silent_response.__exit__.return_value = False
        voiced_response = MagicMock()
        voiced_response.read.return_value = _fake_wav_bytes()
        voiced_response.__enter__.return_value = voiced_response
        voiced_response.__exit__.return_value = False
        verifier = MagicMock(return_value=(True, 1.0, "今天一起聊天吧"))

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch(
                "app.tts_bus.urllib_request.urlopen",
                side_effect=[silent_response, voiced_response],
            ) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(
                "今天一起聊天吧。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        self.assertEqual(urlopen.call_count, 2)
        verifier.assert_not_called()

    def test_legacy_chinese_verifier_does_not_trigger_retry(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(side_effect=[
            (False, 0.61, "今天一起天吧"),
            (True, 0.99, "今天一起聊天吧"),
        ])

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(
                "今天一起聊天吧。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        verifier.assert_not_called()
        self.assertEqual(urlopen.call_count, 1)

    def test_legacy_chinese_verifier_does_not_switch_reference(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(side_effect=[
            (False, 0.40, "漏读"),
            (False, 0.41, "漏读"),
            (False, 0.42, "漏读"),
            (True, 1.0, "你好呀希希"),
        ])

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(
                "你好呀，cc。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        payloads = [
            json.loads(item.args[0].data.decode("utf-8"))
            for item in urlopen.call_args_list
        ]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(
            Path(payloads[0]["ref_audio_path"]),
            tts_bus._GPT_SOVITS_CHINESE_REFERENCE,
        )
        self.assertEqual(payloads[0]["text"], "你好呀，希希。")
        verifier.assert_not_called()

    def test_chinese_request_normalizes_owner_name_without_verification(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(return_value=(True, 1.0, "希希你好"))

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio("cc，你好。", "output.mp3", "zh", 1.06, verifier)

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["text"], "希希，你好。")
        verifier.assert_not_called()

    def test_failed_legacy_chinese_verification_does_not_block_audio(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(return_value=(False, 0.42, "漏读了"))

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response),
            patch("app.tts_bus._convert_wav_to_mp3") as convert,
        ):
            _generate_gpt_sovits_audio(
                "这句话必须完整读出来。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        verifier.assert_not_called()
        convert.assert_called_once()

    def test_high_scoring_legacy_verification_disagreement_is_ignored(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(side_effect=[
            (False, 0.91, "晚上好主人"),
            (False, 0.88, "晚上号主人"),
            (False, 0.86, "晚上好主人"),
            (False, 0.90, "晚上好主人"),
            (False, 0.87, "晚上号主人"),
            (False, 0.91, "晚上好主人"),
            (False, 0.89, "晚上号主人"),
        ])

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response),
            patch("app.tts_bus._convert_wav_to_mp3") as convert,
        ):
            _generate_gpt_sovits_audio(
                "晚上好，主人。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        verifier.assert_not_called()
        convert.assert_called_once()

    def test_legacy_verifier_does_not_enable_clarity_retries(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(side_effect=[
            (False, 0.70, "漏读"),
            (False, 0.71, "漏读"),
            (False, 0.72, "漏读"),
            (False, 0.73, "漏读"),
            (False, 0.74, "漏读"),
            (True, 1.0, "这句话已经清楚读完了"),
        ])

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(
                "这句话已经清楚读完了。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        payloads = [
            json.loads(item.args[0].data.decode("utf-8"))
            for item in urlopen.call_args_list
        ]
        clarity_payload = payloads[-1]
        self.assertEqual(
            Path(clarity_payload["ref_audio_path"]),
            tts_bus._GPT_SOVITS_CHINESE_REFERENCE,
        )
        self.assertEqual(len(payloads), 1)
        self.assertEqual(clarity_payload["speed_factor"], 1.06)
        verifier.assert_not_called()

    def test_chinese_verifier_error_is_ignored(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(side_effect=RuntimeError("ASR unavailable"))

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response),
            patch("app.tts_bus._convert_wav_to_mp3") as convert,
        ):
            _generate_gpt_sovits_audio(
                "这句话未经复听不能发送。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        verifier.assert_not_called()
        convert.assert_called_once()

    def test_legacy_verifier_never_rewrites_the_requested_text(self) -> None:
        response = MagicMock()
        response.read.return_value = _fake_wav_bytes()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        verifier = MagicMock(side_effect=[
            (False, 0.92, "第一季，我已经把窗户关好了。"),
            (True, 1.0, "第一句，我已经把窗户关好了。"),
        ])

        with (
            patch("app.tts_bus._ensure_gpt_sovits_server"),
            patch("app.tts_bus._select_gpt_sovits_gpt"),
            patch("app.tts_bus._select_gpt_sovits_sovits"),
            patch("app.tts_bus.urllib_request.urlopen", return_value=response) as urlopen,
            patch("app.tts_bus._convert_wav_to_mp3"),
        ):
            _generate_gpt_sovits_audio(
                "第一句，我已经把窗户关好了。",
                "output.mp3",
                "zh",
                1.06,
                verifier,
            )

        payloads = [
            json.loads(item.args[0].data.decode("utf-8"))
            for item in urlopen.call_args_list
        ]
        self.assertEqual(payloads[0]["text"], "第一句，我已经把窗户关好了。")
        self.assertEqual(len(payloads), 1)
        verifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
