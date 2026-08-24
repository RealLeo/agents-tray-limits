#!/usr/bin/env python3
"""Export evaluated Blender arm meshes to deterministic screen-space JSON."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
config_path = Path(os.environ["AGENTS_TRAY_RIG_CONFIG"])
if not config_path.is_absolute():
    config_path = ROOT / config_path
CONFIG = json.loads(config_path.read_text(encoding="utf-8"))


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def trajectory_target(frame: int) -> Vector:
    trajectory = sorted(CONFIG["arm"]["trajectory"], key=lambda item: item["frame"])
    if frame <= trajectory[0]["frame"]:
        return Vector(trajectory[0]["target"])
    if frame >= trajectory[-1]["frame"]:
        return Vector(trajectory[-1]["target"])
    for left, right in zip(trajectory, trajectory[1:]):
        if left["frame"] <= frame <= right["frame"]:
            amount = smoothstep(
                (frame - left["frame"]) / (right["frame"] - left["frame"])
            )
            return Vector(left["target"]).lerp(Vector(right["target"]), amount)
    raise ValueError(f"frame {frame} is outside the trajectory")


def rigid_positions(source: list[list[float]]) -> list[list[list[float]]]:
    shoulder = Vector(CONFIG["arm"]["shoulder"])
    bind_vector = Vector(CONFIG["arm"]["wrist"]) - shoulder
    bind_angle = math.atan2(bind_vector.y, bind_vector.x)
    result = []
    for frame in range(1, int(CONFIG["frames"]) + 1):
        desired = trajectory_target(frame) - shoulder
        angle = math.atan2(desired.y, desired.x) - bind_angle
        cosine = math.cos(angle)
        sine = math.sin(angle)
        points = []
        for value in source:
            point = Vector(value) - shoulder
            points.append([
                round(shoulder.x + point.x * cosine - point.y * sine, 6),
                round(shoulder.y + point.x * sine + point.y * cosine, 6),
            ])
        result.append(points)
    return result


def source_vertices() -> list[list[float]]:
    left, top, right, bottom = CONFIG["arm"]["bbox"]
    step = int(CONFIG["gridStep"])
    xs = list(range(left, right, step))
    ys = list(range(top, bottom, step))
    if xs[-1] != right:
        xs.append(right)
    if ys[-1] != bottom:
        ys.append(bottom)
    return [[float(x), float(y)] for y in ys for x in xs]


def main() -> None:
    scene = bpy.context.scene
    camera = scene.camera
    arm = bpy.data.objects["VaultBoyMasterArm"]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    frames: list[list[list[float]]] = []
    faces: list[list[int]] | None = None
    for frame in range(1, int(CONFIG["frames"]) + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        evaluated = arm.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        if faces is None:
            faces = [list(polygon.vertices) for polygon in mesh.polygons]
        points = []
        for vertex in mesh.vertices:
            world = evaluated.matrix_world @ vertex.co
            projected = world_to_camera_view(scene, camera, world)
            points.append([
                round(projected.x * 512.0, 6),
                round((1.0 - projected.y) * 512.0, 6),
            ])
        frames.append(points)
        evaluated.to_mesh_clear()

    source = source_vertices()
    if CONFIG["arm"].get("weightMode") == "rigid":
        frames = rigid_positions(source)
    final_correction = [
        Vector(source_point) - Vector(final_point)
        for source_point, final_point in zip(source, frames[-1])
    ]
    corrected_frames = []
    denominator = max(1, len(frames) - 1)
    for index, points in enumerate(frames):
        progress = index / denominator
        amount = progress * progress * (3.0 - 2.0 * progress)
        corrected_frames.append([
            [round(point[0] + correction.x * amount, 6),
             round(point[1] + correction.y * amount, 6)]
            for point, correction in zip(points, final_correction)
        ])

    destination = Path(CONFIG["renderDir"])
    if not destination.is_absolute():
        # Config paths were authored relative to the v16 renderer directory.
        destination = ROOT.parent / "v16" / destination
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = {
        "canvas": CONFIG["canvas"],
        "frames": CONFIG["frames"],
        "intervalMs": CONFIG["intervalMs"],
        "source": source,
        "faces": faces,
        "positions": corrected_frames,
    }
    (destination / "mesh-frames.json").write_text(
        json.dumps(report, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print({"mesh": str(destination / "mesh-frames.json"), "frames": len(frames)})


if __name__ == "__main__":
    main()
