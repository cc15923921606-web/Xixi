from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from .memory_store import MemoryStore, clean_text

logger = logging.getLogger("continuous_learning")

_LEARNING_PRIORITIES = frozenset({"interest", "general", "academic"})

_JIKAN_ENDPOINTS = (
    ("热门动漫", "https://api.jikan.moe/v4/top/anime"),
    ("本季动漫", "https://api.jikan.moe/v4/seasons/now"),
)
_BANGUMI_SEARCH_URL = "https://api.bgm.tv/v0/search/subjects"


@dataclass(frozen=True)
class LearningSource:
    name: str
    url: str
    category: str
    enabled: bool = True
    priority: str = "general"


def load_sources(path: Path) -> list[LearningSource]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("could not load learning sources: %s", exc)
        return []

    sources = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        category = str(item.get("category", "general")).strip() or "general"
        priority = str(item.get("priority", "general")).strip().lower() or "general"
        if priority not in _LEARNING_PRIORITIES:
            logger.warning(
                "unknown learning priority %r for %s; using general",
                priority,
                name or url,
            )
            priority = "general"
        if name and url.startswith("https://"):
            sources.append(
                LearningSource(
                    name=name,
                    url=url,
                    category=category,
                    enabled=bool(item.get("enabled", True)),
                    priority=priority,
                )
            )
    return sources


def parse_feed(xml_data: bytes, limit: int = 12) -> list[dict[str, str]]:
    root = ET.fromstring(xml_data)
    entries = [element for element in root.iter() if _local_name(element.tag) in {"item", "entry"}]
    parsed: list[dict[str, str]] = []
    for entry in entries[:limit]:
        title = clean_text(_child_text(entry, {"title"}), 180)
        summary = clean_text(
            _child_text(entry, {"description", "summary", "content", "encoded"}),
            420,
        )
        link = _entry_link(entry)
        published = clean_text(
            _child_text(entry, {"pubdate", "published", "updated", "date"}),
            80,
        )
        if title and link:
            parsed.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published,
                }
            )
    return parsed


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if _local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def _entry_link(element: ET.Element) -> str:
    for child in element:
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "")).strip()
        if href:
            return href
        if child.text:
            return child.text.strip()
    return _child_text(element, {"guid", "id"})


class TrustedSourceLearner:
    def __init__(self, store: MemoryStore, sources_file: Path) -> None:
        self.store = store
        self.sources_file = Path(sources_file)

    def learn_once(self, priority: str | None = None) -> tuple[int, int]:
        sources = [source for source in load_sources(self.sources_file) if source.enabled]
        if priority is not None:
            normalized_priority = priority.strip().lower()
            if normalized_priority not in _LEARNING_PRIORITIES:
                raise ValueError(f"unsupported learning priority: {priority}")
            sources = [
                source for source in sources if source.priority == normalized_priority
            ]
        else:
            normalized_priority = ""
        learned = 0
        failures = 0
        headers = {"User-Agent": "XixiLearningBot/1.0 (personal AI companion)"}
        with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
            for source in sources:
                try:
                    response = client.get(source.url)
                    response.raise_for_status()
                    for entry in parse_feed(response.content):
                        content = entry["title"]
                        if entry["summary"] and entry["summary"] != entry["title"]:
                            content = f"{content}：{entry['summary']}"
                        _, created = self.store.upsert_memory(
                            scope="web",
                            content=content,
                            category=source.category,
                            source_type="web",
                            source_name=source.name,
                            source_url=entry["link"],
                            confidence=0.78,
                            importance=4,
                        )
                        learned += int(created)
                    logger.info("learned trusted feed: %s", source.name)
                except Exception as exc:
                    failures += 1
                    logger.warning("trusted feed failed (%s): %s", source.name, exc)
        state_prefix = normalized_priority or "web"
        self.store.set_state(
            f"last_{state_prefix}_learning_at",
            datetime.now(timezone.utc).isoformat(),
        )
        self.store.set_state(f"last_{state_prefix}_learning_new_items", str(learned))
        logger.info(
            "%s learning complete: new=%s failures=%s",
            state_prefix,
            learned,
            failures,
        )
        return learned, failures


