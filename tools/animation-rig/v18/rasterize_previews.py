#!/usr/bin/env python3
"""Rasterize Blender-evaluated UV meshes and build review artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source" / "master"
RENDER = ROOT / "render"
PREVIEWS = ROOT / "previews"
SCALE = 4.0
FRAME_COUNT = 32
INTERVAL_MS = 28


STATES = {
    "worried": {
        "body": "worried-clean-body-v1.png",
        "master": "worried-master-v1.png",
        "back": "worried-arm-back-v1.png",
        "front": "worried-arm-front-v1.png",
    },
    "critical": {
        "body": "critical-clean-body-v1.png",
        "master": "critical-master-v1.png",
        "back": "critical-arm-back-v1.png",
        "front": "critical-arm-front-v1.png",
    },
}


def alpha_over(base: Image.Image, overlay: Image.Image) -> Image.Image:
    return Image.alpha_composite(base.convert("RGBA"), overlay.convert("RGBA"))


def raster_triangle(
    output: np.ndarray, source: np.ndarray,
    destination_points: np.ndarray, source_points: np.ndarray,
) -> None:
    minimum = np.floor(destination_points.min(axis=0)).astype(int)
    maximum = np.ceil(destination_points.max(axis=0)).astype(int)
    x0, y0 = np.maximum(minimum, 0)
    x1, y1 = np.minimum(maximum, np.array([output.shape[1] - 1, output.shape[0] - 1]))
    if x1 < x0 or y1 < y0:
        return
    x_grid, y_grid = np.meshgrid(
        np.arange(x0, x1 + 1, dtype=np.float32),
        np.arange(y0, y1 + 1, dtype=np.float32),
    )
    a, b, c = destination_points.astype(np.float32)
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(float(denominator)) < 1e-5:
        return
    wa = ((b[1] - c[1]) * (x_grid - c[0]) + (c[0] - b[0]) * (y_grid - c[1])) / denominator
    wb = ((c[1] - a[1]) * (x_grid - c[0]) + (a[0] - c[0]) * (y_grid - c[1])) / denominator
    wc = 1.0 - wa - wb
    inside = (wa >= -0.001) & (wb >= -0.001) & (wc >= -0.001)
    if not inside.any():
        return
    source_x = wa * source_points[0, 0] + wb * source_points[1, 0] + wc * source_points[2, 0]
    source_y = wa * source_points[0, 1] + wb * source_points[1, 1] + wc * source_points[2, 1]
    sx = np.clip(np.rint(source_x).astype(int), 0, source.shape[1] - 1)
    sy = np.clip(np.rint(source_y).astype(int), 0, source.shape[0] - 1)
    sampled = source[sy, sx]
    region = output[y0:y1 + 1, x0:x1 + 1]
    alpha = sampled[..., 3:4].astype(np.float32) / 255.0
    selected_alpha = alpha[inside]
    region_rgb = region[..., :3][inside].astype(np.float32)
    sampled_rgb = sampled[..., :3][inside].astype(np.float32)
    region_a = region[..., 3:4][inside].astype(np.float32) / 255.0
    out_a = selected_alpha + region_a * (1.0 - selected_alpha)
    numerator = sampled_rgb * selected_alpha + region_rgb * region_a * (1.0 - selected_alpha)
    out_rgb = np.divide(numerator, np.maximum(out_a, 1e-6))
    region[..., :3][inside] = np.clip(out_rgb, 0, 255).astype(np.uint8)
    region[..., 3:4][inside] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)


def raster_mesh(layer_path: Path, mesh: dict, frame_index: int) -> Image.Image:
    texture = np.asarray(Image.open(layer_path).convert("RGBA"), dtype=np.uint8)
    output = np.zeros_like(texture)
    source = np.asarray(mesh["source"], dtype=np.float32) * SCALE
    target = np.asarray(mesh["positions"][frame_index], dtype=np.float32) * SCALE
    for face in mesh["faces"]:
        first, second, third, fourth = face
        for triangle in ((first, second, third), (first, third, fourth)):
            indices = np.asarray(triangle)
            raster_triangle(output, texture, target[indices], source[indices])
    return Image.fromarray(output, "RGBA")


def load_mesh(status: str, layer: str) -> dict:
    path = RENDER / f"{status}-{layer}" / "mesh-frames.json"
    return json.loads(path.read_text(encoding="utf-8"))


def make_contact_sheet(frames: list[Image.Image], destination: Path) -> None:
    tile = 192
    sheet = Image.new("RGBA", (8 * tile, 4 * tile), (36, 36, 36, 255))
    for index, frame in enumerate(frames):
        preview = frame.resize((tile, tile), Image.Resampling.LANCZOS)
        sheet.alpha_composite(preview, ((index % 8) * tile, (index // 8) * tile))
    sheet.save(destination, optimize=True)


def make_rig_diagnostic(status: str, destination: Path) -> None:
    master = Image.open(SOURCE / STATES[status]["master"]).convert("RGBA").resize((512, 512))
    canvas = Image.new("RGBA", (512, 512), (38, 38, 38, 255))
    canvas.alpha_composite(master)
    draw = ImageDraw.Draw(canvas)
    colors = {"back": "#4fd1ff", "front": "#ff5ad9"}
    for layer in ("back", "front"):
        config = json.loads((ROOT / "configs" / f"{status}-{layer}.json").read_text())
        arm = config["arm"]
        points = [tuple(arm[name]) for name in ("shoulder", "elbow", "wrist", "hand")]
        draw.line(points, fill=colors[layer], width=4, joint="curve")
        for point in points:
            draw.ellipse((point[0] - 5, point[1] - 5, point[0] + 5, point[1] + 5), fill=colors[layer])
    canvas.save(destination, optimize=True)


def make_weight_diagnostic(status: str, destination: Path) -> None:
    master = Image.open(SOURCE / STATES[status]["master"]).convert("RGBA").resize((512, 512))
    canvas = Image.new("RGBA", (512, 512), (38, 38, 38, 255))
    faded = master.copy()
    faded.putalpha(faded.getchannel("A").point(lambda value: round(value * 0.3)))
    canvas.alpha_composite(faded)
    colors = {"back": (79, 209, 255), "front": (255, 90, 217)}
    for layer in ("back", "front"):
        arm = Image.open(SOURCE / STATES[status][layer]).convert("RGBA").resize((512, 512))
        tint = Image.new("RGBA", arm.size, (*colors[layer], 0))
        tint.putalpha(arm.getchannel("A"))
        canvas.alpha_composite(tint)
    canvas.save(destination, optimize=True)


def render_state(status: str, start: int, end: int) -> None:
    config = STATES[status]
    body = Image.open(SOURCE / config["body"]).convert("RGBA")
    back_mesh = load_mesh(status, "back")
    front_mesh = load_mesh(status, "front")
    destination = RENDER / status / "sprites"
    destination.mkdir(parents=True, exist_ok=True)
    for index in range(start - 1, end):
        back = raster_mesh(SOURCE / config["back"], back_mesh, index)
        front = raster_mesh(SOURCE / config["front"], front_mesh, index)
        full = alpha_over(alpha_over(body, back), front)
        sprite = full.resize((512, 512), Image.Resampling.LANCZOS)
        sprite.save(destination / f"{index + 1}.png", optimize=True)

    paths = [destination / f"{index}.png" for index in range(1, FRAME_COUNT + 1)]
    if not all(path.is_file() for path in paths):
        return
    frames = [Image.open(path).convert("RGBA") for path in paths]

    preview_dir = PREVIEWS / status
    preview_dir.mkdir(parents=True, exist_ok=True)
    make_contact_sheet(frames, preview_dir / f"{status}-contact-sheet.png")
    make_rig_diagnostic(status, preview_dir / f"{status}-rig.png")
    make_weight_diagnostic(status, preview_dir / f"{status}-weights.png")
    frames[0].save(preview_dir / f"{status}-frame-01.png", optimize=True)
    frames[-1].save(preview_dir / f"{status}-frame-32.png", optimize=True)
    frames[0].save(
        preview_dir / f"{status}-preview-512.gif", save_all=True,
        append_images=frames[1:], duration=INTERVAL_MS, loop=0, disposal=2,
    )
    small = [frame.resize((98, 98), Image.Resampling.LANCZOS) for frame in frames]
    small[0].save(
        preview_dir / f"{status}-preview-98.gif", save_all=True,
        append_images=small[1:], duration=INTERVAL_MS, loop=0, disposal=2,
    )
    frames[0].save(
        preview_dir / f"{status}-preview-slow.gif", save_all=True,
        append_images=frames[1:], duration=112, loop=0, disposal=2,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=tuple(STATES), required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=FRAME_COUNT)
    arguments = parser.parse_args()
    if not 1 <= arguments.start <= arguments.end <= FRAME_COUNT:
        parser.error("frame range must be inside 1..32")
    render_state(arguments.status, arguments.start, arguments.end)


if __name__ == "__main__":
    main()
