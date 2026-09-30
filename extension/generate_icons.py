"""Generates the extension's toolbar icons (16/48/128px) with Pillow.
Run once: backend/.venv/Scripts/python.exe extension/generate_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent / "icons"
OUT_DIR.mkdir(exist_ok=True)

BG_COLOR = (37, 99, 235)  # blue
RING_COLOR = (255, 255, 255)


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Filled rounded-square background.
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 4, fill=BG_COLOR)

    # A simple "eye" (lens) shape: an outlined circle with a smaller filled pupil,
    # standing in for "TruthLens looking at content."
    margin = size * 0.2
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        outline=RING_COLOR,
        width=max(1, size // 12),
    )
    pupil_r = size * 0.12
    center = size / 2
    draw.ellipse(
        [center - pupil_r, center - pupil_r, center + pupil_r, center + pupil_r],
        fill=RING_COLOR,
    )
    return img


for size in (16, 48, 128):
    make_icon(size).save(OUT_DIR / f"icon{size}.png")
    print(f"saved icons/icon{size}.png")
