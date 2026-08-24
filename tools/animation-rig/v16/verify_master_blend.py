#!/usr/bin/env python3
"""Validate the editable Blender source for the registered staged master rig."""

import math
import json
import os
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parent
CONFIG_NAME = os.environ.get("AGENTS_TRAY_RIG_CONFIG", "master-rig-config.json")
CONFIG = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))


required_objects = {
    "VaultBoyMasterReference",
    "VaultBoyMasterBody",
    "VaultBoyMasterArm",
    "VaultBoyMasterRig",
    "CTRL_IK_Raise",
    "CTRL_Pole_Raise",
    "SpriteCamera",
}
missing = sorted(required_objects.difference(bpy.data.objects.keys()))
if missing:
    raise RuntimeError(f"missing Blender objects: {missing}")

rig = bpy.data.objects["VaultBoyMasterRig"]
required_bones = {"root", "torso", "neck", "upper.raise", "forearm.raise", "hand.raise"}
missing_bones = sorted(required_bones.difference(rig.data.bones.keys()))
if missing_bones:
    raise RuntimeError(f"missing rig bones: {missing_bones}")
if rig.data.bones["hand.raise"].use_inherit_rotation:
    raise RuntimeError("hand bone must keep a stable screen orientation")

constraint = rig.pose.bones["forearm.raise"].constraints.get("GoodRaiseIK")
if not constraint or constraint.type != "IK" or constraint.chain_count != 2:
    raise RuntimeError("continuous two-segment arm IK is not configured")
if constraint.target != bpy.data.objects["CTRL_IK_Raise"]:
    raise RuntimeError("IK target is not registered")
if constraint.pole_target != bpy.data.objects["CTRL_Pole_Raise"]:
    raise RuntimeError("IK pole target is not registered")
if not math.isclose(constraint.pole_angle, math.pi, abs_tol=1e-6):
    raise RuntimeError("IK pole angle does not select the bind-pose elbow branch")

arm = bpy.data.objects["VaultBoyMasterArm"]
if not arm.data.shape_keys:
    raise RuntimeError("master arm corrective shape keys are missing")
if not {"Basis", "ShoulderCorrective", "ElbowCorrective"}.issubset(
    arm.data.shape_keys.key_blocks.keys()
):
    raise RuntimeError("master arm corrective shape keys are incomplete")
required_depth_modifiers = {"DepthUpper", "DepthForearm", "DepthHand"}
missing_depth_modifiers = required_depth_modifiers.difference(arm.modifiers.keys())
if missing_depth_modifiers:
    raise RuntimeError(f"master arm depth modifiers are incomplete: {missing_depth_modifiers}")
for name in required_depth_modifiers:
    if arm.modifiers[name].type != "DISPLACE" or arm.modifiers[name].direction != "Z":
        raise RuntimeError(f"{name} must displace the deformed mesh on the depth axis")

expected_materials = CONFIG.get("materials", {})
body_material = bpy.data.objects["VaultBoyMasterBody"].active_material
arm_material = arm.active_material
if hasattr(body_material, "surface_render_method"):
    if body_material.surface_render_method != expected_materials.get("body", "DITHERED"):
        raise RuntimeError("clean body material does not write the configured depth")
    if arm_material.surface_render_method != expected_materials.get("arm", "DITHERED"):
        raise RuntimeError("animated arm material uses the wrong transparency method")

reference = bpy.data.objects["VaultBoyMasterReference"]
if not reference.hide_render or not reference.hide_get():
    raise RuntimeError("master registration reference must stay hidden from render and viewport")
if not all(reference.lock_location) or not all(reference.lock_rotation) or not all(reference.lock_scale):
    raise RuntimeError("master registration reference must stay transform-locked")

expected_frames = int(CONFIG["frames"])
if bpy.context.scene.frame_start != 1 or bpy.context.scene.frame_end != expected_frames:
    raise RuntimeError(f"master good action must use frames 1..{expected_frames}")
camera = bpy.data.objects["SpriteCamera"].data
expected_camera_type = CONFIG["camera"].get("type", "ORTHO")
if camera.type != expected_camera_type:
    raise RuntimeError(f"sprite camera must use {expected_camera_type}")
if expected_camera_type == "PERSP" and camera.sensor_fit != "VERTICAL":
    raise RuntimeError("perspective sprite camera must use vertical sensor fitting")
file_images = [image for image in bpy.data.images if image.source == "FILE"]
if len(file_images) != 3 or any(not image.packed_file for image in file_images):
    raise RuntimeError("Blender master source has unpacked image dependencies")
print("Blender staged 2D rig validation passed")
