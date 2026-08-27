from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

logger = logging.getLogger("autonomy")

_INTEREST_RE = re.compile(
    r"二次元|动漫|动画|漫画|轻小说|galgame|视觉小说|游戏|steam|主机|角色|声优|新番|番剧|cos",
    re.IGNORECASE,
)
_EMOTION_RE = re.compile(r"累死|难受|烦死|开心|高兴|生气|委屈|无语|笑死|绝了|睡不着|想哭|好气")
_QUESTION_RE = re.compile(r"[？?]|(?:怎么|为什么|咋办|有没有|是不是|觉得|谁知道)")
_COMMAND_RE = re.compile(r"^(?:/|！|!|签到|菜单|帮助|抽奖|点歌)")
_TOPIC_RESET_RE = re.compile(
    r"^(?:换个话题|说点别的|聊点别的|不说这个了|另一个话题)"
)
_BOT_DESCRIPTOR_RE = re.compile(
    r"(?:这个|那个|群里(?:的)?|咱们群(?:的)?)(?:AI|人工智能|机器人|小机器人)"
    r"|(?:你家|你(?:的)?|主人(?:的)?)(?:AI|机器人|女儿)"
    r"|(?:AI|机器人)(?:女孩|妹妹|女儿)",
    re.IGNORECASE,
)
_BOT_CONTINUATION_RE = re.compile(
    r"(?:^|[，,。！？!?\s])她(?:的|刚才|怎么|是不是|会不会|能不能|也|还|真|好|太|挺)?"
    r"|(?:这|那)(?:个)?(?:丫头|孩子)(?:AI|机器人)?",
    re.IGNORECASE,
)


def _contains_alias(text: str, alias: str) -> bool:
    folded_text = text.casefold()
    folded_alias = alias.casefold()
    if folded_alias.isascii() and folded_alias.isalnum():
        return bool(
            re.search(
                rf"(?<![a-z0-9_]){re.escape(folded_alias)}(?![a-z0-9_])",
                folded_text,
            )
        )
    return folded_alias in folded_text


