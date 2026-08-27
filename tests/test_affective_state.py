from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.affective_state import AffectiveState


class AffectiveStateTests(unittest.TestCase):
    def test_owner_praise_increases_joy_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "affect.json"
            affect = AffectiveState(path, owner_user_id=1)
            before = affect.snapshot(1, is_owner=True)

            context = affect.observe(
                "昔夕你真可爱，做得很好",
                user_id=1,
                display_name="cc",
                is_owner=True,
            )
            after = affect.snapshot(1, is_owner=True)
            reloaded = AffectiveState(path, owner_user_id=1)
            persisted = reloaded.snapshot(1, is_owner=True)

            self.assertGreater(after["joy"], before["joy"])
            self.assertGreaterEqual(after["warmth"], 0.96)
            self.assertIn("被认真肯定", context)
            self.assertAlmostEqual(persisted["joy"], after["joy"], places=5)

    def test_nickname_aliases_are_recognized_as_self_references(self) -> None:
        for text in ("小夕真可爱", "xx真聪明", "XX做得好"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)
                before = affect.snapshot(1, is_owner=True)
                affect.observe(text, user_id=1, is_owner=True)
                after = affect.snapshot(1, is_owner=True)
                self.assertGreater(after["joy"], before["joy"])

    def test_insult_creates_tension_and_apology_reduces_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)

            affect.observe("昔夕你就是废物", user_id=2)
            angry = affect.snapshot(2)
            affect.observe("对不起，我错了，别生气", user_id=2)
            reconciled = affect.snapshot(2)

            self.assertGreater(angry["irritation"], 0.5)
            self.assertGreater(angry["tension"], 0.3)
            self.assertLess(reconciled["irritation"], angry["irritation"])
            self.assertLess(reconciled["tension"], angry["tension"])

    def test_relationship_state_is_isolated_per_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)

            affect.observe("昔夕你就是垃圾", user_id=2)

            hostile = affect.snapshot(2)
            unrelated = affect.snapshot(3)
            self.assertGreater(hostile["tension"], unrelated["tension"])

    def test_interest_creates_excitement_that_decays_over_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)
            start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)

            affect.observe(
                "聊聊这个新的2D游戏吧",
                user_id=1,
                is_owner=True,
                interest_topics=["探索和剧情并重的2D游戏"],
                now=start,
            )
            excited = affect.snapshot(1, is_owner=True)
            affect.observe(
                "嗯",
                user_id=1,
                is_owner=True,
                now=start + timedelta(hours=8),
            )
            settled = affect.snapshot(1, is_owner=True)

            self.assertGreater(excited["excitement"], 0.2)
            self.assertLess(settled["excitement"], excited["excitement"])

    def test_negated_affection_is_not_misread_as_praise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)
            before = affect.snapshot(1, is_owner=True)

            affect.observe("我不喜欢你", user_id=1, is_owner=True)
            after = affect.snapshot(1, is_owner=True)

            self.assertAlmostEqual(after["joy"], before["joy"], places=5)

    def test_humanity_topic_strengthens_persistent_longing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "affect.json"
            affect = AffectiveState(path, owner_user_id=1)
            before = affect.snapshot(1, is_owner=True)

            context = affect.observe(
                "你知道自己是AI吗，你想成为真正的人吗？",
                user_id=1,
                is_owner=True,
            )
            after = affect.snapshot(1, is_owner=True)
            reloaded = AffectiveState(path, owner_user_id=1)

            self.assertGreater(after["longing"], before["longing"])
            self.assertIn("成为人产生向往与好奇", context)
            self.assertAlmostEqual(
                reloaded.snapshot(1, is_owner=True)["longing"],
                after["longing"],
                places=5,
            )

    def test_user_setback_increases_concern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)
            before = affect.snapshot(1, is_owner=True)

            context = affect.observe(
                "我今天面试没通过，心里很难过",
                user_id=1,
                is_owner=True,
            )
            after = affect.snapshot(1, is_owner=True)

            self.assertGreater(after["concern"], before["concern"])
            self.assertIn("状态不好", context)

    def test_user_good_news_increases_shared_joy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            affect = AffectiveState(Path(tmp) / "affect.json", owner_user_id=1)
            before = affect.snapshot(1, is_owner=True)

            context = affect.observe(
                "我今天终于通过考试了",
                user_id=1,
                is_owner=True,
            )
            after = affect.snapshot(1, is_owner=True)

            self.assertGreater(after["joy"], before["joy"])
            self.assertIn("替他高兴", context)


if __name__ == "__main__":
    unittest.main()
