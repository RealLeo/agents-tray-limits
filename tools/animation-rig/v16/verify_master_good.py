#!/usr/bin/env python3
"""Validate good animation sprites and motion metadata."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parent
CONFIG_NAME = os.environ.get("AGENTS_TRAY_RIG_CONFIG", "master-rig-config.json")
CONFIG = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
RENDER_DIR = ROOT / CONFIG.get("renderDir", "render/master-good")
MASTER = ROOT / CONFIG["master"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sprites-dir",
        type=Path,
        help="Sprite directory to validate (defaults to the configured render output)",
    )
    parser.add_argument(
        "--motion-file",
        type=Path,
        help="Motion metadata to validate (defaults to the configured render output)",
    )
    return parser.parse_args()


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    box = image.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
    if box is None:
        raise ValueError("empty rendered frame")
    return box


def main() -> None:
    args = parse_args()
    sprites = args.sprites_dir or RENDER_DIR / "sprites"
    motion_file = args.motion_file or RENDER_DIR / "motion.json"
    expected = int(CONFIG["frames"])
    paths = [sprites / f"{index}.png" for index in range(1, expected + 1)]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"missing sprite frames: {missing}")
    frames = [Image.open(path).convert("RGBA") for path in paths]
    for index, frame in enumerate(frames, start=1):
        if frame.size != (512, 512) or frame.mode != "RGBA":
            raise ValueError(f"frame {index} is not 512x512 RGBA")
        alpha = frame.getchannel("A")
        corners = ((0, 0), (511, 0), (0, 511), (511, 511))
        if any(alpha.getpixel(point) for point in corners):
            raise ValueError(f"frame {index} has a non-transparent corner")

    # Head, torso and right side are never part of the animated mesh.
    stable_boxes = ((168, 28, 338, 145), (270, 180, 300, 260), (310, 150, 430, 330))
    for stable_box in stable_boxes:
        reference = frames[0].crop(stable_box)
        for index, frame in enumerate(frames[1:], start=2):
            difference = ImageChops.difference(reference, frame.crop(stable_box))
            if difference.getbbox() is not None:
                maximum = max(channel[1] for channel in difference.getextrema())
                if maximum > 1:
                    raise ValueError(
                        f"frame {index} changes stable pixels in {stable_box} by {maximum}"
                    )

    if not motion_file.is_file():
        raise ValueError(f"missing motion metadata: {motion_file}")
    motion = json.loads(motion_file.read_text(encoding="utf-8"))
    expected_duration = (expected - 1) * int(CONFIG["intervalMs"])
    if (
        motion["frames"] != expected
        or motion["intervalMs"] != int(CONFIG["intervalMs"])
        or motion["durationMs"] != expected_duration
    ):
        raise ValueError("unexpected staged good animation timing")
    for point, step in motion["maxConsecutiveStepDisplayPx"].items():
        if step > 3.0 + 1e-6:
            raise ValueError(f"{point} moves {step:.3f}px between frames at 98px")
    if motion["maxConsecutiveStepDisplayPx"]["root"] != 0:
        raise ValueError("character root is not fixed")
    if motion["maxConsecutiveStepDisplayPx"]["shoulder"] != 0:
        raise ValueError("animated shoulder anchor is not fixed")
    scales = [float(sample["apparentHandScale"]) for sample in motion["samples"]]
    if not 0.67 <= scales[0] <= 0.74:
        raise ValueError(f"first hand scale {scales[0]:.3f} is outside the perspective target")
    if not 0.995 <= scales[-1] <= 1.01:
        raise ValueError(f"final hand scale {scales[-1]:.3f} does not return to bind scale")
    if any(right + 1e-6 < left for left, right in zip(scales, scales[1:])):
        raise ValueError("apparent hand scale regresses during the forward motion")
    depth_strengths = [float(sample["depthStrength"]) for sample in motion["samples"]]
    if depth_strengths[:6] != [1.0] * 6 or depth_strengths[-1] != 0.0:
        raise ValueError("behind-body hold or final front-plane depth is incorrect")
    if all("depthStrengths" in sample for sample in motion["samples"]):
        upper = [float(sample["depthStrengths"]["upper"]) for sample in motion["samples"]]
        forearm = [
            float(sample["depthStrengths"]["forearm"]) for sample in motion["samples"]
        ]
        if upper[:6] != [1.0] * 6 or any(abs(value) > 1e-6 for value in upper[23:]):
            raise ValueError("upper arm does not reach and hold its front plane at frame 24")
        if any(abs(value) > 1e-6 for value in forearm[27:]):
            raise ValueError("forearm does not reach and hold its front plane at frame 28")
    first_hand = motion["samples"][0]["points"]["hand"]
    final_hand = motion["samples"][-1]["points"]["hand"]
    if math.dist(first_hand, final_hand) < 80:
        raise ValueError("animated hand did not complete the raise")
    final_points = motion["samples"][-1]["points"]
    expected_points = {
        "shoulder": CONFIG["arm"]["shoulder"],
        "elbow": CONFIG["arm"]["elbow"],
        "wrist": CONFIG["arm"]["wrist"],
        "hand": CONFIG["arm"]["hand"],
    }
    for name, expected_point in expected_points.items():
        if math.dist(final_points[name], expected_point) > 1.0:
            raise ValueError(f"final {name} misses its registered master point")

    master = Image.open(MASTER).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
    if alpha_bbox(master) != alpha_bbox(frames[-1]):
        raise ValueError("final frame alpha bounds do not match the registered master")
    review_background = Image.new("RGBA", (512, 512), (12, 18, 13, 255))
    master_review = Image.alpha_composite(review_background, master)
    final_review = Image.alpha_composite(review_background, frames[-1])
    final_difference = ImageChops.difference(master_review, final_review)
    if CONFIG.get("finalRepairMask"):
        repair_mask = Image.open(ROOT / CONFIG["finalRepairMask"]).convert("RGBA")
        repair_mask = repair_mask.getchannel("A").resize(
            (512, 512), Image.Resampling.LANCZOS,
        ).point(lambda value: 255 if value >= 8 else 0)
        outside = ImageChops.invert(repair_mask)
        final_difference = ImageChops.multiply(
            final_difference, Image.merge("RGBA", (outside,) * 4),
        )
    changed_pixels = sum(
        1 for pixel in final_difference.getdata() if max(pixel) > 4
    )
    changed_pixel_limit = int(CONFIG.get("finalChangedPixelLimit", 128))
    if changed_pixels > changed_pixel_limit:
        raise ValueError(f"final frame changes {changed_pixels} master pixels")
    if max(ImageStat.Stat(final_difference).mean) > 0.2:
        raise ValueError("final frame mean error is too high for the registered master")

    if max(alpha_bbox(frame)[3] for frame in frames) > 482:
        raise ValueError("rendered character crosses the fixed baseline")
    print(f"{CONFIG.get('previewPrefix', 'master-v3')} good prototype validation passed")


if __name__ == "__main__":
    main()
