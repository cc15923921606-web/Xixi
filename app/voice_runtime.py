from __future__ import annotations

import os
import string
from functools import lru_cache
from pathlib import Path
from typing import Mapping

try:
    import winreg
except ImportError:  # pragma: no cover - Windows is the supported desktop target.
    winreg = None  # type: ignore[assignment]


_REGISTRY_KEY = r"Software\Xixi\Components"
_REGISTRY_VALUE = "GPTSoVITSRoot"

_MULTILINGUAL_GPT_NAMES = (
    "xixi_voice_multilingual.ckpt",
    "xixi_voice_v2Pro-e10.ckpt",
)
_MULTILINGUAL_SOVITS_NAMES = (
    "xixi_voice_multilingual.pth",
    "xixi_voice_v2Pro_e4_s1572.pth",
)
_CHINESE_SOVITS_NAMES = (
    "xixi_voice_chinese.pth",
    "xixi_voice_v2Pro_e2e4_blend30.pth",
)

VOICE_SOURCE_FILES = (
    "api_v2.py",
    "GPT_SoVITS/TTS_infer_pack/TTS.py",
    "GPT_SoVITS/TTS_infer_pack/text_segmentation_method.py",
    "GPT_SoVITS/text/g2pw/onnx_api.py",
    "GPT_SoVITS/text/cleaner.py",
    "GPT_SoVITS/text/chinese2.py",
    "GPT_SoVITS/module/models.py",
    "tools/i18n/i18n.py",
    "tools/audio_sr.py",
)
VOICE_HF_MODEL_FILES = (
    "s1v3.ckpt",
    "sv/pretrained_eres2netv2w24s4ep4.ckpt",
    "chinese-roberta-wwm-ext-large/config.json",
    "chinese-roberta-wwm-ext-large/pytorch_model.bin",
    "chinese-roberta-wwm-ext-large/tokenizer.json",
    "chinese-hubert-base/config.json",
    "chinese-hubert-base/preprocessor_config.json",
    "chinese-hubert-base/pytorch_model.bin",
)
VOICE_FAST_LANGDETECT_FILES = (
    "lid.176.bin",
)
VOICE_G2PW_MODEL_FILES = (
    "config.py",
    "g2pW.onnx",
    "MONOPHONIC_CHARS.txt",
    "POLYPHONIC_CHARS.txt",
    "bopomofo_to_pinyin_wo_tune_dict.json",
    "char_bopomofo_dict.json",
    "version",
)
VOICE_NLTK_DATA_FILES = (
    # g2p_en imports these resources at module load time. Keep them beside the
    # installed voice engine so speech generation never depends on user caches.
    "corpora/cmudict.zip",
    "taggers/averaged_perceptron_tagger.zip",
    "taggers/averaged_perceptron_tagger_eng.zip",
)


def _first_existing(parent: Path, names: tuple[str, ...]) -> Path:
    candidates = tuple(parent / name for name in names)
    return next((path for path in candidates if path.is_file()), candidates[0])


def multilingual_gpt_path(root: Path) -> Path:
    return _first_existing(Path(root) / "GPT_weights_v2Pro", _MULTILINGUAL_GPT_NAMES)


def multilingual_sovits_path(root: Path) -> Path:
    return _first_existing(Path(root) / "SoVITS_weights_v2Pro", _MULTILINGUAL_SOVITS_NAMES)


def chinese_sovits_path(root: Path) -> Path:
    return _first_existing(Path(root) / "SoVITS_weights_v2Pro", _CHINESE_SOVITS_NAMES)


