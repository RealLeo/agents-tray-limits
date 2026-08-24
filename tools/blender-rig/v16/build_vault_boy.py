#!/usr/bin/env python3
"""Build and render the version 16 Blender Vault Boy prototype.

Run inside Blender:
    blender --background --factory-startup --python build_vault_boy.py -- --build --render-good

The generated model uses one shared mesh, one armature, deterministic materials,
an orthographic camera, and a single Blender Action for the good-state preview.
It never writes into the extension's runtime theme directory.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "rig-config.json").read_text(encoding="utf-8"))
BLEND_PATH = ROOT / "vault-boy-v16.blend"
RAW_GOOD_DIR = ROOT / "render" / "good" / "raw"
RAW_TURNTABLE_DIR = ROOT / "render" / "turntable" / "raw"

PALETTE = {
    "blue": (0.010, 0.235, 0.630, 1.0),
    "blue_dark": (0.005, 0.100, 0.270, 1.0),
    "yellow": (1.000, 0.790, 0.015, 1.0),
    "yellow_dark": (0.720, 0.430, 0.000, 1.0),
    "skin": (1.000, 0.705, 0.475, 1.0),
    "skin_dark": (0.700, 0.340, 0.150, 1.0),
    "black": (0.002, 0.002, 0.002, 1.0),
    "white": (1.000, 0.980, 0.920, 1.0),
    "shoe": (0.025, 0.028, 0.032, 1.0),
}

MESH_PARTS: list[bpy.types.Object] = []


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--render-good", action="store_true")
    parser.add_argument("--render-turntable", action="store_true")
    parser.add_argument("--render-frame", type=int)
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                       bpy.data.cameras, bpy.data.armatures, bpy.data.actions):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def material(name: str, rgba: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = rgba
    emission.inputs["Strength"].default_value = 1.0
    mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def outline_material() -> bpy.types.Material:
    """Black material that renders only the back faces of an inverted shell."""
    mat = bpy.data.materials.get("MAT_OUTLINE") or bpy.data.materials.new("MAT_OUTLINE")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    geometry = nodes.new("ShaderNodeNewGeometry")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    black = nodes.new("ShaderNodeEmission")
    black.inputs["Color"].default_value = PALETTE["black"]
    black.inputs["Strength"].default_value = 1.0
    mix = nodes.new("ShaderNodeMixShader")
    mat.node_tree.links.new(geometry.outputs["Backfacing"], mix.inputs[0])
    mat.node_tree.links.new(black.outputs[0], mix.inputs[1])
    mat.node_tree.links.new(transparent.outputs[0], mix.inputs[2])
    mat.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


def decal_material(name: str, image_path: Path) -> bpy.types.Material:
    """Create an emission decal that preserves the accepted 2D identity."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(image_path), check_existing=True)
    texture.image.filepath = f"//references/{image_path.name}"
    texture.interpolation = "Linear"
    emission = nodes.new("ShaderNodeEmission")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    geometry = nodes.new("ShaderNodeNewGeometry")
    front_factor = nodes.new("ShaderNodeMath")
    front_factor.operation = "SUBTRACT"
    front_factor.inputs[0].default_value = 1.0
    visible_alpha = nodes.new("ShaderNodeMath")
    visible_alpha.operation = "MULTIPLY"
    mat.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    mat.node_tree.links.new(geometry.outputs["Backfacing"], front_factor.inputs[1])
    mat.node_tree.links.new(texture.outputs["Alpha"], visible_alpha.inputs[0])
    mat.node_tree.links.new(front_factor.outputs[0], visible_alpha.inputs[1])
    mat.node_tree.links.new(visible_alpha.outputs[0], mix.inputs[0])
    mat.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    mat.node_tree.links.new(emission.outputs[0], mix.inputs[2])
    mat.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


def assign_all_vertices(obj: bpy.types.Object, bone: str) -> None:
    group = obj.vertex_groups.new(name=bone)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")


def finish_part(obj: bpy.types.Object, name: str, mat: bpy.types.Material,
                bone: str, smooth: bool = True) -> bpy.types.Object:
    obj.name = name
    obj.data.materials.append(mat)
    if smooth:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    assign_all_vertices(obj, bone)
    MESH_PARTS.append(obj)
    return obj


