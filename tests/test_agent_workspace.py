from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.agent_workspace import AgentWorkspace


def make_frame(*steps: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        task_plan=steps,
        side_effect="none",
        action="chat",
    )


def make_step(step_id: int, instruction: str, *, action: str = "respond") -> SimpleNamespace:
    return SimpleNamespace(
        id=step_id,
        action=action,
        instruction=instruction,
        kind="content",
        side_effect="none",
        depends_on=(),
    )


class AgentWorkspaceTests(unittest.TestCase):
    def make_workspace(self, root: Path) -> AgentWorkspace:
        return AgentWorkspace(root / "xixi_memory.db")

    def test_initialization_is_incremental_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "xixi_memory.db"
            first = AgentWorkspace(path)
            second = AgentWorkspace(path)

            self.assertTrue(first.migration_status()["up_to_date"])
            self.assertEqual(second.migration_status()["current_version"], first.SCHEMA_VERSION)
            self.assertEqual(len(second.migration_status()["applied"]), 1)

    def test_task_steps_persist_and_interrupted_run_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(Path(tmp))
            frame = make_frame(
                make_step(1, "先查询资料", action="research"),
                make_step(2, "再整理结论"),
            )
            interrupted = workspace.begin_turn(
                session_id="private:1",
                user_id="1",
                source="private",
                request_text="查完以后总结",
                frame=frame,
                model_name="primary",
            )
            self.assertEqual(
                workspace.begin_turn(
                    session_id="private:1",
                    user_id="1",
                    source="private",
                    request_text="普通聊天",
                    frame=make_frame(),
                    model_name="primary",
                ),
                "",
            )
            completed = workspace.begin_turn(
                session_id="private:1",
                user_id="1",
                source="private",
                request_text="继续另一个任务",
                frame=frame,
                model_name="primary",
            )
            workspace.finish_turn(completed, "已经完成")

            runs = {item["id"]: item for item in workspace.runs()["items"]}
            self.assertEqual(runs[interrupted]["status"], "failed")
            self.assertIn("意外中断", runs[interrupted]["error"])
            self.assertEqual(runs[completed]["status"], "completed")
            self.assertEqual(len(runs[completed]["steps"]), 2)

    def test_follow_up_extraction_deduplicates_and_can_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(Path(tmp))
            first = workspace.capture_pending_thread(
                session_id="private:1", user_id="1", content="下次继续聊这个游戏"
            )
            duplicate = workspace.capture_pending_thread(
                session_id="private:1", user_id="1", content="下次继续聊这个游戏"
            )

            self.assertEqual(first, duplicate)
            self.assertEqual(len(workspace.pending_threads()), 1)
            workspace.update_thread(first, "completed")
            self.assertEqual(workspace.pending_threads(), [])

    def test_context_compaction_is_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(Path(tmp))
            history = [
                {"role": "user" if index % 2 == 0 else "assistant", "content": f"消息 {index} " + "内容" * 20}
                for index in range(20)
            ]

            summary = workspace.compact_conversation("studio:owner", history, keep_messages=8)
            usage = workspace.context_usage("studio:owner", history[-8:], max_messages=20)

            self.assertTrue(summary["summary"])
            self.assertEqual(summary["compacted_messages"], 12)
            self.assertTrue(usage["has_summary"])

    def test_policy_enforces_pause_owner_and_manual_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(Path(tmp))
            workspace.update_policy({
                "capability_rules": {
                    "qq_relay": "owner_only",
                    "game_control": "manual_only",
                    "research": "deny",
                }
            })

            self.assertFalse(workspace.capability_allowed("qq_relay"))
            self.assertTrue(workspace.capability_allowed("qq_relay", is_owner=True))
            self.assertFalse(workspace.capability_allowed("game_control"))
            self.assertTrue(workspace.capability_allowed("game_control", manual=True))
            self.assertFalse(workspace.capability_allowed("research", is_owner=True, manual=True))
            workspace.update_policy({"paused": True})
            self.assertFalse(workspace.capability_allowed("game_control", manual=True))
            self.assertTrue(workspace.capability_allowed("chat"))

    def test_goals_reflections_usage_and_model_profiles_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(Path(tmp))
            goal = workspace.create_goal("继续了解一部动画")
            workspace.update_goal(goal["id"], "completed")
            workspace.save_reflection(
                period_type="daily",
                period_key="2026-08-16",
                title="今天的想法",
                content="我想继续弄清楚角色为什么作出那个选择。",
            )
            workspace.record_model_usage(
                capability="language",
                provider="https://example.com/v1",
                model_name="example-model",
                success=True,
                latency_ms=420,
                input_chars=350,
                output_chars=140,
            )
            profile = workspace.save_model_profile({
                "name": "本地备用",
                "capability": "language",
                "base_url": "http://127.0.0.1:11434/v1",
                "model_name": "qwen3:8b",
                "api_type": "ollama",
                "priority": 20,
            })

            self.assertEqual(workspace.goals()[0]["status"], "completed")
            self.assertEqual(workspace.reflections()[0]["period_type"], "daily")
            self.assertEqual(workspace.usage_summary()["requests"], 1)
            self.assertEqual(workspace.model_profiles("language")[0]["id"], profile["id"])
            self.assertTrue(workspace.delete_model_profile(profile["id"]))

    def test_reflections_can_be_filtered_to_a_calendar_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(Path(tmp))
            for period_key in ("2026-07-31", "2026-08-01", "2026-08-17", "2026-09-01"):
                workspace.save_reflection(
                    period_type="daily",
                    period_key=period_key,
                    title=f"想法 {period_key}",
                    content="一条用于验证日历月份范围的成长记录。",
                )

            august = workspace.reflections(
                start_date="2026-08-01",
                end_date="2026-09-01",
            )

            self.assertEqual(
                [item["period_key"] for item in august],
                ["2026-08-17", "2026-08-01"],
            )
            with self.assertRaises(ValueError):
                workspace.reflections(start_date="2026-08-31", end_date="2026-08-01")
            with self.assertRaises(ValueError):
                workspace.reflections(start_date="2026-02-30")


if __name__ == "__main__":
    unittest.main()
