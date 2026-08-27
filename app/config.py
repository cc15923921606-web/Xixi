from __future__ import annotations

import os
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .runtime_paths import get_runtime_paths


def _application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


_PATHS = get_runtime_paths()
_ROOT = _application_root()


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except Exception:
        return default


def _float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except Exception:
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_set(name: str, default: str = "") -> frozenset[int]:
    value = os.environ.get(name, default)
    parsed = set()
    for item in value.split(","):
        try:
            parsed.add(int(item.strip()))
        except ValueError:
            continue
    return frozenset(parsed)


def _parse_rate(value: str) -> str:
    m = re.match(r"^([+-]?\d+%?)$", value.strip())
    return m.group(1) if m else "+0%"


_QQ_GROUP_WAKE_NAME_SPLIT_RE = re.compile(r"[,，、;；\r\n]+")


def normalize_qq_group_wake_names(value: object) -> str:
    aliases: list[str] = []
    seen: set[str] = set()
    for item in _QQ_GROUP_WAKE_NAME_SPLIT_RE.split(str(value or "")):
        alias = item.strip()
        if not alias:
            continue
        if len(alias) > 20:
            raise ValueError("单个群聊唤醒名称不能超过 20 个字符")
        folded = alias.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        aliases.append(alias)
    if len(aliases) > 12:
        raise ValueError("群聊唤醒名称最多设置 12 个")
    return "、".join(aliases)


def qq_group_wake_aliases(value: object) -> tuple[str, ...]:
    normalized = normalize_qq_group_wake_names(value)
    return tuple(alias for alias in normalized.split("、") if alias)


def normalize_assistant_name(value: object) -> str:
    raw = str(value or "")
    if "\n" in raw or "\r" in raw:
        raise ValueError("角色名称只能填写一行")
    name = re.sub(r"\s+", " ", raw).strip()
    if not name:
        raise ValueError("角色名称不能为空")
    if len(name) > 24:
        raise ValueError("角色名称不能超过 24 个字符")
    if any(ord(character) < 32 for character in name):
        raise ValueError("角色名称包含无效字符")
    return name


