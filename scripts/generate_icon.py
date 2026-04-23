"""Generate resources/icons/voice-input.ico from scratch.

Produces a multi-resolution ICO with a simple blue microphone glyph.
Requires Pillow. Run once on any OS before packaging:

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

OUT = Path(__file__).resolve().parent.parent / "resources" / "icons" / "voice-input.ico"
SIZES = [16, 32, 48, 64, 128, 256]
BLUE = (30, 144, 255, 255)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    # mic body: rounded rect
    body_w = int(s * 0.38)
    body_h = int(s * 0.48)
    x = (s - body_w) // 2
    y = int(s * 0.14)
    d.rounded_rectangle(
        (x, y, x + body_w, y + body_h),
        radius=int(body_w / 2),
        fill=BLUE,
    )
    # stand: vertical bar
    bar_w = max(2, int(s * 0.06))
    bar_x = (s - bar_w) // 2
    d.rectangle(
        (bar_x, y + body_h, bar_x + bar_w, y + body_h + int(s * 0.16)),
        fill=BLUE,
    )
    # base: horizontal bar
    base_w = int(s * 0.38)
    base_h = max(2, int(s * 0.06))
    d.rectangle(
        ((s - base_w) // 2, y + body_h + int(s * 0.16),
         (s - base_w) // 2 + base_w, y + body_h + int(s * 0.16) + base_h),
        fill=BLUE,
    )
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [draw(s) for s in SIZES]
    images[0].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
