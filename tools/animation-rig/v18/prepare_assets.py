#!/usr/bin/env python3
"""Prepare registered v18 master, body, and arm layers from ImageGen staging art."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "source" / "raw"
OUT = ROOT / "source" / "master"
SOURCE_SIZE = 1254
TARGET_SIZE = 2048
SCALE = TARGET_SIZE / SOURCE_SIZE


CONFIG = {
    "worried": {
        "master": "worried-imagegen-v1.png",
        "clean": "worried-clean-body-imagegen-v1.png",
        "repair": [(345, 340), (855, 340), (900, 690), (345, 690)],
        # Image-left arm and hand sit in front of the wrist-checking arm.
        "arm_front": [
            (505, 380), (445, 405), (385, 455), (365, 525),
            (380, 590), (430, 615), (505, 570), (590, 540),
            (600, 475), (555, 410),
        ],
        "arm_back": [
            (675, 365), (760, 380), (825, 430), (850, 515),
            (825, 590), (760, 625), (650, 610), (535, 565),
            (520, 505), (600, 470),
        ],
    },
    "critical": {
        "master": "critical-imagegen-v1.png",
        "clean": "critical-clean-body-imagegen-v1.png",
        "repair": [(365, 325), (875, 325), (920, 850), (350, 850)],
        "arm_front": [
            (430, 385), (500, 405), (535, 480), (550, 545),
            (655, 540), (700, 590), (670, 675), (575, 700),
            (500, 675), (430, 620), (405, 520),
        ],
        "arm_back": [
            (650, 330), (745, 335), (820, 390), (860, 500),
            (875, 640), (870, 765), (835, 825), (785, 800),
            (770, 710), (765, 600), (720, 480),
        ],
    },
}


def connected_background(image: Image.Image) -> Image.Image:
    """Remove the generated checkerboard while preserving enclosed light details."""
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size
    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def candidate(x: int, y: int) -> bool:
        red, green, blue = pixels[x, y]
        return min(red, green, blue) >= 230 and max(red, green, blue) - min(red, green, blue) <= 12

    for x in range(width):
        if candidate(x, 0):
            queue.append((x, 0))
        if candidate(x, height - 1):
            queue.append((x, height - 1))
    for y in range(height):
        if candidate(0, y):
            queue.append((0, y))
        if candidate(width - 1, y):
            queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if seen[index] or not candidate(x, y):
            continue
        seen[index] = 1
        if x:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))

    rgba = rgb.convert("RGBA")
    alpha = Image.new("L", (width, height), 255)
    alpha_pixels = alpha.load()
    for y in range(height):
        offset = y * width
        for x in range(width):
            if seen[offset + x]:
                alpha_pixels[x, y] = 0
    rgba.putalpha(alpha)
    return rgba


def normalized(path: Path) -> Image.Image:
    image = connected_background(Image.open(path))
    return image.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)


def mask_for(points: list[tuple[int, int]], blur: float = 2.0) -> Image.Image:
    mask = Image.new("L", (TARGET_SIZE, TARGET_SIZE), 0)
    scaled = [(round(x * SCALE), round(y * SCALE)) for x, y in points]
    ImageDraw.Draw(mask).polygon(scaled, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur * SCALE))


def masked_layer(master: Image.Image, points: list[tuple[int, int]]) -> Image.Image:
    layer = master.copy()
    selection = mask_for(points, 1.2)
    alpha = Image.composite(master.getchannel("A"), Image.new("L", master.size, 0), selection)
    layer.putalpha(alpha)
    return layer


def prepare(status: str, config: dict) -> None:
    master = normalized(RAW / config["master"])
    clean = normalized(RAW / config["clean"])
    repair = mask_for(config["repair"], 1.5)
    body = Image.composite(clean, master, repair)

    master.save(OUT / f"{status}-master-v1.png", optimize=True)
    body.save(OUT / f"{status}-clean-body-v1.png", optimize=True)
    masked_layer(master, config["arm_front"]).save(
        OUT / f"{status}-arm-front-v1.png", optimize=True
    )
    masked_layer(master, config["arm_back"]).save(
        OUT / f"{status}-arm-back-v1.png", optimize=True
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (TARGET_SIZE, TARGET_SIZE), (0, 0, 0, 0)).save(
        OUT / "transparent.png"
    )
    for status, config in CONFIG.items():
        prepare(status, config)


if __name__ == "__main__":
    main()
