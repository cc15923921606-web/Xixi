from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .asr_bus import normalize_asr_transcript, speech_phonetic_key
from .tts_bus import normalize_chinese_speech_identifiers, normalize_chinese_speech_numbers


_TERMINAL_INTERJECTIONS = ("哎", "唉", "诶", "欸", "呃")
_TERMINAL_MODAL_EQUIVALENT_GROUPS = (
    frozenset(("啦", "了")),
    frozenset(("呀", "啊")),
    frozenset(("嘛", "吗")),
)
_OPTIONAL_ERHUA_EQUIVALENTS = (
    ("一会儿", "一会"),
    ("待会儿", "待会"),
    ("这会儿", "这会"),
    ("一点儿", "一点"),
    ("有点儿", "有点"),
    ("哪儿", "哪"),
    ("这儿", "这"),
    ("那儿", "那"),
    ("玩儿", "玩"),
    ("事儿", "事"),
    ("花儿", "花"),
    ("味儿", "味"),
    ("劲儿", "劲"),
    ("样儿", "样"),
)
_SPOKEN_COMPLEMENT_PARTICLE_RE = re.compile(
    r"(?<=[说做听读写跑走看想讲唱笑哭睡觉过活长学玩聊答回记显])得"
    r"(?=[\u3400-\u4dbf\u4e00-\u9fff])"
)
_SPOKEN_ADVERBIAL_PARTICLE_RE = re.compile(
    r"(安静|认真|慢慢|悄悄|轻轻|开心|高兴|自然|清楚|仔细|故意|直接|"
    r"重新|不断|稳定|完整|顺利|快速|准确|耐心|专心|放心|用力)地"
    r"(?=[\u3400-\u4dbf\u4e00-\u9fff])"
)


def _has_terminal_interjection(value: str) -> bool:
    text = re.sub(r"[\s，,。！？!?；;：:、…~～—-]+$", "", str(value or ""))
    return any(text.endswith(interjection) for interjection in _TERMINAL_INTERJECTIONS)


def _compact_voice_verification_text(value: str) -> str:
    normalized = normalize_asr_transcript(
        normalize_chinese_speech_identifiers(
            normalize_chinese_speech_numbers(str(value or ""))
        ),
        language="zh",
    )
    for expanded, compact in _OPTIONAL_ERHUA_EQUIVALENTS:
        normalized = normalized.replace(expanded, compact)
    normalized = _SPOKEN_COMPLEMENT_PARTICLE_RE.sub("的", normalized)
    normalized = _SPOKEN_ADVERBIAL_PARTICLE_RE.sub(r"\1的", normalized)
    return "".join(
        re.findall(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]", normalized)
    ).casefold()


def _normalize_paired_terminal_modal_particles(
    expected: str,
    actual: str,
) -> tuple[str, str]:
    """Canonicalize sentence-final particles that Whisper commonly confuses."""
    if not expected or not actual:
        return expected, actual
    for group in _TERMINAL_MODAL_EQUIVALENT_GROUPS:
        if expected[-1] in group and actual[-1] in group:
            return expected[:-1] + "啊", actual[:-1] + "啊"
    return expected, actual


def _sequence_match_metrics(expected: Any, actual: Any) -> tuple[float, float, float]:
    if not expected or not actual:
        return 0.0, 0.0, 0.0
    matcher = SequenceMatcher(None, expected, actual, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matcher.ratio(), matched / len(expected), matched / len(actual)


def chinese_voice_match(
    expected_text: str,
    transcript: str,
) -> tuple[bool, float, dict[str, float]]:
    expected = _compact_voice_verification_text(expected_text)
    actual = _compact_voice_verification_text(transcript)
    expected, actual = _normalize_paired_terminal_modal_particles(expected, actual)
    unexpected_terminal_interjection = (
        _has_terminal_interjection(transcript)
        and not _has_terminal_interjection(expected_text)
    )
    if not expected or not actual:
        return False, 0.0, {
            "character_similarity": 0.0,
            "character_recall": 0.0,
            "phonetic_similarity": 0.0,
            "length_ratio": 0.0,
            "unexpected_terminal_interjection": float(
                unexpected_terminal_interjection
            ),
        }

    character_similarity, character_recall, _ = _sequence_match_metrics(
        expected,
        actual,
    )
    expected_phonetic = speech_phonetic_key(expected)
    actual_phonetic = speech_phonetic_key(actual)
    phonetic_similarity, phonetic_recall, _ = _sequence_match_metrics(
        expected_phonetic,
        actual_phonetic,
    )
    if not expected_phonetic or not actual_phonetic:
        phonetic_similarity = character_similarity
        phonetic_recall = character_recall
    length_ratio = min(len(expected), len(actual)) / max(len(expected), len(actual))
    score = (
        character_similarity * 0.42
        + phonetic_similarity * 0.46
        + length_ratio * 0.12
    )

    phonetic_equivalent = (
        length_ratio >= 0.92
        and phonetic_recall >= 0.995
        and phonetic_similarity >= 0.995
    )
    if phonetic_equivalent:
        accepted = True
    elif len(expected) <= 6:
        accepted = (
            length_ratio >= 0.78
            and character_recall >= 0.72
            and phonetic_similarity >= 0.88
            and max(character_similarity, phonetic_similarity) >= 0.88
        )
    elif len(expected) <= 12:
        accepted = (
            length_ratio >= 0.90
            and character_recall >= 0.88
            and phonetic_recall >= 0.94
            and character_similarity >= 0.88
            and phonetic_similarity >= 0.94
        )
    else:
        accepted = (
            length_ratio >= 0.92
            and character_recall >= 0.90
            and phonetic_recall >= 0.92
            and character_similarity >= 0.88
            and phonetic_similarity >= 0.91
        )
    if unexpected_terminal_interjection:
        accepted = False
    return accepted, score, {
        "character_similarity": character_similarity,
        "character_recall": character_recall,
        "phonetic_similarity": phonetic_similarity,
        "length_ratio": length_ratio,
        "unexpected_terminal_interjection": float(
            unexpected_terminal_interjection
        ),
    }
