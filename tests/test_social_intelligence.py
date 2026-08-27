from __future__ import annotations

import unittest

from app.social_intelligence import appraise_social_context


class SocialIntelligenceTests(unittest.TestCase):
    def test_venting_is_met_with_presence_instead_of_unsolicited_advice(self) -> None:
        appraisal = appraise_social_context("我今天被领导骂了，真的很委屈")

        self.assertEqual(appraisal.emotion, "sadness")
        self.assertEqual(appraisal.need, "presence")
        rendered = appraisal.render()
        self.assertIn("不急着解决", rendered)
        self.assertIn("不要立刻分析原因、列清单", rendered)

    def test_explicit_help_request_gets_small_actionable_advice(self) -> None:
        appraisal = appraise_social_context("我该怎么办才好，最近压力太大了")

        self.assertEqual(appraisal.emotion, "anxiety")
        self.assertEqual(appraisal.need, "advice")
        self.assertIn("一到三个", appraisal.render())

    def test_self_deprecating_sarcasm_is_not_misread_as_joy(self) -> None:
        appraisal = appraise_social_context("我可真厉害，又把这件事搞砸了")

        self.assertEqual(appraisal.emotion, "shame")
        self.assertEqual(appraisal.need, "reduce_shame")
        self.assertNotEqual(appraisal.need, "celebration")

    def test_withdrawal_after_distress_gets_space_without_interrogation(self) -> None:
        appraisal = appraise_social_context(
            "算了，没事",
            recent_history=[{"role": "user", "content": "我今天真的很难过"}],
        )

        self.assertTrue(appraisal.mixed_signal)
        self.assertEqual(appraisal.need, "gentle_space")
        self.assertIn("不要连问", appraisal.render())

    def test_group_context_can_reveal_mixed_signal(self) -> None:
        appraisal = appraise_social_context(
            "没事",
            context_text="小明：我今天面试没通过，真的很难过\n昔夕：我听着呢",
            speaker="小明（QQ 99，普通群成员）",
        )

        self.assertTrue(appraisal.mixed_signal)
        self.assertEqual(appraisal.need, "gentle_space")

    def test_group_emotion_context_is_not_borrowed_from_another_member(self) -> None:
        appraisal = appraise_social_context(
            "没事",
            context_text="小明（群成员）：我今天真的很难过\n小红（群成员）：没事",
            speaker="小红（QQ 100，普通群成员）",
        )

        self.assertFalse(appraisal.mixed_signal)

    def test_anger_is_validated_without_escalation(self) -> None:
        appraisal = appraise_social_context("他又放我鸽子，真的气死我了")

        self.assertEqual(appraisal.emotion, "anger")
        self.assertEqual(appraisal.need, "validation_without_escalation")
        self.assertIn("不要附和辱骂", appraisal.render())
        self.assertIn("不要", appraisal.render())

    def test_complaint_about_xixi_triggers_accountability(self) -> None:
        appraisal = appraise_social_context("你刚才根本没听懂我的意思，我很失望")

        self.assertTrue(appraisal.directed_at_xixi)
        self.assertEqual(appraisal.need, "accountability")
        rendered = appraisal.render()
        self.assertIn("不要当成对第三方的抱怨", rendered)
        self.assertIn("不要强调“我本意不是这样”", rendered)

    def test_direct_provocation_allows_a_bounded_comeback(self) -> None:
        appraisal = appraise_social_context("昔夕你也太菜了吧")

        self.assertTrue(appraisal.provoked)
        self.assertEqual(appraisal.emotion, "anger")
        self.assertEqual(appraisal.need, "comeback")
        rendered = appraisal.render()
        self.assertIn("机灵地怼回去", rendered)
        self.assertIn("不用客服式劝导", rendered)
        self.assertIn("不贬低人的基本价值", rendered)

    def test_specific_complaint_still_gets_accountability_not_a_comeback(self) -> None:
        appraisal = appraise_social_context("你刚才又说错了，真笨")

        self.assertTrue(appraisal.directed_at_xixi)
        self.assertFalse(appraisal.provoked)
        self.assertEqual(appraisal.need, "accountability")

    def test_explicit_request_to_listen_suppresses_problem_solving(self) -> None:
        appraisal = appraise_social_context("先别给建议，让我把这件事说完")

        self.assertEqual(appraisal.need, "presence")
        self.assertIn("不急着解决", appraisal.render())

    def test_positive_event_is_celebrated_without_a_lecture(self) -> None:
        appraisal = appraise_social_context("我今天拿到录取通知了")

        self.assertEqual(appraisal.emotion, "joy")
        self.assertEqual(appraisal.need, "celebration")
        self.assertIn("不要马上泼冷水", appraisal.render())

    def test_repeated_distress_uses_recent_history(self) -> None:
        appraisal = appraise_social_context(
            "今天还是很焦虑，感觉压力太大了",
            recent_history=[
                {"role": "user", "content": "昨天也很焦虑，一直睡不着"},
                {"role": "assistant", "content": "我在呢。"},
            ],
        )

        self.assertTrue(appraisal.repeated)
        self.assertIn("最近对话出现过", appraisal.render())

    def test_crisis_language_triggers_direct_safety_guidance(self) -> None:
        appraisal = appraise_social_context("我真的不想活了")

        self.assertTrue(appraisal.crisis)
        self.assertEqual(appraisal.need, "safety")
        rendered = appraisal.render()
        self.assertIn("确认对方此刻是否安全", rendered)
        self.assertIn("120/110", rendered)
        self.assertIn("不要用傲娇、玩笑", rendered)

    def test_reported_crisis_line_is_not_treated_as_the_users_own_crisis(self) -> None:
        appraisal = appraise_social_context("电影里的角色说他不想活了，这段怎么理解")

        self.assertFalse(appraisal.crisis)

    def test_neutral_information_request_adds_no_social_prompt(self) -> None:
        appraisal = appraise_social_context("重庆今天多少度？")

        self.assertEqual(appraisal.emotion, "neutral")
        self.assertEqual(appraisal.render(), "")


if __name__ == "__main__":
    unittest.main()