def voice_requirements_path(root: Path) -> Path:
    root = Path(root)
    candidates = (
        root / "requirements-windows-cu121.txt",
        root / "requirements.txt",
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


def voice_nltk_data_root(root: Path) -> Path:
    return Path(root) / "nltk_data"


def voice_required_artifacts(root: Path) -> dict[str, Path]:
    root = Path(root)
    pretrained = root / "GPT_SoVITS" / "pretrained_models"
    fast_langdetect = pretrained / "fast_langdetect"
    g2pw = root / "GPT_SoVITS" / "text" / "G2PWModel"
    nltk_data = voice_nltk_data_root(root)
    artifacts = {
        "python_runtime": root / ".venv" / "Scripts" / "python.exe",
        "requirements": voice_requirements_path(root),
        **{
            f"source:{relative}": root / Path(relative)
            for relative in VOICE_SOURCE_FILES
        },
        **{
            f"base_model:{relative}": pretrained / Path(relative)
            for relative in VOICE_HF_MODEL_FILES
        },
        **{
            f"language_detector:{relative}": fast_langdetect / relative
            for relative in VOICE_FAST_LANGDETECT_FILES
        },
        **{
            f"g2pw:{relative}": g2pw / relative
            for relative in VOICE_G2PW_MODEL_FILES
        },
        **{
            f"nltk_data:{relative}": nltk_data / Path(relative)
            for relative in VOICE_NLTK_DATA_FILES
        },
        "voice_model:multilingual_gpt": multilingual_gpt_path(root),
        "voice_model:multilingual_sovits": multilingual_sovits_path(root),
        "voice_model:chinese_sovits": chinese_sovits_path(root),
    }
    return artifacts


def voice_missing_artifacts(root: Path) -> dict[str, Path]:
    return {
        name: path
        for name, path in voice_required_artifacts(root).items()
        if not path.is_file()
    }


def voice_root_ready(root: Path) -> bool:
    return not voice_missing_artifacts(root)


def voice_root_completeness(root: Path) -> tuple[int, int]:
    artifacts = voice_required_artifacts(root)
    ready = sum(path.is_file() for path in artifacts.values())
    return ready, len(artifacts)


def registered_voice_root() -> Path | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _REGISTRY_VALUE)
    except OSError:
        return None
    text = str(value or "").strip().strip('"')
    return Path(os.path.expandvars(os.path.expanduser(text))) if text else None


def register_voice_root(root: Path) -> None:
    if winreg is None:
        return
    resolved = Path(root).resolve()
    try:
        existing = registered_voice_root()
        if existing is not None and existing.resolve() == resolved:
            return
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
            winreg.SetValueEx(key, _REGISTRY_VALUE, 0, winreg.REG_SZ, str(resolved))
    except OSError:
        return


@lru_cache(maxsize=16)
def _discovered_voice_roots(default_root: Path) -> tuple[Path, ...]:
    """Return inexpensive, deterministic locations that may hold a full engine."""
    default_root = Path(default_root)
    home = Path.home()
    candidates = [
        default_root,
        default_root.parent / "GPT-SoVITS",
        default_root.parent / "work" / "GPT-SoVITS",
        home / "GPT-SoVITS",
        home / "Downloads" / "GPT-SoVITS",
        home / "Desktop" / "GPT-SoVITS",
        home / "Documents" / "GPT-SoVITS",
    ]
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if not drive.exists():
                continue
            candidates.extend((drive / "GPT-SoVITS", drive / "work" / "GPT-SoVITS"))
            try:
                children = [item for item in drive.iterdir() if item.is_dir()]
            except OSError:
                continue
            for child in children:
                candidates.extend((
                    child / "GPT-SoVITS",
                    child / "work" / "GPT-SoVITS",
                    child / "runtime" / "GPT-SoVITS",
                ))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return tuple(unique)


def resolve_voice_root(
    default_root: Path,
    environ: Mapping[str, str] | None = None,
    *,
    allow_registered_fallback: bool = True,
    discover: bool = True,
) -> Path:
    values = os.environ if environ is None else environ
    configured = str(values.get("GPT_SOVITS_ROOT") or "").strip().strip('"')
    configured_root = (
        Path(os.path.expandvars(os.path.expanduser(configured)))
        if configured
        else None
    )
    default_root = Path(default_root)
    if configured_root is not None and voice_root_ready(configured_root):
        return configured_root
    if configured_root is not None and not allow_registered_fallback:
        return configured_root
    if voice_root_ready(default_root):
        return default_root
    registered = registered_voice_root() if allow_registered_fallback else None
    if registered is not None and voice_root_ready(registered):
        return registered
    if allow_registered_fallback and discover:
        discovered = next(
            (candidate for candidate in _discovered_voice_roots(default_root) if voice_root_ready(candidate)),
            None,
        )
        if discovered is not None:
            register_voice_root(discovered)
            return discovered

    partial_candidates: list[Path] = []
    for candidate in (configured_root, default_root, registered):
        if candidate is None or candidate in partial_candidates or not candidate.exists():
            continue
        partial_candidates.append(candidate)
    if partial_candidates:
        best = max(partial_candidates, key=lambda path: voice_root_completeness(path)[0])
        if voice_root_completeness(best)[0] > 0:
            return best
    return configured_root if configured_root is not None else default_root


def resolve_voice_config(root: Path, packaged_config: Path) -> Path:
    root = Path(root)
    candidates = (
        root / "xixi_voice_tts_infer.yaml",
        root.parent / "xixi_voice_tts_infer.yaml",
        Path(packaged_config),
    )
    return next((path for path in candidates if path.is_file()), Path(packaged_config))
