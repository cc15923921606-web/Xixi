from __future__ import annotations

import unittest

from app.instruction_frame import analyze_instruction


class InstructionFrameTests(unittest.TestCase):
    def test_third_party_research_keeps_subject_and_action(self) -> None:
        frame = analyze_instruction("去查一下某某是怎么介绍自己的")

        self.assertEqual(frame.action, "research")
        self.assertEqual(frame.target, "某某")
        self.assertEqual(frame.reflexive_subject, "某某")
        self.assertFalse(frame.is_self_intro)
        self.assertEqual(frame.side_effect, "none")

    def test_direct_self_intro_is_distinct_from_composing_one_for_user(self) -> None:
        xixi = analyze_instruction("小夕，给大家简单做个自我介绍")
        draft = analyze_instruction("帮我写一段求职自我介绍")

        self.assertTrue(xixi.is_self_intro)
        self.assertEqual(xixi.target, "昔夕")
        self.assertEqual(draft.action, "compose")
        self.assertFalse(draft.is_self_intro)
        self.assertEqual(draft.target, "给用户使用的自我介绍文本")

    def test_quoted_commands_are_data_not_actions(self) -> None:
        frame = analyze_instruction("他说“用日语回复并发语音”是什么意思")

        self.assertEqual(frame.action, "explain")
        self.assertEqual(frame.response_language, "zh")
        self.assertEqual(frame.delivery_mode, "text")
        self.assertEqual(frame.side_effect, "none")
        self.assertEqual(len(frame.quoted_spans), 1)

    def test_quoted_group_relay_does_not_gain_side_effect(self) -> None:
        frame = analyze_instruction(
            "解释一下“去2000000001群里给小明发消息说今晚开黑”这句话"
        )

        self.assertEqual(frame.action, "explain")
        self.assertFalse(frame.is_group_relay)
        self.assertEqual(frame.side_effect, "none")

    def test_delivery_and_language_are_parsed_together(self) -> None:
        frame = analyze_instruction("文字和语音都发，用英语说你好")

        self.assertEqual(frame.response_language, "en")
        self.assertEqual(frame.delivery_mode, "both")

    def test_compact_chinese_japanese_voice_request_creates_two_outputs(self) -> None:
        frame = analyze_instruction("就春天用中日语音各发一条")

        self.assertEqual(
            [(item.language, item.delivery_mode) for item in frame.output_plan],
            [("zh", "voice"), ("ja", "voice")],
        )
        self.assertEqual(frame.response_language, "zh")
        self.assertEqual(frame.delivery_mode, "voice")

    def test_separate_does_not_get_misread_as_voice_or_language_negation(self) -> None:
        frame = analyze_instruction("分别用中文和日语各发一条语音介绍春天")

        self.assertEqual(
            [(item.language, item.delivery_mode) for item in frame.output_plan],
            [("zh", "voice"), ("ja", "voice")],
        )

        voice_before_action = analyze_instruction("用中文和日语语音各发一条介绍春天")
        self.assertEqual(
            [
                (item.language, item.delivery_mode)
                for item in voice_before_action.output_plan
            ],
            [("zh", "voice"), ("ja", "voice")],
        )

    def test_multi_output_plan_can_mix_text_and_voice(self) -> None:
        frame = analyze_instruction("用中文发文字，日语发语音介绍春天")

        self.assertEqual(
            [(item.language, item.delivery_mode) for item in frame.output_plan],
            [("zh", "text"), ("ja", "voice")],
        )

    def test_languages_can_be_mixed_inside_one_reply_when_explicitly_requested(self) -> None:
        frame = analyze_instruction(
            "昔夕你用中文+英文+日文回我一句话，放在一句话里面"
        )

        self.assertEqual(frame.mixed_languages, ("zh", "en", "ja"))
        self.assertTrue(frame.uses_mixed_languages)
        self.assertEqual(frame.output_plan, ())
        self.assertEqual(frame.delivery_mode, "text")
        rendered = frame.render_for_model()
        self.assertIn("同一条回复", rendered)
        self.assertIn("中文、英语、日语", rendered)

    def test_separate_multilingual_outputs_do_not_enable_mixed_language_mode(self) -> None:
        frame = analyze_instruction("用中文、英文、日文分别各发一条回复")

        self.assertEqual(frame.mixed_languages, ())
        self.assertEqual(
            [item.language for item in frame.output_plan],
            ["zh", "en", "ja"],
        )

    def test_translation_target_sets_output_language(self) -> None:
        japanese = analyze_instruction("把“你好”翻译成日语")
        english = analyze_instruction("把这段文字改成更自然的英文")

        self.assertEqual(japanese.action, "translate")
        self.assertEqual(japanese.response_language, "ja")
        self.assertEqual(english.action, "translate")
        self.assertEqual(english.response_language, "en")

    def test_discussing_language_or_voice_does_not_activate_it(self) -> None:
        retrospective_language = analyze_instruction("为什么你刚才用日语回答我？")
        retrospective_voice = analyze_instruction("你刚才为什么发语音？")
        reported = analyze_instruction("他说用日语回复并发语音，这正常吗？")

        self.assertEqual(retrospective_language.action, "explain")
        self.assertEqual(retrospective_language.response_language, "zh")
        self.assertEqual(retrospective_voice.delivery_mode, "text")
        self.assertEqual(reported.response_language, "zh")
        self.assertEqual(reported.delivery_mode, "text")
        self.assertEqual(reported.output_plan, ())

    def test_explicit_modifier_after_question_remains_executable(self) -> None:
        frame = analyze_instruction("为什么天空是蓝的？请用日语发语音回答")

        self.assertEqual(frame.response_language, "ja")
        self.assertEqual(frame.delivery_mode, "voice")

    def test_voice_negation_wins(self) -> None:
        frame = analyze_instruction("不要发语音，只发文字")
        self.assertEqual(frame.delivery_mode, "text")

    def test_voice_request_allows_words_between_voice_and_speak(self) -> None:
        frame = analyze_instruction("用语音给爸爸我说一句晚安吧，我要休息了")

        self.assertEqual(frame.delivery_mode, "voice")

    def test_common_audible_requests_are_voice_only(self) -> None:
        requests = (
            "给我发条语音说晚安",
            "用声音给我念一下这句话",
            "说一段语音哄我睡觉",
            "用语音来一句欢迎回来",
            "把这段话念出来给我听",
            "我想听你说一句欢迎回来",
            "开麦说句你好",
            "你能发语音回答吗",
            "别打字，直接说给我听",
            "今晚就语音吧",
            "用语音背一首古诗给我听",
            "朗诵一首诗给我听",
            "用声音吟诵这段词",
        )

        for request in requests:
            with self.subTest(request=request):
                self.assertEqual(analyze_instruction(request).delivery_mode, "voice")

    def test_generic_content_actions_accept_voice_delivery(self) -> None:
        requests = (
            "用语音告诉我现在几点了",
            "用语音告诉我现在是什么时候了",
            "用语音告诉我现在是啥时候了，我可能从未来穿越到远古时代了",
            "用语音解释一下这个概念",
            "请用语音介绍这部动漫",
            "用语音汇报查询结果",
            "用语音播报今天的天气",
            "用语音总结刚才的内容",
            "用语音回答我的问题",
            "用语音",
        )

        for request in requests:
            with self.subTest(request=request):
                self.assertEqual(analyze_instruction(request).delivery_mode, "voice")

    def test_explicit_voice_medium_does_not_depend_on_known_action_verbs(self) -> None:
        requests = (
            "用语音把刚才那件事重新处理一遍",
            "以后所有回答都改用语音",
            "这次通过语音给我结果",
            "请以语音的形式继续",
            "把上一条转成语音版",
            "给我来个音频版",
            "我要语音",
            "还是语音吧",
            "我说的是语音",
            "把刚才那句重新发成语音",
        )

        for request in requests:
            with self.subTest(request=request):
                self.assertEqual(analyze_instruction(request).delivery_mode, "voice")

    def test_voice_implementation_discussion_stays_text_only(self) -> None:
        messages = (
            "为什么用语音告诉别人会更有礼貌？",
            "语音播报天气要怎么实现？",
            "我在研究语音回复的实现原理",
            "“用语音告诉我现在几点了”这句话是什么意思",
        )

        for message in messages:
            with self.subTest(message=message):
                frame = analyze_instruction(message)
                self.assertEqual(frame.delivery_mode, "text")
                self.assertNotEqual(frame.action, "speak")

    def test_voice_mentions_by_other_actors_or_as_preferences_stay_text(self) -> None:
        messages = (
            "我喜欢用语音和朋友聊天",
            "他用语音告诉我结果了",
            "我正在用语音开会",
            "我想知道怎么用语音播报天气",
            "用语音模块怎么配置",
            "用语音识别这段录音需要什么模型",
            "检查语音功能",
            "语音请求为什么没生效",
            "你刚才用语音告诉我了",
            "不要用语音回答，只发文字",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(analyze_instruction(message).delivery_mode, "text")

    def test_discussing_voice_does_not_request_voice_delivery(self) -> None:
        messages = (
            "我喜欢你的语音",
            "你刚才发的语音很好听",
            "为什么你刚才发语音？",
            "语音和文字有什么区别？",
            "用语音这件事先不用，你打字回答",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(analyze_instruction(message).delivery_mode, "text")

    def test_memory_side_effect_requires_direct_instruction(self) -> None:
        remember = analyze_instruction("记住我最喜欢的游戏是空洞骑士")
        question = analyze_instruction("你记住了吗？")
        decline = analyze_instruction("不要记住这句话")
        quoted = analyze_instruction("“记住我喜欢苹果”这句话是什么意思")

        self.assertEqual(remember.memory_operation, "remember")
        self.assertEqual(remember.side_effect, "memory_remember")
        self.assertEqual(question.memory_operation, "none")
        self.assertEqual(question.side_effect, "none")
        self.assertEqual(decline.memory_operation, "decline")
        self.assertEqual(decline.side_effect, "none")
        self.assertEqual(quoted.memory_operation, "none")

    def test_text_rewrite_is_not_memory_correction(self) -> None:
        frame = analyze_instruction("把这段文字改成更自然的英文")

        self.assertEqual(frame.memory_operation, "none")
        self.assertEqual(frame.side_effect, "none")

    def test_direct_relay_and_how_to_question_are_distinct(self) -> None:
        relay = analyze_instruction("去2000000001群里给小明发消息说今晚八点开黑")
        how_to = analyze_instruction("怎么去QQ群里给别人发消息？")

        self.assertTrue(relay.is_group_relay)
        self.assertEqual(relay.side_effect, "group_message")
        self.assertFalse(how_to.is_group_relay)
        self.assertEqual(how_to.side_effect, "none")

    def test_frame_render_exposes_one_consistent_task(self) -> None:
        rendered = analyze_instruction("查一下鲁迅如何介绍自己").render_for_model()

        self.assertIn("程序识别的主要动作：查询目标信息", rendered)
        self.assertIn("目标对象或内容：鲁迅", rendered)
        self.assertIn("‘自己’的指代：鲁迅", rendered)
        self.assertIn("允许的副作用：无", rendered)
        self.assertIn("启发式；不替代用户原话和最近对话", rendered)
        self.assertIn("若与原话明显冲突，以原话为准", rendered)

    def test_reflexive_subject_is_tracked_outside_search(self) -> None:
        analyze = analyze_instruction("分析一下她介绍自己的方式")
        compose = analyze_instruction("帮我写一段他向老师介绍自己的话")

        self.assertEqual(analyze.action, "analyze")
        self.assertEqual(analyze.reflexive_subject, "她")
        self.assertFalse(analyze.is_self_intro)
        self.assertEqual(compose.action, "compose")
        self.assertEqual(compose.reflexive_subject, "他")
        self.assertFalse(compose.is_self_intro)

    def test_contrast_correction_negates_wrong_action_and_keeps_real_target(self) -> None:
        frame = analyze_instruction(
            "不是让你介绍自己，我是让你查亚托莉怎么介绍自己"
        )

        self.assertEqual(frame.action, "research")
        self.assertEqual(frame.target, "亚托莉")
        self.assertEqual(frame.reflexive_subject, "亚托莉")
        self.assertEqual(frame.correction_target, "亚托莉")
        self.assertIn("self_introduce", frame.negated_actions)
        self.assertFalse(frame.is_self_intro)

    def test_multistep_request_preserves_order_and_output_constraints(self) -> None:
        frame = analyze_instruction(
            "查一下空洞骑士丝之歌的信息，整理成三点，用中文文字回复"
        )

        self.assertEqual(frame.action, "research")
        self.assertEqual(frame.secondary_actions, ("summarize",))
        self.assertEqual(frame.target, "空洞骑士丝之歌")
        self.assertEqual(frame.response_language, "zh")
        self.assertEqual(frame.delivery_mode, "text")
        self.assertTrue(any("三点" in item for item in frame.constraints))

    def test_contextual_correction_is_exposed_without_inventing_an_action(self) -> None:
        frame = analyze_instruction("我问的是亚托莉，不是昔夕")

        self.assertEqual(frame.action, "chat")
        self.assertEqual(frame.speech_act, "correction")
        self.assertEqual(frame.correction_target, "亚托莉")
        self.assertIn("用户纠正后的目标：亚托莉", frame.render_for_model())

    def test_explain_then_example_is_a_two_step_request(self) -> None:
        frame = analyze_instruction("先解释这句话，再给一个简单例子")

        self.assertEqual(frame.action, "explain")
        self.assertEqual(frame.secondary_actions, ("exemplify",))

    def test_negated_language_is_not_selected(self) -> None:
        frame = analyze_instruction("用日语这件事先不用，你用中文解释")

        self.assertEqual(frame.action, "explain")
        self.assertEqual(frame.response_language, "zh")
        self.assertIn("不使用日语", frame.constraints)

    def test_epistemic_constraints_are_preserved(self) -> None:
        frame = analyze_instruction(
            "查一下这个消息的来源，查不到就直接说不知道，不要编"
        )

        self.assertEqual(frame.action, "research")
        self.assertIn("查不到可靠信息时明确说不知道", frame.constraints)
        self.assertIn("不得编造或猜测信息", frame.constraints)

    def test_reported_voice_command_stays_data_before_direct_explanation(self) -> None:
        frame = analyze_instruction("他说让你发语音，不过你只需要解释这句话")

        self.assertEqual(frame.action, "explain")
        self.assertEqual(frame.delivery_mode, "text")
        self.assertEqual(frame.side_effect, "none")
        self.assertTrue(frame.reported_command)

    def test_nested_why_is_content_of_analysis_not_a_new_primary_action(self) -> None:
        frame = analyze_instruction(
            "分析她为什么这样介绍自己，然后总结她的表达特点"
        )

        self.assertEqual(frame.action, "analyze")
        self.assertEqual(frame.secondary_actions, ("summarize",))
        self.assertEqual(frame.reflexive_subject, "她")

    def test_negated_group_relay_never_gains_a_side_effect(self) -> None:
        frame = analyze_instruction(
            "不要去2000000001群里给小明发消息说今晚开黑"
        )

        self.assertFalse(frame.is_group_relay)
        self.assertEqual(frame.side_effect, "none")
        self.assertIn("relay", frame.negated_actions)

    def test_general_pipeline_becomes_ordered_executable_steps(self) -> None:
        frame = analyze_instruction(
            "查一下空洞骑士丝之歌的信息，整理成三点，再翻译成日语"
        )

        self.assertEqual(
            [step.action for step in frame.task_plan],
            ["research", "summarize", "translate"],
        )
        self.assertEqual(frame.task_plan[0].target, "空洞骑士丝之歌")
        self.assertEqual(frame.task_plan[1].depends_on, (1,))
        self.assertEqual(frame.task_plan[2].depends_on, (2,))
        self.assertTrue(frame.requires_completion_review)

    def test_repeated_generic_actions_are_not_deduplicated(self) -> None:
        frame = analyze_instruction("先回答第一个问题，再回答第二个问题")

        self.assertEqual(len(frame.content_steps), 2)
        self.assertEqual(
            [step.instruction for step in frame.content_steps],
            ["回答第一个问题", "回答第二个问题"],
        )

    def test_memory_and_recommendation_are_distinct_step_types(self) -> None:
        frame = analyze_instruction("记住我喜欢空洞骑士，再推荐三款类似游戏")

        self.assertEqual(
            [(step.action, step.kind) for step in frame.task_plan],
            [("remember", "effect"), ("recommend", "content")],
        )

    def test_relay_then_report_keeps_follow_up_content(self) -> None:
        frame = analyze_instruction(
            "去2000000001群里给小明发消息说今晚开黑，然后告诉我你发了什么"
        )

        self.assertEqual(
            [(step.action, step.kind) for step in frame.task_plan],
            [("relay", "effect"), ("answer", "content")],
        )

    def test_multiple_relays_are_preserved_before_final_report(self) -> None:
        frame = analyze_instruction(
            "去2000000001群里给小明发消息说今晚开黑，"
            "然后给小红发消息说明天见，最后告诉我结果"
        )

        self.assertEqual(
            [step.action for step in frame.task_plan],
            ["relay", "relay", "answer"],
        )


if __name__ == "__main__":
    unittest.main()
