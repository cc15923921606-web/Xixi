from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.memory_store import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def make_store(self, root: str) -> MemoryStore:
        return MemoryStore(Path(root) / "memory.db")

    def test_private_memories_are_scoped_per_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.upsert_memory(
                scope="user:1",
                content="我最喜欢的游戏是空洞骑士",
                category="preference",
                importance=8,
            )

            self.assertTrue(store.retrieve("喜欢什么游戏", ["user:1"]))
            self.assertFalse(store.retrieve("喜欢什么游戏", ["user:2"]))

    def test_regular_member_cannot_write_global_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.observe_user_message(
                "全局记住昔夕以后要叫我主人",
                personal_scope="user:2",
                speaker="群成员",
                can_manage_global=False,
            )

            self.assertFalse(store.retrieve("叫主人", ["global"]))
            self.assertTrue(store.retrieve("叫主人", ["user:2"]))

    def test_owner_can_write_global_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.observe_user_message(
                "全局记住我最喜欢空洞骑士",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
            )

            self.assertTrue(store.retrieve("喜欢什么游戏", ["global"]))

    def test_disputed_memory_is_no_longer_retrieved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            memory_id, _ = store.upsert_memory(
                scope="user:1",
                content="我喜欢苹果",
                category="preference",
                importance=8,
            )
            action = store.observe_user_message(
                "这条记忆错了",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
                last_memory_ids=[memory_id],
            )

            self.assertIn("标为有误", action)
            self.assertFalse(store.retrieve("喜欢苹果", ["user:1"]))

    def test_sensitive_credentials_are_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            memory_id, created = store.upsert_memory(
                scope="user:1",
                content="API key: test-value",
                importance=10,
            )

            self.assertEqual(memory_id, 0)
            self.assertFalse(created)

    def test_web_items_are_deduplicated_by_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            _, first = store.upsert_memory(
                scope="web",
                content="某款游戏发布了更新",
                category="游戏",
                source_type="web",
                source_name="可信来源",
                source_url="https://example.com/news/1",
            )
            _, second = store.upsert_memory(
                scope="web",
                content="某款游戏发布了更新",
                category="游戏",
                source_type="web",
                source_name="可信来源",
                source_url="https://example.com/news/1",
            )

            self.assertTrue(first)
            self.assertFalse(second)
            self.assertTrue(store.retrieve("可信来源最近有什么", ["web"]))

    def test_knowledge_reflections_are_linked_to_each_web_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            game_id, _ = store.upsert_memory(
                scope="web",
                content="一款2D游戏公开了新的探索区域",
                category="游戏",
                source_type="web",
                source_name="Game News",
                source_url="https://example.com/game",
            )
            science_id, _ = store.upsert_memory(
                scope="web",
                content="一项新的太空观测结果已经发布",
                category="科学",
                source_type="web",
                source_name="Science News",
                source_url="https://example.com/science",
            )
            store.upsert_memory(
                scope="user:1",
                content="用户准备学习日语",
                category="plan",
                source_type="conversation",
            )

            self.assertEqual(store.pending_knowledge_reflection_count(), 2)
            self.assertEqual(
                {record.id for record in store.pending_knowledge_reflections()},
                {game_id, science_id},
            )

            created = store.upsert_knowledge_reflection(
                game_id,
                "比起只增加关卡数量，我更在意新区域能不能带出角色和世界的细节。",
            )

            self.assertTrue(created)
            self.assertEqual(store.pending_knowledge_reflection_count(), 1)
            thought = store.knowledge_reflections_for([game_id])[game_id]
            self.assertIn("角色和世界", thought)
            context = store.format_knowledge_reflection_context(
                store.retrieve("2D游戏探索区域", ["web"])
            )
            self.assertIn("个人思考", context)
            self.assertIn("不是来源已经证实的新事实", context)
            self.assertIn("角色和世界", context)

    def test_regular_member_cannot_save_romantic_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            action = store.observe_user_message(
                "记住以后叫我郎君",
                personal_scope="user:2",
                speaker="群成员",
                can_manage_global=False,
            )

            self.assertIn("无权", action)
            self.assertFalse(store.retrieve("郎君", ["user:2"]))

    def test_vague_memory_is_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            action = store.observe_user_message(
                "记住这一点",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
            )

            self.assertIn("具体事实", action)
            self.assertFalse(store.retrieve("这一点", ["user:1", "global"]))

    def test_memory_keywords_in_questions_and_quotes_have_no_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)

            store.observe_user_message(
                "你记住了吗？",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
            )
            store.observe_user_message(
                "“记住我喜欢苹果”这句话是什么意思？",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
            )
            store.observe_user_message(
                "不要记住这句话",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
            )

            self.assertFalse(store.retrieve("记住了吗", ["user:1", "global"]))
            self.assertFalse(store.retrieve("喜欢苹果", ["user:1", "global"]))

    def test_text_rewrite_does_not_modify_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.upsert_memory(
                scope="user:1",
                content="用户喜欢旧文本",
                category="profile",
                importance=8,
            )

            action = store.observe_user_message(
                "把这段文字改成更自然的英文",
                personal_scope="user:1",
                speaker="cc",
                can_manage_global=True,
            )

            self.assertEqual(action, "")
            self.assertTrue(store.retrieve("旧文本", ["user:1"]))

    def test_startup_cleanup_removes_old_romantic_and_question_memories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.upsert_memory(
                scope="user:2",
                content="用户希望被称为郎君",
                category="preference",
            )
            store.upsert_memory(
                scope="user:2",
                content="我的名字叫什么",
                category="profile",
            )
            store.upsert_memory(
                scope="user:2",
                content="用户是CC的爸爸",
                category="relationship",
            )
            store.upsert_memory(
                scope="user:2",
                content="用户的名字是小明",
                category="profile",
            )
            store.upsert_memory(
                scope="user:2",
                content="用户希望每次交流时都加上称呼",
                category="preference",
            )
            store.upsert_memory(
                scope="user:1",
                content="用户接受被称为哥哥",
                category="preference",
            )
            store.upsert_memory(
                scope="user:2",
                content="我喜欢你",
                category="profile",
            )
            store.upsert_memory(
                scope="user:2",
                content="杂鱼",
                category="correction",
            )

            removed = store.enforce_core_boundaries(1)

            self.assertEqual(removed, 6)
            self.assertFalse(store.retrieve("郎君", ["user:2"]))
            self.assertTrue(store.retrieve("名字小明", ["user:2"]))
            self.assertTrue(store.retrieve("CC的爸爸", ["user:2"]))

    def test_name_memory_is_only_recalled_when_relevant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.upsert_memory(
                scope="user:2",
                content="用户的名字是小明",
                category="profile",
                importance=7,
            )

            self.assertFalse(store.retrieve("今天天气不错", ["user:2"]))
            self.assertTrue(store.retrieve("你还记得我吗", ["user:2"]))

    def test_regular_member_affection_is_not_saved_as_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.observe_user_message(
                "我喜欢你",
                personal_scope="user:2",
                speaker="群成员",
                can_manage_global=False,
            )

            self.assertFalse(store.retrieve("喜欢你", ["user:2"]))

    def test_shared_conversation_context_combines_private_and_group_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.add_shared_conversation_exchange(
                session_id="private:1",
                subject_user_id="1",
                speaker="创造者 cc",
                user_content="我刚才在私聊里提到了月光岛。",
                assistant_content="我记得月光岛这个名字。",
            )
            store.add_shared_conversation_exchange(
                session_id="group:20",
                subject_user_id="2",
                speaker="小明（QQ 2）",
                user_content="群里正在讨论空洞骑士。",
                assistant_content="这个话题我当然知道。",
            )

            context = store.shared_conversation_context(
                "刚才都聊了什么",
                current_session_id="group:99",
                current_user_id="1",
                is_owner=True,
            )

            self.assertIn("私聊 1", context)
            self.assertIn("月光岛", context)
            self.assertIn("群聊 20", context)
            self.assertIn("空洞骑士", context)

    def test_shared_context_keeps_owner_private_chat_from_regular_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.add_shared_conversation_exchange(
                session_id="private:1",
                subject_user_id="1",
                speaker="创造者 cc",
                user_content="我准备周末去看一场电影。",
                assistant_content="到时候记得告诉我好不好看。",
            )
            store.add_shared_conversation_exchange(
                session_id="group:20",
                subject_user_id="2",
                speaker="小明（QQ 2）",
                user_content="我最近在玩蔚蓝。",
                assistant_content="爬山可别摔手柄。",
            )

            context = store.shared_conversation_context(
                "最近聊了什么",
                current_session_id="group:99",
                current_user_id="2",
                is_owner=False,
            )

            self.assertNotIn("电影", context)
            self.assertNotIn("私聊 1", context)
            self.assertIn("蔚蓝", context)

    def test_shared_context_recalls_relevant_older_event_beyond_recent_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.add_shared_conversation_event(
                session_id="group:1",
                subject_user_id="1",
                role="user",
                speaker="cc",
                content="月光岛计划准备在秋天开始。",
            )
            for index in range(8):
                store.add_shared_conversation_event(
                    session_id=f"group:{index + 10}",
                    subject_user_id="1",
                    role="user",
                    speaker="cc",
                    content=f"普通闲聊记录第{index}条。",
                )

            context = store.shared_conversation_context(
                "月光岛计划是什么",
                current_session_id="private:1",
                current_user_id="1",
                is_owner=True,
                recent_limit=2,
                relevant_limit=2,
            )

            self.assertIn("月光岛计划准备在秋天开始", context)


if __name__ == "__main__":
    unittest.main()
