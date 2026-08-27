from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event

import numpy as np

try:
    from pypinyin import Style, lazy_pinyin
except Exception:  # pragma: no cover - optional pronunciation helper
    Style = None  # type: ignore[assignment]
    lazy_pinyin = None  # type: ignore[assignment]

try:
    from opencc import OpenCC

    _TRADITIONAL_TO_SIMPLIFIED = OpenCC("t2s")
except Exception:  # pragma: no cover - optional script normalization
    _TRADITIONAL_TO_SIMPLIFIED = None

logger = logging.getLogger("asr_bus")
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _configure_cuda_dll_search() -> None:
    """Expose the CUDA runtime bundled with GPT-SoVITS to CTranslate2."""
    app_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    workspace = app_root.parent
    configured = os.environ.get("WHISPER_CUDA_DLL_DIRS", "")
    candidates = [Path(item) for item in configured.split(os.pathsep) if item.strip()]
    component_roots = [
        Path(os.environ["XIXI_COMPONENTS_DIR"])
        if os.environ.get("XIXI_COMPONENTS_DIR")
        else None,
        app_root / "runtime",
        workspace / "work",
    ]
    for component_root in component_roots:
        if component_root is None:
            continue
        voice_root = component_root / "GPT-SoVITS"
        candidates.extend(
            [
                voice_root / ".venv" / "Lib" / "site-packages" / "torch" / "lib",
                voice_root / ".venv" / "Lib" / "site-packages" / "ctranslate2",
            ]
        )
    existing = list(dict.fromkeys(str(path) for path in candidates if path.is_dir()))
    if existing:
        os.environ["PATH"] = os.pathsep.join([*existing, os.environ.get("PATH", "")])


_configure_cuda_dll_search()
try:
    from faster_whisper import WhisperModel  # optional in text mode
except Exception:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]

from .config import Config

def _apply_hf_endpoint(cfg: Config) -> None:
    if cfg.hf_endpoint:
        import os
        os.environ.setdefault("HF_ENDPOINT", cfg.hf_endpoint)

_IGNORE_PATTERNS = [
    "字幕", "by", "索兰娅", "弹幕", "感谢", "礼物", "关注", "点赞",
    "直播间", "主播", "上舰", "充电", "投币", "收藏",
]

_ASR_CANONICAL_REPLACEMENTS = (
    (re.compile(r"(?i)(?<![a-z])xixi(?![a-z])|西西|希希|茜茜"), "昔夕"),
    (re.compile(r"小西|小希"), "小夕"),
    (re.compile(r"(?i)gpt[\s_-]*so[\s_-]*vits"), "GPT-SoVITS"),
)

_ASR_SHORT_UTTERANCE_REPLACEMENTS = {
    "恩": "嗯",
    "摁": "嗯",
    "温": "嗯",
}

_ASR_SIMPLIFIED_VARIANTS = str.maketrans({"妳": "你"})

_ASR_KNOWN_HALLUCINATION_PATTERNS = (
    re.compile(r"(?i)amara\s*\.\s*org"),
    re.compile(r"字幕.{0,16}(?:提供|制作|翻译)"),
    re.compile(r"(?:谢谢|感谢)(?:大家)?(?:观看|收看)"),
)

_ASR_ROLE_MARKER_RE = re.compile(
    r"(?:用户|昔夕|助手|user|assistant)\s*[：:]\s*",
    re.IGNORECASE,
)
_ASR_ROLE_PREFIX_RE = re.compile(
    r"^\s*(?:用户|昔夕|助手|user|assistant)\s*[：:]\s*",
    re.IGNORECASE,
)


def _compact_asr_context(value: str, *, limit: int = 600) -> str:
    context = re.sub(r"https?://\S+", "", str(value or ""))
    context = re.sub(r"\s+", " ", context).strip()
    return context[-limit:]