class AnimeKnowledgeLearner:
    def __init__(self, store: MemoryStore, *, limit: int = 15) -> None:
        self.store = store
        self.limit = min(25, max(3, limit))

    def learn_once(self) -> tuple[int, int]:
        learned = 0
        failures = 0
        chinese_title_cache: dict[str, str] = {}
        headers = {"User-Agent": "XixiLearningBot/1.0 (anime knowledge)"}
        with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
            for source_name, url in _JIKAN_ENDPOINTS:
                try:
                    response = client.get(url, params={"limit": self.limit})
                    response.raise_for_status()
                    payload = response.json()
                    entries = payload.get("data") if isinstance(payload, dict) else None
                    if not isinstance(entries, list):
                        raise ValueError("anime response did not contain a data list")
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        title_key = str(
                            entry.get("title_japanese") or entry.get("title") or ""
                        ).strip()
                        if title_key not in chinese_title_cache:
                            try:
                                chinese_title_cache[title_key] = _bangumi_chinese_title(
                                    client,
                                    entry,
                                )
                                time.sleep(0.2)
                            except Exception as exc:
                                logger.debug(
                                    "could not enrich anime title %s: %s",
                                    title_key,
                                    exc,
                                )
                                chinese_title_cache[title_key] = ""
                        content, source_url = _anime_memory(
                            entry,
                            source_name,
                            chinese_title=chinese_title_cache[title_key],
                        )
                        if not content or not source_url:
                            continue
                        _, created = self.store.upsert_memory(
                            scope="web",
                            content=content,
                            category="动漫",
                            source_type="web",
                            source_name=f"Jikan {source_name}",
                            source_url=source_url,
                            confidence=0.86,
                            importance=5,
                        )
                        learned += int(created)
                    logger.info("learned anime source: %s", source_name)
                except Exception as exc:
                    failures += 1
                    logger.warning("anime source failed (%s): %s", source_name, exc)

        self.store.set_state(
            "last_anime_learning_at",
            datetime.now(timezone.utc).isoformat(),
        )
        self.store.set_state("last_anime_learning_new_items", str(learned))
        logger.info("anime learning complete: new=%s failures=%s", learned, failures)
        return learned, failures


def _anime_memory(
    entry: dict[str, object],
    source_name: str,
    *,
    chinese_title: str = "",
) -> tuple[str, str]:
    source_url = str(entry.get("url") or "").strip()
    romanized = str(entry.get("title") or "").strip()
    japanese = str(entry.get("title_japanese") or "").strip()
    english = str(entry.get("title_english") or "").strip()
    primary_title = chinese_title or japanese or english or romanized
    if not primary_title or not source_url.startswith("https://"):
        return "", ""

    alternate_titles = [
        title
        for title in (japanese, romanized, english)
        if title and title != primary_title
    ]
    title_text = f"《{primary_title}》"
    if alternate_titles:
        title_text += f"（{' / '.join(alternate_titles[:2])}）"

    genres = entry.get("genres")
    genre_names = [
        str(item.get("name"))
        for item in genres if isinstance(item, dict) and item.get("name")
    ] if isinstance(genres, list) else []
    studios = entry.get("studios")
    studio_names = [
        str(item.get("name"))
        for item in studios if isinstance(item, dict) and item.get("name")
    ] if isinstance(studios, list) else []
    aired = entry.get("aired") if isinstance(entry.get("aired"), dict) else {}
    aired_from = str(aired.get("from") or "")[:10]

    facts = [f"动漫资料（{source_name}）：{title_text}"]
    anime_type = str(entry.get("type") or "").strip()
    episodes = entry.get("episodes")
    status = str(entry.get("status") or "").strip()
    source_material = str(entry.get("source") or "").strip()
    if anime_type:
        facts.append(f"形式 {anime_type}")
    if isinstance(episodes, int) and episodes > 0:
        facts.append(f"共 {episodes} 集")
    if status:
        facts.append(f"状态 {status}")
    if aired_from:
        facts.append(f"始播 {aired_from}")
    if source_material:
        facts.append(f"原作类型 {source_material}")
    if genre_names:
        facts.append(f"题材 {', '.join(genre_names[:6])}")
    if studio_names:
        facts.append(f"制作 {', '.join(studio_names[:3])}")

    synopsis = clean_text(str(entry.get("synopsis") or ""), 520)
    content = "；".join(facts)
    if synopsis:
        content += f"。简介：{synopsis}"
    return content, source_url


def _bangumi_chinese_title(
    client: httpx.Client,
    entry: dict[str, object],
) -> str:
    japanese = str(entry.get("title_japanese") or "").strip()
    romanized = str(entry.get("title") or "").strip()
    query = japanese or romanized
    if not query:
        return ""
    response = client.post(
        _BANGUMI_SEARCH_URL,
        params={"limit": 5},
        json={"keyword": query, "filter": {"type": [2]}},
    )
    response.raise_for_status()
    payload = response.json()
    candidates = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        return ""

    normalized_query = _normalize_anime_title(query)
    best_score = 0.0
    best_chinese = ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        chinese = str(candidate.get("name_cn") or "").strip()
        original = str(candidate.get("name") or "").strip()
        if not chinese or not original:
            continue
        normalized_original = _normalize_anime_title(original)
        score = SequenceMatcher(
            None,
            normalized_query,
            normalized_original,
        ).ratio()
        if score > best_score:
            best_score = score
            best_chinese = chinese
    return best_chinese if best_score >= 0.72 else ""


def _normalize_anime_title(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff\u3040-\u30ff]+", "", value.casefold())


