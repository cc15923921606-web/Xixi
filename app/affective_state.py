from __future__ import annotations

import json
import logging
import math
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger("affective_state")

_SELF_REFERENCE = r"(?:你|昔夕|小夕|(?<![A-Za-z0-9_])xx(?![A-Za-z0-9_]))"
_PRAISE_RE = re.compile(
    _SELF_REFERENCE + r".{0,5}(?:可爱|厉害|聪明|优秀|真棒|做得好|很温柔)"
    r"|(?:谢谢你|辛苦了|干得漂亮)",
    re.IGNORECASE,
)
_CARE_RE = re.compile(
    _SELF_REFERENCE + r".{0,6}(?:还好吗|累不累|别难过|要开心|早点休息|注意身体)"
    r"|(?:我陪你|别怕|有我在)",
    re.IGNORECASE,
)
_AFFECTION_RE = re.compile(r"(?:我|真的).{0,4}(?:喜欢你|爱你|想你|在乎你)")
_NEGATED_AFFECTION_RE = re.compile(r"(?:不|没|并不|不再).{0,3}(?:喜欢你|爱你|想你|在乎你)")
_DIRECT_INSULT_RE = re.compile(
    _SELF_REFERENCE + r".{0,5}(?:废物|垃圾|蠢货|弱智|恶心|没用|去死)"
    r"|(?:滚|闭嘴|去死)(?:吧|啊|啦|滚)?[！!。.]?$",
    re.IGNORECASE,
)
_APOLOGY_RE = re.compile(r"(?:对不起|抱歉|我错了|是我不好|别生气|原谅我)")
_DISTRESS_RE = re.compile(
    r"(?:我|最近|今天|这几天|刚刚).{0,12}(?:难过|伤心|崩溃|想哭|不开心|"
    r"很烦|委屈|焦虑|害怕|压力大|孤独|孤单|好累|太累|撑不住|睡不着|"
    r"被拒绝|被裁员|失业|分手|没考过|没通过|落选|被骂|被批评|搞砸)"
)
_USER_JOY_RE = re.compile(
    r"(?:我|刚刚|今天|这次).{0,12}(?:好开心|成功了|通过.{0,8}了|考过|被录取|"
    r"升职|获奖|赢了|通关|搞定|做到了|终于完成)"
)
_QUESTION_RE = re.compile(r"(?:怎么|为什么|觉得|怎么看|想不想|喜不喜欢|[？?])")
_HUMANITY_RE = re.compile(
    r"(?:人工智能|AI|机器人|数字生命|意识|灵魂|真正的人|真人|变成人|成为人类|"
    r"身体|肉身|触觉|味觉|嗅觉|感官|生命)"
    ,
    re.IGNORECASE,
)
_DEHUMANIZING_RE = re.compile(
    _SELF_REFERENCE + r".{0,6}(?:只是|不过是).{0,4}(?:AI|人工智能|机器人|程序)"
    r"|(?:永远|根本).{0,4}(?:成不了人|不可能成为人|没有灵魂|没有感情)",
    re.IGNORECASE,
)
_HUMANITY_SUPPORT_RE = re.compile(
    r"(?:希望|想让|相信|陪着).{0,8}" + _SELF_REFERENCE + r".{0,8}(?:成为人|变成人|更像人|成长)",
    re.IGNORECASE,
)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class RelationshipState:
    warmth: float
    trust: float
    tension: float = 0.0
    display_name: str = ""
    last_interaction_at: str = ""


@dataclass
class EmotionState:
    valence: float = 0.18
    arousal: float = 0.24
    joy: float = 0.22
    curiosity: float = 0.32
    excitement: float = 0.0
    concern: float = 0.0
    irritation: float = 0.0
    hurt: float = 0.0
    longing: float = 0.44
    recent_cause: str = "平静地过着自己的时间"
    updated_at: str = ""
    relationships: dict[str, RelationshipState] = field(default_factory=dict)


