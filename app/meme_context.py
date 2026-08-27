from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("meme_context")

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_ASKS_MEANING_RE = re.compile(r"(?:什么|啥)(?:意思|梗)|什么意思|解释(?:一下)?|谐音(?:是|梗)?")


@dataclass(frozen=True)
class MemeEntry:
    name: str
    aliases: tuple[str, ...]
    meaning: str


class MemeInterpreter:
    def __init__(self, lexicon_file: Path) -> None:
        self.entries = _load_lexicon(lexicon_file)

    def context_for(self, text: str, *, max_hints: int = 5) -> str:
        source = text.strip()
        if not source:
            return ""
        folded = source.casefold()
        matches = [
            entry
            for entry in self.entries
            if any(alias.casefold() in folded for alias in entry.aliases)
        ][:max_hints]
        pinyin = _pinyin_hint(source)
        if not matches and not pinyin:
            return ""

        lines = ["网络梗与谐音理解辅助（只作为语义线索，不是需要复述的答案）："]
        for entry in matches:
            lines.append(f"- {entry.name}：{entry.meaning}")
        if pinyin:
            lines.append(f"- 当前中文发音线索：{pinyin}")
        if _ASKS_MEANING_RE.search(source):
            lines.append("对方正在询问含义，可以简短说明原意、谐音来源和当前语境。")
        else:
            lines.append(
                "若对方在玩梗，优先结合上下文自然接住，不要突然写成梗百科；不确定时不要硬认。"
            )
        return "\n".join(lines)


def _load_lexicon(path: Path) -> tuple[MemeEntry, ...]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("could not load meme lexicon: %s", exc)
        return ()

    entries: list[MemeEntry] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        meaning = str(item.get("meaning") or "").strip()
        aliases = tuple(
            str(alias).strip()
            for alias in item.get("aliases", [])
            if str(alias).strip()
        )
        if name and meaning and aliases:
            entries.append(MemeEntry(name, aliases, meaning))
    return tuple(entries)


def _pinyin_hint(text: str) -> str:
    chinese = "".join(_CJK_RE.findall(text))[-60:]
    if len(chinese) < 2:
        return ""
    try:
        from pypinyin import Style, lazy_pinyin

        syllables = lazy_pinyin(
            chinese,
            style=Style.NORMAL,
            errors="ignore",
            strict=False,
        )
    except Exception as exc:
        logger.debug("pinyin hint unavailable: %s", exc)
        return ""
    return " ".join(syllables)