def uv_sphere(name: str, location: tuple[float, float, float],
              scale: tuple[float, float, float], mat: bpy.types.Material,
              bone: str, segments: int = 40, rings: int = 24) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish_part(obj, name, mat, bone)


def rounded_cube(name: str, location: tuple[float, float, float],
                 scale: tuple[float, float, float], radius: float,
                 mat: bpy.types.Material, bone: str) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new("Rounded", "BEVEL")
    bevel.width = radius
    bevel.segments = 4
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return finish_part(obj, name, mat, bone)


def decal_plane(name: str, location: tuple[float, float, float],
                scale: tuple[float, float, float], mat: bpy.types.Material,
                bone: str) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(location=location, rotation=(math.pi / 2, 0, 0))
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish_part(obj, name, mat, bone, smooth=False)


def cylinder_between(name: str, start: tuple[float, float, float],
                     end: tuple[float, float, float], radius: float,
                     mat: bpy.types.Material, bone: str,
                     vertices: int = 32) -> bpy.types.Object:
    a, b = Vector(start), Vector(end)
    direction = b - a
    midpoint = (a + b) * 0.5
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                       depth=direction.length, location=midpoint)
    obj = bpy.context.object
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    finish_part(obj, name, mat, bone)
    uv_sphere(f"{name}.cap.a", start, (radius, radius, radius), mat, bone, segments=24, rings=16)
    uv_sphere(f"{name}.cap.b", end, (radius, radius, radius), mat, bone, segments=24, rings=16)
    return obj