def build_asr_prompt(cfg: Config, context: str = "") -> str | None:
    # Full dialogue text is deliberately excluded. On short utterances Whisper
    # can continue an initial prompt and return old chat lines as recognized speech.
    del context
    prompt = str(cfg.whisper_initial_prompt or "").strip()
    assistant_name = str(getattr(cfg, "assistant_name", "") or "昔夕").strip()
    if assistant_name and assistant_name.casefold() not in prompt.casefold():
        prompt = f"{prompt.rstrip('。')}。角色名称：{assistant_name}。" if prompt else assistant_name
    return prompt[:600] or None


def build_asr_hotwords(cfg: Config, context: str = "") -> str | None:
    # Recent dialogue still participates in conservative post-decode homophone
    # correction, but is too risky to inject into Whisper's decoding prompt.
    del context
    hotwords = str(cfg.whisper_hotwords or "").strip()
    assistant_name = str(getattr(cfg, "assistant_name", "") or "昔夕").strip()
    if assistant_name and assistant_name.casefold() not in hotwords.casefold():
        hotwords = f"{hotwords}，{assistant_name}" if hotwords else assistant_name
    return hotwords[:400] or None


def _looks_like_prompt_leakage(text: str) -> bool:
    value = str(text or "")
    return bool(
        "\ufffd" in value
        or _ASR_ROLE_MARKER_RE.search(value)
        or value.count("：") >= 3
        or value.count(":") >= 4
    )


