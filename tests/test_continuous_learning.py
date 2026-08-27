from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.continuous_learning import (
    TrustedSourceLearner,
    _anime_memory,
    load_sources,
    parse_feed,
    run_learning_scheduler,
)
from app.memory_store import MemoryStore


class ContinuousLearningTests(unittest.TestCase):
    def test_load_sources_reads_priority_and_defaults_to_general(self) -> None:
        payload = [
            {
                "name": "Anime",
                "url": "https://example.com/anime.xml",
                "category": "动漫",
                "priority": "interest",
            },
            {
                "name": "News",
                "url": "https://example.com/news.xml",
                "category": "世界",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "sources.json"
            source_file.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            sources = load_sources(source_file)

        self.assertEqual([source.priority for source in sources], ["interest", "general"])

    def test_learner_fetches_only_requested_priority(self) -> None:
        payload = [
            {
                "name": "Anime",
                "url": "https://example.com/anime.xml",
                "category": "动漫",
                "priority": "interest",
            },
            {
                "name": "Science",
                "url": "https://example.com/science.xml",
                "category": "科学",
                "priority": "academic",
            },
        ]
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel><item>
          <title>Anime update</title>
          <link>https://example.com/anime/1</link>
          <description>New series.</description>
        </item></channel></rss>"""
        response = MagicMock(content=xml)
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_file = root / "sources.json"
            source_file.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            store = MemoryStore(root / "memory.db")
            learner = TrustedSourceLearner(store, source_file)

            with patch("app.continuous_learning.httpx.Client", return_value=client):
                learned, failures = learner.learn_once("interest")

            self.assertTrue(store.get_state("last_interest_learning_at"))
            self.assertEqual(store.get_state("last_interest_learning_new_items"), "1")

        self.assertEqual((learned, failures), (1, 0))
        client.get.assert_called_once_with("https://example.com/anime.xml")

    def test_anime_memory_contains_chinese_title_and_facts(self) -> None:
        content, source_url = _anime_memory(
            {
                "url": "https://myanimelist.net/anime/52991/Sousou_no_Frieren",
                "title": "Sousou no Frieren",
                "title_japanese": "葬送のフリーレン",
                "title_english": "Frieren: Beyond Journey's End",
                "type": "TV",
                "episodes": 28,
                "status": "Finished Airing",
                "source": "Manga",
                "genres": [{"name": "Adventure"}, {"name": "Fantasy"}],
                "studios": [{"name": "Madhouse"}],
                "aired": {"from": "2023-09-29T00:00:00+00:00"},
                "synopsis": "An elf mage learns to understand humans.",
            },
            "热门动漫",
            chinese_title="葬送的芙莉莲",
        )

        self.assertIn("《葬送的芙莉莲》", content)
        self.assertIn("共 28 集", content)
        self.assertIn("Madhouse", content)
        self.assertIn("葬送のフリーレン", content)
        self.assertEqual(
            source_url,
            "https://myanimelist.net/anime/52991/Sousou_no_Frieren",
        )

    def test_parse_rss_feed(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel><item>
          <title>Game update</title>
          <link>https://example.com/game</link>
          <description><![CDATA[<p>A useful update.</p>]]></description>
          <pubDate>Sun, 09 Aug 2026 10:00:00 GMT</pubDate>
        </item></channel></rss>"""

        entries = parse_feed(xml)

        self.assertEqual(entries[0]["title"], "Game update")
        self.assertEqual(entries[0]["summary"], "A useful update.")
        self.assertEqual(entries[0]["link"], "https://example.com/game")

    def test_parse_atom_feed(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Science update</title>
          <link href="https://example.com/science" />
          <summary>New discovery.</summary>
          <updated>2026-08-09T10:00:00Z</updated>
        </entry></feed>"""

        entries = parse_feed(xml)

        self.assertEqual(entries[0]["title"], "Science update")
        self.assertEqual(entries[0]["link"], "https://example.com/science")


class LearningSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_profile_initializes_learning_deadlines_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.db")
            cfg = SimpleNamespace(
                learning_enabled=True,
                learning_sources_file=root / "sources.json",
                anime_learning_limit=15,
                learning_interest_interval_hours=2.0,
                learning_general_interval_hours=12.0,
                learning_academic_interval_hours=24.0,
                anime_learning_enabled=True,
                anime_learning_interval_hours=2.0,
                knowledge_reflection_enabled=False,
                knowledge_reflection_batch_size=6,
                interest_reflection_enabled=False,
                interest_reflection_interval_hours=6.0,
                memory_consolidation_hours=6.0,
                memory_consolidation_min_events=6,
                learning_daily_digest=False,
                learning_digest_hour=20,
            )
            brain = SimpleNamespace(memory=store)

            with (
                patch("app.continuous_learning.TrustedSourceLearner.learn_once") as learn,
                patch("app.continuous_learning.AnimeKnowledgeLearner.learn_once") as learn_anime,
                patch(
                    "app.continuous_learning.asyncio.sleep",
                    new=AsyncMock(side_effect=asyncio.CancelledError),
                ),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await run_learning_scheduler(cfg, brain, 1, AsyncMock())

            learn.assert_not_called()
            learn_anime.assert_not_called()
            for priority in ("interest", "general", "academic", "anime"):
                self.assertTrue(store.get_state(f"last_{priority}_learning_at"))
            self.assertEqual(store.latest_web_memories(limit=10), [])

    async def test_scheduler_reflects_on_pending_web_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = MemoryStore(root / "memory.db")
            store.upsert_memory(
                scope="web",
                content="一款新游戏公开了探索区域",
                category="游戏",
                source_type="web",
                source_name="Game News",
                source_url="https://example.com/game",
            )
            now = datetime.now(timezone.utc).isoformat()
            for priority in ("interest", "general", "academic"):
                store.set_state(f"last_{priority}_learning_at", now)
            cfg = SimpleNamespace(
                learning_enabled=True,
                learning_sources_file=root / "sources.json",
                anime_learning_limit=15,
                learning_interest_interval_hours=2.0,
                learning_general_interval_hours=12.0,
                learning_academic_interval_hours=24.0,
                anime_learning_enabled=False,
                anime_learning_interval_hours=2.0,
                knowledge_reflection_enabled=True,
                knowledge_reflection_batch_size=12,
                interest_reflection_enabled=False,
                interest_reflection_interval_hours=6.0,
                memory_consolidation_hours=6.0,
                memory_consolidation_min_events=6,
                learning_daily_digest=False,
                learning_digest_hour=20,
            )
            reflect = Mock(return_value=1)
            brain = SimpleNamespace(
                memory=store,
                reflect_on_pending_knowledge=reflect,
            )

            with patch(
                "app.continuous_learning.asyncio.sleep",
                new=AsyncMock(side_effect=asyncio.CancelledError),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await run_learning_scheduler(
                        cfg,
                        brain,
                        1,
                        AsyncMock(),
                    )

            reflect.assert_called_once_with(12)
            self.assertEqual(
                store.get_state("last_knowledge_reflection_failure_at"),
                "",
            )


if __name__ == "__main__":
    unittest.main()
