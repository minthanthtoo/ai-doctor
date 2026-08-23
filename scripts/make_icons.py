#!/usr/bin/env python3
"""Generate PWA icons for Personal Health Steward (shield + ECG mark).

Reproducible asset pipeline: run after any intentional brand change.

    /Users/min/miniforge3/bin/python apps/pwa/../../scripts/make_icons.py

Outputs into apps/pwa/public/: icon-192.png, icon-512.png,
maskable-512.png (full-bleed background, mark inside the 80% safe zone),
plus favicon.svg (hand-written vector twin of the same geometry).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

TEAL = (13, 71, 64, 255)        # #0d4740 — app theme_color
CREAM = (244, 241, 232, 255)    # #f4f1e8 — app background_color

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "apps" / "pwa" / "public"

SHIELD_OUTER = [
    (0.18, 0.10),
    (0.82, 0.10),
    (0.82, 0.45),
    (0.50, 0.92),
    (0.18, 0.45),
]
SHIELD_INSET = 0.80
ECG_POINTS = [
    (0.24, 0.48),
    (0.36, 0.48),
    (0.41, 0.37),
    (0.47, 0.60),
    (0.52, 0.31),
    (0.57, 0.54),
    (0.61, 0.48),
    (0.76, 0.48),
]


def _scale(points, size, inset=1.0):
    cx, cy = 0.5, 0.5
    return [
        (
            round((cx + (x - cx) * inset) * size),
            round((cy + (y - cy) * inset) * size),
        )
        for x, y in points
    ]


def _draw_icon(size: int, mark_inset: float = 1.0) -> Image.Image:
    image = Image.new("RGBA", (size, size), CREAM)
    draw = ImageDraw.Draw(image)
    draw.polygon(_scale(SHIELD_OUTER, size, mark_inset), fill=TEAL)
    draw.polygon(_scale(SHIELD_OUTER, size, mark_inset * SHIELD_INSET), fill=CREAM)
    stroke = max(2, round(size * 0.035))
    draw.line(
        _scale(ECG_POINTS, size, mark_inset),
        fill=TEAL,
        width=stroke,
        joint="curve",
    )
    return image


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for name, size, inset in (
        ("icon-192.png", 192, 1.0),
        ("icon-512.png", 512, 1.0),
        ("maskable-512.png", 512, 0.72),
    ):
        _draw_icon(size, inset).save(PUBLIC_DIR / name, optimize=True)
        print(f"wrote {PUBLIC_DIR / name}")


if __name__ == "__main__":
    main()
