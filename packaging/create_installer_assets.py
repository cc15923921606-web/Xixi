"""Generate branded images for the public Inno Setup wizard."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = Path(__file__).resolve().parent / "assets"
AVATAR_PATH = ROOT / "studio" / "assets" / "xixi-avatar-v3.png"


def _avatar(size: int) -> Image.Image:
    avatar = Image.open(AVATAR_PATH).convert("RGBA")
    return avatar.resize((size, size), Image.Resampling.LANCZOS)


def _save_large() -> None:
    canvas = Image.new("RGB", (164, 314), "#fff9fb")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 7, 313), fill="#d58ca2")
    draw.rectangle((8, 0, 163, 42), fill="#f7e4eb")
    draw.rectangle((8, 263, 163, 313), fill="#f3d9e2")
    draw.ellipse((13, 65, 159, 211), fill="#ffffff", outline="#e8b8c7", width=2)
    canvas.paste(_avatar(142), (15, 67), _avatar(142))
    draw.rounded_rectangle((29, 233, 143, 239), radius=3, fill="#d58ca2")
    draw.rounded_rectangle((45, 247, 127, 252), radius=2, fill="#e8b8c7")
    canvas.save(ASSET_DIR / "wizard-large.png", optimize=True)


def _save_small() -> None:
    canvas = Image.new("RGB", (83, 80), "#fff9fb")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((3, 2, 79, 77), radius=10, fill="#ffffff", outline="#e8b8c7", width=2)
    avatar = _avatar(68)
    canvas.paste(avatar, (8, 6), avatar)
    canvas.save(ASSET_DIR / "wizard-small.png", optimize=True)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    _save_large()
    _save_small()


if __name__ == "__main__":
    main()
