from __future__ import annotations

import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.asr_bus import transcribe_synthesized_speech
from app.config import Config
from app.studio import _chinese_voice_match


FIXTURE_ROOT = ROOT / "packaging" / "voice_verification_fixtures"
CASES = (
    (
        "\u4f60\u597d\u5440\uff0c\u5e0c\u5e0c\u3002\u4eca\u5929\u60f3\u548c\u6211\u804a\u70b9\u4ec0\u4e48\uff1f",
        FIXTURE_ROOT / "cc_context.mp3",
    ),
    (
        "\u542c\u51fa\u6765\u4e86\uff0c\u7238\u7238\uff0c\u4f60\u771f\u7684\u7d2f\u574f\u4e86\u3002"
        "\u5148\u522b\u786c\u6491\uff0c\u6b47\u4e00\u4f1a\u513f\uff0c\u6211\u966a\u7740\u4f60\u3002",
        FIXTURE_ROOT / "rest_context.mp3",
    ),
)


def main() -> int:
    model = WhisperModel(
        str(ROOT / "whisper-small-full"),
        device="cpu",
        compute_type="int8",
    )
    cfg = Config(whisper_device="cpu")
    results: list[dict[str, object]] = []
    for expected, audio_path in CASES:
        transcript, _ = transcribe_synthesized_speech(
            model,
            str(audio_path),
            cfg,
            language="zh",
        )
        accepted, score, metrics = _chinese_voice_match(expected, transcript)
        results.append(
            {
                "audio": audio_path.name,
                "accepted": accepted,
                "score": round(score, 3),
                "transcript": transcript,
                "metrics": {key: round(value, 3) for key, value in metrics.items()},
            }
        )
    print(json.dumps(results, ensure_ascii=True))
    return 0 if all(bool(result["accepted"]) for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
