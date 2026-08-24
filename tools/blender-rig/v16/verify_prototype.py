#!/usr/bin/env python3
"""Validate rendered prototype artifacts without importing Blender."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "rig-config.json").read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


require((ROOT / "vault-boy-v16.blend").stat().st_size > 100_000,
        "Blender source is missing or unexpectedly small")
for name in ("turnaround.png", "face-hands-atlas.png", "v15-identity-atlas.png",
             "v15-good-final.png", "face-good-decal.png"):
    require((ROOT / "references" / name).is_file(), f"missing reference {name}")

motion = json.loads((ROOT / "render" / "good" / "motion.json").read_text(encoding="utf-8"))
require(motion["frames"] == 24 and motion["fps"] == 24, "motion timing changed")
for track, distance in motion["maxConsecutiveStepDisplayPx"].items():
    require(distance <= 3.0, f"{track} moves {distance}px between frames")

sprites = sorted((ROOT / "render" / "good" / "sprites").glob("*.png"))
require(len(sprites) == 24, f"expected 24 sprites, found {len(sprites)}")
bottoms = []
for path in sprites:
    image = Image.open(path)
    require(image.mode == "RGBA", f"{path.name} is not RGBA")
    require(image.size == (512, 512), f"{path.name} has the wrong size")
    alpha = image.getchannel("A")
    require(all(alpha.getpixel(point) == 0 for point in ((0, 0), (511, 0), (0, 511), (511, 511))),
            f"{path.name} does not have transparent corners")
    bbox = alpha.getbbox()
    require(bbox is not None, f"{path.name} is empty")
    bottoms.append(bbox[3])
require(max(bottoms) - min(bottoms) <= 1, "foot baseline moves between frames")

for name in ("good-preview-512.gif", "good-preview-98.gif", "good-preview-slow.gif",
             "good-contact-sheet.png", "good-preview.mp4", "model-turntable.gif"):
    require((ROOT / "previews" / name).stat().st_size > 0, f"missing preview {name}")

print("Prototype validation passed")
print(json.dumps({
    "sprites": len(sprites),
    "baselineRange": [min(bottoms), max(bottoms)],
    "maxSteps": motion["maxConsecutiveStepDisplayPx"],
}, indent=2))

