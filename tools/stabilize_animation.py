#!/usr/bin/env python3
"""Slice, clean, and stabilize Fallout 2 animation sprite sheets.

The script is a source-build helper only.  It has no runtime role in the
GNOME extension and intentionally depends on Pillow.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import deque
from pathlib import Path

from PIL import Image


STATUSES = ("good", "worried", "critical", "dead")
FILTER_WEIGHTS = (1, 2, 3, 2, 1)
FILTER_RADIUS = len(FILTER_WEIGHTS) // 2
TARGET_FIRST_FRAME_HEIGHT = 420
TARGET_BASELINE = 480
MAX_FRAME_WIDTH = 460
MAX_FRAME_HEIGHT = 450
MAX_ANCHOR_STEP = 4.0


def _background_candidate(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, _alpha = pixel
    return min(red, green, blue) >= 180 and max(red, green, blue) - min(red, green, blue) <= 18


def ensure_transparency(image: Image.Image) -> Image.Image:
    """Preserve real alpha or remove an edge-connected neutral checkerboard."""
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 255:
        return rgba

    width, height = rgba.size
    pixels = rgba.load()
    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if background[index] or not _background_candidate(pixels[x, y]):
            return
        background[index] = 1
        queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    output = rgba.copy()
    out_pixels = output.load()
    for y in range(height):
        row = y * width
        for x in range(width):
            if background[row + x]:
                red, green, blue, _alpha = out_pixels[x, y]
                out_pixels[x, y] = (red, green, blue, 0)
    return output


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    mask = image.getchannel("A").point(lambda value: 255 if value >= 24 else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError("sprite cell has no visible pixels")
    return box


def split_sheet(image: Image.Image) -> list[Image.Image]:
    width, height = image.size
    frames: list[Image.Image] = []
    for index in range(10):
        column = index % 5
        row = index // 5
        left = round(column * width / 5)
        right = round((column + 1) * width / 5)
        top = round(row * height / 2)
        bottom = round((row + 1) * height / 2)
        frames.append(image.crop((left, top, right, bottom)))
    return frames


def core_center_x(image: Image.Image) -> float:
    left, top, right, bottom = alpha_bbox(image)
    box_width = right - left
    box_height = bottom - top
    roi_left = left + round(box_width * 0.15)
    roi_right = right - round(box_width * 0.15)
    roi_top = top + round(box_height * 0.28)
    roi_bottom = top + round(box_height * 0.78)
    rgba = image.convert("RGBA")
    weighted_sum = 0.0
    weight = 0.0
    for y in range(roi_top, roi_bottom):
        for x in range(roi_left, roi_right):
            red, green, blue, alpha = rgba.getpixel((x, y))
            if (alpha >= 24 and red >= 170 and green >= 140 and blue <= 135
                    and red - blue >= 60 and green - blue >= 35):
                weighted_sum += x * alpha
                weight += alpha
    if weight:
        return weighted_sum / weight

    # Defensive fallback for a future sheet whose costume palette changed.
    alpha_channel = rgba.getchannel("A")
    for y in range(roi_top, roi_bottom):
        for x in range(roi_left, roi_right):
            value = alpha_channel.getpixel((x, y))
            if value >= 24:
                weighted_sum += x * value
                weight += value
    return weighted_sum / weight if weight else (left + right) / 2


def smooth_trajectory(values: list[float]) -> list[float]:
    smoothed: list[float] = []
    for index in range(len(values)):
        numerator = 0.0
        denominator = 0
        for offset, weight in zip(range(-FILTER_RADIUS, FILTER_RADIUS + 1), FILTER_WEIGHTS):
            source = min(max(index + offset, 0), len(values) - 1)
            numerator += values[source] * weight
            denominator += weight
        smoothed.append(numerator / denominator)

    for index in range(1, len(smoothed)):
        lower = smoothed[index - 1] - MAX_ANCHOR_STEP
        upper = smoothed[index - 1] + MAX_ANCHOR_STEP
        smoothed[index] = min(max(smoothed[index], lower), upper)
    for index in range(len(smoothed) - 2, -1, -1):
        lower = smoothed[index + 1] - MAX_ANCHOR_STEP
        upper = smoothed[index + 1] + MAX_ANCHOR_STEP
        smoothed[index] = min(max(smoothed[index], lower), upper)
    return smoothed


def normalize_frames(frames: list[Image.Image]) -> tuple[list[Image.Image], dict[str, object]]:
    boxes = [alpha_bbox(frame) for frame in frames]
    first_height = boxes[0][3] - boxes[0][1]
    maximum_width = max(right - left for left, _top, right, _bottom in boxes)
    maximum_height = max(bottom - top for _left, top, _right, bottom in boxes)
    scale = min(
        TARGET_FIRST_FRAME_HEIGHT / first_height,
        MAX_FRAME_WIDTH / maximum_width,
        MAX_FRAME_HEIGHT / maximum_height,
    )

    raw_centers = [core_center_x(frame) for frame in frames]
    target_centers = smooth_trajectory(raw_centers)
    center_offset = 256.0 - statistics.median(target_centers)
    target_centers = [value + center_offset for value in target_centers]

    normalized: list[Image.Image] = []
    applied_centers: list[float] = []
    for frame, target_center in zip(frames, target_centers):
        box = alpha_bbox(frame)
        figure = frame.crop(box)
        size = (
            max(1, round(figure.width * scale)),
            max(1, round(figure.height * scale)),
        )
        figure = figure.resize(size, Image.Resampling.LANCZOS)
        figure = figure.crop(alpha_bbox(figure))
        figure_center = core_center_x(figure)
        x = round(target_center - figure_center)
        y = TARGET_BASELINE - figure.height
        if x < 0 or y < 0 or x + figure.width > 512 or y + figure.height > 512:
            raise ValueError(f"normalized frame leaves canvas: x={x}, y={y}, size={figure.size}")
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        canvas.alpha_composite(figure, (x, y))
        normalized.append(canvas)
        applied_centers.append(core_center_x(canvas))

    return normalized, {
        "scale": round(scale, 6),
        "rawCenters": [round(value, 3) for value in raw_centers],
        "targetCenters": [round(value, 3) for value in target_centers],
        "appliedCenters": [round(value, 3) for value in applied_centers],
        "baseline": TARGET_BASELINE,
    }


def process_sheet(status: str, sheet_path: Path, output_root: Path, clean_root: Path | None) -> dict[str, object]:
    cleaned = ensure_transparency(Image.open(sheet_path))
    if clean_root is not None:
        clean_root.mkdir(parents=True, exist_ok=True)
        cleaned.save(clean_root / f"{status}-sheet.png", optimize=True)
    frames, metadata = normalize_frames(split_sheet(cleaned))
    status_root = output_root / status
    status_root.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames, start=1):
        frame.save(status_root / f"{index}.png", optimize=True)
    metadata["sheet"] = f"{status}-sheet.png" if clean_root is not None else sheet_path.name
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--clean-sheet-root", type=Path)
    for status in STATUSES:
        parser.add_argument(f"--{status}", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    report = {}
    for status in STATUSES:
        report[status] = process_sheet(
            status,
            getattr(args, status),
            args.output_root,
            args.clean_sheet_root,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
