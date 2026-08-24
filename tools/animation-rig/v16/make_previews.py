#!/usr/bin/env python3
"""Downsample Blender output and create staged review artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "rig-config.json").read_text(encoding="utf-8"))
RAW = ROOT / "render" / "good" / "raw"
SPRITES = ROOT / "render" / "good" / "sprites"
PREVIEWS = ROOT / "previews"


def raw_frames() -> list[Path]:
    frames = sorted(RAW.glob("*.png"))
    if len(frames) != int(CONFIG["frames"]):
        raise ValueError(f"expected {CONFIG['frames']} raw frames, found {len(frames)}")
    return frames


def downsample(paths: list[Path]) -> list[Image.Image]:
    if SPRITES.exists():
        shutil.rmtree(SPRITES)
    SPRITES.mkdir(parents=True)
    frames = []
    for index, path in enumerate(paths, start=1):
        with Image.open(path) as source:
            frame = source.convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
        frame.save(SPRITES / f"{index}.png", optimize=True)
        frames.append(frame)
    return frames


def save_gif(frames: list[Image.Image], path: Path, size: int, duration: int) -> None:
    resized = [frame.resize((size, size), Image.Resampling.LANCZOS) for frame in frames]
    resized[0].save(path, save_all=True, append_images=resized[1:], duration=duration,
                    loop=0, disposal=2, transparency=0)


def contact_sheet(frames: list[Image.Image]) -> Image.Image:
    size, columns, rows = 256, 6, 4
    sheet = Image.new("RGBA", (columns * size, rows * size), (10, 17, 12, 255))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame.resize((size, size), Image.Resampling.LANCZOS),
                              ((index % columns) * size, (index // columns) * size))
    return sheet


def save_mp4() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    subprocess.run([
        ffmpeg, "-y", "-framerate", str(CONFIG["fps"]), "-i", str(SPRITES / "%d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(PREVIEWS / "good-preview.mp4"),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    frames = downsample(raw_frames())
    interval = int(CONFIG["intervalMs"])
    save_gif(frames, PREVIEWS / "good-preview-512.gif", 512, interval)
    save_gif(frames, PREVIEWS / "good-preview-98.gif", 98, interval)
    save_gif(frames, PREVIEWS / "good-preview-slow.gif", 512, interval * 4)
    contact_sheet(frames).save(PREVIEWS / "good-contact-sheet.png", optimize=True)
    save_mp4()
    print(f"Created review artifacts in {PREVIEWS}")


if __name__ == "__main__":
    main()
