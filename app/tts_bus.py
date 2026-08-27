from __future__ import annotations

import asyncio
import atexit
from array import array
import json
import math
import re
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import wave
import zlib
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event, Lock, RLock
from typing import Callable
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

import edge_tts
import yaml
try:
    import pygame  # optional for playback
except Exception:  # pragma: no cover
    pygame = None

from .config import Config
from .output_guard import strip_internal_instruction
from .runtime_paths import get_runtime_paths
from .voice_runtime import (
    VOICE_NLTK_DATA_FILES,
    chinese_sovits_path,
    multilingual_gpt_path,
    multilingual_sovits_path,
    voice_nltk_data_root,
    resolve_voice_config,
    resolve_voice_root,
)

logger = logging.getLogger("tts_bus")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_SUPPORTED_TTS_LANGUAGES = frozenset({"zh", "ja", "en"})
_voice_shutdown = Event()
ChineseAudioVerifier = Callable[[str, str], tuple[bool, float, str]]
_CHINESE_PRIMARY_VERIFICATION_ATTEMPTS = 3
_CHINESE_FALLBACK_VERIFICATION_ATTEMPTS = 2
_CHINESE_CLARITY_VERIFICATION_ATTEMPTS = 2
_CHINESE_VERIFICATION_ATTEMPTS = (
    _CHINESE_PRIMARY_VERIFICATION_ATTEMPTS
    + _CHINESE_FALLBACK_VERIFICATION_ATTEMPTS
    + _CHINESE_CLARITY_VERIFICATION_ATTEMPTS
)
_CHINESE_COMMON_IDENTIFIER_PRONUNCIATIONS = {
    "ai": "诶爱",
    "api": "诶披爱",
    "cc": "希希",
    "cpu": "西披优",
    "gpu": "吉披优",
    "gpt": "吉披提",
    "qq": "扣扣",
}
_CHINESE_LATIN_LETTER_PRONUNCIATIONS = {
    "a": "诶", "b": "比", "c": "西", "d": "迪", "e": "伊",
    "f": "艾弗", "g": "吉", "h": "艾尺", "i": "艾", "j": "杰",
    "k": "开", "l": "艾勒", "m": "艾姆", "n": "恩", "o": "欧",
    "p": "披", "q": "丘", "r": "阿", "s": "艾丝", "t": "提",
    "u": "优", "v": "维", "w": "达不溜", "x": "艾克斯",
    "y": "歪", "z": "滋",
}
_CHINESE_DIGITS = "零一二三四五六七八九"


def _chinese_integer_text(value: str) -> str:
    if len(value) > 1 and value.startswith("0"):
        return "".join(_CHINESE_DIGITS[int(digit)] for digit in value)
    number = int(value)
    if number == 0:
        return _CHINESE_DIGITS[0]
    if number >= 100_000_000:
        return "".join(_CHINESE_DIGITS[int(digit)] for digit in value)

    units = ("", "十", "百", "千")

    def under_ten_thousand(part: int) -> str:
        digits = f"{part:04d}"
        output: list[str] = []
        pending_zero = False
        for index, digit_text in enumerate(digits):
            digit = int(digit_text)
            if digit == 0:
                if output:
                    pending_zero = True
                continue
            if pending_zero:
                output.append("零")
                pending_zero = False
            output.append(_CHINESE_DIGITS[digit])
            output.append(units[3 - index])
        return "".join(output)

    high, low = divmod(number, 10_000)
    pieces: list[str] = []
    if high:
        pieces.extend((under_ten_thousand(high), "万"))
        if 0 < low < 1_000:
            pieces.append("零")
    if low:
        pieces.append(under_ten_thousand(low))
    result = "".join(pieces)
    return result[1:] if result.startswith("一十") else result


def normalize_chinese_speech_numbers(text: str) -> str:
    """Turn Arabic numbers into stable Mandarin text before GPT-SoVITS."""
    source = str(text or "")

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        negative = token.startswith("-")
        if negative:
            token = token[1:]
        percent = token.endswith("%")
        if percent:
            token = token[:-1]
        integer, dot, fraction = token.partition(".")
        next_character = source[match.end():match.end() + 1]
        if next_character == "年" and len(integer) == 4 and not dot:
            spoken = "".join(_CHINESE_DIGITS[int(digit)] for digit in integer)
        else:
            spoken = _chinese_integer_text(integer)
        if dot:
            spoken += "点" + "".join(_CHINESE_DIGITS[int(digit)] for digit in fraction)
        if percent:
            spoken = "百分之" + spoken
        if negative:
            spoken = "负" + spoken
        return spoken

    return re.sub(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", replace, source)


def normalize_chinese_speech_identifiers(text: str) -> str:
    """Give short Latin names and abbreviations a stable Mandarin reading."""
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        lowered = token.casefold()
        common = _CHINESE_COMMON_IDENTIFIER_PRONUNCIATIONS.get(lowered)
        if common:
            return common
        if token.isupper() or len(set(lowered)) == 1:
            return "".join(
                _CHINESE_LATIN_LETTER_PRONUNCIATIONS[letter]
                for letter in lowered
            )
        return token

    return re.sub(r"(?<![A-Za-z])[A-Za-z]{1,4}(?![A-Za-z])", replace, str(text or ""))


def _strip_speech_internal_instruction(text: str) -> str:
    cleaned = strip_internal_instruction(text)
    if cleaned == text:
        return text
    logger.warning("removed internal instruction text before speech synthesis")
    return cleaned


def _voice_text_matches_language(text: str, language: str) -> bool:
    if language == "en":
        return not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text)
    if language == "ja":
        return bool(re.search(r"[\u3040-\u30ff]", text))
    if language == "zh":
        return not re.search(r"[\u3040-\u30ff]", text) and not re.search(
            r"(?:\b[A-Za-z]+(?:['-][A-Za-z]+)?\b[\s,.;:!?]*){4,}",
            text,
        )
    return False


def detect_voice_text_language(text: str, *, fallback: str = "zh") -> str:
    """Detect the dominant language before converting a reply for speech."""
    normalized_fallback = str(fallback or "zh").strip().lower()
    if normalized_fallback not in _SUPPORTED_TTS_LANGUAGES:
        normalized_fallback = "zh"
    sample = str(text or "").strip()
    if not sample:
        return normalized_fallback
    has_kana = bool(re.search(r"[\u3040-\u30ff]", sample))
    has_han = bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", sample))
    has_latin = bool(re.search(r"[A-Za-z]", sample))
    has_chinese_only_hint = bool(
        re.search(r"[这们吗语话过还没让给里着说听读写发为个]", sample)
    )
    if (has_latin and (has_kana or has_han)) or (has_kana and has_chinese_only_hint):
        return "mixed"
    if has_kana:
        return "ja"
    if has_han:
        return "zh"
    if has_latin:
        return "en"
    return normalized_fallback


def resolve_voice_language(cfg: Config, language: str | None = None) -> str:
    """Resolve an explicit output language or the persisted voice preference."""
    explicit = str(language or "").strip().lower()
    if explicit in _SUPPORTED_TTS_LANGUAGES:
        return explicit
    configured = str(getattr(cfg, "voice_language", "zh") or "").strip().lower()
    return configured if configured in _SUPPORTED_TTS_LANGUAGES else "zh"


def prepare_voice_text(
    text: str,
    cfg: Config,
    translator: object,
    *,
    reply_language: str = "zh",
    voice_language: str | None = None,
) -> tuple[str, str]:
    """Convert speech content to the selected language without changing chat text."""
    target_language = resolve_voice_language(cfg, voice_language)
    prepared = sanitize_speech_text(text)
    source_text = prepared
    if reply_language != target_language:
        if not callable(translator):
            raise RuntimeError("brain does not support voice language conversion")
        prepared = sanitize_speech_text(
            str(translator(prepared, target_language) or "").strip()
        )
        if prepared and not _voice_text_matches_language(prepared, target_language):
            raise RuntimeError(
                f"voice language conversion returned invalid {target_language} text"
            )
        if len(prepared) > max(320, len(source_text) * 5):
            raise RuntimeError("voice language conversion returned suspicious extra content")
    if not prepared:
        raise RuntimeError(f"empty {target_language} voice output after language conversion")
    return prepared, target_language

_SPEECH_SOURCE_LABELS = (
    "参考来源",
    "资料来源",
    "数据来源",
    "参考资料",
    "相关链接",
    "参考链接",
    "参考文献",
    "来源链接",
    "来源",
    "出处",
    "出典",
    "参考資料",
    "情報源",
    "参照元",
    "引用元",
    "sources?",
    "source links?",
    "references?",
    "bibliography",
    "citations?",
    "related links?",
    "further reading",
)
_SPEECH_SOURCE_LABEL_RE = re.compile(
    rf"(?:{'|'.join(_SPEECH_SOURCE_LABELS)})",
    re.IGNORECASE,
)
_SPEECH_CODE_BLOCK_RE = re.compile(
    r"(?:```|~~~)[\s\S]*?(?:(?:```|~~~)|$)",
    re.MULTILINE,
)
_SPEECH_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_SPEECH_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")
_SPEECH_HTML_LINK_RE = re.compile(
    r"<a\s+[^>]*href\s*=\s*[\"'][^\"']*[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_SPEECH_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPEECH_STANDALONE_LINK_RE = re.compile(
    r"^\s*(?:(?:[-*+]\s+)|(?:\d+[.)、]\s*))?"
    r"(?:\[[^\]]+\]\((?:https?://|www\.)[^)]*\)|"
    r"<?(?:https?://|www\.)[^>\s]+>?)\s*$",
    re.IGNORECASE,
)
_SPEECH_URL_RE = re.compile(
    r"(?:https?|ftp)://[^\s<>\[\](){}\"'，。！？；：、]+|"
    r"www\.[^\s<>\[\](){}\"'，。！？；：、]+",
    re.IGNORECASE,
)
_SPEECH_DOMAIN_RE = re.compile(
    r"(?<![@\w])(?:[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\.)+"
    r"(?:com|net|org|cn|top|io|ai|co|jp|me|tv|cc|info|dev|app|xyz|site|online)"
    r"(?:/[^\s<>\[\](){}\"'，。！？；：、]*)?",
    re.IGNORECASE,
)
_SPEECH_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+",
    re.IGNORECASE,
)
_SPEECH_CITATION_RE = re.compile(
    r"\s*(?:\[(?:\^?\d{1,3})(?:\s*[,，、;\-–—]\s*\d{1,3})*\]|"
    r"【\s*\d{1,3}(?:\s*[,，、;\-–—]\s*\d{1,3})*\s*】|"
    r"［\s*\d{1,3}(?:\s*[,，、;\-–—]\s*\d{1,3})*\s*］|"
    r"〔\s*\d{1,3}(?:\s*[,，、;\-–—]\s*\d{1,3})*\s*〕|"
    r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+)"
)
_SPEECH_REFERENCE_LINE_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\[\^?\d{1,3}\]|【\s*\d{1,3}\s*】|"
    r"［\s*\d{1,3}\s*］|〔\s*\d{1,3}\s*〕)\s*"
)
_SPEECH_NUMBERED_LINE_RE = re.compile(r"^\s*(?:[-*+]\s*)?\d{1,3}[.)、]\s+")
_SPEECH_INLINE_SOURCE_RE = re.compile(
    rf"[（(]\s*{_SPEECH_SOURCE_LABEL_RE.pattern}\s*[:：][^）)]{{0,160}}[）)]",
    re.IGNORECASE,
)
_SPEECH_OUTPUT_LABEL_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"(?:(?:以下|下面)(?:是|为)|这是|here(?:'s|\s+is))?\s*"
    r"(?:\*{1,2}|__)?"
    r"(?:语音内容|朗读内容|回答内容|回复内容|正文|回答|回复|"
    r"中文|日语|英语|音声内容|返答|中国語|日本語|英語|"
    r"voice(?:\s+content)?|speech|answer|response|"
    r"chinese|japanese|english)"
    r"(?:\*{1,2}|__)?\s*[:：]\s*",
    re.IGNORECASE,
)
_SPEECH_METADATA_LINE_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:source\s*url|url|来源链接|参考链接|链接地址|"
    r"检索词|查询词|语言|language|语音引擎|voice\s*engine|model)\s*[:：]",
    re.IGNORECASE,
)
_SPEECH_STAGE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:昔夕|小夕|xixi)\s*)?"
    r"(?:(?:微微一笑|轻轻一笑|笑了笑|想了想|沉默片刻|清了清嗓子)[，,\s]*)?"
    r"(?:(?:用|以)\s*[^：:\n]{0,32}?(?:语气|口吻|声音|中文|日语|英语)\s*)?"
    r"(?:回复道|回答道|说道|说|回复|回答)\s*[:：]\s*",
    re.IGNORECASE,
)
_SPEECH_DELIVERY_PREFIX_RE = re.compile(
    r"^\s*(?:好的?[，,\s]*)?(?:我(?:会|将|来)?|接下来)?\s*"
    r"(?:用|以)\s*[^：:\n]{0,32}?(?:回答|回复|说)\s*[:：]\s*",
    re.IGNORECASE,
)
_SPEECH_BRACKETED_METADATA_RE = re.compile(
    r"[\[【（(]\s*(?:语气|情绪|语言|language|tone|style|voice)\s*[:：]"
    r"[^\]】）)]{0,48}[\]】）)]",
    re.IGNORECASE,
)
_SPEECH_JSON_METADATA_RE = re.compile(
    r"[\"'](?:source|source_url|url|citation|language|voice|model)[\"']\s*:",
    re.IGNORECASE,
)

_APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
_RUNTIME_PATHS = get_runtime_paths()
_WORKSPACE_ROOT = _APP_ROOT.parent
_PACKAGED_VOICE_ROOT = _APP_ROOT / "runtime" / "voice"
_VOICE_REFERENCE_ROOT = _APP_ROOT / "data" / "voice_assets"


def _allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


_CONFIGURED_GPT_SOVITS_URL = str(os.environ.get("GPT_SOVITS_URL") or "").strip().rstrip("/")
_GPT_SOVITS_EXTERNAL_ENDPOINT = bool(_CONFIGURED_GPT_SOVITS_URL)
_GPT_SOVITS_PORT = (
    int(urlparse(_CONFIGURED_GPT_SOVITS_URL).port or 9880)
    if _GPT_SOVITS_EXTERNAL_ENDPOINT
    else _allocate_loopback_port()
)
_GPT_SOVITS_URL = _CONFIGURED_GPT_SOVITS_URL or f"http://127.0.0.1:{_GPT_SOVITS_PORT}"
_DEFAULT_GPT_SOVITS_ROOT = (
    _RUNTIME_PATHS.components_dir / "GPT-SoVITS"
    if getattr(sys, "frozen", False)
    else _WORKSPACE_ROOT / "work" / "GPT-SoVITS"
)
_GPT_SOVITS_ROOT = resolve_voice_root(
    _DEFAULT_GPT_SOVITS_ROOT,
    allow_registered_fallback=not _RUNTIME_PATHS.public_release,
)
_GPT_SOVITS_PYTHON = Path(
    os.environ.get("GPT_SOVITS_PYTHON", str(_GPT_SOVITS_ROOT / ".venv" / "Scripts" / "python.exe"))
)
_GPT_SOVITS_SERVER = Path(
    os.environ.get("GPT_SOVITS_SERVER", str(_GPT_SOVITS_ROOT / "api_v2.py"))
)
_DEFAULT_GPT_SOVITS_CONFIG = (
    _PACKAGED_VOICE_ROOT / "xixi_voice_tts_infer.yaml"
    if getattr(sys, "frozen", False)
    else _WORKSPACE_ROOT / "work" / "xixi_voice_tts_infer.yaml"
)
_GPT_SOVITS_CONFIG = Path(os.environ["GPT_SOVITS_CONFIG"]) if os.environ.get(
    "GPT_SOVITS_CONFIG"
) else resolve_voice_config(_GPT_SOVITS_ROOT, _DEFAULT_GPT_SOVITS_CONFIG)
_GPT_SOVITS_TRAINED_GPT = Path(
    os.environ.get(
        "GPT_SOVITS_TRAINED_GPT",
        str(multilingual_gpt_path(_GPT_SOVITS_ROOT)),
    )
)
_GPT_SOVITS_CHINESE_GPT = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_GPT",
        str(_GPT_SOVITS_ROOT / "GPT_SoVITS" / "pretrained_models" / "s1v3.ckpt")
        if getattr(sys, "frozen", False)
        else str(_GPT_SOVITS_ROOT / "GPT_SoVITS" / "pretrained_models" / "s1v3.ckpt"),
    )
)
_GPT_SOVITS_TRAINED_SOVITS = Path(
    os.environ.get(
        "GPT_SOVITS_TRAINED_SOVITS",
        str(multilingual_sovits_path(_GPT_SOVITS_ROOT)),
    )
)
_GPT_SOVITS_CHINESE_SOVITS = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_SOVITS",
        str(chinese_sovits_path(_GPT_SOVITS_ROOT)),
    )
)
_GPT_SOVITS_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_reference_ja.ogg"),
    )
)
_GPT_SOVITS_CHINESE_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_voice_reference_zh.mp3"),
    )
)
_GPT_SOVITS_CHINESE_FALLBACK_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_FALLBACK_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_reference_zh.mp3"),
    )
)
_GPT_SOVITS_CHINESE_EMOTION_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_EMOTION_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_reference_emphatic.ogg"),
    )
)
_GPT_SOVITS_CHINESE_WARM_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_WARM_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_reference_warm.ogg"),
    )
)
_GPT_SOVITS_CHINESE_PLAYFUL_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_PLAYFUL_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_reference_playful.ogg"),
    )
)
_GPT_SOVITS_CHINESE_CONCERNED_REFERENCE = Path(
    os.environ.get(
        "GPT_SOVITS_CHINESE_CONCERNED_REFERENCE",
        str(_VOICE_REFERENCE_ROOT / "xixi_reference_concerned.ogg"),
    )
)
_GPT_SOVITS_PROMPT = os.environ.get(
    "GPT_SOVITS_PROMPT",
    "少しずつでも前進しておるのだ。その役に立てるのなら我輩も嬉しいぞ。",
)
_GPT_SOVITS_CHINESE_PROMPT = os.environ.get(
    "GPT_SOVITS_CHINESE_PROMPT",
    "拜拜，希希，现在使用的是固定好的最终版中文声音。",
)
_GPT_SOVITS_CHINESE_FALLBACK_PROMPT = os.environ.get(
    "GPT_SOVITS_CHINESE_FALLBACK_PROMPT",
    "你好呀，今天也一起聊点有意思的事情吧。",
)
_GPT_SOVITS_CHINESE_EMOTION_PROMPTS = {
    "emphatic": "嬉しいこと言ってくれるが、我輩を言い訳にするな。",
    "warm": "少しずつでも前進しておるのだその役に立てるのなら我輩も嬉しいぞ",
    "playful": "嬉しいこと言ってくれるが我輩を言い訳にするな",
    "concerned": "少しずつでも前進しておるのだ。その役に立てるのなら我輩も嬉しいぞ。",
}
_gpt_sovits_process: subprocess.Popen[bytes] | None = None
_gpt_sovits_ready = False
_gpt_sovits_start_lock = Lock()
_gpt_sovits_request_lock = RLock()
_gpt_sovits_active_gpt: Path | None = None
_gpt_sovits_active_sovits: Path | None = None
_gpt_sovits_cpu_fallback = False
_voice_prewarm_lock = Lock()
_voice_prewarm_thread: Thread | None = None
_voice_prewarm_requested_language: str | None = None
_voice_prewarm_requested_generation = 0
_voice_prewarm_generation = 0
_voice_prewarm_language = ""
_voice_prewarm_state = "idle"
_voice_prewarm_error = ""

_FINAL_VOICE_RELEASE = "Xixi Voice System 2026-08-11"
_FINAL_VOICE_PROFILES = {
    "zh": "GPT-SoVITS s1v3 + blend30",
    "ja": "GPT-SoVITS e10 + e4_s1572",
    "en": "GPT-SoVITS e10 + e4_s1572",
}

# Japanese voice for when text contains Japanese
_JP_VOICE = "ja-JP-NanamiNeural"
_EN_VOICE = "en-US-JennyNeural"
_CHINESE_SYNTH_SPEED = 1.06
_CHINESE_POST_SPEED = 1.00
_CHINESE_SYNTH_MAX_SPOKEN_CHARS = 32
_CHINESE_SYNTH_MIN_TRAILING_SPOKEN_CHARS = 10
_JAPANESE_SYNTH_MAX_SPOKEN_CHARS = 48
_ENGLISH_SYNTH_MAX_SPOKEN_CHARS = 180
_GENERATED_SPEECH_SILENCE_THRESHOLD_DB = -48
_GENERATED_SPEECH_LONG_SILENCE_SECONDS = 1.20
_GENERATED_SPEECH_RETAINED_SILENCE_SECONDS = 0.36
_GENERATED_SPEECH_MIN_DURATION_SECONDS = 0.12
_CHINESE_BASE_VOLUME_FILTER = (
    f"loudnorm=I=-15:TP=-1:LRA=7,atempo={_CHINESE_POST_SPEED:.2f}"
)
_CHINESE_CONCERNED_RE = re.compile(
    r"(?:难过|伤心|担心|害怕|别怕|没事|抱歉|对不起|累了|疼|痛|哭|孤单|寂寞|安慰)"
)
_CHINESE_WARM_RE = re.compile(
    r"(?:喜欢|爱你|想你|谢谢|欢迎|放心|陪你|爸爸|老爸|爹爹|老爹|早安|晚安|开心|高兴)"
)
_CHINESE_PLAYFUL_RE = re.compile(
    r"(?:哈哈|嘿嘿|好耶|太好了|一起玩|开黑|赢了|哇|耶|[~～])"
)
_CHINESE_EMPHATIC_RE = re.compile(
    r"(?:生气|气死|讨厌|不许|闭嘴|可恶|笨蛋|白痴|才不是|才没(?:有)?|哼)"
)
_CHINESE_TRAILING_MODAL_RE = re.compile(
    r"[呢啊呀嘛啦呐哦喔哟吧诶欸](?:[。！？!?…~～]*)$"
)
_CHINESE_TRANSITION_RE = re.compile(
    r"^(?:不过|但是|可是|然而|只是|所以|然后|而且|其实|总之|另外|对了|话说)"
)