def torus(name: str, location: tuple[float, float, float], major: float,
          minor: float, scale: tuple[float, float, float], mat: bpy.types.Material,
          bone: str, rotation: tuple[float, float, float] = (0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                    major_segments=48, minor_segments=12,
                                    location=location, rotation=rotation)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish_part(obj, name, mat, bone)


def curve_line(name: str, points: list[tuple[float, float, float]], bevel: float,
               mat: bpy.types.Material, bone: str, cyclic: bool = False) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = bevel
    curve.bevel_resolution = 4
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    return finish_part(obj, name, mat, bone)


def add_bone(edit_bones, name: str, head, tail, parent: str | None = None,
             connected: bool = False):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    if parent:
        bone.parent = edit_bones[parent]
        bone.use_connect = connected
    return bone


def build_armature() -> bpy.types.Object:
    armature = bpy.data.armatures.new("VaultBoyArmature")
    rig = bpy.data.objects.new("VaultBoyRig", armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = armature.edit_bones
    add_bone(bones, "root", (0, 0, 0), (0, 0, 0.5))
    add_bone(bones, "pelvis", (0, 0, 2.0), (0, 0, 3.0), "root")
    add_bone(bones, "spine", (0, 0, 3.0), (0, 0, 4.65), "pelvis", True)
    add_bone(bones, "neck", (0, 0, 4.65), (0, 0, 5.05), "spine", True)
    add_bone(bones, "head", (0, 0, 5.05), (0, 0, 6.45), "neck", True)

    add_bone(bones, "upper_arm.R", (-0.92, 0, 4.45), (-1.95, 0, 4.45), "spine")
    add_bone(bones, "forearm.R", (-1.95, 0, 4.45), (-2.90, 0, 4.45), "upper_arm.R", True)
    add_bone(bones, "hand.R", (-2.90, 0, 4.45), (-3.35, 0, 4.45), "forearm.R", True)
    add_bone(bones, "thumb.R", (-3.18, -0.02, 4.56), (-3.18, -0.02, 5.10), "hand.R")

    add_bone(bones, "upper_arm.L", (0.92, 0, 4.45), (1.95, 0, 4.45), "spine")
    add_bone(bones, "forearm.L", (1.95, 0, 4.45), (2.90, 0, 4.45), "upper_arm.L", True)
    add_bone(bones, "hand.L", (2.90, 0, 4.45), (3.35, 0, 4.45), "forearm.L", True)

    add_bone(bones, "thigh.R", (-0.48, 0, 2.30), (-0.48, 0, 1.25), "pelvis")
    add_bone(bones, "shin.R", (-0.48, 0, 1.25), (-0.48, 0, 0.35), "thigh.R", True)
    add_bone(bones, "foot.R", (-0.48, 0, 0.35), (-0.48, -0.55, 0.18), "shin.R", True)
    add_bone(bones, "thigh.L", (0.48, 0, 2.30), (0.48, 0, 1.25), "pelvis")
    add_bone(bones, "shin.L", (0.48, 0, 1.25), (0.48, 0, 0.35), "thigh.L", True)
    add_bone(bones, "foot.L", (0.48, 0, 0.35), (0.48, -0.55, 0.18), "shin.L", True)
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.show_in_front = True
    return rig


def build_model(rig: bpy.types.Object) -> bpy.types.Object:
    mats = {key: material(f"MAT_{key.upper()}", value) for key, value in PALETTE.items()}
    face_decal_mat = decal_material("MAT_FACE_GOOD_DECAL", ROOT / "references" / "face-good-decal.png")

    # Core body and costume.
    uv_sphere("Torso", (0, 0.03, 3.66), (1.13, 0.60, 1.16), mats["blue"], "spine")
    uv_sphere("Pelvis", (0, 0.03, 2.64), (0.88, 0.52, 0.60), mats["blue"], "pelvis")
    rounded_cube("FrontStripe", (0, -0.595, 3.66), (0.24, 0.045, 0.86), 0.08,
                 mats["yellow"], "spine")
    rounded_cube("WaistBand", (0, -0.555, 2.80), (0.93, 0.05, 0.23), 0.08,
                 mats["yellow"], "pelvis")
    torus("Collar", (0, 0.0, 4.68), 0.60, 0.13, (1.0, 0.72, 1.0),
          mats["yellow"], "spine")
    uv_sphere("Neck", (0, 0, 4.92), (0.38, 0.34, 0.35), mats["skin"], "neck")

    # Legs and shoes.
    for side, x in (("R", -0.48), ("L", 0.48)):
        cylinder_between(f"Thigh.{side}", (x, 0, 2.36), (x, 0, 1.28), 0.40,
                         mats["blue"], f"thigh.{side}")
        cylinder_between(f"Shin.{side}", (x, 0, 1.30), (x, 0, 0.38), 0.34,
                         mats["blue"], f"shin.{side}")
        uv_sphere(f"Shoe.{side}", (x + (-0.07 if side == "R" else 0.07), -0.24, 0.24),
                  (0.48, 0.70, 0.22), mats["shoe"], f"foot.{side}")

    # Arms in rest T-pose; IK supplies the animated pose.
    for side, sign in (("R", -1), ("L", 1)):
        cylinder_between(f"UpperArm.{side}", (0.92 * sign, 0, 4.45),
                         (1.95 * sign, 0, 4.45), 0.34, mats["blue"], f"upper_arm.{side}")
        cylinder_between(f"Forearm.{side}", (1.95 * sign, 0, 4.45),
                         (2.90 * sign, 0, 4.45), 0.30, mats["blue"], f"forearm.{side}")
        torus(f"Cuff.{side}", (2.88 * sign, 0, 4.45), 0.31, 0.075,
              (1.0, 1.0, 1.0), mats["yellow"], f"forearm.{side}",
              rotation=(0, math.pi / 2, 0))

    # Left hand stays relaxed.
    uv_sphere("Palm.L", (3.18, -0.02, 4.45), (0.34, 0.22, 0.34), mats["skin"], "hand.L")
    cylinder_between("Fingers.L", (3.23, -0.02, 4.43), (3.53, -0.02, 4.43),
                     0.22, mats["skin"], "hand.L")

    # Right palm and thumb are driven by separate bones, so the gesture changes
    # continuously rather than swapping between two images.
    uv_sphere("Palm.R", (-3.18, -0.02, 4.45), (0.36, 0.23, 0.38), mats["skin"], "hand.R")
    uv_sphere("Knuckles.R", (-3.34, -0.03, 4.42), (0.28, 0.21, 0.30), mats["skin"], "hand.R")
    cylinder_between("Thumb.R", (-3.18, -0.02, 4.56), (-3.18, -0.02, 5.10),
                     0.16, mats["skin"], "thumb.R", vertices=24)

    # Head, ears, hair volume and recognisable front curl.
    # A compact head volume sits behind the accepted front decal. Keeping it
    # inside the decal silhouette prevents a second, mismatched face outline in
    # front renders while retaining real volume for the turntable.
    uv_sphere("Head", (0, 0.05, 5.94), (0.74, 0.72, 0.96), mats["skin"], "head")
    uv_sphere("HairCap", (0.04, 0.25, 6.48), (0.76, 0.68, 0.64), mats["yellow"], "head")
    uv_sphere("Ear.R", (-0.72, -0.01, 5.93), (0.17, 0.16, 0.25), mats["skin"], "head",
              segments=24, rings=16)
    uv_sphere("Ear.L", (0.72, -0.01, 5.93), (0.17, 0.16, 0.25), mats["skin"], "head",
              segments=24, rings=16)
    uv_sphere("NoseVolume", (0, -0.67, 5.98), (0.14, 0.25, 0.18), mats["skin"], "head",
              segments=24, rings=16)
    uv_sphere("SideEye.R", (-0.69, -0.43, 6.13), (0.035, 0.075, 0.10), mats["black"], "head",
              segments=16, rings=10)
    uv_sphere("SideEye.L", (0.69, -0.43, 6.13), (0.035, 0.075, 0.10), mats["black"], "head",
              segments=16, rings=10)

    # Face decals are thin geometry, not projected animation textures.
    front_y = -0.694
    uv_sphere("Eye.R", (-0.36, front_y - 0.015, 6.08), (0.09, 0.035, 0.16),
              mats["black"], "head", segments=20, rings=12)
    uv_sphere("Eye.L", (0.36, front_y - 0.015, 6.08), (0.09, 0.035, 0.16),
              mats["black"], "head", segments=20, rings=12)
    curve_line("Brow.R", [(-0.52, front_y - 0.02, 6.34), (-0.34, front_y - 0.03, 6.40),
                          (-0.18, front_y - 0.02, 6.34)], 0.035, mats["black"], "head")
    curve_line("Brow.L", [(0.18, front_y - 0.02, 6.34), (0.34, front_y - 0.03, 6.40),
                          (0.52, front_y - 0.02, 6.34)], 0.035, mats["black"], "head")
    curve_line("NoseLine", [(-0.03, front_y - 0.035, 6.15), (-0.12, front_y - 0.045, 5.91),
                            (0.04, front_y - 0.045, 5.83)], 0.045, mats["black"], "head")
    uv_sphere("MouthOutline", (0, front_y - 0.040, 5.63), (0.56, 0.040, 0.23),
              mats["black"], "head", segments=32, rings=16)
    uv_sphere("Teeth", (0, front_y - 0.082, 5.66), (0.48, 0.030, 0.15),
              mats["white"], "head", segments=32, rings=16)
    rounded_cube("MouthMask", (0, front_y - 0.113, 5.77), (0.54, 0.020, 0.10), 0.08,
                 mats["skin"], "head")
    curve_line("Chin", [(-0.16, front_y - 0.03, 5.31), (0, front_y - 0.04, 5.27),
                        (0.16, front_y - 0.03, 5.31)], 0.026, mats["black"], "head")
    for index, z in enumerate((6.02, 5.91, 5.80)):
        curve_line(f"TempleLine.{index}", [(0.82, front_y - 0.01, z + 0.05),
                                           (0.92, front_y - 0.01, z)],
                   0.025, mats["black"], "head")

    # The accepted v15 face is used as a UV decal on the front of the volume.
    # It is a single rigid surface attached to the head bone, so identity is
    # pixel-stable while the underlying 3D head remains visible in side views.
    decal_plane("FaceGoodDecal", (-0.12, -0.755, 6.03), (1.53, 1.36, 1.0),
                face_decal_mat, "head")

    # Join every modeled element into one mesh while preserving rigid bone groups.
    bpy.ops.object.select_all(action="DESELECT")
    for part in MESH_PARTS:
        part.select_set(True)
    bpy.context.view_layer.objects.active = MESH_PARTS[0]
    bpy.ops.object.join()
    model = bpy.context.object
    model.name = "VaultBoyMesh"
    modifier = model.modifiers.new("VaultBoyArmature", "ARMATURE")
    modifier.object = rig
    model.parent = rig

    # A shared inverted shell provides a stable toon outline without Freestyle's
    # frame-dependent edge analysis. It uses the same armature and vertex groups.
    outline = model.copy()
    outline.data = model.data.copy()
    outline.name = "VaultBoyOutline"
    bpy.context.collection.objects.link(outline)
    outline.data.materials.clear()
    outline.data.materials.append(outline_material())
    for polygon in outline.data.polygons:
        polygon.material_index = 0
    solidify = outline.modifiers.new("OutlineShell", "SOLIDIFY")
    solidify.thickness = 0.045
    solidify.offset = 1.0
    solidify.use_rim = False
    solidify.use_flip_normals = True
    outline.parent = rig
    outline.display_type = "WIRE"
    # The shell remains editable in the source file. Review sprites use a
    # deterministic alpha-derived contour during post-processing because Eevee
    # front-face transparency is not reliable in this headless Snap build.
    outline.hide_render = True
    return model


def add_ik(rig: bpy.types.Object) -> dict[str, bpy.types.Object]:
    targets: dict[str, bpy.types.Object] = {}
    for side, sign in (("R", -1), ("L", 1)):
        target = bpy.data.objects.new(f"IK_Hand_{side}", None)
        target.empty_display_type = "SPHERE"
        target.empty_display_size = 0.18
        target.location = (2.90 * sign, 0, 4.45)
        bpy.context.collection.objects.link(target)
        targets[f"hand.{side}"] = target
        pole = bpy.data.objects.new(f"Pole_Elbow_{side}", None)
        pole.empty_display_type = "CUBE"
        pole.empty_display_size = 0.15
        pole.location = (1.95 * sign, -2.0, 4.0)
        bpy.context.collection.objects.link(pole)
        targets[f"pole.{side}"] = pole
        constraint = rig.pose.bones[f"forearm.{side}"].constraints.new("IK")
        constraint.target = target
        constraint.pole_target = pole
        constraint.chain_count = 2
        constraint.use_stretch = False
        constraint.pole_angle = -math.pi / 2 if side == "R" else math.pi / 2
    thumb_target = bpy.data.objects.new("IK_Thumb_R", None)
    thumb_target.empty_display_type = "SPHERE"
    thumb_target.empty_display_size = 0.12
    thumb_target.location = (-3.18, -0.02, 5.10)
    bpy.context.collection.objects.link(thumb_target)
    targets["thumb.R"] = thumb_target
    thumb_constraint = rig.pose.bones["thumb.R"].constraints.new("DAMPED_TRACK")
    thumb_constraint.target = thumb_target
    thumb_constraint.track_axis = "TRACK_Y"
    return targets


def key_location(obj: bpy.types.Object, frame: int, location) -> None:
    obj.location = location
    obj.keyframe_insert(data_path="location", frame=frame, group=obj.name)


def key_rotation(bone: bpy.types.PoseBone, frame: int, rotation) -> None:
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = rotation
    bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone.name)


def smootherstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def eased_linear(value: float, edge: float = 0.08) -> float:
    """Near-linear motion with short continuous acceleration/deceleration."""
    value = max(0.0, min(1.0, value))
    velocity = 1.0 / (1.0 - edge)
    if value < edge:
        return 0.5 * (velocity / edge) * value * value
    if value > 1.0 - edge:
        remaining = 1.0 - value
        return 1.0 - 0.5 * (velocity / edge) * remaining * remaining
    return 0.5 * velocity * edge + velocity * (value - edge)


def interpolate(a, b, factor: float):
    return tuple(x + (y - x) * factor for x, y in zip(a, b))


def iter_action_fcurves(action: bpy.types.Action):
    """Yield F-Curves from Blender's layered Action API."""
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                yield from channelbag.fcurves


def animate_good(rig: bpy.types.Object, targets: dict[str, bpy.types.Object]) -> bpy.types.Action:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = CONFIG["frames"]
    rig.animation_data_create()
    action = bpy.data.actions.new("good")
    rig.animation_data.action = action

    # Character's right hand is on the viewer's left. The target follows a
    # controlled arc while the pole target keeps the elbow on one stable side.
    target = targets["hand.R"]
    pole = targets["pole.R"]
    thumb_target = targets["thumb.R"]
    hand = rig.pose.bones["hand.R"]
    start = (-1.28, -0.08, 3.18)
    anticipation = (-1.22, -0.08, 3.02)
    end = (-2.88, -0.08, 4.78)
    for frame in range(1, CONFIG["frames"] + 1):
        if frame <= 4:
            phase = smootherstep((frame - 1) / 3.0)
            hand_location = interpolate(start, anticipation, phase)
            gesture = 0.0
        else:
            gesture = eased_linear((frame - 4) / (CONFIG["frames"] - 4))
            hand_location = interpolate(anticipation, end, gesture)
        key_location(target, frame, hand_location)
        key_location(pole, frame, (-1.65, -2.20, 3.90))

        # Track the moving palm in world space and rotate the digit from folded
        # down to a clear vertical thumbs-up without a solver-plane flip.
        folded_offset = (-0.12, -0.02, -0.46)
        raised_offset = (-0.27, -0.02, 0.62)
        thumb_offset = interpolate(folded_offset, raised_offset, gesture)
        key_location(thumb_target, frame, tuple(a + b for a, b in zip(hand_location, thumb_offset)))

        hand_angle = -0.18 if frame <= 4 else -0.18 * (1.0 - gesture)
        key_rotation(hand, frame, (0.0, 0.0, hand_angle))

    # The unused arm hangs naturally and remains still throughout the action.
    left_target = targets["hand.L"]
    left_pole = targets["pole.L"]
    for frame in (1, 24):
        key_location(left_target, frame, (1.22, -0.02, 3.18))
        key_location(left_pole, frame, (1.65, -2.0, 3.85))
        key_rotation(rig.pose.bones["hand.L"], frame, (0, 0, 0.30))

    # Subtle anticipation without root translation; feet and baseline remain fixed.
    spine = rig.pose.bones["spine"]
    head = rig.pose.bones["head"]
    for frame, spine_rot, head_rot in (
        (1, (0, 0, 0), (0, 0, 0)),
        (4, (0, 0.015, 0.018), (0, -0.010, -0.015)),
        (13, (0, -0.010, -0.018), (0, 0.008, 0.016)),
        (21, (0, 0.004, 0.005), (0, -0.003, -0.004)),
        (24, (0, 0, 0), (0, 0, 0)),
    ):
        key_rotation(spine, frame, spine_rot)
        key_rotation(head, frame, head_rot)

    # Blender 5.x stores action channels in layered slots. Keyframe insertion
    # creates separate actions for the rig and each animated IK control, so
    # normalize all of the generated curves through the layered API.
    for generated_action in bpy.data.actions:
        for fcurve in iter_action_fcurves(generated_action):
            for key in fcurve.keyframe_points:
                key.interpolation = "BEZIER"
                key.handle_left_type = "AUTO_CLAMPED"
                key.handle_right_type = "AUTO_CLAMPED"
            fcurve.auto_smoothing = "CONT_ACCEL"
    return action


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("SpriteCamera")
    camera = bpy.data.objects.new("SpriteCamera", data)
    bpy.context.collection.objects.link(camera)
    camera.location = CONFIG["camera"]["location"]
    data.type = "ORTHO"
    data.ortho_scale = CONFIG["camera"]["orthoScale"]
    look_at(camera, tuple(CONFIG["camera"]["target"]))
    bpy.context.scene.camera = camera
    return camera


def add_reference_images() -> None:
    collection = bpy.data.collections.new("References")
    bpy.context.scene.collection.children.link(collection)
    collection.hide_render = True
    for name, path, location, rotation in (
        ("Turnaround", ROOT / "references" / "turnaround.png", (0, 1.4, 4.1), (math.pi / 2, 0, 0)),
        ("IdentityAtlas", ROOT / "references" / "v15-identity-atlas.png", (0, 1.6, 4.1), (math.pi / 2, 0, 0)),
    ):
        image = bpy.data.images.load(str(path), check_existing=True)
        image.filepath = f"//references/{path.name}"
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "IMAGE"
        empty.data = image
        empty.location = location
        empty.rotation_euler = rotation
        empty.empty_display_size = 8.0
        empty.hide_render = True
        collection.objects.link(empty)
    collection.hide_viewport = True


def configure_render(quick: bool = False) -> None:
    scene = bpy.context.scene
    scene.render.engine = CONFIG["renderEngine"]
    scene.render.resolution_x = 256 if quick else CONFIG["sourceSize"]
    scene.render.resolution_y = 256 if quick else CONFIG["sourceSize"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    scene.render.use_file_extension = True
    scene.render.use_freestyle = False
    scene.render.filter_size = 1.0
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.world.color = (0.0, 0.0, 0.0)
    scene.render.fps = CONFIG["fps"]
    scene.render.fps_base = 1.0


def write_motion_report() -> None:
    """Export projected bone motion so smoothness checks are reproducible."""
    scene = bpy.context.scene
    camera = bpy.data.objects["SpriteCamera"]
    rig = bpy.data.objects["VaultBoyRig"]
    tracks = {
        "root": ("root", "head"),
        "pelvis": ("pelvis", "head"),
        "head": ("head", "tail"),
        "elbow": ("forearm.R", "head"),
        "wrist": ("hand.R", "head"),
        "hand": ("hand.R", "tail"),
        "thumb": ("thumb.R", "tail"),
    }
    samples = []
    for frame in range(1, CONFIG["frames"] + 1):
        scene.frame_set(frame)
        points = {}
        for label, (bone_name, endpoint) in tracks.items():
            bone = rig.pose.bones[bone_name]
            local = getattr(bone, endpoint)
            ndc = world_to_camera_view(scene, camera, rig.matrix_world @ local)
            points[label] = [round(ndc.x * CONFIG["spriteSize"], 4),
                             round((1.0 - ndc.y) * CONFIG["spriteSize"], 4)]
        samples.append({"frame": frame, "points": points})

    max_steps = {}
    scale = CONFIG["displaySize"] / CONFIG["spriteSize"]
    for label in tracks:
        largest = 0.0
        for previous, current in zip(samples, samples[1:]):
            a = Vector(previous["points"][label])
            b = Vector(current["points"][label])
            largest = max(largest, (b - a).length * scale)
        max_steps[label] = round(largest, 4)
    report = {
        "frames": CONFIG["frames"],
        "fps": CONFIG["fps"],
        "intervalMs": CONFIG["intervalMs"],
        "displaySize": CONFIG["displaySize"],
        "maxConsecutiveStepDisplayPx": max_steps,
        "samples": samples,
    }
    report_path = ROOT / "render" / "good" / "motion.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(1)

def render_good(quick: bool = False) -> None:
    RAW_GOOD_DIR.mkdir(parents=True, exist_ok=True)
    for stale_frame in RAW_GOOD_DIR.glob("*.png"):
        stale_frame.unlink()
    configure_render(quick)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = CONFIG["frames"]
    scene.render.filepath = str(RAW_GOOD_DIR) + "/"
    bpy.ops.render.render(animation=True)


def render_frame(frame: int, quick: bool = False) -> None:
    configure_render(quick)
    output = ROOT / "previews" / f"good-frame-{frame:02d}-quick.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_set(frame)
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


def render_turntable(quick: bool = False) -> None:
    RAW_TURNTABLE_DIR.mkdir(parents=True, exist_ok=True)
    configure_render(quick)
    camera = bpy.data.objects["SpriteCamera"]
    scene = bpy.context.scene
    original_action = bpy.data.objects["VaultBoyRig"].animation_data.action
    scene.frame_set(24)
    radius = 22.0
    for frame in range(1, 37):
        angle = 2 * math.pi * (frame - 1) / 36
        camera.location = (radius * math.sin(angle), -radius * math.cos(angle), 4.7)
        look_at(camera, tuple(CONFIG["camera"]["target"]))
        scene.render.filepath = str(RAW_TURNTABLE_DIR / f"{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    bpy.data.objects["VaultBoyRig"].animation_data.action = original_action


def build(quick: bool = False) -> None:
    clear_scene()
    rig = build_armature()
    build_model(rig)
    targets = add_ik(rig)
    animate_good(rig, targets)
    add_camera()
    add_reference_images()
    configure_render(quick)
    write_motion_report()
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), compress=True)


def main() -> None:
    args = parse_args()
    if args.build or not BLEND_PATH.exists():
        build(args.quick)
    else:
        bpy.ops.wm.open_mainfile(filepath=str(BLEND_PATH))
    if args.render_good:
        render_good(args.quick)
    if args.render_frame is not None:
        render_frame(args.render_frame, args.quick)
    if args.render_turntable:
        render_turntable(args.quick)


if __name__ == "__main__":
    main()
