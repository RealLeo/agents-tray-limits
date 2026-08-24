#!/usr/bin/env python3
"""Create review sprites, contact sheets and animated previews from Blender PNGs."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "rig-config.json").read_text(encoding="utf-8"))
RAW_DIR = ROOT / "render" / "good" / "raw"
SPRITE_DIR = ROOT / "render" / "good" / "sprites"
PREVIEW_DIR = ROOT / "previews"
TURNTABLE_RAW_DIR = ROOT / "render" / "turntable" / "raw"


def add_outline(image: Image.Image, radius: int = 2) -> Image.Image:
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    expanded = alpha.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    outside = ImageChops.subtract(expanded, alpha)
    outline = Image.new("RGBA", image.size, (4, 4, 3, 0))
    outline.putalpha(outside)
    return Image.alpha_composite(outline, image)


def process_frames() -> list[Image.Image]:
    files = sorted(RAW_DIR.glob("*.png"))
    if len(files) != CONFIG["frames"]:
        raise SystemExit(f"expected {CONFIG['frames']} raw frames, found {len(files)}")
    SPRITE_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, path in enumerate(files, start=1):
        image = Image.open(path).convert("RGBA")
        if image.size != (CONFIG["spriteSize"], CONFIG["spriteSize"]):
            image = image.resize((CONFIG["spriteSize"], CONFIG["spriteSize"]), Image.Resampling.LANCZOS)
        image = add_outline(image, radius=2)
        output = SPRITE_DIR / f"{index:02d}.png"
        image.save(output, optimize=True)
        frames.append(image)
    return frames


def on_background(image: Image.Image, color=(12, 18, 13, 255)) -> Image.Image:
    background = Image.new("RGBA", image.size, color)
    return Image.alpha_composite(background, image).convert("RGB")


def make_contact_sheet(frames: list[Image.Image]) -> Path:
    columns, rows = 6, 4
    cell = CONFIG["spriteSize"]
    sheet = Image.new("RGB", (columns * cell, rows * cell), (24, 27, 24))
    for index, frame in enumerate(frames):
        sheet.paste(on_background(frame), ((index % columns) * cell, (index // columns) * cell))
    path = PREVIEW_DIR / "good-contact-sheet.png"
    sheet.save(path, optimize=True)
    return path


def save_gif(frames: list[Image.Image], path: Path, size: int, duration: int) -> None:
    prepared = [on_background(frame).resize((size, size), Image.Resampling.LANCZOS) for frame in frames]
    prepared[0].save(path, save_all=True, append_images=prepared[1:], duration=duration,
                     loop=0, disposal=2, optimize=False)


def make_video() -> None:
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(CONFIG["fps"]),
        "-i", str(SPRITE_DIR / "%02d.png"), "-vf", "format=yuv420p",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(PREVIEW_DIR / "good-preview.mp4"),
    ], check=True)


def make_turntable() -> None:
    files = sorted(TURNTABLE_RAW_DIR.glob("*.png"))
    if len(files) != 36:
        raise SystemExit(f"expected 36 turntable frames, found {len(files)}")
    frames = []
    for path in files:
        image = Image.open(path).convert("RGBA")
        image = image.resize((CONFIG["spriteSize"], CONFIG["spriteSize"]), Image.Resampling.LANCZOS)
        frames.append(on_background(add_outline(image, radius=2)))
    frames[0].save(PREVIEW_DIR / "model-turntable.gif", save_all=True,
                   append_images=frames[1:], duration=83, loop=0,
                   disposal=2, optimize=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-video", action="store_true")
    args = parser.parse_args()
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    frames = process_frames()
    make_contact_sheet(frames)
    save_gif(frames, PREVIEW_DIR / "good-preview-512.gif", 512, CONFIG["intervalMs"])
    save_gif(frames, PREVIEW_DIR / "good-preview-98.gif", 98, CONFIG["intervalMs"])
    save_gif(frames, PREVIEW_DIR / "good-preview-slow.gif", 512, CONFIG["intervalMs"] * 4)
    make_turntable()
    if not args.skip_video:
        make_video()


if __name__ == "__main__":
    main()
