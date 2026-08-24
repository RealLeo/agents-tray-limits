#!/usr/bin/env python3
"""Validate the staged good animation without touching runtime assets."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "rig-config.json").read_text(encoding="utf-8"))
SPRITES = ROOT / "render" / "good" / "sprites"


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    box = image.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
    if box is None:
        raise ValueError("empty rendered frame")
    return box


def main() -> None:
    paths = [SPRITES / f"{index}.png" for index in range(1, 25)]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"missing sprite frames: {missing}")
    frames = [Image.open(path).convert("RGBA") for path in paths]
    for index, frame in enumerate(frames, start=1):
        if frame.size != (512, 512) or frame.mode != "RGBA":
            raise ValueError(f"frame {index} is not 512x512 RGBA")
        alpha = frame.getchannel("A")
        if any(alpha.getpixel(point) for point in ((0, 0), (511, 0), (0, 511), (511, 511))):
            raise ValueError(f"frame {index} has a non-transparent corner")

    # Head pixels never belong to an animated mesh.
    stable_box = (210, 24, 310, 128)
    reference = frames[0].crop(stable_box)
    for index, frame in enumerate(frames[1:], start=2):
        difference = ImageChops.difference(reference, frame.crop(stable_box))
        if difference.getbbox() is not None:
            maximum = max(channel[1] for channel in difference.getextrema())
            if maximum > 1:
                raise ValueError(f"frame {index} changes stable face pixels by {maximum}")

    if max(alpha_bbox(frame)[3] for frame in frames) > 482:
        raise ValueError("rendered character crosses the baseline")
    motion = json.loads((ROOT / "render" / "good" / "motion.json").read_text(encoding="utf-8"))
    if motion["frames"] != 24 or motion["intervalMs"] != 42 or motion["durationMs"] != 966:
        raise ValueError("unexpected good animation timing")
    for point, step in motion["maxConsecutiveStepDisplayPx"].items():
        if step > 3.0 + 1e-6:
            raise ValueError(f"{point} moves {step:.3f}px between frames at 98px")
    first_hand = motion["samples"][0]["points"]["hand"]
    final_hand = motion["samples"][-1]["points"]["hand"]
    if math.dist(first_hand, final_hand) < 80:
        raise ValueError("animated hand did not complete the raise")
    if motion["maxConsecutiveStepDisplayPx"]["root"] != 0:
        raise ValueError("character root is not fixed")
    print("2D good prototype validation passed")


if __name__ == "__main__":
    main()