# emoji unicode ranges (safe: does NOT touch CJK)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\u2600-\u26FF"
    "\u2B50-\u2B55"
    "\u200d\ufe0f"
    "]+", re.UNICODE
)

_KAOMOJI = [
    "(^_^)", "(T_T)", "(>_<)", "(^o^)", "(^O^)", "(._.)",
    "(=^.^=)", "XD", ":D", ":P", ":)", ":(",
]


# Polyphonic word corrections using SSML pinyin annotations
_POLYPHONIC_PINYIN = [
    ("银行", "yin2hang2"),
    ("行业", "hang2ye4"),
    ("内行", "nei4hang2"),
    ("外行", "wai4hang2"),
    ("同行", "tong2hang2"),
    ("行情", "hang2qing2"),
    ("各行各业", "ge4hang2ge4ye4"),
    ("行长", "hang2zhang3"),
    ("不行", "bu4xing2"),
    ("行走", "xing2zou3"),
    ("行为", "xing2wei2"),
    ("行动", "xing2dong4"),
    ("进行", "jin4xing2"),
    ("旅行", "lv3xing2"),
    ("行李", "xing2li3"),
    ("成长", "cheng2zhang3"),
    ("生长", "sheng1zhang3"),
    ("家长", "jia1zhang3"),
    ("校长", "xiao4zhang3"),
    ("班长", "ban1zhang3"),
    ("队长", "dui4zhang3"),
    ("市长", "shi4zhang3"),
    ("长辈", "zhang3bei4"),
    ("长相", "zhang3xiang4"),
    ("长大", "zhang3da4"),
    ("长高", "zhang3gao1"),
    ("长度", "chang2du4"),
    ("长期", "chang2qi1"),
    ("长远", "chang2yuan3"),
    ("长久", "chang2jiu3"),
    ("长途", "chang2tu2"),
    ("长城", "chang2cheng2"),
    ("长江", "chang2jiang1"),
    ("了解", "liao3jie3"),
    ("了结", "liao3jie2"),
    ("了不起", "liao3bu4qi3"),
    ("不得了", "bu4de2liao3"),
    ("受不了", "shou4bu4liao3"),
    ("少不了", "shao3bu4liao3"),
    ("了得", "liao3de2"),
    ("获得", "huo4de2"),
    ("取得", "qu3de2"),
    ("得分", "de2fen1"),
    ("得到", "de2dao4"),
    ("得出", "de2chu1"),
    ("得意", "de2yi4"),
    ("心得", "xin1de2"),
    ("还是", "hai2shi4"),
    ("还有", "hai2you3"),
    ("还在", "hai2zai4"),
    ("还没", "hai2mei2"),
    ("还能", "hai2neng2"),
    ("还会", "hai2hui4"),
    ("还好", "hai2hao3"),
    ("还要", "hai2yao4"),
    ("还不", "hai2bu4"),
    ("还得", "hai2dei3"),
    ("归还", "gui1huan2"),
    ("还钱", "huan2qian2"),
    ("还债", "huan2zhai4"),
    ("还书", "huan2shu1"),
    ("还给", "huan2gei3"),
    ("还清", "huan2qing1"),
    ("快乐", "kuai4le4"),
    ("乐趣", "le4qu4"),
    ("欢乐", "huan1le4"),
    ("乐观", "le4guan1"),
    ("娱乐", "yu2le4"),
    ("音乐", "yin1yue4"),
    ("乐器", "yue4qi4"),
    ("乐曲", "yue4qu3"),
    ("乐团", "yue4tuan2"),
    ("乐队", "yue4dui4"),
    ("干净", "gan1jing4"),
    ("干燥", "gan1zao4"),
    ("干脆", "gan1cui4"),
    ("干活", "gan4huo2"),
    ("干什么", "gan4shen2me5"),
    ("数数", "shu3shu4"),
    ("数不清", "shu3bu4qing1"),
    ("数学", "shu4xue2"),
    ("数字", "shu4zi4"),
    ("数量", "shu4liang4"),
    ("重要", "zhong4yao4"),
    ("重大", "zhong4da4"),
    ("重量", "zhong4liang4"),
    ("重视", "zhong4shi4"),
    ("重点", "zhong4dian3"),
    ("重复", "chong2fu4"),
    ("重新", "chong2xin1"),
    ("重来", "chong2lai2"),
    ("各种", "ge4zhong3"),
    ("一种", "yi1zhong3"),
    ("种类", "zhong3lei4"),
    ("种子", "zhong3zi3"),
    ("种地", "zhong4di4"),
    ("种花", "zhong4hua1"),
    ("方便", "fang1bian4"),
    ("随便", "sui2bian4"),
    ("便利", "bian4li4"),
    ("便宜", "pian2yi2"),
    ("觉得", "jue2de5"),
    ("感觉", "gan3jue2"),
    ("觉察", "jue2cha2"),
    ("睡觉", "shui4jiao4"),
    ("午觉", "wu3jiao4"),
]


def _fix_polyphonic(text: str) -> str:
    """Disabled: edge-tts does not support SSML phoneme tags.
    Leaving text as-is since edge-tts neural model handles polyphonic words reasonably well in context."""
    return text


def _is_japanese_text(text: str) -> bool:
    """Check if text is Japanese by looking for hiragana/katakana."""
    for char in text:
        cp = ord(char)
        if 0x3040 <= cp <= 0x30FF:
            return True
    return False


def _fix_japanese_readings(text: str) -> str:
    """Replace Japanese kanji compound words with hiragana for correct TTS.

    Only applies when text already contains hiragana/katakana,
    to avoid converting Chinese text into Japanese readings.
    Single-char kanji mappings are excluded since they are valid Chinese too.
    """
    if not _is_japanese_text(text):
        return text

    _JP_READINGS = {
        "\u4eca\u65e5": "\u304d\u3087\u3046",
        "\u660e\u65e5": "\u3042\u3057\u305f",
        "\u6628\u65e5": "\u304d\u306e\u3046",
        "\u8cb3\u65b9": "\u3042\u306a\u305f",
        "\u5f7c\u5973": "\u304b\u306e\u3058\u3087",
        "\u5927\u4e08\u592b": "\u3060\u3044\u3058\u3087\u3046\u3076",
        "\u7f8e\u5473\u3057\u3044": "\u304a\u3044\u3057\u3044",
        "\u53ef\u611b\u3044": "\u304b\u308f\u3044\u3044",
        "\u5b09\u3057": "\u3046\u308c\u3057",
        "\u60b2\u3057": "\u304b\u306a\u3057",
        "\u697d\u3057": "\u305f\u306e\u3057",
        "\u96e3\u3057": "\u3080\u305a\u304b\u3057",
        "\u7db6\u9e97": "\u304d\u308c\u3044",
        "\u7d20\u6575": "\u3059\u3066\u304d",
        "\u9811\u5f35": "\u304c\u3093\u3070",
        "\u4e86\u89e3": "\u308a\u3087\u3046\u304b\u3044",
        "\u672c\u5f53": "\u307b\u3093\u3068\u3046",
        "\u6709\u96e3\u3046": "\u3042\u308a\u304c\u3068\u3046",
        "\u5fa1\u514d": "\u3054\u3081\u3093",
        "\u4e00\u7dd2": "\u3044\u3063\u3057\u3087",
        "\u5168\u7136": "\u305c\u3093\u305c\u3093",
        "\u591a\u5206": "\u305f\u3076\u3093",
        "\u52ff\u8ad6": "\u3082\u3061\u308d\u3093",
        "\u6210\u7a0b": "\u306a\u308b\u307b\u3069",
        "\u77e2\u5f35\u308a": "\u3084\u306f\u308a",
        "\u5176\u51e6": "\u305d\u3053",
        "\u5176\u308c": "\u305d\u308c",
        "\u6b64\u51e6": "\u3053\u3053",
        "\u6b64\u308c": "\u3053\u308c",
        "\u4f55\u51e6": "\u3069\u3053",
        "\u4f55\u6545": "\u306a\u305c",
        "\u5b66\u6821": "\u304c\u3063\u3053\u3046",
        "\u5148\u751f": "\u305b\u3093\u305b\u3044",
        "\u53cb\u9054": "\u3068\u3082\u3060\u3061",
        "\u5143\u6c17": "\u3052\u3093\u304d",
        "\u5929\u6c17": "\u3066\u3093\u304d",
        "\u4ed5\u4e8b": "\u3057\u3054\u3068",
        "\u96fb\u8eca": "\u3067\u3093\u3057\u3083",
        "\u98db\u884c\u6a5f": "\u3072\u3053\u3046\u304d",
        "\u56f3\u66f8\u9928": "\u3068\u3057\u3087\u304b\u3093",
        "\u75c5\u9662": "\u3073\u3087\u3046\u3044\u3093",
        "\u98df\u5802": "\u3057\u3087\u304f\u3069\u3046",
        "\u8cb7\u7269": "\u304b\u3044\u3082\u306e",
        "\u6563\u6b69": "\u3055\u3093\u307d",
        "\u52c9\u5f37": "\u3079\u3093\u304d\u3087\u3046",
        "\u5bbf\u984c": "\u3057\u3085\u304f\u3060\u3044",
        "\u8a66\u9a13": "\u3057\u3051\u3093",
        "\u9023\u7d61": "\u308c\u3093\u3089\u304f",
        "\u7d04\u675f": "\u3084\u304f\u305d\u304f",
        "\u5fc3\u914d": "\u3057\u3093\u3071\u3044",
        "\u5927\u597d\u304d": "\u3060\u3044\u3059\u304d",
        "\u5acc\u3044": "\u304d\u3089\u3044",
        "\u4e0a\u624b": "\u3058\u3087\u3046\u305a",
        "\u4e0b\u624b": "\u3078\u305f",
        "\u53ef\u54c0\u60f3": "\u304b\u308f\u3044\u305d\u3046",
        "\u304a\u3081\u3067\u3068\u3046": "\u304a\u3081\u3067\u3068\u3046",
        "\u5b9c\u3057\u304f": "\u3088\u308d\u3057\u304f",
        "\u53ef\u7b11\u3057\u3044": "\u304a\u304b\u3057\u3044",
        "\u7f8e\u3057\u3044": "\u3046\u3064\u304f\u3057\u3044",
        "\u5927\u304d\u3044": "\u304a\u304a\u304d\u3044",
        "\u5c0f\u3055\u3044": "\u3061\u3044\u3055\u3044",
        "\u65b0\u3057\u3044": "\u3042\u305f\u3089\u3057\u3044",
        "\u53e4\u3044": "\u3075\u308b\u3044",
        "\u9577\u3044": "\u306a\u304c\u3044",
        "\u77ed\u3044": "\u307f\u3058\u304b\u3044",
        "\u65e9\u3044": "\u306f\u3084\u3044",
        "\u9045\u3044": "\u304a\u305d\u3044",
        "\u6691\u3044": "\u3042\u3064\u3044",
        "\u5bd2\u3044": "\u3055\u3080\u3044",
        "\u5b09\u3057\u3044": "\u3046\u308c\u3057\u3044",
        "\u60b2\u3057\u3044": "\u304b\u306a\u3057\u3044",
        "\u697d\u3057\u3044": "\u305f\u306e\u3057\u3044",
        "\u96e3\u3057\u3044": "\u3080\u305a\u304b\u3057\u3044",
        "\u7f8e\u5473\u3057\u3044": "\u304a\u3044\u3057\u3044",
    }
    for kanji, hiragana in _JP_READINGS.items():
        if kanji in text:
            text = text.replace(kanji, hiragana)
    return text


