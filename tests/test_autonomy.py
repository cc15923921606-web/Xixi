from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.autonomy import (
    GroupAutonomy,
    group_participation_score,
    run_private_autonomy_scheduler,
)
from app.brain import Brain
from app.config import Config


class FixedRandom:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


class GroupAutonomyTests(unittest.TestCase):
    def make_config(self) -> Config:
        cfg = Config()
        cfg.qq_user_id = 1
        cfg.autonomous_group_enabled = True
        cfg.autonomous_group_ids = frozenset({123})
        cfg.autonomous_group_min_messages = 2
        cfg.autonomous_group_cooldown_s = 0
        cfg.autonomous_group_base_chance = 0.06
        cfg.autonomous_group_context_idle_s = 1800
        cfg.autonomous_group_buffer_messages = 200
        cfg.autonomous_group_context_messages = 24
        return cfg

    @staticmethod
    def raw(group_id: int, user_id: int, name: str) -> dict[str, object]:
        return {
            "group_id": group_id,
            "sender": {"user_id": user_id, "nickname": name},
        }

    def test_joins_allowed_group_after_enough_messages(self) -> None:
        now = [1000.0]
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )

        first = manager.observe(
            self.raw(123, 2, "小明"),
            "今天好累",
            directly_addressed=False,
        )
        second = manager.observe(
            self.raw(123, 3, "小红"),
            "晚上一起打游戏吗？",
            directly_addressed=False,
        )

        self.assertIsNone(first)
        self.assertIn("小明", second or "")
        self.assertIn("打游戏", second or "")

    def test_can_join_again_without_cooldown(self) -> None:
        now = [1000.0]
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )
        manager.observe(self.raw(123, 2, "甲"), "聊动漫吧", directly_addressed=False)
        self.assertIsNotNone(
            manager.observe(self.raw(123, 3, "乙"), "最近新番不错", directly_addressed=False)
        )
        manager.mark_spoke(123)
        now[0] += 20

        manager.observe(self.raw(123, 2, "甲"), "继续聊动漫", directly_addressed=False)
        result = manager.observe(self.raw(123, 3, "乙"), "这个角色很好看", directly_addressed=False)

        self.assertIsNotNone(result)

    def test_unlisted_group_is_ignored(self) -> None:
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
        )
        manager.observe(self.raw(456, 2, "甲"), "聊动漫吧", directly_addressed=False)
        result = manager.observe(self.raw(456, 3, "乙"), "一起打游戏吗", directly_addressed=False)
        self.assertIsNone(result)

    def test_old_group_context_expires(self) -> None:
        now = [1000.0]
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )
        manager.observe(
            self.raw(123, 2, "甲"),
            "刚才在聊旧游戏",
            directly_addressed=True,
        )
        now[0] += 1801
        manager.observe(
            self.raw(123, 3, "乙"),
            "现在换个新话题",
            directly_addressed=True,
        )

        context = manager.recent_context(123)

        self.assertNotIn("旧游戏", context)
        self.assertIn("新话题", context)

    def test_active_topic_survives_long_total_duration(self) -> None:
        now = [1000.0]
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )
        manager.observe(
            self.raw(123, 2, "甲"),
            "这个话题开头在讨论星空",
            directly_addressed=True,
        )
        for index in range(4):
            now[0] += 600
            manager.observe(
                self.raw(123, 3, "乙"),
                f"继续讨论星空第{index}段",
                directly_addressed=True,
            )

        context = manager.recent_context(123, query="星空")

        self.assertIn("话题开头", context)
        self.assertGreater(now[0] - 1000.0, 1800)

    def test_large_topic_retrieves_relevant_middle_message(self) -> None:
        cfg = self.make_config()
        cfg.autonomous_group_context_messages = 12
        now = [1000.0]
        manager = GroupAutonomy(
            cfg,
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )
        for index in range(40):
            message = (
                "量子猫设定是关键线索"
                if index == 18
                else f"群聊中的普通消息第{index}条"
            )
            manager.observe(
                self.raw(123, 2 + index % 2, "群友"),
                message,
                directly_addressed=True,
            )
            now[0] += 5

        context = manager.recent_context(123, query="量子猫的线索是什么")

        self.assertIn("量子猫设定是关键线索", context)
        self.assertLessEqual(len(context.splitlines()), 12)

    def test_topic_opening_survives_ring_buffer_overflow(self) -> None:
        cfg = self.make_config()
        cfg.autonomous_group_buffer_messages = 20
        cfg.autonomous_group_context_messages = 12
        now = [1000.0]
        manager = GroupAutonomy(
            cfg,
            Mock(),
            9999,
            rng=FixedRandom(0.0),  # type: ignore[arg-type]
            clock=lambda: now[0],
        )
        for index in range(35):
            message = "最初约定主角怕水" if index == 0 else f"后续剧情讨论第{index}条"
            manager.observe(
                self.raw(123, 2, "群友"),
                message,
                directly_addressed=True,
            )
            now[0] += 3

        context = manager.recent_context(123, query="主角的最初设定")

        self.assertIn("最初约定主角怕水", context)

    def test_interesting_topic_scores_above_plain_chat(self) -> None:
        plain = group_participation_score("今天吃了米饭", is_owner=False, distinct_speakers=1)
        interesting = group_participation_score(
            "这部新番动画你们觉得怎么样？",
            is_owner=False,
            distinct_speakers=2,
        )
        self.assertGreater(interesting, plain)

    def test_bot_topic_triggers_without_message_threshold_or_random_chance(self) -> None:
        cfg = self.make_config()
        cfg.autonomous_group_min_messages = 99
        manager = GroupAutonomy(
            cfg,
            Mock(),
            9999,
            rng=FixedRandom(1.0),
        )
        text = "这个机器人刚才说得挺可爱的"

        self.assertTrue(manager.message_is_about_bot(123, text))
        context = manager.observe(
            self.raw(123, 2, "小明"),
            text,
            directly_addressed=False,
            about_bot=True,
        )

        self.assertIn(text, context or "")

    def test_nickname_aliases_refer_to_bot_without_matching_longer_words(self) -> None:
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(1.0),
        )

        self.assertTrue(manager.message_is_about_bot(123, "小夕刚才在嘴硬吧"))
        self.assertTrue(manager.message_is_about_bot(123, "xx刚才的回复挺可爱"))
        self.assertTrue(manager.message_is_about_bot(123, "XX是不是害羞了"))
        self.assertFalse(manager.message_is_about_bot(123, "这件xxl衣服挺好看"))
        self.assertFalse(manager.message_is_about_bot(123, "boxx这个拼写不对"))

    def test_pronoun_continues_recent_bot_topic_but_does_not_stand_alone(self) -> None:
        manager = GroupAutonomy(
            self.make_config(),
            Mock(),
            9999,
            rng=FixedRandom(1.0),
        )
        self.assertFalse(manager.message_is_about_bot(123, "她今天吃饭了吗"))
        manager.observe(
            self.raw(123, 2, "小明"),
            "昔夕刚才的回复挺有意思",
            directly_addressed=True,
        )

        self.assertTrue(manager.message_is_about_bot(123, "她刚才是不是在嘴硬"))
        self.assertFalse(manager.message_is_about_bot(123, "那个家伙又在说什么"))
        self.assertFalse(manager.message_is_about_bot(123, "这个家伙怎么还没来"))


