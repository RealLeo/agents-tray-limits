#!/usr/bin/env python3
"""Create registered full-canvas layers from the approved Vault Boy master."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "master-rig-config.json").read_text(encoding="utf-8"))
SOURCE = ROOT / CONFIG["master"]
DESTINATION = ROOT / "sources" / "master-v3"


def scaled_polygon(points: list[list[int]], factor: int) -> list[tuple[int, int]]:
    return [(x * factor, y * factor) for x, y in points]


def main() -> None:
    master = Image.open(SOURCE).convert("RGBA")
    expected = (int(CONFIG["textureSize"]), int(CONFIG["textureSize"]))
    if master.size != expected:
        raise ValueError(f"master must be {expected}, found {master.size}")
    if master.getchannel("A").getbbox() is None:
        raise ValueError("master has no visible pixels")
    if any(master.getchannel("A").getpixel(point) for point in (
        (0, 0), (expected[0] - 1, 0), (0, expected[1] - 1),
        (expected[0] - 1, expected[1] - 1),
    )):
        raise ValueError("master corners must be transparent")

    factor = expected[0] // int(CONFIG["canvas"][0])
    arm_mask = Image.new("L", expected, 0)
    mask_draw = ImageDraw.Draw(arm_mask)
    mask_draw.polygon(scaled_polygon(CONFIG["arm"]["polygon"], factor), fill=255)
    for left, top, right, bottom in CONFIG["arm"].get("extraRects", []):
        mask_draw.rectangle(
            (left * factor, top * factor, right * factor, bottom * factor), fill=255,
        )
    arm_alpha = ImageChops.multiply(master.getchannel("A"), arm_mask)
    arm = master.copy()
    arm.putalpha(arm_alpha)

    erase_mask = arm_mask.copy()
    cutoff = int(CONFIG["arm"]["bodyEraseCutoffX"]) * factor
    opaque_overlap = master.getchannel("A").point(lambda value: 255 if value == 255 else 0)
    ImageDraw.Draw(opaque_overlap).rectangle((0, 0, cutoff - 1, expected[1]), fill=0)
    erase_mask = ImageChops.subtract(erase_mask, opaque_overlap)
    body = master.copy()
    body_alpha = body.getchannel("A")
    body_alpha = ImageChops.subtract(body_alpha, ImageChops.multiply(body_alpha, erase_mask))
    body.putalpha(body_alpha)

    DESTINATION.mkdir(parents=True, exist_ok=True)
    outputs = {
        "good-reference-master-v3.png": master,
        "good-body-master-v3.png": body,
        "good-arm-master-v3.png": arm,
        "good-arm-mask-master-v3.png": Image.merge("RGBA", (arm_mask,) * 4),
    }
    for name, image in outputs.items():
        path = DESTINATION / name
        image.save(path, optimize=True)
        print(f"Prepared {path}")

    composite = Image.alpha_composite(body, arm)
    difference = ImageChops.difference(master, composite)
    extrema = difference.getextrema()
    maximum = max(channel[1] for channel in extrema)
    changed = difference.getbbox()
    if maximum > 1:
        raise ValueError(f"registered bind composite differs from master by {maximum} in {changed}")
    print("Bind composite is pixel-registered to the master")


if __name__ == "__main__":
    main()
