#!/usr/bin/env python3
"""Build registered body/arm layers with a generated clean-plate donor."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw
from scipy import ndimage


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "clean-plate-config.json").read_text(encoding="utf-8"))
MASTER_PATH = ROOT / CONFIG["master"]
DONOR_PATH = ROOT / CONFIG["donor"]
DESTINATION = ROOT / "sources" / "master-v4"


def scaled_polygon(points: list[list[int]], factor: int) -> list[tuple[int, int]]:
    return [(x * factor, y * factor) for x, y in points]


def extract_donor_foreground(donor: Image.Image) -> Image.Image:
    """Remove the baked checkerboard while retaining enclosed light artwork."""
    rgb = np.asarray(donor.convert("RGB"), dtype=np.uint8)
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    neutral_bright = (minimum >= 220) & ((maximum - minimum) <= 18)
    labels, _count = ndimage.label(neutral_bright)
    border_labels = np.unique(np.concatenate((
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    )))
    background = np.isin(labels, border_labels) & neutral_bright
    foreground = ~background
    # Close tiny checker remnants without growing the silhouette materially.
    foreground = ndimage.binary_closing(foreground, iterations=1)
    foreground = ndimage.binary_fill_holes(foreground)
    rgba = donor.convert("RGBA")
    rgba.putalpha(Image.fromarray((foreground * 255).astype(np.uint8), mode="L"))
    return rgba


def register_donor(donor: Image.Image, size: tuple[int, int]) -> Image.Image:
    transform = CONFIG["donorTransform"]
    scale_x = float(transform["scaleX"])
    scale_y = float(transform["scaleY"])
    translate_x = float(transform["translateX"])
    translate_y = float(transform["translateY"])
    inverse = (
        1.0 / scale_x, 0.0, -translate_x / scale_x,
        0.0, 1.0 / scale_y, -translate_y / scale_y,
    )
    return donor.transform(
        size,
        Image.Transform.AFFINE,
        inverse,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def main() -> None:
    master = Image.open(MASTER_PATH).convert("RGBA")
    expected = (int(CONFIG["textureSize"]), int(CONFIG["textureSize"]))
    if master.size != expected:
        raise ValueError(f"master must be {expected}, found {master.size}")
    factor = expected[0] // int(CONFIG["canvas"][0])

    donor_source = Image.open(DONOR_PATH).convert("RGB")
    donor = register_donor(extract_donor_foreground(donor_source), expected)

    arm_mask = Image.new("L", expected, 0)
    ImageDraw.Draw(arm_mask).polygon(
        scaled_polygon(CONFIG["arm"]["polygon"], factor), fill=255,
    )
    arm_mask_draw = ImageDraw.Draw(arm_mask)
    for left, top, right, bottom in CONFIG["arm"].get("extraRects", []):
        arm_mask_draw.rectangle(
            (left * factor, top * factor, right * factor, bottom * factor), fill=255,
        )
    clean_plate_mask = Image.new("L", expected, 0)
    ImageDraw.Draw(clean_plate_mask).polygon(
        scaled_polygon(CONFIG["arm"]["cleanPlatePolygon"], factor), fill=255,
    )

    master_alpha = master.getchannel("A")
    arm_alpha = ImageChops.multiply(master_alpha, arm_mask)
    arm = master.copy()
    arm.putalpha(arm_alpha)

    body = master.copy()
    body_alpha = ImageChops.subtract(master_alpha, arm_alpha)
    body.putalpha(body_alpha)

    # The generated donor is permitted only where the original arm was removed.
    fill_window = ImageChops.multiply(clean_plate_mask, arm_mask)
    missing_body = ImageChops.multiply(fill_window, ImageChops.invert(body_alpha))
    donor_alpha = ImageChops.multiply(donor.getchannel("A"), missing_body)
    donor_patch = donor.copy()
    donor_patch.putalpha(donor_alpha)
    body = Image.alpha_composite(body, donor_patch)

    DESTINATION.mkdir(parents=True, exist_ok=True)
    outputs = {
        "good-reference-master-v3.png": master,
        "good-clean-body-master-v4.png": body,
        "good-raise-arm-master-v4.png": arm,
        "good-raise-arm-mask-master-v4.png": Image.merge("RGBA", (arm_mask,) * 4),
        "good-clean-plate-mask-master-v4.png": Image.merge(
            "RGBA", (clean_plate_mask,) * 4,
        ),
        "good-clean-plate-donor-registered-v4.png": donor,
    }
    for name, image in outputs.items():
        path = DESTINATION / name
        image.save(path, optimize=True)
        print(f"Prepared {path}")

    bind = Image.alpha_composite(body, arm)
    difference = ImageChops.difference(master, bind)
    changed = difference.getbbox()
    changed_pixels = sum(1 for pixel in difference.getdata() if max(pixel) > 4)
    if changed_pixels > 128:
        raise ValueError(
            f"registered bind changes {changed_pixels} master pixels in {changed}"
        )
    print("Clean-plate bind remains registered to the master")


if __name__ == "__main__":
    main()
