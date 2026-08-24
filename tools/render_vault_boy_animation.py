#!/usr/bin/env python3
"""Render deterministic, layered character animations for the Fallout 2 theme.

The ImageGen-produced source atlas is used only as a set of reusable cutout
parts.  Every runtime frame is composed from the same pixels and deterministic
joint transforms, so anatomy and line work cannot drift between frames.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RIG = ROOT / "tools" / "animation-rig" / "v15" / "rig.json"
STATUSES = ("good", "worried", "critical", "dead")
SUPERSAMPLE = max(1, int(os.environ.get("AGENTS_TRAY_RIG_SUPERSAMPLE", "4")))
ALPHA_THRESHOLD = 18


def remove_edge_background(image: Image.Image) -> Image.Image:
    """Remove an edge-connected light neutral checkerboard from an RGB source."""
    rgba = image.convert("RGBA")
    if rgba.getchannel("A").getextrema()[0] < 255:
        return rgba

    width, height = rgba.size
    pixels = rgba.load()
    seen = bytearray(width * height)
    queue: list[tuple[int, int]] = []
    cursor = 0

    def candidate(x: int, y: int) -> bool:
        red, green, blue, _alpha = pixels[x, y]
        return min(red, green, blue) >= 185 and max(red, green, blue) - min(red, green, blue) <= 22

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if seen[index] or not candidate(x, y):
            return
        seen[index] = 1
        queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while cursor < len(queue):
        x, y = queue[cursor]
        cursor += 1
        if x:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    output = rgba.copy()
    out = output.load()
    for y in range(height):
        offset = y * width
        for x in range(width):
            if seen[offset + x]:
                red, green, blue, _alpha = out[x, y]
                out[x, y] = (red, green, blue, 0)
    return output


def trim(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A").point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0)
    box = alpha.getbbox()
    if box is None:
        raise ValueError("rig part has no visible pixels")
    return image.crop(box)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def keyframes(value: float, points: tuple[tuple[float, float], ...]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    for (left_time, left_value), (right_time, right_value) in zip(points, points[1:]):
        if value <= right_time:
            span = right_time - left_time
            amount = ease((value - left_time) / span) if span else 1.0
            return left_value + (right_value - left_value) * amount
    return points[-1][1]


def rotate_vector(vector: tuple[float, float], angle: float) -> tuple[float, float]:
    radians = math.radians(angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    x, y = vector
    return x * cosine - y * sine, x * sine + y * cosine


def add(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    return left[0] + right[0], left[1] + right[1]


@dataclass(frozen=True)
class Pose:
    root: tuple[float, float]
    torso_angle: float
    head_angle: float
    left_upper: float
    left_lower: float
    right_upper: float
    right_lower: float
    left_leg: float
    right_leg: float
    left_hand: str
    right_hand: str


class Rig:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.root = config_path.parent
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        if self.config.get("version") != 1:
            raise ValueError("unsupported rig version")
        self.width, self.height = self.config["canvas"]
        self.frame_count = int(self.config["frameCount"])
        self.interval_ms = int(self.config["intervalMs"])
        self.baseline = int(self.config["baseline"])
        self.sources = {
            name: Image.open(self.root / relative).convert("RGBA")
            for name, relative in self.config["sources"].items()
        }
        self.parts: dict[str, Image.Image] = {}
        self._transform_cache: dict[
            tuple[str, float, tuple[float, float], float, bool],
            tuple[Image.Image, tuple[int, int]],
        ] = {}
        for name, spec in self.config["parts"].items():
            x, y, width, height = spec["box"]
            source = self.sources[spec["source"]].crop((x, y, x + width, y + height))
            if spec.get("cleanBackground"):
                source = remove_edge_background(source)
            self.parts[name] = trim(source)

    def _sprite_on_pivot(
        self,
        part: str,
        sprite: Image.Image,
        scale: float,
        pivot: tuple[float, float],
        angle: float,
        mirror: bool = False,
    ) -> tuple[Image.Image, tuple[int, int]]:
        cache_key = (part, scale, pivot, round(angle, 5), mirror)
        cached = self._transform_cache.get(cache_key)
        if cached is not None:
            return cached

        if mirror:
            sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            pivot = (1.0 - pivot[0], pivot[1])

        scaled_size = (
            max(1, round(sprite.width * scale * SUPERSAMPLE)),
            max(1, round(sprite.height * scale * SUPERSAMPLE)),
        )
        scaled = sprite.resize(scaled_size, Image.Resampling.LANCZOS)
        pivot_px = (round(pivot[0] * scaled.width), round(pivot[1] * scaled.height))
        radius = int(math.ceil(math.hypot(scaled.width, scaled.height))) + 12
        stage = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
        origin = (radius - pivot_px[0], radius - pivot_px[1])
        stage.alpha_composite(scaled, origin)
        rotated = stage.rotate(angle, Image.Resampling.BICUBIC, expand=False, center=(radius, radius))
        result = rotated, (radius, radius)
        self._transform_cache[cache_key] = result
        return result

    def paste(
        self,
        canvas: Image.Image,
        part: str,
        world: tuple[float, float],
        *,
        scale: float,
        pivot: tuple[float, float],
        angle: float = 0.0,
        mirror: bool = False,
    ) -> None:
        sprite, sprite_pivot = self._sprite_on_pivot(
            part, self.parts[part], scale, pivot, angle, mirror
        )
        world_px = (round(world[0] * SUPERSAMPLE), round(world[1] * SUPERSAMPLE))
        destination = (world_px[0] - sprite_pivot[0], world_px[1] - sprite_pivot[1])
        canvas.alpha_composite(sprite, destination)

    @staticmethod
    def arm_endpoint(
        shoulder: tuple[float, float], angle: float, length: float
    ) -> tuple[float, float]:
        radians = math.radians(angle)
        return shoulder[0] + math.sin(radians) * length, shoulder[1] + math.cos(radians) * length

    def pose(self, status: str, progress: float) -> Pose:
        if status == "good":
            path = progress * 0.92 + ease(progress) * 0.08
            moving = -90.0 * path
            lower = moving
            moving_hand = "handRelaxed" if progress < 0.62 else "thumb"
            return Pose((256, 327), 0, 0, moving, lower, -20, -38, -4, 4,
                        moving_hand, "handDown")
        if status == "worried":
            amount = ease(progress)
            return Pose(
                (256, 327),
                0,
                7 * amount,
                8 + 45 * amount,
                5 + 68 * amount,
                -8 - 45 * amount,
                -5 - 68 * amount,
                -6,
                6,
                "handHorizontal",
                "handHorizontal",
            )
        if status == "critical":
            amount = ease(progress)
            limb_amount = progress * 0.75 + amount * 0.25
            return Pose(
                (256 + 8 * amount, 327),
                -11 * amount,
                -5 * amount,
                3 - 12 * limb_amount,
                4 - 8 * limb_amount,
                -8 - 54 * limb_amount,
                -5 - 70 * limb_amount,
                -8 - 7 * amount,
                7 + 5 * amount,
                "handDown",
                "handHorizontal",
            )
        if status == "dead":
            amount = ease(progress)
            return Pose(
                (256, 322 + 62 * amount),
                -13 * amount,
                7 * amount,
                4 - 18 * amount,
                2 - 14 * amount,
                -4 + 18 * amount,
                -2 + 14 * amount,
                -4 - 70 * amount,
                4 + 70 * amount,
                "handDown",
                "handDown",
            )
        raise ValueError(f"unknown status: {status}")

    def _limb(
        self,
        canvas: Image.Image,
        shoulder: tuple[float, float],
        upper_angle: float,
        lower_angle: float,
        hand: str,
        *,
        mirror: bool,
    ) -> None:
        upper_scale = 0.48
        lower_scale = 0.42
        upper_length = 76.0
        lower_length = 66.0
        self.paste(canvas, "armA", shoulder, scale=upper_scale, pivot=(0.5, 0.06),
                   angle=upper_angle, mirror=mirror)
        elbow = self.arm_endpoint(shoulder, upper_angle, upper_length)
        if hand == "thumb":
            self.paste(canvas, "armB", elbow, scale=lower_scale, pivot=(0.5, 0.06),
                       angle=lower_angle, mirror=mirror)
            wrist = self.arm_endpoint(elbow, lower_angle, lower_length)
            self.paste(canvas, "thumb", wrist, scale=0.42, pivot=(0.82, 0.82), angle=0)
        elif hand == "handRelaxed":
            self.paste(canvas, "armB", elbow, scale=lower_scale, pivot=(0.5, 0.06),
                       angle=lower_angle, mirror=mirror)
            wrist = self.arm_endpoint(elbow, lower_angle, lower_length)
            self.paste(canvas, hand, wrist, scale=0.44, pivot=(0.50, 0.08),
                       angle=lower_angle, mirror=mirror)
        elif hand == "handHorizontal":
            natural_angle = 90 if mirror else -90
            self.paste(canvas, hand, elbow, scale=0.40, pivot=(0.93, 0.52),
                       angle=lower_angle - natural_angle, mirror=mirror)
        elif hand == "handDown":
            natural_angle = -18 if mirror else 18
            self.paste(canvas, hand, elbow, scale=0.42, pivot=(0.18, 0.10),
                       angle=lower_angle - natural_angle, mirror=mirror)
        else:
            raise ValueError(f"unknown hand: {hand}")

    def render(self, status: str, progress: float) -> Image.Image:
        pose = self.pose(status, progress)
        canvas = Image.new(
            "RGBA", (self.width * SUPERSAMPLE, self.height * SUPERSAMPLE), (0, 0, 0, 0)
        )
        root = pose.root
        torso_scale = 0.61
        torso_pivot = (0.5, 0.92)

        left_hip = add(root, rotate_vector((-31, -1), pose.torso_angle))
        right_hip = add(root, rotate_vector((31, -1), pose.torso_angle))
        left_leg_length = 136
        right_leg_length = 136
        self.paste(canvas, "legA", left_hip, scale=0.61, pivot=(0.5, 0.04),
                   angle=pose.left_leg)
        self.paste(canvas, "legB", right_hip, scale=0.62, pivot=(0.5, 0.04),
                   angle=pose.right_leg, mirror=True)
        left_ankle = self.arm_endpoint(left_hip, pose.left_leg, left_leg_length)
        right_ankle = self.arm_endpoint(right_hip, pose.right_leg, right_leg_length)
        self.paste(canvas, "shoeA", left_ankle, scale=0.62, pivot=(0.48, 0.46),
                   angle=pose.left_leg * 0.45)
        self.paste(canvas, "shoeB", right_ankle, scale=0.64, pivot=(0.52, 0.46),
                   angle=pose.right_leg * 0.45)

        left_shoulder = add(root, rotate_vector((-66, -144), pose.torso_angle))
        right_shoulder = add(root, rotate_vector((66, -144), pose.torso_angle))
        arms_front = status in {"worried", "critical", "dead"}
        if not arms_front:
            self._limb(canvas, left_shoulder, pose.left_upper, pose.left_lower,
                       pose.left_hand, mirror=False)
            self._limb(canvas, right_shoulder, pose.right_upper, pose.right_lower,
                       pose.right_hand, mirror=True)

        self.paste(canvas, "torso", root, scale=torso_scale, pivot=torso_pivot,
                   angle=pose.torso_angle)

        if arms_front:
            self._limb(canvas, left_shoulder, pose.left_upper, pose.left_lower,
                       pose.left_hand, mirror=False)
            self._limb(canvas, right_shoulder, pose.right_upper, pose.right_lower,
                       pose.right_hand, mirror=True)

        head_name = {
            "good": "headGood",
            "worried": "headWorried",
            "critical": "headCritical",
            "dead": "headDead",
        }[status]
        if status == "dead" and progress < 0.72:
            head_name = "headCritical"
        neck = add(root, rotate_vector((0, -174), pose.torso_angle))
        self.paste(canvas, head_name, neck, scale=0.67, pivot=(0.5, 0.90),
                   angle=pose.torso_angle + pose.head_angle)

        return canvas.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def joint_points(self, status: str, progress: float) -> tuple[tuple[float, float], ...]:
        pose = self.pose(status, progress)
        root = pose.root
        left_shoulder = add(root, rotate_vector((-66, -144), pose.torso_angle))
        right_shoulder = add(root, rotate_vector((66, -144), pose.torso_angle))
        left_elbow = self.arm_endpoint(left_shoulder, pose.left_upper, 76)
        right_elbow = self.arm_endpoint(right_shoulder, pose.right_upper, 76)
        left_wrist = self.arm_endpoint(left_elbow, pose.left_lower, 66)
        right_wrist = self.arm_endpoint(right_elbow, pose.right_lower, 66)
        left_hip = add(root, rotate_vector((-31, -1), pose.torso_angle))
        right_hip = add(root, rotate_vector((31, -1), pose.torso_angle))
        left_ankle = self.arm_endpoint(left_hip, pose.left_leg, 136)
        right_ankle = self.arm_endpoint(right_hip, pose.right_leg, 136)
        neck = add(root, rotate_vector((0, -174), pose.torso_angle))
        return (
            root, neck, left_shoulder, right_shoulder, left_elbow, right_elbow,
            left_wrist, right_wrist, left_hip, right_hip, left_ankle, right_ankle,
        )


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    box = image.getchannel("A").point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0).getbbox()
    if box is None:
        raise ValueError("rendered frame is empty")
    return box


def validate_frames(rig: Rig, rendered: dict[str, list[Image.Image]]) -> dict[str, object]:
    report: dict[str, object] = {
        "frameCount": rig.frame_count,
        "intervalMs": rig.interval_ms,
        "durationMs": (rig.frame_count - 1) * rig.interval_ms,
        "canvas": [rig.width, rig.height],
        "baseline": rig.baseline,
        "statuses": {},
    }
    for status, frames in rendered.items():
        if len(frames) != rig.frame_count:
            raise ValueError(f"{status}: expected {rig.frame_count} frames")
        boxes = [alpha_bbox(frame) for frame in frames]
        if any(frame.size != (rig.width, rig.height) or frame.mode != "RGBA" for frame in frames):
            raise ValueError(f"{status}: frames must be {rig.width}x{rig.height} RGBA")
        for frame in frames:
            alpha = frame.getchannel("A")
            corners = (alpha.getpixel((0, 0)), alpha.getpixel((rig.width - 1, 0)),
                       alpha.getpixel((0, rig.height - 1)), alpha.getpixel((rig.width - 1, rig.height - 1)))
            if any(corners):
                raise ValueError(f"{status}: frame has a non-transparent corner")
        center_steps = []
        previous = None
        for left, top, right, bottom in boxes:
            center = ((left + right) / 2, (top + bottom) / 2)
            if previous is not None:
                center_steps.append(round(math.dist(center, previous), 3))
            previous = center
        joint_frames = [
            rig.joint_points(status, index / (rig.frame_count - 1))
            for index in range(rig.frame_count)
        ]
        joint_steps = [
            max(math.dist(previous, current) for previous, current in zip(left, right))
            for left, right in zip(joint_frames, joint_frames[1:])
        ]
        max_joint_step_screen = max(joint_steps, default=0) * 98 / rig.width
        max_bottom = max(box[3] for box in boxes)
        if max_joint_step_screen > 3.0 + 1e-6:
            raise ValueError(
                f"{status}: joint step {max_joint_step_screen:.3f}px exceeds 3px at menu size"
            )
        if max_bottom > rig.baseline:
            raise ValueError(f"{status}: artwork crosses baseline {rig.baseline}: {max_bottom}")
        report["statuses"][status] = {
            "boxes": [list(box) for box in boxes],
            "maxCenterStep": max(center_steps, default=0),
            "maxJointStepScreenPx": round(max_joint_step_screen, 3),
            "maxBottom": max_bottom,
        }
    return report


def render_all(
    rig: Rig, statuses: tuple[str, ...] = STATUSES,
) -> dict[str, list[Image.Image]]:
    rendered: dict[str, list[Image.Image]] = {}
    for status in statuses:
        rendered[status] = [
            rig.render(status, index / (rig.frame_count - 1))
            for index in range(rig.frame_count)
        ]
    return rendered


def save_frames(rendered: dict[str, list[Image.Image]], output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    for status, frames in rendered.items():
        destination = output / status
        destination.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames, start=1):
            frame.save(destination / f"{index}.png", optimize=True)


def verify_against(rendered: dict[str, list[Image.Image]], expected: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="agents-tray-rig-") as temporary:
        actual = Path(temporary)
        save_frames(rendered, actual)
        for status, frames in rendered.items():
            expected_paths = sorted(
                (expected / status).glob("*.png"),
                key=lambda path: int(path.stem),
            )
            if len(expected_paths) != len(frames):
                raise ValueError(f"{status}: installed frame count does not match rig")
            for index, path in enumerate(expected_paths):
                expected_image = Image.open(path).convert("RGBA")
                if ImageChops.difference(expected_image, frames[index]).getbbox() is not None:
                    raise ValueError(f"{status}/{index + 1}.png differs from deterministic render")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rig", type=Path, default=DEFAULT_RIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--statuses", nargs="+", choices=STATUSES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.output and not args.verify:
        raise SystemExit("provide --output or --verify")
    rig = Rig(args.rig.resolve())
    statuses = tuple(args.statuses) if args.statuses else STATUSES
    rendered = render_all(rig, statuses)
    report = validate_frames(rig, rendered)
    if args.output:
        save_frames(rendered, args.output.resolve())
    if args.verify:
        verify_against(rendered, args.verify.resolve())
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