class GroupAutonomy:
    def __init__(
        self,
        cfg: "Config",
        brain: "Brain",
        bot_user_id: int,
        *,
        bot_name: str = "昔夕",
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg = cfg
        self.brain = brain
        self.bot_user_id = bot_user_id
        self.default_bot_name = bot_name.strip()
        self.rng = rng or random.Random()
        self.clock = clock
        self.buffers: dict[int, deque[tuple[float, str, str]]] = defaultdict(
            lambda: deque(maxlen=max(20, self.cfg.autonomous_group_buffer_messages))
        )
        self.messages_since_reply: dict[int, int] = defaultdict(int)
        self.last_reply_at: dict[int, float] = defaultdict(float)
        self.last_message_at: dict[int, float] = defaultdict(float)
        self.topic_openers: dict[int, list[tuple[float, str, str]]] = defaultdict(list)
        self.last_bot_reference_at: dict[int, float] = defaultdict(float)

    def message_is_about_bot(self, group_id: int, text: str) -> bool:
        if self._has_explicit_bot_reference(text):
            return True
        if not _BOT_CONTINUATION_RE.search(text):
            return False

        now = self.clock()
        if now - self.last_bot_reference_at[group_id] <= 600:
            return True
        return any(
            self._has_explicit_bot_reference(message)
            for _, _, message in list(self.buffers[group_id])[-6:]
        )

    def _has_explicit_bot_reference(self, text: str) -> bool:
        return any(_contains_alias(text, alias) for alias in self._bot_aliases()) or bool(
            _BOT_DESCRIPTOR_RE.search(text)
        )

    def _bot_aliases(self) -> set[str]:
        formal_name = str(
            getattr(self.cfg, "assistant_name", "") or self.default_bot_name or "昔夕"
        ).strip()
        configured = str(getattr(self.cfg, "qq_group_wake_names", "") or "")
        values = [formal_name]
        values.extend(
            alias.strip()
            for alias in re.split(r"[,，、;；\r\n]+", configured)
            if alias.strip()
        )
        if formal_name == "昔夕":
            values.extend(("昔夕", "小夕", "xx", "有地绫"))
        return {alias.casefold() for alias in values if alias}

    def observe(
        self,
        raw: dict[str, object],
        text: str,
        *,
        directly_addressed: bool,
        about_bot: bool = False,
    ) -> str | None:
        group_id = int(raw.get("group_id") or 0)
        sender = raw.get("sender") if isinstance(raw.get("sender"), dict) else {}
        sender_id = int(sender.get("user_id") or 0)
        if not group_id or sender_id == self.bot_user_id or not text.strip():
            return None

        now = self.clock()
        self._reset_inactive_or_changed_topic(group_id, text, now)
        sender_name = str(sender.get("card") or sender.get("nickname") or f"QQ用户{sender_id}")
        owner_name = str(getattr(self.cfg, "owner_display_name", "") or "主人").strip()
        identity = f"主人 {owner_name}" if sender_id == self.cfg.qq_user_id else "群成员"
        label = f"{sender_name}（{identity}）"
        record = (now, label, text.strip()[:300])
        self.buffers[group_id].append(record)
        if len(self.topic_openers[group_id]) < 4:
            self.topic_openers[group_id].append(record)
        self.last_message_at[group_id] = now

        if directly_addressed:
            self.last_bot_reference_at[group_id] = now
            return None
        if not self.cfg.autonomous_group_enabled:
            return None
        workspace = getattr(self.brain, "workspace", None)
        if workspace is not None and not workspace.capability_allowed("autonomy"):
            return None
        if self.cfg.autonomous_group_ids and group_id not in self.cfg.autonomous_group_ids:
            return None
        if _COMMAND_RE.search(text.strip()):
            return None

        self.messages_since_reply[group_id] += 1
        if about_bot:
            self.last_bot_reference_at[group_id] = now
            return self.recent_context(group_id, query=text)
        if self.messages_since_reply[group_id] < self.cfg.autonomous_group_min_messages:
            return None
        if now - self.last_reply_at[group_id] < self.cfg.autonomous_group_cooldown_s:
            return None

        score = group_participation_score(
            text,
            is_owner=sender_id == self.cfg.qq_user_id,
            distinct_speakers=len({name for _, name, _ in self.buffers[group_id]}),
        )
        chance = min(0.82, self.cfg.autonomous_group_base_chance + score * 0.13)
        if self.rng.random() > chance:
            return None

        return self.recent_context(group_id, query=text)

    def recent_context(
        self,
        group_id: int,
        *,
        query: str = "",
        max_messages: int | None = None,
    ) -> str:
        self._expire_inactive_topic(group_id, self.clock())
        records = list(self.topic_openers[group_id])
        records.extend(
            record
            for record in self.buffers[group_id]
            if record not in self.topic_openers[group_id]
        )
        limit = max(
            4,
            max_messages or self.cfg.autonomous_group_context_messages,
        )
        if len(records) > limit:
            records = _select_topic_context(records, query, limit)
        return "\n".join(f"{name}：{message}" for _, name, message in records)

    def _reset_inactive_or_changed_topic(
        self,
        group_id: int,
        text: str,
        now: float,
    ) -> None:
        self._expire_inactive_topic(group_id, now)
        if self.buffers[group_id] and _TOPIC_RESET_RE.search(text.strip()):
            self._clear_topic(group_id)

    def _expire_inactive_topic(self, group_id: int, now: float) -> None:
        last_message = self.last_message_at[group_id]
        idle_limit = max(60.0, self.cfg.autonomous_group_context_idle_s)
        if self.buffers[group_id] and last_message and now - last_message > idle_limit:
            self._clear_topic(group_id)

    def _clear_topic(self, group_id: int) -> None:
        self.buffers[group_id].clear()
        self.topic_openers[group_id].clear()
        self.messages_since_reply[group_id] = 0
        self.last_message_at[group_id] = 0.0
        self.last_bot_reference_at[group_id] = 0.0

    def mark_spoke(self, group_id: int) -> None:
        self.last_reply_at[group_id] = self.clock()
        self.messages_since_reply[group_id] = 0


def group_participation_score(
    text: str,
    *,
    is_owner: bool,
    distinct_speakers: int,
) -> float:
    score = 0.0
    if _INTEREST_RE.search(text):
        score += 2.2
    if _EMOTION_RE.search(text):
        score += 1.2
    if _QUESTION_RE.search(text):
        score += 0.9
    if is_owner:
        score += 1.0
    if distinct_speakers >= 2:
        score += 0.6
    if len(text.strip()) >= 18:
        score += 0.3
    return score


def _select_topic_context(
    records: list[tuple[float, str, str]],
    query: str,
    limit: int,
) -> list[tuple[float, str, str]]:
    opening_count = min(4, max(1, limit // 5))
    recent_count = min(12, max(3, limit // 2))
    selected = set(range(opening_count))
    selected.update(range(max(0, len(records) - recent_count), len(records)))

    remaining = max(0, limit - len(selected))
    if remaining:
        query_terms = _topic_terms(query or records[-1][2])
        candidates: list[tuple[float, int]] = []
        for index, (_, _, message) in enumerate(records):
            if index in selected:
                continue
            terms = _topic_terms(message)
            overlap = len(query_terms & terms)
            score = overlap / max(1, len(query_terms))
            score += index / max(1, len(records)) * 0.02
            candidates.append((score, index))
        candidates.sort(reverse=True)
        selected.update(index for _, index in candidates[:remaining])

    return [records[index] for index in sorted(selected)[:limit]]


def _topic_terms(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    terms = set(re.findall(r"[a-z0-9_]{2,}", normalized))
    for run in re.findall(r"[\u3400-\u9fff]{2,}", normalized):
        terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return terms


async def run_private_autonomy_scheduler(
    cfg: "Config",
    brain: "Brain",
    owner_user_id: int,
    send_private: Callable[[int, str], Awaitable[None]],
    runtime_enabled: Callable[[], bool] | None = None,
) -> None:
    rng = random.Random()
    previously_enabled: bool | None = None
    while True:
        enabled = bool(cfg.autonomous_private_enabled) and (
            runtime_enabled is None or runtime_enabled()
        )
        if not enabled:
            if previously_enabled is not False:
                logger.info("autonomous private messaging paused")
            previously_enabled = False
            await asyncio.sleep(1.0)
            continue
        _ensure_initial_private_schedule(cfg, brain, rng)
        if previously_enabled is False:
            logger.info("autonomous private messaging resumed")
        elif previously_enabled is None:
            logger.info("autonomous private messaging scheduler started")
        previously_enabled = True
        try:
            now = datetime.now().astimezone()
            due = _parse_timestamp(brain.memory.get_state("autonomy_private_next_at"))
            if due and datetime.now(timezone.utc) >= due:
                if not _is_active_hour(cfg, now.hour):
                    _schedule_at_next_active_hour(cfg, brain, rng, now)
                elif _private_daily_limit_reached(cfg, brain, now.date().isoformat()):
                    _schedule_at_next_active_hour(
                        cfg,
                        brain,
                        rng,
                        now,
                        force_next_day=True,
                    )
                elif _owner_was_recently_active(brain, minutes=30):
                    _schedule_private_after(brain, rng.uniform(0.5, 1.2))
                else:
                    workspace = getattr(brain, "workspace", None)
                    if workspace is not None and not workspace.capability_allowed(
                        "autonomy", is_owner=True
                    ):
                        await asyncio.sleep(30.0)
                        continue
                    message = await asyncio.to_thread(
                        brain.compose_autonomous_private_message,
                        owner_user_id,
                    )
                    if message:
                        await send_private(owner_user_id, message)
                        brain.remember_autonomous_reply(
                            f"private:{owner_user_id}",
                            message,
                            f"你主动给主人 {getattr(brain.cfg, 'owner_display_name', '主人')} 发起了私聊。",
                        )
                        _increment_private_daily_count(brain, now.date().isoformat())
                        if workspace is not None:
                            workspace.record_tool(
                                capability="autonomy",
                                risk_level="external_write",
                                status="completed",
                                request={"destination": f"private:{owner_user_id}"},
                                result=message,
                            )
                        logger.info("sent autonomous private message to owner")
                    _schedule_private_after(
                        brain,
                        rng.uniform(
                            cfg.autonomous_private_min_interval_hours,
                            cfg.autonomous_private_max_interval_hours,
                        ),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("autonomous private messaging cycle failed: %s", exc)

        remaining_sleep = 60.0
        while (
            remaining_sleep > 0
            and cfg.autonomous_private_enabled
            and (runtime_enabled is None or runtime_enabled())
        ):
            delay = min(1.0, remaining_sleep)
            await asyncio.sleep(delay)
            remaining_sleep -= delay


def note_owner_activity(brain: "Brain") -> None:
    brain.memory.set_state(
        "last_owner_activity_at",
        datetime.now(timezone.utc).isoformat(),
    )


def _ensure_initial_private_schedule(
    cfg: "Config", brain: "Brain", rng: random.Random
) -> None:
    if _parse_timestamp(brain.memory.get_state("autonomy_private_next_at")):
        return
    minutes = rng.uniform(
        cfg.autonomous_private_initial_min_minutes,
        cfg.autonomous_private_initial_max_minutes,
    )
    _schedule_private_after(brain, minutes / 60.0)


def _schedule_private_after(brain: "Brain", hours: float) -> None:
    due = datetime.now(timezone.utc) + timedelta(hours=max(0.05, hours))
    brain.memory.set_state("autonomy_private_next_at", due.isoformat())


def _schedule_at_next_active_hour(
    cfg: "Config",
    brain: "Brain",
    rng: random.Random,
    local_now: datetime,
    *,
    force_next_day: bool = False,
) -> None:
    target = local_now.replace(
        hour=cfg.autonomous_private_active_start_hour,
        minute=rng.randint(10, 50),
        second=0,
        microsecond=0,
    )
    if force_next_day or target <= local_now:
        target += timedelta(days=1)
    brain.memory.set_state(
        "autonomy_private_next_at",
        target.astimezone(timezone.utc).isoformat(),
    )


def _is_active_hour(cfg: "Config", hour: int) -> bool:
    return cfg.autonomous_private_active_start_hour <= hour < cfg.autonomous_private_active_end_hour


def _owner_was_recently_active(brain: "Brain", *, minutes: int) -> bool:
    last_activity = _parse_timestamp(brain.memory.get_state("last_owner_activity_at"))
    return bool(
        last_activity
        and datetime.now(timezone.utc) - last_activity < timedelta(minutes=minutes)
    )


def _private_daily_limit_reached(cfg: "Config", brain: "Brain", date_text: str) -> bool:
    if brain.memory.get_state("autonomy_private_count_date") != date_text:
        return False
    try:
        count = int(brain.memory.get_state("autonomy_private_count", "0"))
    except ValueError:
        count = 0
    return count >= cfg.autonomous_private_max_per_day


def _increment_private_daily_count(brain: "Brain", date_text: str) -> None:
    if brain.memory.get_state("autonomy_private_count_date") != date_text:
        count = 0
    else:
        try:
            count = int(brain.memory.get_state("autonomy_private_count", "0"))
        except ValueError:
            count = 0
    brain.memory.set_state("autonomy_private_count_date", date_text)
    brain.memory.set_state("autonomy_private_count", str(count + 1))


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
