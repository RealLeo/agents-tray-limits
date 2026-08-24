#!/usr/bin/env python3
"""Flatten accepted v15 pixels into stable layers for the v16 Blender rig."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
LEGACY_RENDERER = PROJECT / "tools" / "render_vault_boy_animation.py"
LEGACY_CONFIG = PROJECT / "tools" / "animation-rig" / "v15" / "rig.json"


def load_renderer():
    spec = importlib.util.spec_from_file_location("legacy_v15_renderer", LEGACY_RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the v15 renderer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canvas(module) -> Image.Image:
    size = 512 * module.SUPERSAMPLE
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def downsample(image: Image.Image) -> Image.Image:
    return image.resize((512, 512), Image.Resampling.LANCZOS)


def render_body(module, rig) -> Image.Image:
    image = canvas(module)
    root = (256, 327)
    left_hip, right_hip = (225, 326), (287, 326)
    rig.paste(image, "legA", left_hip, scale=0.61, pivot=(0.5, 0.04), angle=-4)
    rig.paste(image, "legB", right_hip, scale=0.62, pivot=(0.5, 0.04), angle=4, mirror=True)
    left_ankle = rig.arm_endpoint(left_hip, -4, 136)
    right_ankle = rig.arm_endpoint(right_hip, 4, 136)
    rig.paste(image, "shoeA", left_ankle, scale=0.62, pivot=(0.48, 0.46), angle=-1.8)
    rig.paste(image, "shoeB", right_ankle, scale=0.64, pivot=(0.52, 0.46), angle=1.8)
    rig.paste(image, "torso", root, scale=0.61, pivot=(0.5, 0.92))
    rig.paste(image, "headGood", (256, 153), scale=0.67, pivot=(0.5, 0.90))
    return downsample(image)


def render_raise_arm(module, rig) -> Image.Image:
    image = canvas(module)
    rig._limb(image, (190, 183), -90, -90, "thumb", mirror=False)
    return downsample(image)


def render_rest_arm(module, rig) -> Image.Image:
    image = canvas(module)
    rig._limb(image, (322, 183), 20, 38, "handDown", mirror=True)
    return downsample(image)


def main() -> None:
    module = load_renderer()
    rig = module.Rig(LEGACY_CONFIG)
    sources = ROOT / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    layers = {
        "good-body.png": render_body(module, rig),
        "good-raise-arm.png": render_raise_arm(module, rig),
        "good-rest-arm.png": render_rest_arm(module, rig),
    }
    for name, image in layers.items():
        if image.size != (512, 512) or image.mode != "RGBA" or image.getchannel("A").getbbox() is None:
            raise ValueError(f"invalid generated source layer: {name}")
        destination = sources / name
        image.save(destination, optimize=True)
        print(f"Prepared {destination}")


if __name__ == "__main__":
    main()
