#!/usr/bin/env python3
"""Prepare deterministic v6 shoulder layers from the accepted v4 artwork."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from scipy import ndimage


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources" / "master-v4"
DESTINATION = ROOT / "sources" / "master-v6"
SCALE = 4
SIZE = (2048, 2048)


def polygon_mask(points: list[tuple[int, int]], blur: float = 0.0) -> Image.Image:
    mask = Image.new("L", SIZE, 0)
    ImageDraw.Draw(mask).polygon(
        [(x * SCALE, y * SCALE) for x, y in points], fill=255,
    )
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur * SCALE))
    return mask


def assert_unchanged_outside(
    before: Image.Image, after: Image.Image, support: Image.Image, name: str,
) -> None:
    outside = ImageChops.invert(support.point(lambda value: 255 if value else 0))
    outside_rgba = Image.merge("RGBA", (outside,) * 4)
    difference = ImageChops.multiply(
        ImageChops.difference(before, after), outside_rgba,
    )
    if difference.getbbox() is not None:
        maximum = max(channel[1] for channel in difference.getextrema())
        raise ValueError(f"{name} changed outside the repair support by {maximum}")


def repair_body(body: Image.Image) -> tuple[Image.Image, Image.Image]:
    # The v4 clean plate already contains the restored jacket. Only erase the
    # thin black/blue spur left by the old arm mask and taper it into the real
    # shoulder silhouette. No generated donor pixels are introduced in v6.
    support = polygon_mask([
        (180, 202), (194, 202), (194, 206), (198, 208), (202, 210),
        (206, 212), (209, 214), (210, 218), (180, 218),
    ])
    feather = support.filter(ImageFilter.GaussianBlur(0.75 * SCALE))
    rgba = np.asarray(body, dtype=np.uint8).copy()
    keep = 1.0 - np.asarray(feather, dtype=np.float32) / 255.0
    rgba[:, :, 3] = np.rint(rgba[:, :, 3] * keep).astype(np.uint8)
    repaired = Image.fromarray(rgba, mode="RGBA")
    support_array = np.asarray(support) > 0
    if np.any(support_array & (rgba[:, :, 3] >= 128)):
        raise ValueError("the clean-body shoulder shard remains opaque after repair")
    assert_unchanged_outside(body, repaired, feather, "body layer")
    return repaired, feather


def repair_arm(arm: Image.Image) -> tuple[Image.Image, Image.Image]:
    # The lower outline is valid on the outer forearm silhouette, but its
    # shoulder-most portion becomes an internal seam over the jacket. Recolour
    # only that local section from neighbouring accepted sleeve pixels.
    support = polygon_mask([
        (191, 193), (203, 198), (216, 198), (229, 184), (238, 167),
        (238, 220), (218, 228), (201, 220),
    ])
    rgba = np.asarray(arm, dtype=np.uint8).copy()
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    support_array = np.asarray(support) > 0

    rgb_wide = rgb.astype(np.int16)
    maximum = rgb_wide.max(axis=2)
    minimum = rgb_wide.min(axis=2)
    blue = (
        (alpha >= 224)
        & (rgb_wide[:, :, 2] >= 100)
        & (rgb_wide[:, :, 2] >= rgb_wide[:, :, 1] + 22)
        & (rgb_wide[:, :, 1] >= rgb_wide[:, :, 0] + 18)
    )
    dark_seam = support_array & (alpha >= 24) & (maximum <= 105) & (minimum <= 55)
    if not dark_seam.any():
        raise ValueError("the shoulder seam mask found no dark outline pixels")

    _distance, indices = ndimage.distance_transform_edt(~blue, return_indices=True)
    replacement = rgb[indices[0], indices[1]]
    blend_seed = ndimage.binary_dilation(dark_seam, iterations=3)
    blend_seed &= support_array & (alpha > 0)
    blend = ndimage.gaussian_filter(blend_seed.astype(np.float32), sigma=2.0)
    blend *= support_array
    blend = np.clip(blend, 0.0, 1.0)[:, :, None]
    rgb[:] = np.rint(rgb * (1.0 - blend) + replacement * blend).astype(np.uint8)

    repaired_wide = rgb.astype(np.int16)
    repaired_dark = (
        support_array
        & (alpha >= 24)
        & (repaired_wide.max(axis=2) <= 105)
        & (repaired_wide.min(axis=2) <= 55)
    )
    if repaired_dark.sum() > dark_seam.sum() * 0.30:
        raise ValueError("the inner shoulder outline was not reduced sufficiently")

    repaired = Image.fromarray(rgba, mode="RGBA")
    if ImageChops.difference(arm.getchannel("A"), repaired.getchannel("A")).getbbox():
        raise ValueError("arm alpha changed while repairing the colour seam")
    assert_unchanged_outside(arm, repaired, support, "arm layer")
    return repaired, support


def main() -> None:
    body = Image.open(SOURCE / "good-clean-body-master-v4.png").convert("RGBA")
    arm = Image.open(SOURCE / "good-raise-arm-master-v4.png").convert("RGBA")
    reference = Image.open(SOURCE / "good-reference-master-v3.png").convert("RGBA")
    for name, image in (
        ("body", body), ("arm", arm), ("reference", reference),
    ):
        if image.size != SIZE or image.mode != "RGBA":
            raise ValueError(f"{name} must be {SIZE} RGBA")

    repaired_body, body_support = repair_body(body)
    repaired_arm, arm_support = repair_arm(arm)
    repair_support = ImageChops.lighter(body_support, arm_support)

    DESTINATION.mkdir(parents=True, exist_ok=True)
    outputs = {
        "good-reference-master-v3.png": reference,
        "good-clean-body-master-v6.png": repaired_body,
        "good-raise-arm-master-v6.png": repaired_arm,
        "good-shoulder-repair-mask-master-v6.png": Image.merge(
            "RGBA", (repair_support,) * 4,
        ),
    }
    for name, image in outputs.items():
        destination = DESTINATION / name
        image.save(destination, optimize=True)
        print(f"Prepared {destination}")

    bind = Image.alpha_composite(repaired_body, repaired_arm)
    original_bind = Image.alpha_composite(body, arm)
    staged_difference = ImageChops.difference(original_bind, bind)
    outside_mask = ImageChops.invert(
        repair_support.point(lambda value: 255 if value else 0)
    )
    outside = ImageChops.multiply(
        staged_difference,
        Image.merge("RGBA", (outside_mask,) * 4),
    )
    if outside.getbbox() is not None:
        raise ValueError("the repaired bind differs from v4 outside its local mask")
    difference = ImageChops.difference(reference, bind)
    changed_pixels = sum(1 for pixel in difference.getdata() if max(pixel) > 4)
    print(f"Shoulder repair is confined to {changed_pixels} master pixels")


if __name__ == "__main__":
    main()