class BrainAutonomyTests(unittest.TestCase):
    def make_brain(self, root: Path) -> Brain:
        persona = root / "persona.txt"
        persona.write_text("你是昔夕。", encoding="utf-8")
        cfg = Config(
            root=root,
            persona_file=persona,
            logs_dir=root / "logs",
            memory_file=root / "data" / "conversations.json",
            memory_db=root / "data" / "memory.db",
            weather_enabled=False,
            use_openai=False,
        )
        with patch.object(Brain, "_init_ollama"):
            return Brain(cfg)

    def test_model_can_choose_not_to_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = self.make_brain(Path(tmp))
            brain._raw_completion = Mock(return_value="[不插话]")  # type: ignore[method-assign]
            self.assertEqual(brain.compose_autonomous_group_reply("甲：早点睡\n乙：嗯"), "")

    def test_self_related_topic_must_receive_a_direct_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = self.make_brain(Path(tmp))
            brain._raw_completion = Mock(  # type: ignore[method-assign]
                return_value="可爱什么呀，你们别当着我的面乱说。"
            )

            reply = brain.compose_autonomous_group_reply(
                "甲：这个机器人刚才说得挺可爱的",
                about_bot=True,
            )

            self.assertEqual(reply, "可爱什么呀，你们别当着我的面乱说。")
            system = brain._raw_completion.call_args.args[0]
            self.assertIn("正在明确谈论你本人", system)
            self.assertIn("这轮必须回复", system)

    def test_self_related_topic_never_uses_a_canned_failure_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = self.make_brain(Path(tmp))
            brain._raw_completion = Mock(side_effect=RuntimeError("model offline"))

            reply = brain.compose_autonomous_group_reply(
                "甲：昔夕刚才说得挺有意思",
                about_bot=True,
            )

            self.assertEqual(reply, "")

    def test_autonomous_reply_requires_recent_topic_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = self.make_brain(Path(tmp))
            brain._raw_completion = Mock(  # type: ignore[method-assign]
                return_value=(
                    '{"action":"reply","anchor":"新番动画",'
                    '"reply":"这部节奏确实挺舒服的。"}'
                )
            )

            reply = brain.compose_autonomous_group_reply(
                "甲：今晚吃什么\n乙：刚看的新番动画还不错"
            )

            self.assertEqual(reply, "这部节奏确实挺舒服的。")

    def test_autonomous_reply_rejects_missing_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = self.make_brain(Path(tmp))
            brain._raw_completion = Mock(  # type: ignore[method-assign]
                return_value=(
                    '{"action":"reply","anchor":"不存在的话题",'
                    '"reply":"突然想聊点别的。"}'
                )
            )

            reply = brain.compose_autonomous_group_reply("甲：今晚吃什么\n乙：吃火锅吧")

            self.assertEqual(reply, "")

    def test_autonomous_reply_is_remembered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = self.make_brain(Path(tmp))
            brain.remember_autonomous_reply("group:1", "这个我也玩过。", "你主动加入群聊。")
            history = brain.sessions["group:1"]
            self.assertEqual(history[-1], {"role": "assistant", "content": "这个我也玩过。"})


class PrivateAutonomySchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_scheduler_waits_and_can_resume_at_runtime(self) -> None:
        cfg = Config(autonomous_private_enabled=False)
        brain = Mock()
        brain.memory.get_state.return_value = None
        task = asyncio.create_task(
            run_private_autonomy_scheduler(cfg, brain, 1, Mock())
        )
        try:
            await asyncio.sleep(0.05)
            self.assertFalse(task.done())
            self.assertFalse(brain.memory.set_state.called)

            cfg.autonomous_private_enabled = True
            await asyncio.sleep(1.05)
            brain.memory.set_state.assert_called()
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    unittest.main()
