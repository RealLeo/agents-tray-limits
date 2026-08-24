#!/usr/bin/env python3
"""Validate the editable Blender source. Run inside Blender."""

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise AssertionError(message)


rig = bpy.data.objects.get("VaultBoyRig")
model = bpy.data.objects.get("VaultBoyMesh")
outline = bpy.data.objects.get("VaultBoyOutline")
camera = bpy.data.objects.get("SpriteCamera")

require(rig and rig.type == "ARMATURE", "VaultBoyRig armature is missing")
require(model and model.type == "MESH", "VaultBoyMesh is missing")
require(outline and outline.type == "MESH", "editable outline shell is missing")
require(outline.hide_render, "outline shell must stay disabled for review renders")
require(camera and camera.data.type == "ORTHO", "orthographic camera is missing")
require(abs(camera.data.ortho_scale - 9.0) < 1e-6, "camera scale changed")
require(bpy.context.scene.frame_start == 1 and bpy.context.scene.frame_end == 24,
        "good action must cover frames 1..24")
require(rig.animation_data and rig.animation_data.action,
        "rig action is missing")
require(rig.animation_data.action.name == "good", "active action must be good")

right_arm_constraints = {constraint.type for constraint in rig.pose.bones["forearm.R"].constraints}
left_arm_constraints = {constraint.type for constraint in rig.pose.bones["forearm.L"].constraints}
thumb_constraints = {constraint.type for constraint in rig.pose.bones["thumb.R"].constraints}
require("IK" in right_arm_constraints and "IK" in left_arm_constraints,
        "two-segment arm IK is missing")
require("DAMPED_TRACK" in thumb_constraints, "stable thumb controller is missing")
require(any(modifier.type == "ARMATURE" and modifier.object == rig for modifier in model.modifiers),
        "mesh is not deformed by VaultBoyRig")

missing = []
for image in bpy.data.images:
    if not image.filepath or image.source != "FILE":
        continue
    path = Path(bpy.path.abspath(image.filepath))
    if not path.is_file():
        missing.append(str(path))
require(not missing, f"missing external images: {missing}")

print("Blender prototype validation passed")
bpy.ops.wm.quit_blender()
