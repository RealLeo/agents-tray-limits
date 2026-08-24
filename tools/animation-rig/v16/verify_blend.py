#!/usr/bin/env python3
"""Validate the editable Blender source for the staged 2D prototype."""

import bpy


required_objects = {
    "VaultBoy2DRig", "VaultBoy2DBody", "GoodRaiseArm", "GoodRestArm", "SpriteCamera",
}
missing = sorted(required_objects.difference(bpy.data.objects.keys()))
if missing:
    raise RuntimeError(f"missing Blender objects: {missing}")
rig = bpy.data.objects["VaultBoy2DRig"]
required_bones = {
    "root", "torso", "neck", "upper.raise", "forearm.raise", "hand.raise",
    "upper.rest", "forearm.rest", "hand.rest", "thigh.L", "shin.L", "foot.L",
    "thigh.R", "shin.R", "foot.R",
}
missing_bones = sorted(required_bones.difference(rig.data.bones.keys()))
if missing_bones:
    raise RuntimeError(f"missing rig bones: {missing_bones}")
if bpy.context.scene.frame_start != 1 or bpy.context.scene.frame_end != 24:
    raise RuntimeError("good action must use frames 1..24")
if not rig.animation_data or not rig.animation_data.action or rig.animation_data.action.name != "Good":
    raise RuntimeError("Good action is not active")
if any(obj.type == "MESH" and obj.name.startswith("Face") for obj in bpy.data.objects):
    raise RuntimeError("2D prototype must not contain a face-mask mesh")
file_images = [image for image in bpy.data.images if image.source == "FILE"]
if len(file_images) != 3 or any(not image.packed_file for image in file_images):
    raise RuntimeError("Blender source has unpacked image dependencies")
print("Blender 2D rig validation passed")
