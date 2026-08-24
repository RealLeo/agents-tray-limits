#!/usr/bin/env python3
"""Create staged review artifacts for the registered master-v3 good rig."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
CONFIG_NAME = os.environ.get("AGENTS_TRAY_RIG_CONFIG", "master-rig-config.json")
CONFIG = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
RENDER_DIR = ROOT / CONFIG.get("renderDir", "render/master-good")
RAW = RENDER_DIR / "raw"
SPRITES = RENDER_DIR / "sprites"
PREVIEWS = ROOT / CONFIG.get("previewDir", "previews/master-good")
PREFIX = CONFIG.get("previewPrefix", "master-v3")
OLIVE = (12, 18, 13, 255)


def raw_frames() -> list[Path]:
    frames = sorted(RAW.glob("*.png"))
    expected = int(CONFIG["frames"])
    if len(frames) != expected:
        raise ValueError(f"expected {expected} raw frames, found {len(frames)}")
    return frames


def downsample(paths: list[Path]) -> list[Image.Image]:
    if SPRITES.exists():
        shutil.rmtree(SPRITES)
    SPRITES.mkdir(parents=True)
    frames: list[Image.Image] = []
    for index, path in enumerate(paths, start=1):
        with Image.open(path) as source:
            frame = source.convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
        frame.save(SPRITES / f"{index}.png", optimize=True)
        frames.append(frame)
    return frames


def on_review_background(frame: Image.Image, size: int) -> Image.Image:
    resized = frame.resize((size, size), Image.Resampling.LANCZOS)
    review = Image.new("RGBA", resized.size, OLIVE)
    review.alpha_composite(resized)
    return review.convert("RGB")


def save_gif(frames: list[Image.Image], path: Path, size: int, duration: int) -> None:
    review_frames = [on_review_background(frame, size) for frame in frames]
    review_frames[0].save(
        path,
        save_all=True,
        append_images=review_frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
        optimize=False,
    )


def save_contact_sheet(frames: list[Image.Image], path: Path) -> None:
    cell = 256
    columns = 6
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * cell, rows * cell), OLIVE[:3])
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames, start=1):
        x = ((index - 1) % columns) * cell
        y = ((index - 1) // columns) * cell
        sheet.paste(on_review_background(frame, cell), (x, y))
        draw.text((x + 8, y + 8), f"{index:02d}", fill=(135, 231, 126))
    sheet.save(path, optimize=True)


def save_depth_trajectory(path: Path) -> None:
    motion = json.loads((RENDER_DIR / "motion.json").read_text(encoding="utf-8"))
    width, height = 1280, 480
    margin_left, margin_right = 80, 40
    margin_top, margin_bottom = 54, 70
    chart = Image.new("RGB", (width, height), OLIVE[:3])
    draw = ImageDraw.Draw(chart)
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    draw.rectangle(
        (margin_left, margin_top, margin_left + plot_width, margin_top + plot_height),
        outline=(77, 119, 69),
        width=2,
    )
    draw.text((margin_left, 16), "HAND DEPTH / APPARENT SCALE", fill=(135, 231, 126))
    samples = motion["samples"]
    max_depth = max(abs(float(sample["handZ"])) for sample in samples) or 1.0
    for index in range(5):
        y = margin_top + round(plot_height * index / 4)
        draw.line((margin_left, y, margin_left + plot_width, y), fill=(29, 52, 31), width=1)
    depth_points = []
    scale_points = []
    for sample in samples:
        progress = (int(sample["frame"]) - 1) / max(1, len(samples) - 1)
        x = margin_left + round(progress * plot_width)
        depth_ratio = abs(float(sample["handZ"])) / max_depth
        scale = float(sample["apparentHandScale"])
        depth_y = margin_top + round((1.0 - depth_ratio) * plot_height)
        scale_y = margin_top + round((1.0 - max(0.0, min(1.0, scale))) * plot_height)
        depth_points.append((x, depth_y))
        scale_points.append((x, scale_y))
    draw.line(depth_points, fill=(235, 92, 59), width=4, joint="curve")
    draw.line(scale_points, fill=(135, 231, 126), width=4, joint="curve")
    draw.text((margin_left, height - 44), "red: distance behind body", fill=(235, 92, 59))
    draw.text((margin_left + 310, height - 44), "green: apparent hand scale", fill=(135, 231, 126))
    draw.text(
        (width - 370, height - 44),
        f"{samples[0]['apparentHandScale']:.3f} -> {samples[-1]['apparentHandScale']:.3f}",
        fill=(196, 203, 151),
    )
    chart.save(path, optimize=True)


def save_mp4() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    playback_rate = f"1000/{int(CONFIG['intervalMs'])}"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0c120d:s=512x512:r={playback_rate}",
            "-framerate",
            playback_rate,
            "-i",
            str(SPRITES / "%d.png"),
            "-filter_complex",
            "[0:v][1:v]overlay=shortest=1:format=auto,format=yuv420p",
            "-c:v",
            "libx264",
            str(PREVIEWS / f"good-preview-{PREFIX}.mp4"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    frames = downsample(raw_frames())
    interval = int(CONFIG["intervalMs"])
    save_gif(frames, PREVIEWS / f"good-preview-{PREFIX}-512.gif", 512, interval)
    save_gif(frames, PREVIEWS / f"good-preview-{PREFIX}-98.gif", 98, interval)
    save_gif(frames, PREVIEWS / f"good-preview-{PREFIX}-slow.gif", 512, interval * 4)
    save_contact_sheet(frames, PREVIEWS / f"good-contact-sheet-{PREFIX}.png")
    save_depth_trajectory(PREVIEWS / f"good-depth-trajectory-{PREFIX}.png")
    save_mp4()
    print(f"Created {PREFIX} review artifacts in {PREVIEWS}")


if __name__ == "__main__":
    main()