def _split_by_language(text: str) -> list[tuple[str, str]]:
    """Split text into Chinese, Japanese, and English speech segments."""
    if not text:
        return []

    def is_cjk(char: str) -> bool:
        cp = ord(char)
        return 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF

    def is_kana(char: str) -> bool:
        cp = ord(char)
        return 0x3040 <= cp <= 0x30FF

    # A kanji run touching kana is Japanese. This keeps Chinese text before
    # a Japanese phrase from being sent to the Japanese voice.
    cjk_is_japanese = [False] * len(text)
    index = 0
    while index < len(text):
        if not is_cjk(text[index]):
            index += 1
            continue
        end = index
        while end < len(text) and is_cjk(text[end]):
            end += 1
        touches_kana = (
            (index > 0 and is_kana(text[index - 1]))
            or (end < len(text) and is_kana(text[end]))
        )
        for cjk_index in range(index, end):
            cjk_is_japanese[cjk_index] = touches_kana
        index = end

    segments: list[tuple[str, str]] = []
    current_lang = "zh"
    current_text = []

    for index, char in enumerate(text):
        cp = ord(char)

        if is_kana(char):
            lang = "ja"
        elif (0x41 <= cp <= 0x5A) or (0x61 <= cp <= 0x7A):
            lang = "en"
        elif is_cjk(char):
            lang = "ja" if cjk_is_japanese[index] else "zh"
        else:
            lang = current_lang

        if lang == current_lang:
            current_text.append(char)
        else:
            if current_text:
                segments.append((current_lang, "".join(current_text)))
            current_lang = lang
            current_text = [char]

    if current_text:
        segments.append((current_lang, "".join(current_text)))

    return segments


def _voice_for_language(language: str | None, cfg: Config) -> str:
    if language == "ja":
        return _JP_VOICE
    if language == "en":
        return _EN_VOICE
    return cfg.tts_voice


def _merge_mp3_files(input_files: list[str], output_path: str) -> None:
    """Merge MP3 streams with ffmpeg instead of concatenating file bytes."""
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        command = [ffmpeg, "-y"]
        for input_file in input_files:
            command.extend(["-i", input_file])
        labels = "".join(f"[{index}:a]" for index in range(len(input_files)))
        command.extend([
            "-filter_complex",
            f"{labels}concat=n={len(input_files)}:v=0:a=1[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            output_path,
        ])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1000:])
    except Exception as exc:
        logger.exception("MP3 merge failed: %s", exc)
        raise RuntimeError("无法合并多语言语音片段") from exc


def _final_voice_assets() -> tuple[Path, ...]:
    return (
        _GPT_SOVITS_TRAINED_GPT,
        _GPT_SOVITS_CHINESE_GPT,
        _GPT_SOVITS_TRAINED_SOVITS,
        _GPT_SOVITS_CHINESE_SOVITS,
        _GPT_SOVITS_REFERENCE,
        _GPT_SOVITS_CHINESE_REFERENCE,
        _GPT_SOVITS_CHINESE_FALLBACK_REFERENCE,
        _GPT_SOVITS_CHINESE_EMOTION_REFERENCE,
        _GPT_SOVITS_CHINESE_WARM_REFERENCE,
        _GPT_SOVITS_CHINESE_PLAYFUL_REFERENCE,
        _GPT_SOVITS_CHINESE_CONCERNED_REFERENCE,
        *tuple(
            voice_nltk_data_root(_GPT_SOVITS_ROOT) / Path(relative)
            for relative in VOICE_NLTK_DATA_FILES
        ),
    )


def _missing_final_voice_assets() -> tuple[Path, ...]:
    return tuple(path for path in _final_voice_assets() if not path.is_file())


def _validate_final_voice_release() -> None:
    missing = _missing_final_voice_assets()
    if missing:
        details = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"最终版语音文件缺失，已拒绝回退旧版：{details}")


def _gpt_sovits_process_environment() -> dict[str, str]:
    """Launch the voice server with only the installed, self-contained data."""
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment.pop("_MEIPASS2", None)
    for name in tuple(environment):
        if name.startswith("_PYI_"):
            environment.pop(name, None)
    environment["NLTK_DATA"] = str(voice_nltk_data_root(_GPT_SOVITS_ROOT))
    return environment


class GPTSovitsRequestError(RuntimeError):
    def __init__(self, action: str, detail: str, *, status: int = 0) -> None:
        self.action = action
        self.detail = detail
        self.status = status
        super().__init__(f"{action}失败：{detail}")


def _http_error_detail(exc: HTTPError) -> str:
    try:
        payload = exc.read(16_384)
    except Exception:
        payload = b""
    text = payload.decode("utf-8", errors="replace").strip()
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            message = str(parsed.get("message") or "").strip()
            exception = str(parsed.get("Exception") or parsed.get("exception") or "").strip()
            combined = "：".join(part for part in (message, exception) if part)
            if combined:
                return combined[:2000]
        return text[:2000]
    return str(exc.reason or exc)


