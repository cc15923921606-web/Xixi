from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.config import Config
from app.environment_context import WeatherAlert
from app.qq_bridge import (
    _CASUAL_IMAGE_PROMPT,
    QQBridge,
    _VOICE_TOOL_INSTRUCTION,
    _bot_name_is_vocative,
    _clean_voice_reply,
    _image_reply_instruction,
    _parse_group_relay_request,
    _split_text_messages,
    send_group_voice,
    send_group_weather_alert,
    send_private_voice,
)
from app.vision import VisionError


class FakeBrain:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.translation_calls: list[dict[str, str]] = []
        self.relay_calls: list[dict[str, str]] = []
        self.autonomous_calls: list[dict[str, object]] = []
        self.observed_group_calls: list[dict[str, object]] = []
        self.memory = Mock()

    def think(self, text: str, **kwargs: str) -> str:
        self.calls.append({"text": text, **kwargs})
        return "知道了。"

    def translate_reply(self, text: str, target_language: str) -> str:
        self.translation_calls.append(
            {"text": text, "target_language": target_language}
        )
        translations = {
            "zh": "知道了。",
            "ja": "わかったよ。",
            "en": "Got it.",
        }
        return translations[target_language]

    def compose_group_relay_message(
        self,
        instruction: str,
        *,
        target_name: str,
        group_name: str,
    ) -> str:
        self.relay_calls.append(
            {
                "instruction": instruction,
                "target_name": target_name,
                "group_name": group_name,
            }
        )
        return "生日快乐呀，祝你新的一岁平安顺利，每天都有好心情。"

    def compose_autonomous_group_reply(
        self,
        transcript: str,
        *,
        about_bot: bool = False,
    ) -> str:
        self.autonomous_calls.append(
            {"transcript": transcript, "about_bot": about_bot}
        )
        return "在聊我呀，我听见了。"

    def remember_autonomous_reply(self, *args: object) -> None:
        return None

    def remember_observed_group_message(self, **kwargs: object) -> None:
        self.observed_group_calls.append(kwargs)


class QQBridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_image_reply_defaults_to_a_brief_personal_reaction(self) -> None:
        instruction = _image_reply_instruction("你看看这张图", True)

        self.assertIn("日常看图聊天", instruction)
        self.assertIn("自己的看法或第一反应", instruction)
        self.assertIn("一两句", instruction)
        self.assertIn("不要逐项复述", instruction)

    def test_explicit_detailed_image_request_allows_more_detail(self) -> None:
        instruction = _image_reply_instruction("仔细分析一下图里的所有细节", True)

        self.assertIn("明确要求细看", instruction)
        self.assertNotIn("只挑最值得说的一两个", instruction)

    async def test_private_image_only_is_analyzed_and_answered(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="图片1：一只白色杯子。")
        raw = {
            "post_type": "message",
            "message_type": "private",
            "sender": {"user_id": 1000000001},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/cup.png"}}
            ],
        }

        with patch("app.qq_bridge.send_private_text", new=AsyncMock()):
            await bridge.handle_message(raw)

        bridge.vision.analyze.assert_awaited_once_with(
            ["https://example.com/cup.png"],
            _CASUAL_IMAGE_PROMPT,
        )
        self.assertIn("白色杯子", brain.calls[0]["attachment_context"])
        self.assertIn("日常看图聊天", brain.calls[0]["turn_instruction"])

    async def test_private_image_question_is_passed_to_vision(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="图片1：界面显示登录失败。")
        raw = {
            "post_type": "message",
            "message_type": "private",
            "sender": {"user_id": 1000000001},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/error.png"}},
                {"type": "text", "data": {"text": "这里为什么报错？"}},
            ],
        }

        with patch("app.qq_bridge.send_private_text", new=AsyncMock()):
            await bridge.handle_message(raw)

        bridge.vision.analyze.assert_awaited_once_with(
            ["https://example.com/error.png"],
            "这里为什么报错？",
        )
        self.assertEqual(brain.calls[0]["text"], "这里为什么报错？")

    async def test_group_image_is_not_analyzed_without_addressing_bot(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="不应调用")
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "text", "data": {"text": "看看这个"}},
                {"type": "image", "data": {"url": "https://example.com/group.png"}},
            ],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()):
            await bridge.handle_message(raw)

        bridge.vision.analyze.assert_not_awaited()
        self.assertEqual(brain.calls, [])

    async def test_group_at_with_image_is_analyzed(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="图片1：一张游戏结算截图。")
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "at", "data": {"qq": "1000000002"}},
                {"type": "image", "data": {"url": "https://example.com/game.png"}},
            ],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()):
            await bridge.handle_message(raw)

        bridge.vision.analyze.assert_awaited_once()
        self.assertIn("游戏结算截图", brain.calls[0]["attachment_context"])

    async def test_group_image_then_separate_at_uses_recent_image(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="图片1：一张蓝色的游戏截图。")
        image_raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/recent.png"}}
            ],
        }
        at_raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [{"type": "at", "data": {"qq": "1000000002"}}],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()):
            await bridge.handle_message(image_raw)
            await bridge.handle_message(at_raw)

        bridge.vision.analyze.assert_awaited_once_with(
            ["https://example.com/recent.png"],
            _CASUAL_IMAGE_PROMPT,
        )
        self.assertIn("蓝色的游戏截图", brain.calls[0]["attachment_context"])

    async def test_unrelated_group_at_does_not_reuse_recent_image(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="不应调用")
        image_raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/old.png"}}
            ],
        }
        question_raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "at", "data": {"qq": "1000000002"}},
                {"type": "text", "data": {"text": "今天天气怎么样？"}},
            ],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()):
            await bridge.handle_message(image_raw)
            await bridge.handle_message(question_raw)

        bridge.vision.analyze.assert_not_awaited()
        self.assertEqual(brain.calls[0]["attachment_context"], "")

    async def test_replying_to_another_members_image_uses_replied_message(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(bot_qq_id=1000000002), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(return_value="图片1：一张角色立绘。")
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [
                {"type": "reply", "data": {"id": "456"}},
                {"type": "at", "data": {"qq": "1000000002"}},
                {"type": "text", "data": {"text": "这是谁？"}},
            ],
        }
        get_msg = AsyncMock(
            return_value={
                "status": "ok",
                "data": {
                    "message": [
                        {
                            "type": "image",
                            "data": {"url": "https://example.com/replied.png"},
                        }
                    ]
                },
            }
        )

        with (
            patch("app.qq_bridge._ob_post", new=get_msg),
            patch("app.qq_bridge.send_group_text", new=AsyncMock()),
        ):
            await bridge.handle_message(raw)

        get_msg.assert_awaited_once_with("get_msg", {"message_id": 456})
        bridge.vision.analyze.assert_awaited_once_with(
            ["https://example.com/replied.png"],
            "这是谁？",
        )
        self.assertIn("角色立绘", brain.calls[0]["attachment_context"])

    async def test_vision_failure_forbids_brain_from_guessing(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        bridge.vision.analyze = AsyncMock(side_effect=VisionError("download failed"))
        raw = {
            "post_type": "message",
            "message_type": "private",
            "sender": {"user_id": 1000000001},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/broken.png"}}
            ],
        }

        with patch("app.qq_bridge.send_private_text", new=AsyncMock()):
            await bridge.handle_message(raw)

        context = brain.calls[0]["attachment_context"]
        self.assertIn("图片读取失败", context)
        self.assertIn("严禁猜测", context)

    def test_voice_reply_removes_source_section_citations_and_urls(self) -> None:
        reply = (
            "爸爸，现在是下午五点四十七分。[1]\n"
            "来源：\n"
            "[1] 在线报时：https://example.com/time\n"
            "[2] 文字转语音：https://example.com/tts"
        )

        self.assertEqual(
            _clean_voice_reply(reply),
            "爸爸，现在是下午五点四十七分。",
        )

    def test_voice_reply_removes_labels_code_and_source_formats(self) -> None:
        reply = (
            "昔夕轻轻一笑，用中文回答道：爸爸，已经查好了。【1】\n"
            "```json\n{\"source\": \"search\", \"url\": \"https://example.com\"}\n```\n"
            "References:\n1. Official site: www.example.com"
        )

        self.assertEqual(_clean_voice_reply(reply), "爸爸，已经查好了。")

    async def test_both_delivery_keeps_sources_in_text_but_not_voice(self) -> None:
        bridge = QQBridge(Config(), 1000000001, FakeBrain())
        reply = (
            "结果已经确认。[1]\n来源：\n"
            "[1] 官方页面：https://example.com/official"
        )
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_group_text", new=send_text),
            patch("app.qq_bridge.send_group_voice", new=send_voice),
        ):
            await bridge._deliver_group(123, reply, "both")

        send_text.assert_awaited_once_with(123, reply)
        send_voice.assert_awaited_once_with(
            123,
            "结果已经确认。",
            bridge.cfg,
        )

    def test_nickname_aliases_can_directly_address_bot(self) -> None:
        self.assertTrue(_bot_name_is_vocative("小夕"))
        self.assertTrue(_bot_name_is_vocative("小夕你好"))
        self.assertTrue(_bot_name_is_vocative("xx，在吗"))
        self.assertTrue(_bot_name_is_vocative("XX你好"))
        self.assertFalse(_bot_name_is_vocative("xxl这件衣服"))

    def test_custom_assistant_name_is_used_for_qq_references(self) -> None:
        cfg = Config(
            assistant_name="星璃",
            bot_qq_id=1000000002,
            qq_group_wake_names="星璃、璃璃",
        )
        bridge = QQBridge(cfg, 1000000001, FakeBrain())

        self.assertEqual(bridge._assistant_name(), "星璃")
        self.assertIn("星璃", bridge._configured_bot_aliases())
        self.assertTrue(_bot_name_is_vocative("星璃你好", bridge._configured_bot_aliases()))
        self.assertTrue(bridge.group_autonomy.message_is_about_bot(123, "星璃今天在吗"))
        relay = _parse_group_relay_request(
            "星璃，去测试群里给小明发消息说：晚上见",
            aliases=bridge._configured_bot_aliases(),
        )
        self.assertIsNotNone(relay)

    async def test_group_at_wake_can_be_disabled(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_at_wake_enabled=False,
            qq_group_name_wake_enabled=False,
            autonomous_group_enabled=True,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "at", "data": {"qq": "1000000002"}},
                {"type": "text", "data": {"text": "昔夕你好"}},
            ],
        }
        send = AsyncMock()

        with patch("app.qq_bridge.send_group_text", new=send):
            await bridge.handle_message(raw)

        self.assertEqual(brain.calls, [])
        send.assert_not_awaited()

    async def test_group_at_wake_remains_enabled_by_default(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_at_wake_enabled=True,
            autonomous_group_enabled=False,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "at", "data": {"qq": "1000000002"}},
                {"type": "text", "data": {"text": "你好"}},
            ],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()) as send:
            await bridge.handle_message(raw)

        self.assertEqual(brain.calls[0]["text"], "你好")
        send.assert_awaited_once_with(123, "知道了。")

    async def test_group_at_only_is_ignored_when_at_wake_is_disabled(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_at_wake_enabled=False,
            autonomous_group_enabled=False,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [{"type": "at", "data": {"qq": "1000000002"}}],
        }
        send = AsyncMock()

        with patch("app.qq_bridge.send_group_text", new=send):
            await bridge.handle_message(raw)

        self.assertEqual(brain.calls, [])
        send.assert_not_awaited()

    async def test_group_name_wake_uses_live_custom_aliases(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_name_wake_enabled=True,
            qq_group_wake_names="夕夕",
            autonomous_group_enabled=False,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [{"type": "text", "data": {"text": "夕夕你好"}}],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()):
            await bridge.handle_message(raw)
            cfg.qq_group_wake_names = "小夕"
            raw["message"][0]["data"]["text"] = "小夕你好"
            await bridge.handle_message(raw)

        self.assertEqual([call["text"] for call in brain.calls], ["你好", "你好"])

    async def test_removed_default_name_no_longer_wakes_group_chat(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_name_wake_enabled=True,
            qq_group_wake_names="夕夕",
            autonomous_group_enabled=True,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [{"type": "text", "data": {"text": "小夕你好"}}],
        }
        send = AsyncMock()

        with patch("app.qq_bridge.send_group_text", new=send):
            await bridge.handle_message(raw)

        self.assertEqual(brain.calls, [])
        send.assert_not_awaited()

    async def test_group_name_wake_can_be_disabled(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_name_wake_enabled=False,
            qq_group_wake_names="昔夕、小夕、xx",
            autonomous_group_enabled=True,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [{"type": "text", "data": {"text": "昔夕你好"}}],
        }
        send = AsyncMock()

        with patch("app.qq_bridge.send_group_text", new=send):
            await bridge.handle_message(raw)

        self.assertEqual(brain.calls, [])
        send.assert_not_awaited()

    async def test_third_person_bot_discussion_still_allows_autonomous_reply(self) -> None:
        cfg = Config(
            bot_qq_id=1000000002,
            qq_group_name_wake_enabled=False,
            autonomous_group_enabled=True,
        )
        brain = FakeBrain()
        bridge = QQBridge(cfg, 1000000001, brain)
        raw = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {"type": "text", "data": {"text": "昔夕刚才说得挺可爱的"}}
            ],
        }
        send = AsyncMock()

        with patch("app.qq_bridge.send_group_text", new=send):
            await bridge.handle_message(raw)

        self.assertEqual(brain.calls, [])
        self.assertEqual(len(brain.autonomous_calls), 1)
        send.assert_awaited_once_with(123, "在聊我呀，我听见了。")

    def test_group_relay_request_parses_natural_command(self) -> None:
        request = _parse_group_relay_request(
            "去2000000001群里给小明发消息说：今晚八点开黑"
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertIn("2000000001", request.group_selector)
        self.assertEqual(request.member_selector, "小明")
        self.assertEqual(request.message, "今晚八点开黑")

    def test_group_relay_request_parses_semantic_task_with_embedded_qq(self) -> None:
        request = _parse_group_relay_request(
            "宝贝，你去这个群里2000000001给qq号是1000000003的男孩子祝福他生日快乐可以吗"
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertIn("2000000001", request.group_selector)
        self.assertIn("1000000003", request.member_selector)
        self.assertEqual(request.message, "祝福他生日快乐可以吗")
        self.assertTrue(request.compose_message)

    async def test_owner_can_relay_private_command_to_group_member(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        post = AsyncMock(
            side_effect=[
                {
                    "status": "ok",
                    "data": [{"group_id": 2000000001, "group_name": "测试群"}],
                },
                {
                    "status": "ok",
                    "data": [
                        {"user_id": 99, "card": "小明", "nickname": "明明"}
                    ],
                },
                {"status": "ok"},
            ]
        )
        private_reply = AsyncMock()
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }

        with (
            patch("app.qq_bridge._ob_post", new=post),
            patch("app.qq_bridge.send_private_text", new=private_reply),
        ):
            await bridge._handle_private(
                raw,
                "去2000000001群里给小明发消息说：今晚八点开黑",
            )

        self.assertEqual(brain.calls, [])
        self.assertEqual(post.await_args_list[0].args, ("get_group_list", {}))
        self.assertEqual(
            post.await_args_list[1].args,
            ("get_group_member_list", {"group_id": 2000000001}),
        )
        sent = post.await_args_list[2].args
        self.assertEqual(sent[0], "send_group_msg")
        self.assertEqual(sent[1]["group_id"], 2000000001)
        self.assertEqual(sent[1]["message"][0]["data"]["qq"], "99")
        self.assertEqual(sent[1]["message"][1]["data"]["text"], " 今晚八点开黑")
        self.assertIn("发好了", private_reply.await_args.args[1])

    async def test_owner_semantic_relay_is_composed_and_sent(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        post = AsyncMock(
            side_effect=[
                {
                    "status": "ok",
                    "data": [{"group_id": 2000000001, "group_name": "🦌"}],
                },
                {
                    "status": "ok",
                    "data": [
                        {
                            "user_id": 1000000003,
                            "card": "cc爹爹",
                            "nickname": "惜",
                        }
                    ],
                },
                {"status": "ok"},
                {"status": "ok"},
            ]
        )
        private_reply = AsyncMock()
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }

        with (
            patch("app.qq_bridge._ob_post", new=post),
            patch("app.qq_bridge.send_private_text", new=private_reply),
        ):
            await bridge._handle_private(
                raw,
                "宝贝，你去这个群里2000000001给qq号是1000000003的男孩子祝福他生日快乐可以吗",
            )

        self.assertEqual(brain.calls, [])
        self.assertEqual(len(brain.relay_calls), 1)
        self.assertEqual(
            brain.relay_calls[0]["instruction"],
            "祝福他生日快乐可以吗",
        )
        sent = post.await_args_list[2].args[1]
        self.assertEqual(sent["message"][0]["data"]["qq"], "1000000003")
        self.assertIn("生日快乐", sent["message"][1]["data"]["text"])
        self.assertIn("好心情", post.await_args_list[3].args[1]["message"])
        self.assertIn("发好了", private_reply.await_args.args[1])

    async def test_multiple_relays_execute_before_follow_up_answer(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        group = {
            "status": "ok",
            "data": [{"group_id": 2000000001, "group_name": "测试群"}],
        }
        members = {
            "status": "ok",
            "data": [
                {"user_id": 98, "card": "小明"},
                {"user_id": 99, "card": "小红"},
            ],
        }
        post = AsyncMock(
            side_effect=[
                group,
                members,
                {"status": "ok"},
                group,
                members,
                {"status": "ok"},
            ]
        )
        private_reply = AsyncMock()
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }

        with (
            patch("app.qq_bridge._ob_post", new=post),
            patch("app.qq_bridge.send_private_text", new=private_reply),
        ):
            await bridge._handle_private(
                raw,
                "去2000000001群里给小明发消息说今晚开黑，"
                "然后给小红发消息说明天见，最后告诉我结果",
            )

        sent_members = [
            call.args[1]["message"][0]["data"]["qq"]
            for call in post.await_args_list
            if call.args[0] == "send_group_msg"
        ]
        self.assertEqual(sent_members, ["98", "99"])
        self.assertEqual(len(brain.calls), 1)
        turn_instruction = brain.calls[0]["turn_instruction"]
        self.assertIn("@小明", turn_instruction)
        self.assertIn("@小红", turn_instruction)
        private_reply.assert_awaited_once_with(1000000001, "知道了。")

    async def test_group_relay_refuses_ambiguous_member_name(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        post = AsyncMock(
            side_effect=[
                {
                    "status": "ok",
                    "data": [{"group_id": 2000000001, "group_name": "测试群"}],
                },
                {
                    "status": "ok",
                    "data": [
                        {"user_id": 98, "card": "小明"},
                        {"user_id": 99, "card": "小明"},
                    ],
                },
            ]
        )
        private_reply = AsyncMock()
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }

        with (
            patch("app.qq_bridge._ob_post", new=post),
            patch("app.qq_bridge.send_private_text", new=private_reply),
        ):
            await bridge._handle_private(
                raw,
                "去2000000001群里给小明发消息说：今晚八点开黑",
            )

        self.assertEqual(post.await_count, 2)
        self.assertIn("重名", private_reply.await_args.args[1])
        self.assertEqual(brain.calls, [])

    async def test_quoted_group_relay_is_explained_without_sending(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }

        with (
            patch("app.qq_bridge._ob_post", new=AsyncMock()) as post,
            patch("app.qq_bridge.send_private_text", new=AsyncMock()),
        ):
            await bridge._handle_private(
                raw,
                "解释一下“去2000000001群里给小明发消息说今晚开黑”这句话",
            )

        post.assert_not_awaited()
        self.assertEqual(len(brain.calls), 1)
        frame = brain.calls[0]["instruction_frame"]
        self.assertEqual(frame.action, "explain")
        self.assertFalse(frame.is_group_relay)

    async def test_non_owner_cannot_use_group_relay(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "private",
            "sender": {"user_id": 99},
        }

        with patch("app.qq_bridge._ob_post", new=AsyncMock()) as post:
            await bridge._handle_private(
                raw,
                "去2000000001群里给小明发消息说：今晚八点开黑",
            )

        post.assert_not_awaited()
        self.assertEqual(brain.calls, [])

    async def test_weather_alert_individually_mentions_humans_only(self) -> None:
        response = {
            "status": "ok",
            "data": [
                {"user_id": 1000000002},
                {"user_id": 88},
                {"user_id": 1000000001, "nickname": "测试昵称"},
                {"user_id": 99},
            ],
        }
        post = AsyncMock(
            side_effect=[response, {"status": "ok"}, {"status": "ok"}]
        )

        with patch("app.qq_bridge._ob_post", new=post):
            await send_group_weather_alert(
                123,
                WeatherAlert(
                    fingerprint="test",
                    location="重庆",
                    level=4,
                    title="雷暴风险",
                    detail="未来约12小时内预计有雷暴",
                    advice="尽量待在室内。",
                ),
                cfg=Config(bot_qq_id=1000000002, qq_user_id=1000000001),
                excluded_user_ids=frozenset({88}),
            )

        sent_messages = [call.args[1] for call in post.await_args_list[1:]]
        mentions = [message["message"][0]["data"]["qq"] for message in sent_messages]
        self.assertEqual(mentions, ["1000000001", "99"])
        self.assertTrue(all(message["group_id"] == 123 for message in sent_messages))
        self.assertTrue(all(len(message["message"]) == 2 for message in sent_messages))
        texts = [message["message"][1]["data"]["text"] for message in sent_messages]
        self.assertEqual(len(set(texts)), 2)
        self.assertIn("爸爸", texts[0])
        self.assertNotIn("爸爸", texts[1])

    def test_text_reply_is_split_by_sentence(self) -> None:
        self.assertEqual(
            _split_text_messages("第一句话。第二句话！第三句话。"),
            ["第一句话。", "第二句话！", "第三句话。"],
        )

    def test_text_reply_has_no_default_message_count_limit(self) -> None:
        text = "第一句。第二句。第三句。第四句。第五句。"

        with patch("app.qq_bridge._TEXT_MAX_MESSAGES", 0):
            chunks = _split_text_messages(text)

        self.assertEqual(chunks, ["第一句。", "第二句。", "第三句。", "第四句。", "第五句。"])

    def test_short_reply_stays_in_one_message(self) -> None:
        self.assertEqual(_split_text_messages("知道了，笨蛋。"), ["知道了，笨蛋。"])

    def test_closing_quote_stays_with_sentence(self) -> None:
        self.assertEqual(
            _split_text_messages("她说：“知道了。”我就去睡觉。"),
            ["她说：“知道了。”", "我就去睡觉。"],
        )

    async def test_group_context_names_each_sender(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(
            Config(bot_qq_id=1000000002, owner_display_name="cc"),
            1000000001,
            brain,
        )
        first = {
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [{"type": "text", "data": {"text": "昔夕记住这是我的话"}}],
        }
        second = {
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 99, "card": "小明"},
            "message": [{"type": "text", "data": {"text": "昔夕你好"}}],
        }

        with patch("app.qq_bridge.send_group_text", new=AsyncMock()):
            await bridge._handle_group(first, "昔夕记住这是我的话")
            await bridge._handle_group(second, "昔夕你好")

        self.assertEqual(brain.calls[0]["session_id"], "group:123")
        self.assertEqual(brain.calls[1]["session_id"], "group:123")
        self.assertIn("主人 cc", brain.calls[0]["speaker"])
        self.assertTrue(brain.calls[0]["is_owner"])
        self.assertIn("小明", brain.calls[1]["speaker"])
        self.assertIn("普通群成员", brain.calls[1]["speaker"])
        self.assertFalse(brain.calls[1]["is_owner"])
        self.assertEqual(brain.calls[1]["user_id"], 99)
        self.assertIn("这是我的话", brain.calls[1]["turn_instruction"])
        self.assertIn("这是我的话", brain.calls[1]["context_text"])

    async def test_group_discussing_bot_triggers_without_direct_mention(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "group",
            "group_id": 2000000001,
            "sender": {"user_id": 99, "nickname": "小明"},
            "message": [
                {
                    "type": "text",
                    "data": {"text": "这个机器人刚才说得挺可爱的"},
                }
            ],
        }
        send = AsyncMock()

        with patch("app.qq_bridge.send_group_text", new=send):
            await bridge._handle_group(raw, "这个机器人刚才说得挺可爱的")

        self.assertEqual(brain.calls, [])
        self.assertEqual(len(brain.autonomous_calls), 1)
        self.assertTrue(brain.autonomous_calls[0]["about_bot"])
        self.assertEqual(len(brain.observed_group_calls), 1)
        self.assertEqual(brain.observed_group_calls[0]["group_id"], 2000000001)
        self.assertEqual(brain.observed_group_calls[0]["user_id"], 99)
        self.assertIn("小明", str(brain.observed_group_calls[0]["speaker"]))
        self.assertIn("机器人刚才说得挺可爱", str(brain.observed_group_calls[0]["content"]))
        send.assert_awaited_once_with(2000000001, "在聊我呀，我听见了。")

    async def test_voice_instruction_is_transient(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [{"type": "text", "data": {"text": "昔夕用语音说你好"}}],
        }

        with patch("app.qq_bridge.send_group_voice", new=AsyncMock()):
            await bridge._handle_group(raw, "昔夕用语音说你好")

        self.assertEqual(brain.calls[0]["text"], "用语音说你好")
        self.assertIn(_VOICE_TOOL_INSTRUCTION, brain.calls[0]["turn_instruction"])
        self.assertIn("当前群聊话题的自适应上下文", brain.calls[0]["turn_instruction"])

    async def test_indirect_voice_wording_can_never_send_group_text(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [
                {
                    "type": "text",
                    "data": {
                        "text": "昔夕用语音给爸爸我说一句晚安吧，我要休息了"
                    },
                }
            ],
        }
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_group_text", new=send_text),
            patch("app.qq_bridge.send_group_voice", new=send_voice),
        ):
            await bridge._handle_group(
                raw,
                "昔夕用语音给爸爸我说一句晚安吧，我要休息了",
            )

        send_text.assert_not_awaited()
        send_voice.assert_awaited_once_with(
            123,
            "知道了。",
            bridge.cfg,
        )
        self.assertIn(_VOICE_TOOL_INSTRUCTION, brain.calls[0]["turn_instruction"])

    async def test_explicit_voice_medium_always_bypasses_group_text_sender(self) -> None:
        requests = (
            "昔夕用语音告诉我现在几点了",
            "昔夕用语音把这件事重新处理一遍",
        )

        for request in requests:
            with self.subTest(request=request):
                brain = FakeBrain()
                bridge = QQBridge(Config(), 1000000001, brain)
                raw = {
                    "message_type": "group",
                    "group_id": 123,
                    "sender": {"user_id": 1000000001, "nickname": "cc"},
                    "message": [{"type": "text", "data": {"text": request}}],
                }
                send_text = AsyncMock()
                send_voice = AsyncMock()

                with (
                    patch("app.qq_bridge.send_group_text", new=send_text),
                    patch("app.qq_bridge.send_group_voice", new=send_voice),
                ):
                    await bridge._handle_group(raw, request)

                send_text.assert_not_awaited()
                send_voice.assert_awaited_once_with(
                    123,
                    "知道了。",
                    bridge.cfg,
                )
                self.assertIn(
                    _VOICE_TOOL_INSTRUCTION,
                    brain.calls[0]["turn_instruction"],
                )

    async def test_private_voice_contract_never_calls_text_sender(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_private_text", new=send_text),
            patch("app.qq_bridge.send_private_voice", new=send_voice),
        ):
            await bridge._handle_private(raw, "别打字，直接说给我听")

        send_text.assert_not_awaited()
        send_voice.assert_awaited_once_with(
            1000000001,
            "知道了。",
            bridge.cfg,
        )

    async def test_private_voice_sender_ignores_legacy_chinese_verifier(self) -> None:
        cfg = Config()
        verifier = Mock()
        generate = AsyncMock()
        post = AsyncMock()

        with (
            patch("app.qq_bridge.generate_tts_audio", new=generate),
            patch("app.qq_bridge._ob_post", new=post),
        ):
            await send_private_voice(
                1000000001,
                "你好呀。",
                cfg,
                chinese_verifier=verifier,
            )

        self.assertNotIn("chinese_verifier", generate.await_args.kwargs)
        self.assertEqual(generate.await_args.kwargs["forced_language"], "zh")
        post.assert_awaited_once()

    async def test_group_voice_sender_ignores_legacy_chinese_verifier(self) -> None:
        cfg = Config()
        verifier = Mock()
        generate = AsyncMock()
        post = AsyncMock()

        with (
            patch("app.qq_bridge.generate_tts_audio", new=generate),
            patch("app.qq_bridge._ob_post", new=post),
        ):
            await send_group_voice(
                123,
                "大家好。",
                cfg,
                chinese_verifier=verifier,
            )

        self.assertNotIn("chinese_verifier", generate.await_args.kwargs)
        self.assertEqual(generate.await_args.kwargs["forced_language"], "zh")
        post.assert_awaited_once()

    async def test_private_voice_uses_persisted_japanese_language(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(voice_language="ja"), 1000000001, brain)
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_private_text", new=send_text),
            patch("app.qq_bridge.send_private_voice", new=send_voice),
        ):
            await bridge._handle_private(raw, "别打字，直接说给我听")

        send_text.assert_not_awaited()
        self.assertEqual(
            brain.translation_calls,
            [{"text": "知道了。", "target_language": "ja"}],
        )
        send_voice.assert_awaited_once_with(1000000001, "わかったよ。", bridge.cfg)

    async def test_group_voice_uses_persisted_english_language(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(voice_language="en"), 1000000001, brain)
        send_voice = AsyncMock()

        with patch("app.qq_bridge.send_group_voice", new=send_voice):
            await bridge._deliver_group(
                123,
                "知道了。",
                "voice",
                reply_language="zh",
            )

        self.assertEqual(
            brain.translation_calls,
            [{"text": "知道了。", "target_language": "en"}],
        )
        send_voice.assert_awaited_once_with(123, "Got it.", bridge.cfg)

    async def test_private_chinese_and_japanese_voice_plan_sends_only_two_voices(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_private_text", new=send_text),
            patch("app.qq_bridge.send_private_voice", new=send_voice),
        ):
            await bridge._handle_private(raw, "就春天用中日语音各发一条")

        self.assertEqual(len(brain.calls), 1)
        self.assertEqual(brain.calls[0]["instruction_frame"].response_language, "zh")
        self.assertEqual(brain.calls[0]["instruction_frame"].output_plan, ())
        self.assertIn("当前只生成第1项的中文内容母稿", brain.calls[0]["turn_instruction"])
        self.assertEqual(
            brain.translation_calls,
            [{"text": "知道了。", "target_language": "ja"}],
        )
        send_text.assert_not_awaited()
        self.assertEqual(
            [call.args[1] for call in send_voice.await_args_list],
            ["知道了。", "わかったよ。"],
        )
        self.assertEqual(
            [call.kwargs["language"] for call in send_voice.await_args_list],
            ["zh", "ja"],
        )

    async def test_group_multi_output_plan_can_send_chinese_text_and_japanese_voice(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "group",
            "group_id": 123,
            "sender": {"user_id": 1000000001, "nickname": "cc"},
            "message": [
                {
                    "type": "text",
                    "data": {
                        "text": "昔夕分别用中文发文字，日语发语音介绍春天"
                    },
                }
            ],
        }
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_group_text", new=send_text),
            patch("app.qq_bridge.send_group_voice", new=send_voice),
        ):
            await bridge._handle_group(
                raw,
                "昔夕分别用中文发文字，日语发语音介绍春天",
            )

        send_text.assert_awaited_once_with(123, "知道了。")
        send_voice.assert_awaited_once()
        self.assertEqual(send_voice.await_args.args[:2], (123, "わかったよ。"))
        self.assertEqual(brain.translation_calls[0]["target_language"], "ja")

    async def test_quoted_voice_instruction_stays_text_only(self) -> None:
        brain = FakeBrain()
        bridge = QQBridge(Config(), 1000000001, brain)
        raw = {
            "message_type": "private",
            "sender": {"user_id": 1000000001},
        }
        send_text = AsyncMock()
        send_voice = AsyncMock()

        with (
            patch("app.qq_bridge.send_private_text", new=send_text),
            patch("app.qq_bridge.send_private_voice", new=send_voice),
        ):
            await bridge._handle_private(raw, "他说“给我发语音”是什么意思")

        send_text.assert_awaited_once()
        send_voice.assert_not_awaited()
        self.assertEqual(brain.calls[0]["instruction_frame"].delivery_mode, "text")


if __name__ == "__main__":
    unittest.main()