async def run_learning_scheduler(
    cfg: "Config",
    brain: "Brain",
    owner_user_id: int,
    send_private: Callable[[int, str], Awaitable[None]],
) -> None:
    learner = TrustedSourceLearner(brain.memory, cfg.learning_sources_file)
    anime_learner = AnimeKnowledgeLearner(
        brain.memory,
        limit=cfg.anime_learning_limit,
    )
    logger.info("continuous learning scheduler started")
    previously_enabled: bool | None = None
    while True:
        if not cfg.learning_enabled:
            if previously_enabled is not False:
                logger.info("continuous learning paused")
            previously_enabled = False
            await asyncio.sleep(1.0)
            continue
        if previously_enabled is False:
            logger.info("continuous learning resumed")
        previously_enabled = True
        try:
            now = datetime.now(timezone.utc)
            learning_tiers = (
                ("interest", cfg.learning_interest_interval_hours),
                ("general", cfg.learning_general_interval_hours),
                ("academic", cfg.learning_academic_interval_hours),
            )
            for priority, interval_hours in learning_tiers:
                try:
                    state_key = f"last_{priority}_learning_at"
                    last_learning = _parse_timestamp(
                        brain.memory.get_state(state_key)
                    )
                    if last_learning is None:
                        brain.memory.set_state(state_key, now.isoformat())
                        logger.info("initialized %s learning schedule", priority)
                    elif now - last_learning >= timedelta(hours=interval_hours):
                        await asyncio.to_thread(learner.learn_once, priority)
                except Exception as exc:
                    logger.exception("%s learning tier failed: %s", priority, exc)

            try:
                last_anime = _parse_timestamp(
                    brain.memory.get_state("last_anime_learning_at")
                )
                if cfg.anime_learning_enabled and last_anime is None:
                    brain.memory.set_state("last_anime_learning_at", now.isoformat())
                    logger.info("initialized anime learning schedule")
                elif (
                    cfg.anime_learning_enabled
                    and now - last_anime
                    >= timedelta(hours=cfg.anime_learning_interval_hours)
                ):
                    await asyncio.to_thread(anime_learner.learn_once)
            except Exception as exc:
                logger.exception("anime learning tier failed: %s", exc)

            pending_reflections = brain.memory.pending_knowledge_reflection_count()
            last_reflection_failure = _parse_timestamp(
                brain.memory.get_state("last_knowledge_reflection_failure_at")
            )
            reflection_retry_ready = (
                not last_reflection_failure
                or now - last_reflection_failure >= timedelta(minutes=15)
            )
            if (
                cfg.knowledge_reflection_enabled
                and pending_reflections
                and reflection_retry_ready
            ):
                try:
                    batch_size = max(
                        1,
                        min(24, cfg.knowledge_reflection_batch_size),
                    )
                    await asyncio.to_thread(
                        brain.reflect_on_pending_knowledge,
                        batch_size,
                    )
                    brain.memory.set_state("last_knowledge_reflection_failure_at", "")
                except Exception as exc:
                    brain.memory.set_state(
                        "last_knowledge_reflection_failure_at",
                        datetime.now(timezone.utc).isoformat(),
                    )
                    logger.exception("knowledge reflection failed: %s", exc)

            try:
                last_reflection = _parse_timestamp(
                    brain.memory.get_state("last_interest_reflection_at")
                )
                last_reflection_attempt = _parse_timestamp(
                    brain.memory.get_state("last_interest_reflection_attempt_at")
                )
                reflection_due = (
                    not last_reflection
                    or now - last_reflection
                    >= timedelta(hours=cfg.interest_reflection_interval_hours)
                )
                retry_ready = (
                    not last_reflection_attempt
                    or now - last_reflection_attempt >= timedelta(minutes=30)
                )
                if (
                    cfg.interest_reflection_enabled
                    and reflection_due
                    and retry_ready
                ):
                    await asyncio.to_thread(brain.reflect_on_interests)
            except Exception as exc:
                logger.exception("interest reflection failed: %s", exc)

            pending = brain.memory.pending_event_count()
            last_sleep = _parse_timestamp(brain.memory.get_state("last_memory_consolidation_at"))
            last_attempt = _parse_timestamp(
                brain.memory.get_state("last_memory_consolidation_attempt_at")
            )
            consolidation_due = not last_sleep or now - last_sleep >= timedelta(
                hours=cfg.memory_consolidation_hours
            )
            retry_ready = not last_attempt or now - last_attempt >= timedelta(minutes=15)
            if pending and retry_ready and (
                pending >= cfg.memory_consolidation_min_events or consolidation_due
            ):
                await asyncio.to_thread(brain.consolidate_pending_memories)

            local_now = datetime.now().astimezone()
            last_digest_date = brain.memory.get_state("last_learning_digest_date")
            if (
                cfg.learning_daily_digest
                and local_now.hour >= cfg.learning_digest_hour
                and last_digest_date != local_now.date().isoformat()
            ):
                digest = await asyncio.to_thread(brain.compose_learning_digest)
                if digest:
                    await send_private(owner_user_id, digest)
                    brain.memory.set_state("last_learning_digest_date", local_now.date().isoformat())
                    logger.info("sent daily learning digest to owner")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("continuous learning cycle failed: %s", exc)

        remaining_sleep = 60.0
        while remaining_sleep > 0 and cfg.learning_enabled:
            delay = min(1.0, remaining_sleep)
            await asyncio.sleep(delay)
            remaining_sleep -= delay


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None
