"""Generate resources/icons/voice-input.ico.

Priority:
  1. If resources/icons/voice-input-source.png exists, convert it to a
     multi-resolution ICO (preserving transparency).
  2. Otherwise draw a minimal blue microphone glyph from scratch.

Usage:
    python scripts/generate_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Please `pip install Pillow` first.", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).resolve().parent
ICONS = HERE.parent / "resources" / "icons"
SRC_PNG = ICONS / "voice-input-source.png"
OUT_ICO = ICONS / "voice-input.ico"
SIZES = [16, 32, 48, 64, 128, 256]
BLUE = (30, 144, 255, 255)


def _from_png(src: Path) -> None:
    """Resample the source PNG to every ICO size with high-quality filter.

    Pillow's `sizes=` argument to ICO save only downsamples the base
    image; to preserve quality at small sizes we pre-render each size
    ourselves and hand them to `save(append_images=...)`.
    """
    img = Image.open(src).convert("RGBA")
    frames = []
    for s in SIZES:
        frames.append(img.resize((s, s), Image.Resampling.LANCZOS))
    # Largest first so the .ico header lists all resolutions
    frames.sort(key=lambda f: f.size[0], reverse=True)
    frames[0].save(
        OUT_ICO,
        format="ICO",
        sizes=[(f.size[0], f.size[1]) for f in frames],
        append_images=frames[1:],
    )
    print(f"wrote {OUT_ICO}  (source: {src.name}, {len(frames)} sizes)")


def _draw_fallback() -> None:
    """Programmatic fallback when no source PNG is present."""
    def draw(size: int) -> Image.Image:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        s = size
        body_w = int(s * 0.38)
        body_h = int(s * 0.48)
        x = (s - body_w) // 2
        y = int(s * 0.14)
        d.rounded_rectangle(
            (x, y, x + body_w, y + body_h),
            radius=int(body_w / 2),
            fill=BLUE,
        )
        bar_w = max(2, int(s * 0.06))
        bar_x = (s - bar_w) // 2
        d.rectangle(
            (bar_x, y + body_h, bar_x + bar_w, y + body_h + int(s * 0.16)),
            fill=BLUE,
        )
        base_w = int(s * 0.38)
        base_h = max(2, int(s * 0.06))
        d.rectangle(
            ((s - base_w) // 2, y + body_h + int(s * 0.16),
             (s - base_w) // 2 + base_w, y + body_h + int(s * 0.16) + base_h),
            fill=BLUE,
        )
        return img

    frames = [draw(s) for s in SIZES]
    frames[0].save(OUT_ICO, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT_ICO}  (programmatic fallback)")


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    if SRC_PNG.exists():
        _from_png(SRC_PNG)
    else:
        _draw_fallback()


if __name__ == "__main__":
    main()
