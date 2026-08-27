from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


LEGACY_BOT_QQ_ID = 0
LEGACY_OWNER_QQ_ID = 0
IDENTITY_FILENAME = "qq_identity.json"
_QQ_ID_PATTERN = re.compile(r"^[1-9]\d{4,11}$")


def _qq_id(value: Any, field_name: str) -> int:
    text = str(value or "").strip()
    if not _QQ_ID_PATTERN.fullmatch(text):
        label = "昔夕登录 QQ" if field_name == "bot_qq_id" else "主人 QQ"
        raise ValueError(f"{label}必须是 5 到 12 位数字")
    return int(text)


def normalize_qq_identity(payload: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(payload, Mapping):
        raise ValueError("QQ 身份配置格式无效")
    return {
        "bot_qq_id": _qq_id(payload.get("bot_qq_id"), "bot_qq_id"),
        "owner_qq_id": _qq_id(payload.get("owner_qq_id"), "owner_qq_id"),
    }


def identity_path(root: Path, *, data_root: Path | None = None) -> Path:
    return Path(data_root) / IDENTITY_FILENAME if data_root else Path(root) / "data" / IDENTITY_FILENAME


def load_qq_identity(
    root: Path,
    *,
    data_root: Path | None = None,
    default_bot_qq_id: int = LEGACY_BOT_QQ_ID,
    default_owner_qq_id: int = LEGACY_OWNER_QQ_ID,
    create_if_missing: bool = False,
) -> dict[str, int]:
    path = identity_path(root, data_root=data_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return normalize_qq_identity(payload)
    except FileNotFoundError:
        if not default_bot_qq_id or not default_owner_qq_id:
            return {
                "bot_qq_id": int(default_bot_qq_id or 0),
                "owner_qq_id": int(default_owner_qq_id or 0),
            }
        identity = normalize_qq_identity(
            {
                "bot_qq_id": default_bot_qq_id,
                "owner_qq_id": default_owner_qq_id,
            }
        )
        if create_if_missing:
            save_qq_identity(root, identity, data_root=data_root)
        return identity
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"无法读取本机 QQ 身份配置：{exc}") from exc


def save_qq_identity(
    root: Path,
    payload: Mapping[str, Any],
    *,
    data_root: Path | None = None,
) -> dict[str, int]:
    identity = normalize_qq_identity(payload)
    path = identity_path(root, data_root=data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    return identity