def _looks_like_repetition_hallucination(text: str) -> bool:
    value = re.sub(r"\s+", "", str(text or ""))
    compact = re.sub(r"[,，。！？!?、;；:：]+", "", value)
    if len(compact) < 12:
        return False

    phrases = [part for part in re.split(r"[,，。！？!?、;；:：]+", value) if part]
    if len(phrases) >= 4:
        dominant_count = max(phrases.count(phrase) for phrase in set(phrases))
        if dominant_count >= 4 and dominant_count / len(phrases) >= 0.65:
            return True

    for size in range(2, min(16, len(compact) // 4) + 1):
        if len(compact) % size:
            continue
        unit = compact[:size]
        if compact == unit * (len(compact) // size):
            return True
    return False


def _looks_like_decode_hallucination(text: str, speech_duration: float = 0.0) -> bool:
    value = str(text or "")
    if _looks_like_prompt_leakage(value) or _looks_like_repetition_hallucination(value):
        return True
    if any(pattern.search(value) for pattern in _ASR_KNOWN_HALLUCINATION_PATTERNS):
        return True
    spoken_characters = len(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", value))
    if 0.0 < speech_duration < 2.0:
        plausible_limit = max(10, round(speech_duration * 9) + 4)
        if spoken_characters > plausible_limit:
            return True
    return False


def strip_asr_prompt_leakage(text: str, assistant_name: str = "") -> str:
    """Remove role-labelled prompt continuations without rewriting normal speech."""
    cleaned = str(text or "").replace("\ufffd", "").strip()
    name = str(assistant_name or "").strip()
    if name and name.casefold() not in {"昔夕", "小夕", "xixi"}:
        role_pattern = re.compile(
            rf"(?:用户|昔夕|{re.escape(name)}|助手|user|assistant)\s*[：:]\s*",
            re.IGNORECASE,
        )
        cleaned = re.sub(rf"^\s*{role_pattern.pattern}", "", cleaned, count=1, flags=re.IGNORECASE)
        marker = role_pattern.search(cleaned)
        if marker:
            cleaned = cleaned[: marker.start()].rstrip()
    cleaned = _ASR_ROLE_PREFIX_RE.sub("", cleaned, count=1)
    marker = _ASR_ROLE_MARKER_RE.search(cleaned)
    if marker:
        cleaned = cleaned[: marker.start()].rstrip()
    cleaned = re.sub(r"\s+([，。！？!?])", r"\1", cleaned)
    return cleaned.strip(" \t\r\n,，:：")


def normalize_asr_transcript(
    text: str,
    *,
    language: str | None = "zh",
    assistant_name: str = "",
) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if language == "zh" and _TRADITIONAL_TO_SIMPLIFIED is not None:
        normalized = _TRADITIONAL_TO_SIMPLIFIED.convert(normalized).translate(
            _ASR_SIMPLIFIED_VARIANTS
        )
    for pattern, replacement in _ASR_CANONICAL_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    name = str(assistant_name or "").strip()
    if name and name != "昔夕":
        normalized = normalized.replace("昔夕", name).replace("小夕", name)
    core = normalized.strip(" \t\r\n,，。！？!?")
    if core in _ASR_SHORT_UTTERANCE_REPLACEMENTS and len(core) == 1:
        replacement = _ASR_SHORT_UTTERANCE_REPLACEMENTS[core]
        suffix_match = re.search(r"([。！？!?]+)$", normalized)
        normalized = replacement + (suffix_match.group(1) if suffix_match else "")
    return normalized


def _pinyin_key(value: str) -> tuple[str, ...]:
    if lazy_pinyin is None or Style is None:
        return ()
    return tuple(
        lazy_pinyin(
            value,
            style=Style.TONE3,
            neutral_tone_with_five=True,
            errors="ignore",
        )
    )


def speech_phonetic_key(value: str) -> tuple[str, ...]:
    """Return a stable Mandarin pronunciation key for speech verification."""
    return _pinyin_key(re.sub(r"[^A-Za-z0-9\u3400-\u9fff]", "", str(value or "")))


def correct_asr_with_context(text: str, context: str) -> str:
    """Replace unique same-pronunciation phrases found in recent context."""
    normalized = str(text or "")
    compact_context = _compact_asr_context(context)
    if not normalized or not compact_context or lazy_pinyin is None:
        return normalized

    candidates: dict[tuple[int, tuple[str, ...]], set[str]] = {}
    for run in re.findall(r"[\u3400-\u9fff]+", compact_context):
        for size in range(min(6, len(run)), 1, -1):
            for start in range(0, len(run) - size + 1):
                phrase = run[start : start + size]
                key = _pinyin_key(phrase)
                if len(key) == size:
                    candidates.setdefault((size, key), set()).add(phrase)

    if not candidates:
        return normalized

    output: list[str] = []
    cursor = 0
    for match in re.finditer(r"[\u3400-\u9fff]+", normalized):
        output.append(normalized[cursor : match.start()])
        run = match.group(0)
        chars = list(run)
        index = 0
        corrected: list[str] = []
        while index < len(chars):
            replacement = ""
            consumed = 1
            for size in range(min(6, len(chars) - index), 1, -1):
                source = "".join(chars[index : index + size])
                terms = candidates.get((size, _pinyin_key(source)), set())
                if len(terms) != 1:
                    continue
                candidate = next(iter(terms))
                if candidate != source:
                    replacement = candidate
                    consumed = size
                    break
            corrected.append(replacement or chars[index])
            index += consumed
        output.append("".join(corrected))
        cursor = match.end()
    output.append(normalized[cursor:])
    corrected_text = "".join(output)
    if corrected_text != normalized:
        logger.info("asr homophone context correction: %s -> %s", normalized, corrected_text)
    return corrected_text


def _prepare_asr_audio(audio_path: str, cfg: Config) -> tuple[str, str | None]:
    if not cfg.whisper_audio_preprocess:
        return audio_path, None
    output_path = tempfile.mktemp(suffix="_asr.wav")
    try:
        import imageio_ffmpeg

        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i",
            audio_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=70,lowpass=f=7600,loudnorm=I=-20:TP=-2:LRA=7",
            "-c:a",
            "pcm_s16le",
            output_path,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
        if result.returncode == 0 and Path(output_path).stat().st_size > 44:
            return output_path, output_path
        logger.warning("ASR audio preprocessing failed; using original audio: %s", result.stderr[-300:])
    except Exception as exc:
        logger.warning("ASR audio preprocessing unavailable; using original audio: %s", exc)
    try:
        os.remove(output_path)
    except OSError:
        pass
    return audio_path, None


def _decode_whisper(
    model: object,
    audio_path: str,
    cfg: Config,
    *,
    language: str | None,
    context: str,
    beam_size: int,
    patience: float,
    use_hints: bool = True,
) -> tuple[str, object, float, float]:
    segments, info = model.transcribe(  # type: ignore[attr-defined]
        audio_path,
        language=language,
        beam_size=max(1, int(beam_size)),
        best_of=5,
        patience=patience,
        temperature=0.0,
        task="transcribe",
        vad_filter=True,
        vad_parameters={
            "threshold": 0.45,
            "min_speech_duration_ms": 100,
            "min_silence_duration_ms": 320,
            "speech_pad_ms": 300,
        },
        condition_on_previous_text=False,
        initial_prompt=build_asr_prompt(cfg, context) if use_hints else None,
        hotwords=build_asr_hotwords(cfg, context) if use_hints else None,
        repetition_penalty=1.0 if use_hints else 1.08,
        no_repeat_ngram_size=0 if use_hints else 3,
        max_new_tokens=128 if use_hints else 64,
        no_speech_threshold=0.55,
    )
    segment_list = list(segments)
    raw_text = " ".join(segment.text for segment in segment_list).strip()
    weighted_logprob = 0.0
    total_weight = 0.0
    for segment in segment_list:
        try:
            weight = max(0.1, float(segment.end) - float(segment.start))
            logprob = float(segment.avg_logprob)
        except (AttributeError, TypeError, ValueError):
            continue
        weighted_logprob += logprob * weight
        total_weight += weight
    average_logprob = weighted_logprob / total_weight if total_weight else 0.0
    return raw_text, info, average_logprob, total_weight


def transcribe_speech(
    model: object,
    audio_path: str,
    cfg: Config,
    *,
    language: str | None = None,
    context: str = "",
) -> tuple[str, object]:
    """Transcribe one utterance with conversational hints and stable decoding."""
    prepared_path, cleanup_path = _prepare_asr_audio(audio_path, cfg)
    try:
        raw_text, info, logprob, speech_duration = _decode_whisper(
            model,
            prepared_path,
            cfg,
            language=language,
            context=context,
            beam_size=cfg.whisper_beam_size,
            patience=1.2,
        )
        decode_hallucination = _looks_like_decode_hallucination(raw_text, speech_duration)
        low_confidence = not raw_text or logprob < float(cfg.whisper_retry_logprob_threshold)
        if decode_hallucination or low_confidence:
            if decode_hallucination:
                logger.warning(
                    "ASR decode hallucination detected; retrying without hints: %s",
                    raw_text[:160],
                )
            retry_audio_path = (
                audio_path
                if decode_hallucination
                and speech_duration < 2.0
                and prepared_path != audio_path
                else prepared_path
            )
            retry_text, retry_info, retry_logprob, retry_duration = _decode_whisper(
                model,
                retry_audio_path,
                cfg,
                language=language,
                context="",
                beam_size=max(cfg.whisper_beam_size, cfg.whisper_retry_beam_size),
                patience=1.5,
                use_hints=False,
            )
            retry_hallucination = _looks_like_decode_hallucination(
                retry_text,
                retry_duration,
            )
            if retry_text and not retry_hallucination and (
                decode_hallucination or not raw_text or retry_logprob >= logprob
            ):
                logger.info(
                    "ASR retry selected: first=%.3f retry=%.3f",
                    logprob,
                    retry_logprob,
                )
                raw_text, info, logprob, speech_duration = (
                    retry_text,
                    retry_info,
                    retry_logprob,
                    retry_duration,
                )
        if _looks_like_decode_hallucination(raw_text, speech_duration):
            logger.warning("ASR discarded hallucinated transcript: %s", raw_text[:160])
            raw_text = ""
        assistant_name = str(getattr(cfg, "assistant_name", "") or "昔夕").strip()
        cleaned_text = strip_asr_prompt_leakage(raw_text, assistant_name)
        text = correct_asr_with_context(
            normalize_asr_transcript(
                cleaned_text,
                language=language,
                assistant_name=assistant_name,
            ),
            context,
        )
    finally:
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass
    if text != raw_text:
        logger.info("asr contextual correction: %s -> %s", raw_text, text)
    return text, info


def transcribe_synthesized_speech(
    model: object,
    audio_path: str,
    cfg: Config,
    *,
    language: str = "zh",
) -> tuple[str, object]:
    """Transcribe clean TTS output without microphone-oriented processing."""
    verification_beam_size = max(
        8,
        int(cfg.whisper_beam_size),
        int(cfg.whisper_retry_beam_size),
    )
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=verification_beam_size,
        best_of=verification_beam_size,
        patience=1.2,
        temperature=0.0,
        task="transcribe",
        vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt=None,
        hotwords=None,
    )
    raw_text = " ".join(segment.text for segment in segments).strip()
    assistant_name = str(getattr(cfg, "assistant_name", "") or "昔夕").strip()
    cleaned_text = strip_asr_prompt_leakage(raw_text, assistant_name)
    return (
        normalize_asr_transcript(
            cleaned_text,
            language=language,
            assistant_name=assistant_name,
        ),
        info,
    )


def _local_whisper_model_ready(model_id: str) -> bool:
    candidate = Path(str(model_id or ""))
    if not candidate.exists():
        return not candidate.is_absolute()
    model_file = candidate / "model.bin"
    return (
        candidate.is_dir()
        and model_file.is_file()
        and model_file.stat().st_size > 100_000_000
        and (candidate / "config.json").is_file()
        and (candidate / "tokenizer.json").is_file()
    )


def create_whisper_model(cfg: Config, *, device_override: str | None = None):
    if WhisperModel is None:
        raise RuntimeError("faster-whisper is not installed")
    device = str(device_override or cfg.whisper_device or "cuda").strip().lower()
    primary = cfg.whisper_model_path or cfg.whisper_model
    fallback = cfg.whisper_fallback_model_path or "small"
    primary_compute_type = str(cfg.whisper_compute_type or "int8_float16").strip().lower()
    fallback_compute_type = str(cfg.whisper_fallback_compute_type or "float16").strip().lower()
    if device == "cpu":
        candidates = [
            (primary, "cpu", "int8"),
            (fallback, "cpu", "int8"),
        ]
    else:
        candidates = [
            (primary, device, primary_compute_type),
        ]
        if primary_compute_type != "int8":
            candidates.append((primary, device, "int8"))
        candidates.append((fallback, device, fallback_compute_type))
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for model_id, candidate_device, compute_type in candidates:
        key = (str(model_id), candidate_device, compute_type)
        if key in seen:
            continue
        seen.add(key)
        if not _local_whisper_model_ready(str(model_id)):
            errors.append(f"{model_id}: model files are incomplete")
            continue
        try:
            model = WhisperModel(
                model_id,
                device=candidate_device,
                compute_type=compute_type,
                cpu_threads=max(2, min(8, os.cpu_count() or 4)),
                num_workers=1,
            )
            logger.info(
                "whisper model ready: model=%s device=%s compute_type=%s",
                model_id,
                candidate_device,
                compute_type,
            )
            return model
        except Exception as exc:
            errors.append(f"{model_id} ({candidate_device}/{compute_type}): {exc}")
            logger.warning("could not load Whisper candidate %s: %s", model_id, exc)

    if device != "cpu" and _local_whisper_model_ready(str(fallback)):
        try:
            model = WhisperModel(
                fallback,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(2, min(8, os.cpu_count() or 4)),
                num_workers=1,
            )
            logger.warning("whisper using emergency CPU fallback: model=%s", fallback)
            return model
        except Exception as exc:
            errors.append(f"{fallback} (cpu/int8): {exc}")
    raise RuntimeError("No usable Whisper model: " + " | ".join(errors))


def prewarm_whisper_model(cfg: Config):
    """Load Whisper and run one tiny inference so the first real utterance is fast."""
    started = time.perf_counter()
    model = create_whisper_model(cfg)
    try:
        warm_whisper_model(model, cfg)
    except Exception as exc:
        if str(cfg.whisper_device or "cuda").strip().lower() == "cpu":
            raise
        logger.warning("Whisper GPU warmup failed; retrying on CPU: %s", exc)
        model = create_whisper_model(cfg, device_override="cpu")
        warm_whisper_model(model, cfg)
    logger.info(
        "whisper prewarm complete: duration_ms=%s",
        round((time.perf_counter() - started) * 1000),
    )
    return model


def warm_whisper_model(model: object, cfg: Config) -> None:
    """Run a tiny inference on an existing model to restore its CUDA hot state."""
    started = time.perf_counter()
    sample = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sample.close()
    try:
        with wave.open(sample.name, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(cfg.sample_rate)
            wav_file.writeframes(b"\x00\x00" * max(1, int(cfg.sample_rate * 0.6)))
        segments, _ = model.transcribe(  # type: ignore[attr-defined]
            sample.name,
            language=cfg.whisper_language or "zh",
            beam_size=1,
            task="transcribe",
            vad_filter=False,
            condition_on_previous_text=False,
        )
        list(segments)
        logger.info(
            "whisper inference warmed: duration_ms=%s",
            round((time.perf_counter() - started) * 1000),
        )
    finally:
        try:
            os.unlink(sample.name)
        except OSError:
            pass


class AsrBus:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.inbox: Queue[str] = Queue()
        self._stop = Event()
        self._model = None

    def start(self) -> None:
        if WhisperModel is None:
            logger.warning("faster-whisper not available; ASR disabled")
            return
        _apply_hf_endpoint(self.cfg)
        model_id = self.cfg.whisper_model_path or self.cfg.whisper_model
        logger.info("loading whisper model: %s", model_id)
        self._model = prewarm_whisper_model(self.cfg)
        Thread(target=self._loop, name="asr-loop", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        logger.info("asr loop started")
        if WhisperModel is None:
            logger.info("asr loop skipped (whisper unavailable)")
            return
        while not self._stop.is_set():
            try:
                audio = self._record_audio()
                if audio is None or len(audio) == 0:
                    continue
                text = self._transcribe(audio)
                if text and self._is_valid_speech(text, audio):
                    logger.info("asr recognized: %s", text)
                    self.inbox.put(text)
                elif text:
                    logger.debug("asr ignored: %s", text)
            except Exception as e:
                logger.exception("asr loop error: %s", e)
                time.sleep(0.5)
        logger.info("asr loop stopped")

    def _is_valid_speech(self, text: str, audio: np.ndarray) -> bool:
        # too short to be real speech
        if len(text.strip()) < 3:
            return False
        # audio too short (likely noise)
        duration = len(audio) / self.cfg.sample_rate
        if duration < 1.5:
            return False
        # matches known noise patterns
        lower = text.lower()
        for pat in _IGNORE_PATTERNS:
            if pat in lower:
                return False
        return True

    def _record_audio(self) -> np.ndarray | None:
        import sounddevice as sd

        cfg = self.cfg
        chunk_samples = int(cfg.sample_rate * 0.1)
        max_silent_chunks = int(cfg.silence_threshold / 0.1)

        all_audio = []
        started = False
        silent_chunks = 0
        started_at = time.time()

        try:
            with sd.InputStream(samplerate=cfg.sample_rate, channels=cfg.channels, dtype="int16", blocksize=chunk_samples) as stream:
                while time.time() - started_at < cfg.max_record_seconds and not self._stop.is_set():
                    chunk, overflowed = stream.read(chunk_samples)
                    chunk = chunk.flatten()
                    volume = float(np.abs(chunk).mean())

                    if volume > cfg.silence_volume_threshold:
                        started = True
                        silent_chunks = 0
                        all_audio.append(chunk)
                    elif started:
                        silent_chunks += 1
                        all_audio.append(chunk)
                        if silent_chunks >= max_silent_chunks:
                            break
        except Exception as e:
            logger.warning("recording error: %s", e)
            return None

        if not all_audio:
            return None
        return np.concatenate(all_audio)

    def _transcribe(self, audio: np.ndarray) -> str:
        cfg = self.cfg
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        try:
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(cfg.channels)
                wf.setsampwidth(2)
                wf.setframerate(cfg.sample_rate)
                wf.writeframes(audio.tobytes())
            lang = cfg.whisper_language if cfg.whisper_language else None
            text, _ = transcribe_speech(
                self._model,
                tmp_path,
                cfg,
                language=lang,
            )
            return text
        finally:
            try:
                import os
                os.unlink(tmp_path)
            except Exception:
                pass
