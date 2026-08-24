#!/usr/bin/env python3
"""Validate the master-v4 clean body and isolated animated arm layers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops
from scipy import ndimage


ROOT = Path(__file__).resolve().parent
CONFIG_NAME = os.environ.get("AGENTS_TRAY_RIG_CONFIG", "clean-plate-config.json")
CONFIG = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
SOURCE = ROOT / CONFIG["sourceDir"]
MASTER = Image.open(ROOT / CONFIG["master"]).convert("RGBA")
BODY = Image.open(SOURCE / CONFIG["bodyFile"]).convert("RGBA")
ARM = Image.open(SOURCE / CONFIG["armFile"]).convert("RGBA")
FRAME_ONE = Image.open(ROOT / CONFIG["renderDir"] / "sprites" / "1.png").convert("RGBA")
REPAIR_MASK = (
    Image.open(ROOT / CONFIG["finalRepairMask"]).convert("RGBA").getchannel("A")
    if CONFIG.get("finalRepairMask") else None
)


def significant_components(image: Image.Image, minimum_size: int = 16) -> list[int]:
    alpha = np.asarray(image.getchannel("A")) >= 16
    labels, count = ndimage.label(alpha)
    sizes = np.bincount(labels.ravel())[1:]
    return sorted((int(size) for size in sizes if size >= minimum_size), reverse=True)


def assert_empty_alpha(image: Image.Image, box: tuple[int, int, int, int], name: str) -> None:
    if image.getchannel("A").crop(box).getbbox() is not None:
        raise ValueError(f"animated arm contains forbidden {name} pixels in {box}")


def main() -> None:
    expected = (int(CONFIG["textureSize"]), int(CONFIG["textureSize"]))
    for name, image in (("master", MASTER), ("body", BODY), ("arm", ARM)):
        if image.size != expected or image.mode != "RGBA":
            raise ValueError(f"{name} must be {expected} RGBA")

    body_components = significant_components(BODY)
    arm_components = significant_components(ARM)
    frame_components = significant_components(FRAME_ONE.resize(expected))
    if len(body_components) != 1:
        raise ValueError(f"clean body has disconnected significant pieces: {body_components}")
    if len(arm_components) != 1:
        raise ValueError(f"animated arm has disconnected significant pieces: {arm_components}")
    if len(frame_components) != 1:
        raise ValueError(f"frame 1 silhouette is disconnected: {frame_components}")

    # The hand occupies the upper-left, but head/collar/chest must remain static.
    assert_empty_alpha(ARM, (640, 80, 1370, 570), "head")
    assert_empty_alpha(ARM, (960, 570, 1370, 1020), "collar/chest")

    bind = Image.alpha_composite(BODY, ARM)
    difference = ImageChops.difference(MASTER, bind)
    if REPAIR_MASK is not None:
        outside = ImageChops.invert(
            REPAIR_MASK.point(lambda value: 255 if value else 0)
        )
        difference = ImageChops.multiply(
            difference, Image.merge("RGBA", (outside,) * 4),
        )
    changed_pixels = sum(1 for pixel in difference.getdata() if max(pixel) > 4)
    if changed_pixels > int(CONFIG["finalChangedPixelLimit"]):
        raise ValueError(f"clean-plate bind changes {changed_pixels} master pixels")

    if BODY.getchannel("A").crop((720, 560, 960, 940)).getbbox() is None:
        raise ValueError("clean body did not restore the hidden shoulder/chest region")
    print(f"{CONFIG.get('previewPrefix', 'master-v4')} clean-plate validation passed")


if __name__ == "__main__":
    main()