def _gpt_sovits_json_request(url: str, *, timeout: float, action: str) -> dict[str, object]:
    try:
        with urllib_request.urlopen(url, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        raise GPTSovitsRequestError(
            action,
            _http_error_detail(exc),
            status=int(getattr(exc, "code", 0) or 0),
        ) from exc
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GPTSovitsRequestError(action, "语音服务返回了无法识别的数据") from exc
    if not isinstance(result, dict):
        raise GPTSovitsRequestError(action, "语音服务返回格式不正确")
    return result


def _voice_server_log_tail(path: Path, *, limit: int = 5000) -> str:
    try:
        payload = path.read_bytes()[-limit:]
    except OSError:
        return ""
    for encoding in ("utf-8", "gb18030"):
        try:
            return payload.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace").strip()


def _is_acceleration_failure(detail: str) -> bool:
    normalized = str(detail or "").casefold()
    markers = (
        "cuda",
        "cublas",
        "cudnn",
        "out of memory",
        "not enough memory",
        "nvidia driver",
        "显存",
    )
    return any(marker in normalized for marker in markers)


def _activate_gpt_sovits_cpu_fallback() -> None:
    global _GPT_SOVITS_CONFIG, _gpt_sovits_cpu_fallback
    if _GPT_SOVITS_EXTERNAL_ENDPOINT:
        raise RuntimeError("外部语音服务无法由昔夕自动切换到 CPU")
    try:
        config = yaml.safe_load(_GPT_SOVITS_CONFIG.read_text(encoding="utf-8-sig")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError("无法创建语音服务 CPU 兼容配置") from exc
    if not isinstance(config, dict):
        raise RuntimeError("语音服务配置格式不正确")
    custom = dict(config.get("custom") or {})
    custom["device"] = "cpu"
    custom["is_half"] = False
    config["custom"] = custom
    target = _GPT_SOVITS_ROOT / "xixi_voice_tts_infer_cpu.yaml"
    temporary = target.with_suffix(".yaml.tmp")
    temporary.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    _stop_gpt_sovits_server()
    _GPT_SOVITS_CONFIG = target
    _gpt_sovits_cpu_fallback = True
    logger.warning("GPT-SoVITS switched to CPU compatibility mode after acceleration failure")


def _gpt_sovits_health() -> bool:
    try:
        with urllib_request.urlopen(f"{_GPT_SOVITS_URL}/openapi.json", timeout=1.5) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def voice_service_status() -> dict[str, object]:
    missing = _missing_final_voice_assets()
    process = _gpt_sovits_process
    process_alive = process is not None and process.poll() is None
    if _gpt_sovits_ready and (process is None or process_alive):
        server_online = True
    else:
        server_online = _gpt_sovits_health()
    with _voice_prewarm_lock:
        prewarm = {
            "state": _voice_prewarm_state,
            "language": _voice_prewarm_language,
            "error": _voice_prewarm_error,
        }
    return {
        "online": server_online and not missing,
        "engine": "GPT-SoVITS",
        "voice": "昔夕语音系统（中/日/英）",
        "release": _FINAL_VOICE_RELEASE,
        "profiles": dict(_FINAL_VOICE_PROFILES),
        "release_ready": not missing,
        "missing_assets": [str(path) for path in missing],
        "prewarm": prewarm,
    }


def start_voice_service() -> dict[str, object]:
    _validate_final_voice_release()
    _ensure_gpt_sovits_server()
    return voice_service_status()


def _prepare_voice_language(language: str) -> None:
    with _gpt_sovits_request_lock:
        _ensure_gpt_sovits_server()
        _select_gpt_sovits_gpt(language)
        _select_gpt_sovits_sovits(language)
        _warm_gpt_sovits_inference(language)


def _warm_gpt_sovits_inference(language: str) -> None:
    warmup_text = {
        "zh": "嗯。",
        "ja": "はい。",
        "en": "Okay.",
    }[language]
    output_path = tempfile.mktemp(suffix="_xixi_voice_warmup.wav")
    try:
        _generate_gpt_sovits_audio_unlocked(
            warmup_text,
            output_path,
            language,
            _CHINESE_SYNTH_SPEED if language == "zh" else 1.0,
        )
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def _voice_prewarm_worker() -> None:
    global _voice_prewarm_thread
    global _voice_prewarm_requested_language
    global _voice_prewarm_requested_generation
    global _voice_prewarm_language
    global _voice_prewarm_state
    global _voice_prewarm_error

    while True:
        with _voice_prewarm_lock:
            language = _voice_prewarm_requested_language
            generation = _voice_prewarm_requested_generation
            _voice_prewarm_requested_language = None
            if language is None:
                _voice_prewarm_thread = None
                return
            _voice_prewarm_language = language
            _voice_prewarm_state = "warming"
            _voice_prewarm_error = ""
        try:
            started = time.monotonic()
            with _gpt_sovits_request_lock:
                with _voice_prewarm_lock:
                    if generation != _voice_prewarm_generation:
                        continue
                _prepare_voice_language(language)
            logger.info(
                "voice language prewarmed: language=%s duration_ms=%s",
                language,
                round((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            logger.exception("could not prewarm %s voice", language)
            with _voice_prewarm_lock:
                if (
                    generation == _voice_prewarm_generation
                    and _voice_prewarm_requested_language is None
                ):
                    _voice_prewarm_state = "error"
                    _voice_prewarm_error = str(exc)[:240]
            continue
        with _voice_prewarm_lock:
            if (
                generation == _voice_prewarm_generation
                and _voice_prewarm_requested_language is None
            ):
                _voice_prewarm_state = "ready"
                _voice_prewarm_error = ""


def prewarm_voice_language(language: str) -> dict[str, str]:
    """Load the selected final voice weights without synthesizing warm-up audio."""
    global _voice_prewarm_thread
    global _voice_prewarm_requested_language
    global _voice_prewarm_requested_generation
    global _voice_prewarm_generation
    global _voice_prewarm_language
    global _voice_prewarm_state
    global _voice_prewarm_error

    normalized = str(language or "").strip().lower()
    if normalized not in _SUPPORTED_TTS_LANGUAGES:
        raise ValueError(f"unsupported TTS language: {normalized}")
    with _voice_prewarm_lock:
        if (
            normalized == _voice_prewarm_language
            and _voice_prewarm_state in {"warming", "ready"}
        ):
            return {
                "state": _voice_prewarm_state,
                "language": _voice_prewarm_language,
                "error": _voice_prewarm_error,
            }
        _voice_prewarm_generation += 1
        _voice_prewarm_requested_language = normalized
        _voice_prewarm_requested_generation = _voice_prewarm_generation
        _voice_prewarm_language = normalized
        _voice_prewarm_state = "warming"
        _voice_prewarm_error = ""
        if _voice_prewarm_thread is None or not _voice_prewarm_thread.is_alive():
            _voice_prewarm_thread = Thread(
                target=_voice_prewarm_worker,
                name="xixi-voice-prewarm",
                daemon=True,
            )
            _voice_prewarm_thread.start()
        return {
            "state": _voice_prewarm_state,
            "language": _voice_prewarm_language,
            "error": _voice_prewarm_error,
        }


def wait_for_voice_prewarm(timeout: float = 300.0) -> dict[str, str]:
    """Wait for the current prewarm job; intended for diagnostics and tests."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        with _voice_prewarm_lock:
            thread = _voice_prewarm_thread
        if thread is None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(timeout=remaining)
    with _voice_prewarm_lock:
        return {
            "state": _voice_prewarm_state,
            "language": _voice_prewarm_language,
            "error": _voice_prewarm_error,
        }


def stop_voice_service() -> dict[str, object]:
    global _voice_prewarm_requested_language
    global _voice_prewarm_generation
    global _voice_prewarm_language
    global _voice_prewarm_state
    global _voice_prewarm_error
    with _voice_prewarm_lock:
        _voice_prewarm_generation += 1
        _voice_prewarm_requested_language = None
        _voice_prewarm_language = ""
        _voice_prewarm_state = "idle"
        _voice_prewarm_error = ""
        prewarm_thread = _voice_prewarm_thread
    with _gpt_sovits_request_lock:
        if _gpt_sovits_health():
            try:
                urllib_request.urlopen(
                    f"{_GPT_SOVITS_URL}/control?command=exit",
                    timeout=4.0,
                ).close()
            except Exception:
                # The server may close its socket before responding while it exits.
                pass
        _stop_gpt_sovits_server()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not _gpt_sovits_health():
                break
            time.sleep(0.2)
    if prewarm_thread is not None and prewarm_thread.is_alive():
        prewarm_thread.join(timeout=3.0)
    with _voice_prewarm_lock:
        _voice_prewarm_language = ""
        _voice_prewarm_state = "idle"
        _voice_prewarm_error = ""
    status = voice_service_status()
    if status["online"]:
        raise RuntimeError("GPT-SoVITS 语音服务未能停止")
    return status


def _ensure_gpt_sovits_server() -> None:
    global _gpt_sovits_process, _gpt_sovits_ready
    _validate_final_voice_release()
    if _voice_shutdown.is_set():
        raise RuntimeError("GPT-SoVITS voice service is shutting down")
    if _gpt_sovits_health():
        _gpt_sovits_ready = True
        return
    with _gpt_sovits_start_lock:
        if _voice_shutdown.is_set():
            raise RuntimeError("GPT-SoVITS voice service is shutting down")
        if _gpt_sovits_health():
            _gpt_sovits_ready = True
            return
        if _GPT_SOVITS_EXTERNAL_ENDPOINT:
            raise RuntimeError(f"配置的外部语音服务不可用：{_GPT_SOVITS_URL}")
        required = [
            _GPT_SOVITS_PYTHON,
            _GPT_SOVITS_SERVER,
            _GPT_SOVITS_CONFIG,
            _GPT_SOVITS_REFERENCE,
            _GPT_SOVITS_CHINESE_REFERENCE,
            _GPT_SOVITS_CHINESE_FALLBACK_REFERENCE,
            _GPT_SOVITS_CHINESE_EMOTION_REFERENCE,
            _GPT_SOVITS_CHINESE_WARM_REFERENCE,
            _GPT_SOVITS_CHINESE_PLAYFUL_REFERENCE,
            _GPT_SOVITS_CHINESE_CONCERNED_REFERENCE,
            _GPT_SOVITS_TRAINED_GPT,
            _GPT_SOVITS_CHINESE_GPT,
            _GPT_SOVITS_TRAINED_SOVITS,
            _GPT_SOVITS_CHINESE_SOVITS,
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"GPT-SoVITS files not found: {', '.join(missing)}")

        log_path = _GPT_SOVITS_ROOT / "gpt_sovits_server.log"
        log_file = open(log_path, "ab")
        process = subprocess.Popen(
            [
                str(_GPT_SOVITS_PYTHON),
                "-u",
                str(_GPT_SOVITS_SERVER),
                "-a",
                "127.0.0.1",
                "-p",
                str(_GPT_SOVITS_PORT),
                "-c",
                str(_GPT_SOVITS_CONFIG),
            ],
            cwd=str(_GPT_SOVITS_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=_gpt_sovits_process_environment(),
            creationflags=_NO_WINDOW,
        )
        _gpt_sovits_process = process
        _gpt_sovits_ready = False
        log_file.close()

        deadline = time.monotonic() + 240.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = _voice_server_log_tail(log_path)
                raise RuntimeError(
                    "GPT-SoVITS server exited"
                    + (f"：{detail}" if detail else f"；请检查 {log_path}")
                )
            if _gpt_sovits_health():
                _gpt_sovits_ready = True
                logger.info("GPT-SoVITS server ready")
                return
            time.sleep(1.0)
        detail = _voice_server_log_tail(log_path)
        raise TimeoutError(
            "GPT-SoVITS server startup timed out"
            + (f"：{detail}" if detail else "")
        )


def _stop_gpt_sovits_server() -> None:
    global _gpt_sovits_process, _gpt_sovits_ready
    global _gpt_sovits_active_gpt, _gpt_sovits_active_sovits
    process = _gpt_sovits_process
    _gpt_sovits_process = None
    _gpt_sovits_ready = False
    _gpt_sovits_active_gpt = None
    _gpt_sovits_active_sovits = None
    if process is not None:
        try:
            # api_v2.py starts a separate worker process (uvicorn reload/runtime
            # process). Terminating only the launcher leaves the model resident,
            # so stop the complete process tree on Windows.
            if os.name == "nt":
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    creationflags=_NO_WINDOW,
                )
            else:
                process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    # api_v2.py can outlive its launcher when uvicorn has already re-parented
    # the worker. Clean only the worker that owns this app instance's port.
    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.CommandLine -like '*api_v2.py*' "
                    f"-and $_.CommandLine -like '* -p {_GPT_SOVITS_PORT}*' }} | "
                    "ForEach-Object { $_.ProcessId }",
                ],
                capture_output=True,
                text=True,
                check=False,
                creationflags=_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                pid = line.strip()
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(
                        ["taskkill.exe", "/PID", pid, "/T", "/F"],
                        capture_output=True,
                        check=False,
                        creationflags=_NO_WINDOW,
                    )
        except Exception:
            logger.debug("could not clean orphaned GPT-SoVITS workers", exc_info=True)


def _cleanup_gpt_sovits_server() -> None:
    """Release a voice backend started by this interpreter at process exit."""
    global _voice_prewarm_generation
    global _voice_prewarm_requested_language
    with _voice_prewarm_lock:
        prewarm_thread = _voice_prewarm_thread
    if _gpt_sovits_process is None and (
        prewarm_thread is None or not prewarm_thread.is_alive()
    ):
        return

    _voice_shutdown.set()
    with _voice_prewarm_lock:
        _voice_prewarm_generation += 1
        _voice_prewarm_requested_language = None
        prewarm_thread = _voice_prewarm_thread
    # A prewarm worker may be between the health check and Popen(). Give it a
    # moment to observe shutdown before terminating the process it registered.
    if prewarm_thread is not None and prewarm_thread.is_alive():
        prewarm_thread.join(timeout=3.0)
    if _gpt_sovits_process is None:
        return
    try:
        _stop_gpt_sovits_server()
    except Exception:
        logger.debug("could not clean up GPT-SoVITS at interpreter exit", exc_info=True)


atexit.register(_cleanup_gpt_sovits_server)


def _convert_wav_to_mp3(
    input_path: str,
    output_path: str,
    audio_filter: str | None = None,
) -> None:
    output_is_wav = Path(output_path).suffix.lower() == ".wav"
    if output_is_wav and not audio_filter:
        try:
            os.replace(input_path, output_path)
        except OSError:
            shutil.copyfile(input_path, output_path)
            os.remove(input_path)
        return
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-y", "-i", input_path]
    if audio_filter:
        command.extend(["-af", audio_filter])
    if output_is_wav:
        command.extend(["-c:a", "pcm_s16le", output_path])
    else:
        command.extend(["-c:a", "libmp3lame", "-b:a", "128k", output_path])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1000:])


def prewarm_call_voice(cfg: Config, language: str) -> dict[str, str]:
    selected_language = resolve_voice_language(cfg, language)
    result = prewarm_voice_language(selected_language)
    return {
        **result,
        "engine": "gpt_sovits",
    }


async def generate_call_tts_audio(
    text: str,
    cfg: Config,
    output_path: str,
    *,
    forced_language: str,
    chinese_verifier: ChineseAudioVerifier | None = None,
) -> None:
    language = resolve_voice_language(cfg, forced_language)
    prepared = _fix_polyphonic(sanitize_speech_text(text))
    if not prepared:
        raise ValueError("TTS text is empty")
    verification_options = (
        {"chinese_verifier": chinese_verifier}
        if chinese_verifier is not None
        else {}
    )
    await generate_tts_audio(
        prepared,
        cfg,
        output_path,
        forced_language=language,
        **verification_options,
    )


def _select_gpt_sovits_gpt(text_language: str) -> None:
    global _gpt_sovits_active_gpt
    target = _GPT_SOVITS_CHINESE_GPT if text_language == "zh" else _GPT_SOVITS_TRAINED_GPT
    if _gpt_sovits_active_gpt == target:
        return
    if not target.is_file():
        raise FileNotFoundError(f"GPT-SoVITS GPT weight not found: {target}")

    query = urlencode({"weights_path": str(target)})
    result = _gpt_sovits_json_request(
        f"{_GPT_SOVITS_URL}/set_gpt_weights?{query}",
        timeout=120,
        action="切换语义模型",
    )
    if result.get("message") != "success":
        raise RuntimeError(f"Could not switch GPT-SoVITS GPT weight: {result}")
    _gpt_sovits_active_gpt = target
    logger.info("GPT-SoVITS semantic weight: %s", target.name)


def _select_gpt_sovits_sovits(text_language: str) -> None:
    global _gpt_sovits_active_sovits
    target = _GPT_SOVITS_CHINESE_SOVITS if text_language == "zh" else _GPT_SOVITS_TRAINED_SOVITS
    if _gpt_sovits_active_sovits == target:
        return
    if not target.is_file():
        raise FileNotFoundError(f"GPT-SoVITS SoVITS weight not found: {target}")

    query = urlencode({"weights_path": str(target)})
    result = _gpt_sovits_json_request(
        f"{_GPT_SOVITS_URL}/set_sovits_weights?{query}",
        timeout=120,
        action="切换声学模型",
    )
    if result.get("message") != "success":
        raise RuntimeError(f"Could not switch GPT-SoVITS SoVITS weight: {result}")
    _gpt_sovits_active_sovits = target
    logger.info("GPT-SoVITS acoustic weight: %s", target.name)


def _generate_gpt_sovits_audio(
    text: str,
    output_path: str,
    text_language: str = "ja",
    speed: float = _CHINESE_SYNTH_SPEED,
    chinese_verifier: ChineseAudioVerifier | None = None,
) -> None:
    with _gpt_sovits_request_lock:
        restarted_after_request_error = False
        while True:
            try:
                _generate_gpt_sovits_audio_unlocked(
                    text,
                    output_path,
                    text_language,
                    speed,
                    chinese_verifier,
                )
                return
            except Exception as exc:
                detail = str(exc)
                if _is_acceleration_failure(detail) and not _gpt_sovits_cpu_fallback:
                    logger.warning(
                        "GPT-SoVITS acceleration failed; retrying on CPU: %s",
                        detail[-1200:],
                    )
                    _activate_gpt_sovits_cpu_fallback()
                    continue
                if (
                    isinstance(exc, GPTSovitsRequestError)
                    and exc.status == 400
                    and not restarted_after_request_error
                    and _gpt_sovits_process is not None
                    and not _GPT_SOVITS_EXTERNAL_ENDPOINT
                ):
                    restarted_after_request_error = True
                    logger.warning(
                        "GPT-SoVITS request failed; restarting isolated voice service once: %s",
                        detail[-1200:],
                    )
                    _stop_gpt_sovits_server()
                    continue
                raise


def _chinese_emotion_profile(text: str) -> tuple[str, Path]:
    if _CHINESE_CONCERNED_RE.search(text):
        return "concerned", _GPT_SOVITS_CHINESE_CONCERNED_REFERENCE
    if _CHINESE_EMPHATIC_RE.search(text):
        return "emphatic", _GPT_SOVITS_CHINESE_EMOTION_REFERENCE
    if _CHINESE_PLAYFUL_RE.search(text):
        return "playful", _GPT_SOVITS_CHINESE_PLAYFUL_REFERENCE
    if _CHINESE_WARM_RE.search(text):
        return "warm", _GPT_SOVITS_CHINESE_WARM_REFERENCE
    return "natural", _GPT_SOVITS_REFERENCE


def _chinese_reference_plan(
    text: str,
) -> tuple[str, Path, str, str, tuple[Path, ...]]:
    """Keep every Chinese request on the articulation-checked Chinese path.

    The emotional source clips are Japanese recordings. Using them as the
    primary prompt for Mandarin made the model occasionally inherit Japanese
    phonetics, which showed up as an accent and unclear initials/finals. The
    Chinese reference still carries the trained voice identity; emotion is
    expressed through the sampling profile instead of changing language data.
    """
    style, _ = _chinese_emotion_profile(text)
    return (
        style,
        _GPT_SOVITS_CHINESE_REFERENCE,
        "zh",
        _GPT_SOVITS_CHINESE_PROMPT,
        (),
    )


def _split_chinese_prosody_segments(text: str) -> tuple[str, ...]:
    clauses = [
        clause.strip()
        for clause in re.findall(r".+?(?:[，,。！？!?；;\n]+|$)", text, flags=re.S)
        if clause.strip()
    ]
    if not clauses:
        return (text,)

    grouped: list[tuple[str, str]] = []
    for clause in clauses:
        style, _ = _chinese_emotion_profile(clause)
        if grouped and grouped[-1][0] == style:
            previous_style, previous_text = grouped[-1]
            grouped[-1] = (previous_style, previous_text + clause)
        else:
            grouped.append((style, clause))
    merged: list[tuple[str, str]] = []
    index = 0
    while index < len(grouped):
        style, segment = grouped[index]
        spoken_length = len(re.sub(r"[^\w\u3400-\u9fff]", "", segment))
        if (
            style == "natural"
            and index + 1 < len(grouped)
            and spoken_length <= 12
            and _CHINESE_TRANSITION_RE.match(segment)
        ):
            next_style, next_segment = grouped[index + 1]
            combined = segment + next_segment
            if merged and merged[-1][0] == next_style:
                previous_style, previous_text = merged[-1]
                merged[-1] = (previous_style, previous_text + combined)
            else:
                merged.append((next_style, combined))
            index += 2
            continue
        if merged and merged[-1][0] == style:
            previous_style, previous_text = merged[-1]
            merged[-1] = (previous_style, previous_text + segment)
        else:
            merged.append((style, segment))
        index += 1
    return tuple(segment for _, segment in merged)


def _chinese_synthesis_segments(text: str) -> tuple[str, ...]:
    def spoken_length(value: str) -> int:
        return len(re.sub(r"[^\w\u3400-\u9fff]", "", value))

    if spoken_length(text) <= _CHINESE_SYNTH_MAX_SPOKEN_CHARS:
        return (text,)

    # GPT-SoVITS cut5 splits at every comma. Long Mandarin replies therefore
    # produce tiny fragments such as "第四段，" or "如果你累了，", and the
    # acoustic model can skip those fragments. Build bounded, complete chunks
    # here and send each one through cut0 instead.
    sentences = [
        sentence
        for sentence in re.findall(r".+?(?:[。！？!?；;\n]+|$)", text, flags=re.S)
        if sentence
    ]
    if not sentences:
        sentences = [text]

    segments: list[str] = []
    for sentence in sentences:
        clauses = [
            clause
            for clause in re.findall(r".+?(?:[，,：:、]+|$)", sentence, flags=re.S)
            if clause
        ]
        sentence_parts: list[str] = []
        for clause in clauses or [sentence]:
            if spoken_length(clause) <= _CHINESE_SYNTH_MAX_SPOKEN_CHARS:
                sentence_parts.append(clause)
                continue

            current = ""
            current_spoken = 0
            for character in clause:
                character_spoken = int(bool(re.match(r"[\w\u3400-\u9fff]", character)))
                if current and current_spoken + character_spoken > _CHINESE_SYNTH_MAX_SPOKEN_CHARS:
                    sentence_parts.append(current)
                    current = ""
                    current_spoken = 0
                current += character
                current_spoken += character_spoken
            if current:
                sentence_parts.append(current)

        stable_parts: list[str] = []
        leading_short = ""
        for part in sentence_parts:
            if spoken_length(part) < 4:
                if stable_parts:
                    stable_parts[-1] += part
                else:
                    leading_short += part
                continue
            stable_parts.append(leading_short + part)
            leading_short = ""
        if leading_short:
            if stable_parts:
                stable_parts[-1] += leading_short
            else:
                stable_parts.append(leading_short)
        if (
            len(stable_parts) >= 2
            and spoken_length(stable_parts[-1]) < _CHINESE_SYNTH_MIN_TRAILING_SPOKEN_CHARS
            and spoken_length(stable_parts[-2] + stable_parts[-1])
            <= _CHINESE_SYNTH_MAX_SPOKEN_CHARS
        ):
            trailing_part = stable_parts.pop()
            stable_parts[-1] += trailing_part
        segments.extend(stable_parts)

    merged_segments: list[str] = []
    for segment in segments:
        if (
            merged_segments
            and spoken_length(merged_segments[-1] + segment)
            <= _CHINESE_SYNTH_MAX_SPOKEN_CHARS
        ):
            merged_segments[-1] += segment
        else:
            merged_segments.append(segment)

    if "".join(merged_segments) != text:
        raise RuntimeError("Chinese speech segmentation lost reply content")
    return tuple(merged_segments)


def _multilingual_synthesis_segments(text: str, language: str) -> tuple[str, ...]:
    """Build complete bounded requests instead of trusting engine-side splitting."""
    if language == "zh":
        return _chinese_synthesis_segments(text)
    maximum = (
        _JAPANESE_SYNTH_MAX_SPOKEN_CHARS
        if language == "ja"
        else _ENGLISH_SYNTH_MAX_SPOKEN_CHARS
    )

    def spoken_length(value: str) -> int:
        return len(re.sub(r"\s+", "", value))

    if spoken_length(text) <= maximum:
        return (text,)
    sentences = [
        sentence
        for sentence in re.findall(r".+?(?:[。！？!?；;\n]+|$)", text, flags=re.S)
        if sentence
    ] or [text]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and spoken_length(current + sentence) <= maximum:
            current += sentence
            continue
        if current:
            pieces.append(current)
            current = ""
        if spoken_length(sentence) <= maximum:
            current = sentence
            continue
        chunk = ""
        for character in sentence:
            if chunk and spoken_length(chunk + character) > maximum:
                pieces.append(chunk)
                chunk = ""
            chunk += character
        current = chunk
    if current:
        pieces.append(current)
    if "".join(pieces) != text:
        raise RuntimeError("Speech segmentation lost reply content")
    return tuple(pieces)


def _chinese_sampling_profile(
    style: str,
    text: str,
    retry_index: int = 0,
) -> tuple[int, float, float, int]:
    # Emotion still comes from the sentence and punctuation. Wider sampling
    # made this model invent or omit syllables, especially around particles.
    top_k, top_p, temperature = 10, 0.88, 0.68
    seed = zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF
    if retry_index > 0:
        seed = (seed + 104729 * retry_index) & 0x7FFFFFFF
        top_k = max(8, top_k - 2 * retry_index)
        top_p = max(0.84, top_p - 0.025 * retry_index)
        temperature = max(0.64, temperature - 0.04 * retry_index)
    return top_k, top_p, temperature, seed


def _wav_duration_seconds(path: str) -> float:
    try:
        with wave.open(path, "rb") as source:
            frame_rate = source.getframerate()
            if frame_rate <= 0:
                raise RuntimeError("generated WAV has an invalid sample rate")
            return source.getnframes() / frame_rate
    except (EOFError, OSError, wave.Error) as exc:
        raise RuntimeError("GPT-SoVITS returned an invalid WAV file") from exc


def _maximum_chinese_segment_duration(text: str) -> float:
    spoken_length = len(re.sub(r"[^\w\u3400-\u9fff]", "", text))
    return max(2.5, 2.5 + spoken_length * 0.42)


def _normalize_generated_wav_silence(input_path: str) -> tuple[float, float]:
    """Remove pathological GPT-SoVITS gaps while preserving normal phrasing."""
    try:
        with wave.open(input_path, "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            frame_rate = source.getframerate()
            compression = source.getcomptype()
            frames = source.readframes(source.getnframes())
    except (EOFError, OSError, wave.Error) as exc:
        raise RuntimeError("GPT-SoVITS returned an invalid WAV file") from exc
    if channels <= 0 or frame_rate <= 0 or sample_width != 2 or compression != "NONE":
        raise RuntimeError("GPT-SoVITS returned an unsupported WAV format")

    frame_width = channels * sample_width
    total_frames = len(frames) // frame_width
    original_duration = total_frames / frame_rate
    window_frames = max(1, int(frame_rate * 0.02))
    windows: list[tuple[int, int, float]] = []
    peak_rms = 0.0
    for start_frame in range(0, total_frames, window_frames):
        end_frame = min(total_frames, start_frame + window_frames)
        chunk = frames[start_frame * frame_width:end_frame * frame_width]
        samples = array("h")
        samples.frombytes(chunk)
        if sys.byteorder != "little":
            samples.byteswap()
        rms = math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))
        peak_rms = max(peak_rms, rms)
        windows.append((start_frame, end_frame, rms))

    if peak_rms < 8.0:
        raise RuntimeError("GPT-SoVITS returned audio without effective speech")
    absolute_threshold = 32768 * 10 ** (
        _GENERATED_SPEECH_SILENCE_THRESHOLD_DB / 20
    )
    silence_threshold = min(absolute_threshold, max(12.0, peak_rms * 0.08))
    silent = [rms <= silence_threshold for _, _, rms in windows]
    if not any(not item for item in silent):
        raise RuntimeError("GPT-SoVITS returned audio without effective speech")

    leading_keep_frames = int(frame_rate * 0.04)
    trailing_keep_frames = int(
        frame_rate * _GENERATED_SPEECH_RETAINED_SILENCE_SECONDS
    )
    internal_keep_frames = trailing_keep_frames
    output_frames = bytearray()
    index = 0
    while index < len(windows):
        run_end = index + 1
        while run_end < len(windows) and silent[run_end] == silent[index]:
            run_end += 1
        start_frame = windows[index][0]
        end_frame = windows[run_end - 1][1]
        if not silent[index]:
            keep_ranges = ((start_frame, end_frame),)
        else:
            run_frames = end_frame - start_frame
            run_duration = run_frames / frame_rate
            if index == 0:
                keep_start = max(start_frame, end_frame - leading_keep_frames)
                keep_ranges = ((keep_start, end_frame),)
            elif run_end == len(windows):
                keep_end = min(end_frame, start_frame + trailing_keep_frames)
                keep_ranges = ((start_frame, keep_end),)
            elif run_duration > _GENERATED_SPEECH_LONG_SILENCE_SECONDS:
                before_frames = internal_keep_frames // 2
                after_frames = internal_keep_frames - before_frames
                keep_ranges = (
                    (start_frame, min(end_frame, start_frame + before_frames)),
                    (max(start_frame, end_frame - after_frames), end_frame),
                )
            else:
                keep_ranges = ((start_frame, end_frame),)
        for keep_start, keep_end in keep_ranges:
            if keep_end > keep_start:
                output_frames.extend(
                    frames[keep_start * frame_width:keep_end * frame_width]
                )
        index = run_end

    normalized_duration = len(output_frames) / frame_width / frame_rate
    if normalized_duration < _GENERATED_SPEECH_MIN_DURATION_SECONDS:
        raise RuntimeError("GPT-SoVITS returned audio without effective speech")

    normalized_path = tempfile.mktemp(
        suffix="_speech_normalized.wav",
        dir=str(Path(input_path).resolve().parent),
    )
    try:
        with wave.open(normalized_path, "wb") as destination:
            destination.setnchannels(channels)
            destination.setsampwidth(sample_width)
            destination.setframerate(frame_rate)
            destination.writeframes(output_frames)
        os.replace(normalized_path, input_path)
        return original_duration, normalized_duration
    finally:
        if os.path.exists(normalized_path):
            os.remove(normalized_path)


def _merge_wav_files(input_files: list[str], output_path: str) -> None:
    if not input_files:
        raise ValueError("No WAV files to merge")

    expected: tuple[int, int, int, str] | None = None
    chunks: list[bytes] = []
    output_params = None
    for input_file in input_files:
        with wave.open(input_file, "rb") as source:
            signature = (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getcomptype(),
            )
            if expected is None:
                expected = signature
                output_params = source.getparams()
            elif signature != expected:
                raise RuntimeError("GPT-SoVITS returned incompatible WAV segments")
            chunks.append(source.readframes(source.getnframes()))

    assert output_params is not None
    with wave.open(output_path, "wb") as destination:
        destination.setparams(output_params)
        for chunk in chunks:
            destination.writeframes(chunk)


def _generate_gpt_sovits_audio_unlocked(
    text: str,
    output_path: str,
    text_language: str,
    speed: float = _CHINESE_SYNTH_SPEED,
    chinese_verifier: ChineseAudioVerifier | None = None,
) -> None:
    # ASR-based post-generation verification produced frequent false rejects.
    # Keep structural WAV/silence/duration checks, but never block on ASR text.
    chinese_verifier = None
    _ensure_gpt_sovits_server()
    _select_gpt_sovits_gpt(text_language)
    _select_gpt_sovits_sovits(text_language)
    temp_wav = tempfile.mktemp(suffix=".wav")
    synthesis_source_text = text
    if text_language == "zh":
        synthesis_source_text = normalize_chinese_speech_identifiers(
            normalize_chinese_speech_numbers(text)
        )
    synthesis_segments = _multilingual_synthesis_segments(
        synthesis_source_text,
        text_language,
    )
    segment_files: list[str] = []
    try:
        for segment_text in synthesis_segments:
            attempts = (
                _CHINESE_PRIMARY_VERIFICATION_ATTEMPTS
                if text_language == "zh"
                else 1
            )
            accepted_file = ""
            rejected_files: list[str] = []
            for retry_index in range(attempts):
                if text_language == "zh":
                    (
                        emotion_style,
                        primary_reference,
                        prompt_language,
                        prompt_text,
                        auxiliary_references,
                    ) = _chinese_reference_plan(segment_text)
                    fallback_start = _CHINESE_PRIMARY_VERIFICATION_ATTEMPTS
                    clarity_start = fallback_start + _CHINESE_FALLBACK_VERIFICATION_ATTEMPTS
                    using_clarity_retry = retry_index >= clarity_start
                    using_fallback_reference = (
                        fallback_start <= retry_index < clarity_start
                        and _GPT_SOVITS_CHINESE_FALLBACK_REFERENCE.is_file()
                    )
                    if using_fallback_reference:
                        primary_reference = _GPT_SOVITS_CHINESE_FALLBACK_REFERENCE
                        prompt_language = "zh"
                        prompt_text = _GPT_SOVITS_CHINESE_FALLBACK_PROMPT
                        auxiliary_references = ()
                    sampling_retry_index = (
                        retry_index - fallback_start
                        if using_fallback_reference
                        else retry_index
                    )
                    top_k, top_p, temperature, seed = _chinese_sampling_profile(
                        emotion_style,
                        segment_text,
                        sampling_retry_index,
                    )
                    request_speed = speed
                    if using_clarity_retry:
                        primary_reference = _GPT_SOVITS_CHINESE_REFERENCE
                        prompt_language = "zh"
                        prompt_text = _GPT_SOVITS_CHINESE_PROMPT
                        auxiliary_references = ()
                        clarity_index = retry_index - clarity_start
                        top_k = 8
                        top_p = 0.84
                        temperature = 0.64
                        seed = (
                            (zlib.crc32(segment_text.encode("utf-8")) & 0x7FFFFFFF)
                            + 15485863 * clarity_index
                        ) & 0x7FFFFFFF
                        request_speed = min(speed, 1.0)
                    logger.info(
                        "GPT-SoVITS Chinese prosody: style=%s primary=%s prompt_lang=%s speed=%.3f sampling=%s/%.2f/%.2f seed=%s attempt=%s clarity=%s text=%s",
                        emotion_style,
                        primary_reference.name,
                        prompt_language,
                        request_speed * _CHINESE_POST_SPEED,
                        top_k,
                        top_p,
                        temperature,
                        seed,
                        retry_index + 1,
                        using_clarity_retry,
                        segment_text[:40],
                    )
                else:
                    primary_reference = _GPT_SOVITS_REFERENCE
                    prompt_language = "ja"
                    prompt_text = _GPT_SOVITS_PROMPT
                    auxiliary_references = ()
                    top_k, top_p, temperature, seed = 15, 1.0, 0.8, 1234
                    request_speed = speed

                payload = json.dumps(
                    {
                        "text": segment_text,
                        "text_lang": text_language,
                        "ref_audio_path": str(primary_reference),
                        "aux_ref_audio_paths": [
                            str(path) for path in auxiliary_references
                        ],
                        "prompt_lang": prompt_language,
                        "prompt_text": prompt_text,
                        "top_k": top_k,
                        "top_p": top_p,
                        "temperature": temperature,
                        "text_split_method": "cut0",
                        "batch_size": 1,
                        "split_bucket": False,
                        "speed_factor": request_speed,
                        "fragment_interval": 0.36 if text_language == "zh" else 0.45,
                        "seed": seed,
                        "media_type": "wav",
                        "streaming_mode": False,
                        "parallel_infer": False,
                        "repetition_penalty": 1.35,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                http_request = urllib_request.Request(
                    f"{_GPT_SOVITS_URL}/tts",
                    data=payload,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                )
                try:
                    with urllib_request.urlopen(http_request, timeout=300) as response:
                        audio = response.read()
                except HTTPError as exc:
                    raise GPTSovitsRequestError(
                        "生成本地语音",
                        _http_error_detail(exc),
                        status=int(getattr(exc, "code", 0) or 0),
                    ) from exc
                if not audio.startswith(b"RIFF"):
                    detail = audio[:500].decode("utf-8", errors="replace")
                    raise RuntimeError(f"GPT-SoVITS returned an error: {detail}")
                segment_file = tempfile.mktemp(suffix="_gsv_segment.wav")
                with open(segment_file, "wb") as audio_file:
                    audio_file.write(audio)

                if text_language == "zh":
                    try:
                        original_duration, normalized_duration = (
                            _normalize_generated_wav_silence(segment_file)
                        )
                    except Exception as exc:
                        rejected_files.append(segment_file)
                        logger.warning(
                            "rejected malformed Chinese speech segment: attempt=%s text=%s detail=%s",
                            retry_index + 1,
                            segment_text[:80],
                            str(exc)[-500:],
                        )
                        continue
                    removed_silence = original_duration - normalized_duration
                    if removed_silence >= 0.60:
                        logger.warning(
                            "normalized abnormal Chinese speech silence: attempt=%s duration=%.3f->%.3f removed=%.3f text=%s",
                            retry_index + 1,
                            original_duration,
                            normalized_duration,
                            removed_silence,
                            segment_text[:80],
                        )
                    maximum_duration = _maximum_chinese_segment_duration(segment_text)
                    if normalized_duration > maximum_duration:
                        rejected_files.append(segment_file)
                        logger.warning(
                            "rejected abnormally long Chinese speech segment: attempt=%s duration=%.3f maximum=%.3f text=%s",
                            retry_index + 1,
                            normalized_duration,
                            maximum_duration,
                            segment_text[:80],
                        )
                        continue

                accepted_file = segment_file
                break
            for rejected_file in rejected_files:
                if rejected_file != accepted_file and os.path.exists(rejected_file):
                    os.remove(rejected_file)
            if not accepted_file:
                raise RuntimeError("中文语音生成异常，请重新生成")
            segment_files.append(accepted_file)

        if len(segment_files) == 1:
            os.replace(segment_files[0], temp_wav)
        else:
            _merge_wav_files(segment_files, temp_wav)
        audio_filter = None
        if text_language == "zh" and _gpt_sovits_active_sovits == _GPT_SOVITS_CHINESE_SOVITS:
            audio_filter = _CHINESE_BASE_VOLUME_FILTER
        _convert_wav_to_mp3(temp_wav, output_path, audio_filter=audio_filter)
    finally:
        for segment_file in segment_files:
            if os.path.exists(segment_file):
                os.remove(segment_file)
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


async def _generate_xixi_voice_chinese_audio(
    text: str,
    output_path: str,
    chinese_speed: float = _CHINESE_SYNTH_SPEED,
    chinese_verifier: ChineseAudioVerifier | None = None,
) -> None:
    await asyncio.to_thread(
        _generate_gpt_sovits_audio,
        text,
        output_path,
        "zh",
        chinese_speed,
        chinese_verifier,
    )


def _is_speech_source_heading(line: str) -> bool:
    value = re.sub(r"^\s*#{1,6}\s*", "", line.strip())
    value = value.replace("**", "").replace("__", "").strip(" *_`")
    return bool(
        re.fullmatch(
            rf"{_SPEECH_SOURCE_LABEL_RE.pattern}"
            rf"(?:\s*[（(【\[]\s*\d+\s*[）)】\]])?(?:\s*[:：].*)?",
            value,
            flags=re.IGNORECASE,
        )
    )


def sanitize_speech_text(text: str) -> str:
    """Return only content that is appropriate to send to a TTS engine."""
    if not text:
        return ""

    text = _strip_speech_internal_instruction(text)
    text = _SPEECH_CODE_BLOCK_RE.sub("\n", text.replace("\r\n", "\n"))
    output_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _is_speech_source_heading(line):
            break
        if _SPEECH_METADATA_LINE_RE.match(line):
            continue
        if _SPEECH_STANDALONE_LINK_RE.fullmatch(line):
            continue
        has_external_reference = bool(
            _SPEECH_URL_RE.search(line)
            or _SPEECH_DOMAIN_RE.search(line)
            or _SPEECH_MARKDOWN_LINK_RE.search(line)
            or _SPEECH_HTML_LINK_RE.search(line)
        )
        if has_external_reference and (
            _SPEECH_REFERENCE_LINE_RE.match(line)
            or _SPEECH_NUMBERED_LINE_RE.match(line)
        ):
            continue
        if output_lines and _SPEECH_REFERENCE_LINE_RE.match(line):
            continue
        if (
            line[:1] in {"{", "["}
            and line[-1:] in {"}", "]"}
            and _SPEECH_JSON_METADATA_RE.search(line)
        ):
            continue

        line = _SPEECH_MARKDOWN_IMAGE_RE.sub("", line)
        line = _SPEECH_MARKDOWN_LINK_RE.sub(r"\1", line)
        line = _SPEECH_HTML_LINK_RE.sub(r"\1", line)
        line = _SPEECH_HTML_TAG_RE.sub("", line)
        line = _SPEECH_INLINE_SOURCE_RE.sub("", line)
        line = _SPEECH_BRACKETED_METADATA_RE.sub("", line)
        line = _SPEECH_STAGE_PREFIX_RE.sub("", line)
        line = _SPEECH_DELIVERY_PREFIX_RE.sub("", line)
        previous = None
        while line != previous:
            previous = line
            line = _SPEECH_OUTPUT_LABEL_RE.sub("", line)
        line = _SPEECH_URL_RE.sub("", line)
        line = _SPEECH_DOMAIN_RE.sub("", line)
        line = _SPEECH_EMAIL_RE.sub("", line)
        line = _SPEECH_CITATION_RE.sub("", line)
        line = re.sub(r"^\s*(?:#{1,6}|>|[-*+])\s+", "", line)
        line = line.replace("`", "").replace("**", "").replace("__", "")
        line = re.sub(r"\s+", " ", line).strip(" ，,;；:-")
        if line:
            output_lines.append(line)

    cleaned = " ".join(output_lines)
    cleaned = _SPEECH_URL_RE.sub("", cleaned)
    cleaned = _SPEECH_DOMAIN_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,;；:-")
    return _strip_emoji(cleaned)


async def generate_tts_audio(
    text: str,
    cfg: Config,
    output_path: str,
    *,
    forced_language: str | None = None,
    chinese_verifier: ChineseAudioVerifier | None = None,
) -> None:
    """Generate one MP3, optionally forcing the selected language engine."""
    if not cfg.voice_enabled:
        raise RuntimeError("语音合成已关闭，请先在运行状态中开启语音")
    text = sanitize_speech_text(text)
    text = _fix_polyphonic(text)
    if not text or len(text.strip()) < 1:
        raise ValueError("TTS text is empty")

    if forced_language is not None:
        forced_language = str(forced_language).strip().lower()
    if forced_language not in {None, *_SUPPORTED_TTS_LANGUAGES}:
        raise ValueError(f"unsupported TTS language: {forced_language}")
    segments = (
        [(forced_language, text)]
        if forced_language is not None
        else _split_by_language(text)
    )
    logger.info("tts input text: %s", text[:100])
    if forced_language:
        logger.info("tts forced language: %s", forced_language)
    logger.info("tts segments: %s", [(lang, seg[:30]) for lang, seg in segments])

    if len(segments) <= 1:
        language = segments[0][0] if segments else "zh"
        if language == "zh":
            logger.info("tts single segment: lang=zh voice=xixi-voice-system")
            verification_options = (
                {"chinese_verifier": chinese_verifier}
                if chinese_verifier is not None
                else {}
            )
            await _generate_xixi_voice_chinese_audio(
                text,
                output_path,
                cfg.gpt_sovits_chinese_speed,
                **verification_options,
            )
        elif language == "ja":
            logger.info("tts single segment: lang=ja voice=xixi-voice-system")
            await asyncio.to_thread(
                _generate_gpt_sovits_audio,
                text,
                output_path,
                language,
                speed=cfg.gpt_sovits_japanese_speed,
            )
        elif language == "en":
            logger.info("tts single segment: lang=en voice=xixi-voice-system")
            await asyncio.to_thread(
                _generate_gpt_sovits_audio,
                text,
                output_path,
                language,
                speed=cfg.gpt_sovits_english_speed,
            )
        else:
            voice = _voice_for_language(language, cfg)
            logger.info("tts single segment: lang=%s voice=%s", language, voice)
            await edge_tts.Communicate(text, voice, rate=cfg.tts_rate).save(output_path)
        return

    temp_files: list[str] = []
    try:
        for index, (language, segment_text) in enumerate(segments):
            segment_text = segment_text.strip()
            if not segment_text:
                continue
            voice = _voice_for_language(language, cfg)
            logger.info("tts segment %d: lang=%s voice=%s text=%s", index, language, voice, segment_text[:30])
            temp_file = tempfile.mktemp(suffix=f"_seg{index}.mp3")
            try:
                if language == "zh":
                    verification_options = (
                        {"chinese_verifier": chinese_verifier}
                        if chinese_verifier is not None
                        else {}
                    )
                    await _generate_xixi_voice_chinese_audio(
                        segment_text,
                        temp_file,
                        cfg.gpt_sovits_chinese_speed,
                        **verification_options,
                    )
                elif language == "ja":
                    await asyncio.to_thread(
                        _generate_gpt_sovits_audio,
                        segment_text,
                        temp_file,
                        language,
                        speed=cfg.gpt_sovits_japanese_speed,
                    )
                elif language == "en":
                    await asyncio.to_thread(
                        _generate_gpt_sovits_audio,
                        segment_text,
                        temp_file,
                        language,
                        speed=cfg.gpt_sovits_english_speed,
                    )
                else:
                    await edge_tts.Communicate(segment_text, voice, rate=cfg.tts_rate).save(temp_file)
                temp_files.append(temp_file)
            except Exception:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise

        if not temp_files:
            raise RuntimeError("没有生成任何语音片段")
        if len(temp_files) == 1:
            os.replace(temp_files[0], output_path)
            temp_files.clear()
            return
        _merge_mp3_files(temp_files, output_path)
    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass


class TtsBus:
    def __init__(self, cfg: Config, translator: object = None) -> None:
        self.cfg = cfg
        self.translator = translator
        self.inbox: Queue[tuple[str, str] | str] = Queue()
        self._stop = Event()

    def start(self) -> None:
        try:
            if pygame is not None:
                pygame.mixer.init(frequency=24000)
        except Exception as e:
            logger.warning("pygame mixer init failed: %s", e)
        Thread(target=self._loop, name="tts-loop", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        _stop_gpt_sovits_server()

    def _loop(self) -> None:
        logger.info("tts loop started")
        while not self._stop.is_set():
            try:
                item = self.inbox.get(timeout=0.2)
            except Empty:
                continue
            text, reply_language = item if isinstance(item, tuple) else (item, "zh")
            if not text or not text.strip():
                continue
            try:
                self._speak(text, reply_language=reply_language)
            except Exception as e:
                logger.warning("tts speak failed: %s", e)
        logger.info("tts loop stopped")

    def _speak(self, text: str, *, reply_language: str = "zh") -> None:
        text = _strip_emoji(text)
        if not text or len(text.strip()) < 2:
            return
        text, voice_language = prepare_voice_text(
            text,
            self.cfg,
            self.translator,
            reply_language=reply_language,
        )
        tmp_path = tempfile.mktemp(suffix=".mp3")
        try:
            asyncio.run(
                generate_tts_audio(
                    text,
                    self.cfg,
                    tmp_path,
                    forced_language=voice_language,
                )
            )
            if pygame is None:
                logger.info("tts audio generated but pygame not available: %s", tmp_path)
                return
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            pygame.mixer.music.unload()
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    async def _generate_audio(
        self,
        text: str,
        output_path: str,
        *,
        reply_language: str = "zh",
    ) -> None:
        text, voice_language = prepare_voice_text(
            text,
            self.cfg,
            self.translator,
            reply_language=reply_language,
        )
        await generate_tts_audio(
            text,
            self.cfg,
            output_path,
            forced_language=voice_language,
        )


def _strip_emoji(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    for pat in _KAOMOJI:
        text = text.replace(pat, "")
    text = re.sub(r"\s+", " ", text).strip()
    return text