@dataclass
class Config:
    # Paths
    root: Path = _ROOT
    data_root: Path | None = None
    webview_root: Path | None = None
    downloads_root: Path | None = None
    components_root: Path | None = None
    models_root: Path | None = None
    persona_file: Path | None = None
    interest_profile_file: Path | None = None
    knowledge_file: Path | None = None
    logs_dir: Path | None = None
    memory_file: Path | None = None
    memory_db: Path | None = None
    learning_sources_file: Path | None = None
    meme_lexicon_file: Path | None = None

    # LLM
    llm_model: str = _env("LLM_MODEL", "qwen2.5:3b")
    llm_timeout_s: float = _float("LLM_TIMEOUT_S", 60.0)
    llm_max_history: int = _int("LLM_MAX_HISTORY", 30)
    brain_enabled: bool = _bool("BRAIN_ENABLED", True)

    # Continuous learning
    learning_enabled: bool = _bool("LEARNING_ENABLED", True)
    # Kept for compatibility with older launch configurations.
    learning_interval_hours: float = _float("LEARNING_INTERVAL_HOURS", 6.0)
    learning_interest_interval_hours: float = _float(
        "LEARNING_INTEREST_INTERVAL_HOURS", 2.0
    )
    learning_general_interval_hours: float = _float(
        "LEARNING_GENERAL_INTERVAL_HOURS", 12.0
    )
    learning_academic_interval_hours: float = _float(
        "LEARNING_ACADEMIC_INTERVAL_HOURS", 24.0
    )
    interest_reflection_enabled: bool = _bool("INTEREST_REFLECTION_ENABLED", True)
    interest_reflection_interval_hours: float = _float(
        "INTEREST_REFLECTION_INTERVAL_HOURS", 6.0
    )
    memory_consolidation_hours: float = _float("MEMORY_CONSOLIDATION_HOURS", 6.0)
    memory_consolidation_min_events: int = _int("MEMORY_CONSOLIDATION_MIN_EVENTS", 6)
    shared_memory_enabled: bool = _bool("SHARED_MEMORY_ENABLED", True)
    shared_memory_recent_events: int = _int("SHARED_MEMORY_RECENT_EVENTS", 10)
    shared_memory_relevant_events: int = _int("SHARED_MEMORY_RELEVANT_EVENTS", 4)
    learning_daily_digest: bool = _bool("LEARNING_DAILY_DIGEST", True)
    learning_digest_hour: int = _int("LEARNING_DIGEST_HOUR", 20)
    anime_learning_enabled: bool = _bool("ANIME_LEARNING_ENABLED", True)
    anime_learning_interval_hours: float = _float(
        "ANIME_LEARNING_INTERVAL_HOURS", 2.0
    )
    anime_learning_limit: int = _int("ANIME_LEARNING_LIMIT", 15)
    knowledge_reflection_enabled: bool = _bool("KNOWLEDGE_REFLECTION_ENABLED", True)
    knowledge_reflection_batch_size: int = _int(
        "KNOWLEDGE_REFLECTION_BATCH_SIZE", 6
    )

    # Realtime environment
    weather_enabled: bool = _bool("WEATHER_ENABLED", False)
    weather_location: str = _env("WEATHER_LOCATION", "未设置")
    weather_cache_minutes: float = _float("WEATHER_CACHE_MINUTES", 10.0)
    weather_timeout_s: float = _float("WEATHER_TIMEOUT_S", 5.0)
    weather_alert_enabled: bool = _bool("WEATHER_ALERT_ENABLED", False)
    weather_alert_check_minutes: float = _float(
        "WEATHER_ALERT_CHECK_MINUTES", 10.0
    )
    weather_alert_group_enabled: bool = _bool("WEATHER_ALERT_GROUP_ENABLED", True)
    weather_alert_max_group_mentions: int = _int(
        "WEATHER_ALERT_MAX_GROUP_MENTIONS", 20
    )
    weather_alert_excluded_qq_ids: frozenset[int] = _int_set(
        "WEATHER_ALERT_EXCLUDED_QQ_IDS"
    )

    # Autonomous conversation
    autonomous_group_enabled: bool = _bool("AUTONOMOUS_GROUP_ENABLED", True)
    autonomous_group_ids: frozenset[int] = _int_set("AUTONOMOUS_GROUP_IDS")
    autonomous_group_min_messages: int = _int("AUTONOMOUS_GROUP_MIN_MESSAGES", 3)
    autonomous_group_cooldown_s: float = _float("AUTONOMOUS_GROUP_COOLDOWN_S", 0.0)
    autonomous_group_base_chance: float = _float("AUTONOMOUS_GROUP_BASE_CHANCE", 0.06)
    autonomous_group_context_idle_s: float = _float(
        "AUTONOMOUS_GROUP_CONTEXT_IDLE_S", 1800.0
    )
    autonomous_group_buffer_messages: int = _int(
        "AUTONOMOUS_GROUP_BUFFER_MESSAGES", 200
    )
    autonomous_group_context_messages: int = _int(
        "AUTONOMOUS_GROUP_CONTEXT_MESSAGES", 24
    )
    autonomous_private_enabled: bool = _bool("AUTONOMOUS_PRIVATE_ENABLED", True)
    autonomous_private_initial_min_minutes: float = _float(
        "AUTONOMOUS_PRIVATE_INITIAL_MIN_MINUTES", 5.0
    )
    autonomous_private_initial_max_minutes: float = _float(
        "AUTONOMOUS_PRIVATE_INITIAL_MAX_MINUTES", 20.0
    )
    autonomous_private_min_interval_hours: float = _float(
        "AUTONOMOUS_PRIVATE_MIN_INTERVAL_HOURS", 0.5
    )
    autonomous_private_max_interval_hours: float = _float(
        "AUTONOMOUS_PRIVATE_MAX_INTERVAL_HOURS", 2.0
    )
    autonomous_private_max_per_day: int = _int("AUTONOMOUS_PRIVATE_MAX_PER_DAY", 6)
    autonomous_private_active_start_hour: int = _int(
        "AUTONOMOUS_PRIVATE_ACTIVE_START_HOUR", 9
    )
    autonomous_private_active_end_hour: int = _int(
        "AUTONOMOUS_PRIVATE_ACTIVE_END_HOUR", 23
    )

    # ASR
    whisper_model: str = _env("WHISPER_MODEL", "large-v3")
    whisper_model_path: str = _env(
        "WHISPER_MODEL_PATH",
        str(_ROOT / "whisper-large-v3-ct2"),
    )
    whisper_fallback_model_path: str = _env(
        "WHISPER_FALLBACK_MODEL_PATH",
        str(_ROOT / "whisper-small-full"),
    )
    whisper_device: str = _env("WHISPER_DEVICE", "cuda")
    whisper_compute_type: str = _env("WHISPER_COMPUTE_TYPE", "int8_float16")
    whisper_fallback_compute_type: str = _env(
        "WHISPER_FALLBACK_COMPUTE_TYPE",
        "float16",
    )
    hf_endpoint: str = _env("HF_ENDPOINT", "")
    whisper_language: str = _env("WHISPER_LANGUAGE", "")  # empty = auto-detect
    whisper_beam_size: int = _int("WHISPER_BEAM_SIZE", 5)
    whisper_initial_prompt: str = _env(
        "WHISPER_INITIAL_PROMPT",
        "简体中文自然口语，可能夹杂少量英语。专有名词：昔夕、小夕、Neuro-sama、GPT-SoVITS、二次元。",
    )
    whisper_hotwords: str = _env(
        "WHISPER_HOTWORDS",
        "昔夕 小夕 Neuro-sama GPT-SoVITS 二次元",
    )
    whisper_audio_preprocess: bool = _bool("WHISPER_AUDIO_PREPROCESS", True)
    whisper_retry_logprob_threshold: float = _float(
        "WHISPER_RETRY_LOGPROB_THRESHOLD",
        -0.55,
    )
    whisper_retry_beam_size: int = _int("WHISPER_RETRY_BEAM_SIZE", 8)
    sample_rate: int = 16000
    channels: int = 1
    max_record_seconds: float = _float("MAX_RECORD_SECONDS", 15.0)
    silence_threshold: float = _float("SILENCE_THRESHOLD", 1.0)
    silence_volume_threshold: float = _float("SILENCE_VOLUME_THRESHOLD", 300.0)

    # TTS
    voice_enabled: bool = _bool("VOICE_ENABLED", True)
    voice_language: str = _env("VOICE_LANGUAGE", "zh")
    tts_voice: str = _env("TTS_VOICE", "zh-CN-XiaoyiNeural")
    tts_rate: str = _parse_rate(_env("TTS_RATE", "+0%"))
    gpt_sovits_chinese_speed: float = _float("GPT_SOVITS_CHINESE_SPEED", 1.06)
    gpt_sovits_japanese_speed: float = _float("GPT_SOVITS_JAPANESE_SPEED", 1.0)
    gpt_sovits_english_speed: float = _float("GPT_SOVITS_ENGLISH_SPEED", 1.0)
    assistant_name: str = _env("ASSISTANT_NAME", "昔夕")
    owner_display_name: str = _env("OWNER_DISPLAY_NAME", "主人")
    owner_relationship: str = _env("OWNER_RELATIONSHIP", "创造者与重要的人")
    owner_addresses: str = _env("OWNER_ADDRESSES", "爸爸,老爸,爹爹,老爹")
    owner_address_chance: float = _float("OWNER_ADDRESS_CHANCE", 0.55)
    owner_address_max_gap: int = _int("OWNER_ADDRESS_MAX_GAP", 3)
    setup_complete: bool = _bool("SETUP_COMPLETE", False)

    # On-demand web search
    web_search_enabled: bool = _bool("WEB_SEARCH_ENABLED", True)
    web_search_timeout_s: float = _float("WEB_SEARCH_TIMEOUT_S", 10.0)
    web_search_max_results: int = _int("WEB_SEARCH_MAX_RESULTS", 5)
    web_search_cache_minutes: float = _float("WEB_SEARCH_CACHE_MINUTES", 10.0)

    # Image understanding
    vision_enabled: bool = _bool("VISION_ENABLED", True)
    vision_model: str = _env("VISION_MODEL", "gpt-5.6-sol")
    vision_api_type: str = _env("VISION_API_TYPE", "auto")
    vision_api_key: str = _env("VISION_API_KEY", "")
    vision_base_url: str = _env("VISION_BASE_URL", "")
    vision_timeout_s: float = _float("VISION_TIMEOUT_S", 75.0)
    vision_max_images: int = _int("VISION_MAX_IMAGES", 4)
    vision_max_image_bytes: int = _int("VISION_MAX_IMAGE_BYTES", 10 * 1024 * 1024)
    vision_detail: str = _env("VISION_DETAIL", "high")

    # Runtime
    hotkey_stop: str = _env("HOTKEY_STOP", "ctrl+shift+q")
    window_title: str = _env("WINDOW_TITLE", "")
    use_window_pin: bool = _env("USE_WINDOW_PIN", "1") == "1"

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        active_root = self.root.resolve() == _PATHS.app_root.resolve()
        data_root = _PATHS.data_dir if active_root else self.root / "data"
        self.data_root = Path(self.data_root or data_root)
        self.webview_root = Path(
            self.webview_root
            or (_PATHS.webview_dir if active_root else self.data_root)
        )
        self.downloads_root = Path(
            self.downloads_root
            or (_PATHS.downloads_dir if active_root else self.data_root / "environment_downloads")
        )
        self.components_root = Path(
            self.components_root
            or (_PATHS.components_dir if active_root else self.root / "runtime")
        )
        self.models_root = Path(
            self.models_root
            or (_PATHS.models_dir if active_root else self.root)
        )
        if active_root and _PATHS.public_release:
            packaged_whisper = self.root / "whisper-small-full"
            downloaded_whisper = self.models_root / "whisper-small-full"
            if "WHISPER_FALLBACK_MODEL_PATH" not in os.environ:
                self.whisper_fallback_model_path = str(
                    packaged_whisper
                    if (packaged_whisper / "model.bin").is_file()
                    else downloaded_whisper
                )
        external_public_layout = (
            active_root
            and _PATHS.public_release
            and self.data_root.resolve() != (self.root / "data").resolve()
        )
        mutable_root = self.data_root if external_public_layout else self.root
        self.persona_file = Path(self.persona_file or mutable_root / "persona.txt")
        self.interest_profile_file = Path(
            self.interest_profile_file or mutable_root / "interest_profile.json"
        )
        self.knowledge_file = Path(self.knowledge_file or mutable_root / "knowledge.txt")
        self.logs_dir = Path(
            self.logs_dir or (_PATHS.logs_dir if active_root else self.root / "logs")
        )
        self.memory_file = Path(self.memory_file or self.data_root / "conversations.json")
        self.memory_db = Path(self.memory_db or self.data_root / "xixi_memory.db")
        self.learning_sources_file = Path(
            self.learning_sources_file or mutable_root / "learning_sources.json"
        )
        self.meme_lexicon_file = Path(
            self.meme_lexicon_file or mutable_root / "meme_lexicon.json"
        )

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        from .qq_identity import load_qq_identity

        identity = load_qq_identity(
            cfg.root,
            data_root=cfg.data_root,
            default_bot_qq_id=cfg.bot_qq_id,
            default_owner_qq_id=cfg.qq_user_id,
            create_if_missing=True,
        )
        cfg.bot_qq_id = identity["bot_qq_id"]
        cfg.qq_user_id = identity["owner_qq_id"]
        settings_file = cfg.data_root / "studio_settings.json"
        try:
            saved_settings = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            saved_settings = {}
        saved_voice_language = str(saved_settings.get("voice_language") or "").strip()
        if saved_voice_language in {"zh", "ja", "en"}:
            cfg.voice_language = saved_voice_language
        if "assistant_name" in saved_settings:
            try:
                cfg.assistant_name = normalize_assistant_name(saved_settings["assistant_name"])
            except ValueError:
                pass
        if "qq_group_at_wake_enabled" in saved_settings:
            cfg.qq_group_at_wake_enabled = bool(
                saved_settings["qq_group_at_wake_enabled"]
            )
        if "qq_group_name_wake_enabled" in saved_settings:
            cfg.qq_group_name_wake_enabled = bool(
                saved_settings["qq_group_name_wake_enabled"]
            )
        if "qq_group_wake_names" in saved_settings:
            try:
                cfg.qq_group_wake_names = normalize_qq_group_wake_names(
                    saved_settings["qq_group_wake_names"]
                )
            except ValueError:
                pass
        return cfg

    def ensure_dirs(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.webview_root.mkdir(parents=True, exist_ok=True)
        self.downloads_root.mkdir(parents=True, exist_ok=True)
        self.components_root.mkdir(parents=True, exist_ok=True)
        self.models_root.mkdir(parents=True, exist_ok=True)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory_db.parent.mkdir(parents=True, exist_ok=True)
    # OpenAI API
    use_openai: bool = _env("USE_OPENAI", "0") == "1"
    openai_api_key: str = _env("OPENAI_API_KEY", "")
    openai_model: str = _env("OPENAI_MODEL", "gpt-5.6-sol")
    openai_base_url: str = _env("OPENAI_BASE_URL", "")
    language_api_type: str = _env("LANGUAGE_API_TYPE", "auto")

    # QQ Bot
    qq_user_id: int = int(_env("QQ_USER_ID", "0"))
    bot_qq_id: int = int(_env("BOT_QQ_ID", "0"))
    qq_enabled: bool = _bool("QQ_ENABLED", False)
    qq_group_at_wake_enabled: bool = _bool("QQ_GROUP_AT_WAKE_ENABLED", True)
    qq_group_name_wake_enabled: bool = _bool("QQ_GROUP_NAME_WAKE_ENABLED", True)
    qq_group_wake_names: str = _env("QQ_GROUP_WAKE_NAMES", "昔夕、小夕、xx")
    onebot_api: str = _env("ONEBOT_API", "http://127.0.0.1:3000")
    onebot_ws: str = _env("ONEBOT_WS", "ws://127.0.0.1:3001")
