#!/usr/bin/env python3
"""Validate the curated v18 runtime sprites and compact rig fixtures."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from prepare_assets import CONFIG, SOURCE_SIZE


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
RENDER = ROOT / "render"
SOURCE = ROOT / "source" / "master"
RUNTIME = PROJECT_ROOT / "themes" / "fallout-2" / "assets" / "animation"
STATUSES = ("worried", "critical")
FRAME_COUNT = 32
DISPLAY_SCALE = 98.0 / 512.0
TRANSPARENT_CORNERS = ((0, 0), (511, 0), (0, 511), (511, 511))


def repair_mask(status: str) -> Image.Image:
    mask = Image.new("L", (512, 512), 0)
    points = [
        (round(x * 512 / SOURCE_SIZE), round(y * 512 / SOURCE_SIZE))
        for x, y in CONFIG[status]["repair"]
    ]
    ImageDraw.Draw(mask).polygon(points, fill=255)
    # Include antialiasing and the intentional shoulder overlap around the
    # local repair polygon while keeping the rest of the character immutable.
    return mask.filter(ImageFilter.MaxFilter(31))


def max_mesh_step(status: str) -> float:
    maximum = 0.0
    for layer in ("back", "front"):
        report = json.loads(
            (RENDER / f"{status}-{layer}" / "mesh-frames.json").read_text()
        )
        for previous, current in zip(report["positions"], report["positions"][1:]):
            for left, right in zip(previous, current):
                step = math.hypot(right[0] - left[0], right[1] - left[1]) * DISPLAY_SCALE
                maximum = max(maximum, step)
    return maximum


def verify_status(status: str) -> None:
    directory = RUNTIME / status
    paths = [directory / f"{index}.png" for index in range(1, FRAME_COUNT + 1)]
    assert all(path.is_file() for path in paths), f"{status}: missing sprite"
    assert len(list(directory.glob("*.png"))) == FRAME_COUNT, (
        f"{status}: unexpected runtime sprite count"
    )

    frames = []
    for index, path in enumerate(paths, 1):
        with Image.open(path) as image:
            assert image.mode == "RGBA", f"{status}/{index}: wrong mode"
            frame = image.copy()
        assert frame.size == (512, 512), f"{status}/{index}: wrong size"
        assert all(frame.getpixel(point)[3] == 0 for point in TRANSPARENT_CORNERS), (
            f"{status}/{index}: opaque corner"
        )
        frames.append(frame)

    master = Image.open(SOURCE / f"{status}-master-v1.png").convert("RGBA")
    master = master.resize((512, 512), Image.Resampling.LANCZOS)
    outside = Image.eval(repair_mask(status), lambda value: 255 - value)
    final_difference = ImageChops.difference(frames[-1], master)
    assert not Image.composite(final_difference, Image.new("RGBA", master.size), outside).getbbox(), (
        f"{status}: final frame changed pixels outside the repair region"
    )

    step = max_mesh_step(status)
    assert step <= 3.0, f"{status}: {step:.3f}px movement exceeds 3px at 98px"
    print(f"{status}: 32 RGBA frames, max step {step:.3f}px at 98px")


def verify_static_dead() -> None:
    runtime_path = RUNTIME / "dead" / "16.png"
    master_path = SOURCE / "dead-static-v1.png"
    assert runtime_path.is_file(), "dead: missing runtime sprite"
    assert master_path.is_file(), "dead: missing accepted source master"
    assert runtime_path.read_bytes() == master_path.read_bytes(), (
        "dead: runtime sprite differs from accepted source master"
    )
    assert len(list(runtime_path.parent.glob("*.png"))) == 1, (
        "dead: static state must contain exactly one runtime sprite"
    )
    with Image.open(runtime_path) as image:
        assert image.mode == "RGBA", "dead: wrong mode"
        assert image.size == (512, 512), "dead: wrong size"
        assert all(image.getpixel(point)[3] == 0 for point in TRANSPARENT_CORNERS), (
            "dead: opaque corner"
        )
    print("dead: one static RGBA frame, source master matches runtime")


def main() -> None:
    for status in STATUSES:
        verify_status(status)
    verify_static_dead()


if __name__ == "__main__":
    main()