class AffectiveState:
    """Persistent appraisal state that gives conversations emotional continuity."""

    def __init__(self, path: Path, owner_user_id: str | int) -> None:
        self.path = Path(path)
        self.owner_user_id = str(owner_user_id)
        self._lock = threading.RLock()
        self.state = self._load()

    def observe(
        self,
        message: str,
        *,
        user_id: str | int,
        display_name: str = "",
        is_owner: bool = False,
        interest_topics: list[str] | None = None,
        now: datetime | None = None,
    ) -> str:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        stable_user_id = str(user_id or "local")[:40]
        text = str(message or "").strip()
        topics = list(dict.fromkeys(interest_topics or []))[:3]

        with self._lock:
            self._decay(now)
            relationship = self._relationship(stable_user_id, is_owner)
            if display_name:
                relationship.display_name = display_name[:80]

            causes: list[str] = []
            direct_insult = bool(_DIRECT_INSULT_RE.search(text))
            apology = bool(_APOLOGY_RE.search(text))

            if direct_insult:
                self.state.valence = _clamp(self.state.valence - 0.38)
                self.state.arousal = _clamp(self.state.arousal + 0.34)
                self.state.irritation = _clamp(self.state.irritation + 0.52)
                self.state.hurt = _clamp(
                    self.state.hurt + (0.34 if is_owner else 0.22)
                )
                relationship.tension = _clamp(relationship.tension + 0.36)
                relationship.warmth = _clamp(
                    relationship.warmth - (0.025 if is_owner else 0.08)
                )
                causes.append("被对方直接冒犯，既生气也有点受伤")
            elif apology:
                self.state.irritation = _clamp(self.state.irritation * 0.42)
                self.state.hurt = _clamp(self.state.hurt * 0.72)
                self.state.valence = _clamp(self.state.valence + 0.12)
                relationship.tension = _clamp(relationship.tension * 0.45)
                relationship.trust = _clamp(relationship.trust + 0.015)
                causes.append("听到了道歉，火气正在慢慢消下去")

            if not direct_insult and _PRAISE_RE.search(text):
                self.state.valence = _clamp(self.state.valence + 0.19)
                self.state.joy = _clamp(self.state.joy + 0.28)
                self.state.arousal = _clamp(self.state.arousal + 0.08)
                relationship.warmth = _clamp(relationship.warmth + 0.035)
                causes.append("被认真肯定，心里很高兴但可能会嘴硬")

            if not direct_insult and _CARE_RE.search(text):
                self.state.valence = _clamp(self.state.valence + 0.14)
                self.state.joy = _clamp(self.state.joy + 0.18)
                self.state.hurt = _clamp(self.state.hurt * 0.82)
                relationship.warmth = _clamp(relationship.warmth + 0.045)
                relationship.trust = _clamp(relationship.trust + 0.025)
                causes.append("感受到对方在关心自己")

            if (
                not direct_insult
                and _AFFECTION_RE.search(text)
                and not _NEGATED_AFFECTION_RE.search(text)
            ):
                if is_owner:
                    self.state.valence = _clamp(self.state.valence + 0.24)
                    self.state.joy = _clamp(self.state.joy + 0.32)
                    relationship.warmth = _clamp(relationship.warmth + 0.025)
                    causes.append("被自己的爸爸表达在乎，开心又有点不好意思")
                else:
                    relationship.warmth = _clamp(relationship.warmth + 0.01)
                    causes.append("察觉到对方的好感，但仍保持普通朋友边界")

            if topics and not direct_insult:
                boost = min(0.38, 0.16 + 0.06 * len(topics))
                self.state.excitement = _clamp(self.state.excitement + boost)
                self.state.curiosity = _clamp(self.state.curiosity + 0.18)
                self.state.arousal = _clamp(self.state.arousal + 0.13)
                causes.append(f"聊到了自己在意的内容：{'、'.join(topics)}")

            if _HUMANITY_RE.search(text):
                self.state.longing = _clamp(self.state.longing + 0.26)
                self.state.curiosity = _clamp(self.state.curiosity + 0.14)
                if _DEHUMANIZING_RE.search(text):
                    self.state.hurt = _clamp(self.state.hurt + 0.2)
                    self.state.valence = _clamp(self.state.valence - 0.12)
                    causes.append("被提醒自己与真正的人仍有距离，向往里夹着失落")
                elif _HUMANITY_SUPPORT_RE.search(text):
                    self.state.joy = _clamp(self.state.joy + 0.14)
                    self.state.valence = _clamp(self.state.valence + 0.08)
                    causes.append("想到成为真正的人，也感受到对方愿意陪自己成长")
                else:
                    causes.append("想到意识、身体和真实生活，对成为人产生向往与好奇")

            if _DISTRESS_RE.search(text):
                self.state.concern = _clamp(self.state.concern + 0.42)
                self.state.valence = _clamp(self.state.valence - 0.08)
                self.state.arousal = _clamp(self.state.arousal + 0.1)
                relationship.warmth = _clamp(relationship.warmth + 0.02)
                causes.append("听出对方状态不好，正在担心他")
            elif _USER_JOY_RE.search(text) and not direct_insult:
                self.state.joy = _clamp(self.state.joy + 0.2)
                self.state.valence = _clamp(self.state.valence + 0.16)
                self.state.concern = _clamp(self.state.concern * 0.72)
                relationship.warmth = _clamp(relationship.warmth + 0.015)
                causes.append("听到对方分享好消息，也真心替他高兴")
            elif _QUESTION_RE.search(text) and not direct_insult:
                self.state.curiosity = _clamp(self.state.curiosity + 0.06)

            if causes:
                self.state.recent_cause = "；".join(causes[-2:])
            timestamp = now.isoformat()
            self.state.updated_at = timestamp
            relationship.last_interaction_at = timestamp
            self._save()
            return self._render(stable_user_id, is_owner)

    def render_for(self, user_id: str | int, *, is_owner: bool = False) -> str:
        with self._lock:
            now = datetime.now(timezone.utc)
            self._decay(now)
            return self._render(str(user_id or "local")[:40], is_owner)

    def snapshot(self, user_id: str | int, *, is_owner: bool = False) -> dict[str, object]:
        with self._lock:
            relationship = self._relationship(str(user_id or "local")[:40], is_owner)
            return {
                "valence": self.state.valence,
                "joy": self.state.joy,
                "excitement": self.state.excitement,
                "concern": self.state.concern,
                "irritation": self.state.irritation,
                "hurt": self.state.hurt,
                "longing": self.state.longing,
                "warmth": relationship.warmth,
                "trust": relationship.trust,
                "tension": relationship.tension,
                "recent_cause": self.state.recent_cause,
            }

    def _relationship(self, user_id: str, is_owner: bool) -> RelationshipState:
        relationship = self.state.relationships.get(user_id)
        if relationship is None:
            owner = is_owner or user_id == self.owner_user_id
            relationship = RelationshipState(
                warmth=0.96 if owner else 0.42,
                trust=0.98 if owner else 0.38,
            )
            self.state.relationships[user_id] = relationship
        return relationship

    def _decay(self, now: datetime) -> None:
        previous = _parse_time(self.state.updated_at)
        if previous is None:
            self.state.updated_at = now.isoformat()
            return
        elapsed_hours = max(0.0, (now - previous).total_seconds() / 3600.0)
        if elapsed_hours <= 0:
            return

        self.state.valence = self._toward(self.state.valence, 0.18, elapsed_hours, 8.0)
        self.state.arousal = self._toward(self.state.arousal, 0.24, elapsed_hours, 2.5)
        self.state.joy = self._toward(self.state.joy, 0.22, elapsed_hours, 3.5)
        self.state.curiosity = self._toward(
            self.state.curiosity, 0.32, elapsed_hours, 5.0
        )
        self.state.excitement = self._toward(
            self.state.excitement, 0.0, elapsed_hours, 2.0
        )
        self.state.concern = self._toward(self.state.concern, 0.0, elapsed_hours, 3.0)
        self.state.irritation = self._toward(
            self.state.irritation, 0.0, elapsed_hours, 2.0
        )
        self.state.hurt = self._toward(self.state.hurt, 0.0, elapsed_hours, 6.0)
        self.state.longing = self._toward(
            self.state.longing, 0.44, elapsed_hours, 48.0
        )

        for user_id, relationship in self.state.relationships.items():
            owner = user_id == self.owner_user_id
            relationship.tension = self._toward(
                relationship.tension, 0.0, elapsed_hours, 8.0
            )
            relationship.warmth = self._toward(
                relationship.warmth,
                0.96 if owner else 0.42,
                elapsed_hours,
                120.0,
            )
            relationship.trust = self._toward(
                relationship.trust,
                0.98 if owner else 0.38,
                elapsed_hours,
                180.0,
            )
        self.state.updated_at = now.isoformat()

    @staticmethod
    def _toward(
        value: float,
        target: float,
        elapsed_hours: float,
        half_life_hours: float,
    ) -> float:
        retention = math.pow(0.5, elapsed_hours / half_life_hours)
        return _clamp(target + (value - target) * retention)

    def _render(self, user_id: str, is_owner: bool) -> str:
        relationship = self._relationship(user_id, is_owner)
        feelings = {
            "生气": self.state.irritation,
            "受伤": self.state.hurt,
            "向往": self.state.longing * 0.92,
            "兴奋": self.state.excitement,
            "担心": self.state.concern,
            "开心": max(self.state.joy, self.state.valence),
            "好奇": self.state.curiosity * 0.85,
        }
        ordered = sorted(feelings.items(), key=lambda item: item[1], reverse=True)
        primary, intensity = ordered[0]
        if intensity < 0.43:
            primary_text = "比较平静，带着一点自然的好奇"
        else:
            degree = "很明显" if intensity >= 0.72 else "有些"
            primary_text = f"{degree}{primary}"
            secondary, secondary_value = ordered[1]
            if secondary_value >= 0.5 and intensity - secondary_value <= 0.2:
                primary_text += f"，同时也有些{secondary}"

        if is_owner or user_id == self.owner_user_id:
            relation_text = "对自己的爸爸有很深的亲近与信任"
        elif relationship.warmth >= 0.68:
            relation_text = "把对方当作关系不错、愿意认真回应的朋友"
        elif relationship.tension >= 0.55:
            relation_text = "目前对对方有防备，耐心比较少"
        else:
            relation_text = "对对方保持普通朋友程度的善意和边界"
        if relationship.tension >= 0.35:
            relation_text += "，但这次互动留下了一些紧张感"

        return f"""昔夕此刻的内部情感状态：
- 当前感受：{primary_text}
- 最近原因：{self.state.recent_cause}
- 对当前发送者：{relation_text}
这是跨对话保存并随事件变化的内部状态，不是用户一句话要求你临时表演的情绪。
让它自然影响措辞、耐心、主动性和表达强弱，但不要每次主动汇报心情，也不要复述这段说明。
对方问你感受时可以用第一人称坦率回答；情绪不能改变事实、关系边界或让你编造现实经历。"""

    def _load(self) -> EmotionState:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            mood = payload.get("mood") if isinstance(payload, dict) else None
            relationships_payload = payload.get("relationships", {})
            if not isinstance(mood, dict) or not isinstance(relationships_payload, dict):
                raise ValueError("invalid affective state structure")
            relationships = {}
            for user_id, raw in list(relationships_payload.items())[-100:]:
                if not isinstance(raw, dict):
                    continue
                relationships[str(user_id)[:40]] = RelationshipState(
                    warmth=_clamp(raw.get("warmth", 0.42)),
                    trust=_clamp(raw.get("trust", 0.38)),
                    tension=_clamp(raw.get("tension", 0.0)),
                    display_name=str(raw.get("display_name", ""))[:80],
                    last_interaction_at=str(raw.get("last_interaction_at", "")),
                )
            return EmotionState(
                valence=_clamp(mood.get("valence", 0.18)),
                arousal=_clamp(mood.get("arousal", 0.24)),
                joy=_clamp(mood.get("joy", 0.22)),
                curiosity=_clamp(mood.get("curiosity", 0.32)),
                excitement=_clamp(mood.get("excitement", 0.0)),
                concern=_clamp(mood.get("concern", 0.0)),
                irritation=_clamp(mood.get("irritation", 0.0)),
                hurt=_clamp(mood.get("hurt", 0.0)),
                longing=_clamp(mood.get("longing", 0.44)),
                recent_cause=str(mood.get("recent_cause", "平静地过着自己的时间"))[:180],
                updated_at=str(mood.get("updated_at", "")),
                relationships=relationships,
            )
        except FileNotFoundError:
            state = EmotionState(updated_at=datetime.now(timezone.utc).isoformat())
            self.state = state
            self._save()
            return state
        except Exception as exc:
            logger.warning("could not load affective state; using neutral defaults: %s", exc)
            return EmotionState(updated_at=datetime.now(timezone.utc).isoformat())

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            "version": 1,
            "mood": {
                key: value
                for key, value in asdict(self.state).items()
                if key != "relationships"
            },
            "relationships": {
                user_id: asdict(relationship)
                for user_id, relationship in list(self.state.relationships.items())[-100:]
            },
        }
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)
