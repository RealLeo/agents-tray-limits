#!/usr/bin/env python3
"""Build and render the staged v16 flat textured Blender armature."""

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
BLEND_PATH = ROOT / "vault-boy-2d-rig.blend"
RAW_DIR = ROOT / "render" / "good" / "raw"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--render-good", action="store_true")
    parser.add_argument("--render-frame", type=int)
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args(argv)


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.armatures,
        bpy.data.actions,
    ):
        for datablock in list(collection):
            if datablock.users == 0:
                collection.remove(datablock)


def smoothstep(left: float, right: float, value: float) -> float:
    amount = max(0.0, min(1.0, (value - left) / (right - left)))
    return amount * amount * (3.0 - 2.0 * amount)


def pixel_to_world(x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
    center_x, center_y = CONFIG["camera"]["centerPixel"]
    scale = CONFIG["pixelScale"]
    return ((x - center_x) * scale, (center_y - y) * scale, z)


def texture_material(name: str, path: Path) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(path), check_existing=True)
    texture.image.filepath = f"//sources/{path.name}"
    texture.image.alpha_mode = "STRAIGHT"
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    emission = nodes.new("ShaderNodeEmission")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    material.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(texture.outputs["Alpha"], mix.inputs[0])
    material.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    material.node_tree.links.new(emission.outputs[0], mix.inputs[2])
    material.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    if hasattr(material, "surface_render_method"):
        # Transparent body pixels must reveal the arm planes behind them.
        material.surface_render_method = "BLENDED"
    return material


def add_bone(edit_bones, name: str, head_px, tail_px, parent=None):
    bone = edit_bones.new(name)
    bone.head = pixel_to_world(*head_px)
    bone.tail = pixel_to_world(*tail_px)
    if parent:
        bone.parent = edit_bones[parent]
        bone.use_connect = False
    return bone


def build_armature() -> bpy.types.Object:
    data = bpy.data.armatures.new("VaultBoy2DRigData")
    rig = bpy.data.objects.new("VaultBoy2DRig", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = data.edit_bones
    joints = CONFIG["joints"]
    add_bone(bones, "root", (256, 470), (256, 300))
    add_bone(bones, "torso", (256, 300), (256, 175), "root")
    add_bone(bones, "neck", (256, 175), (256, 120), "torso")
    add_bone(bones, "upper.raise", joints["raiseShoulder"], joints["raiseElbow"], "torso")
    add_bone(bones, "forearm.raise", joints["raiseElbow"], joints["raiseWrist"], "upper.raise")
    add_bone(bones, "hand.raise", joints["raiseWrist"], joints["raiseHand"], "forearm.raise")
    add_bone(bones, "upper.rest", joints["restShoulder"], joints["restElbow"], "torso")
    add_bone(bones, "forearm.rest", joints["restElbow"], joints["restWrist"], "upper.rest")
    add_bone(bones, "hand.rest", joints["restWrist"], joints["restHand"], "forearm.rest")
    add_bone(bones, "thigh.L", (225, 326), (220, 395), "root")
    add_bone(bones, "shin.L", (220, 395), (215, 460), "thigh.L")
    add_bone(bones, "foot.L", (215, 460), (190, 475), "shin.L")
    add_bone(bones, "thigh.R", (287, 326), (292, 395), "root")
    add_bone(bones, "shin.R", (292, 395), (297, 460), "thigh.R")
    add_bone(bones, "foot.R", (297, 460), (322, 475), "shin.R")
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.show_in_front = True
    return rig


def build_static_layer(name: str, source_name: str, z: float) -> bpy.types.Object:
    path = ROOT / "sources" / source_name
    image = bpy.data.images.load(str(path), check_existing=True)
    width, height = image.size
    vertices = [
        pixel_to_world(0, 0, z),
        pixel_to_world(width, 0, z),
        pixel_to_world(width, height, z),
        pixel_to_world(0, height, z),
    ]
    mesh = bpy.data.meshes.new(f"{name}Data")
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(texture_material(f"MAT_{name.upper()}", path))
    uv = mesh.uv_layers.new(name="UVMap")
    for loop_index, value in enumerate(((0, 1), (1, 1), (1, 0), (0, 0))):
        uv.data[loop_index].uv = value
    return obj


def arm_weights(x: float) -> dict[str, float]:
    upper = smoothstep(100, 142, x)
    hand = 1.0 - smoothstep(42, 72, x)
    forearm = max(0.0, 1.0 - upper - hand)
    return {
        "upper.raise": upper,
        "forearm.raise": forearm,
        "hand.raise": hand,
    }


def build_raise_arm(rig: bpy.types.Object) -> bpy.types.Object:
    path = ROOT / "sources" / "good-raise-arm.png"
    image = bpy.data.images.load(str(path), check_existing=True)
    width, height = image.size
    left, top, right, bottom = (6, 120, 210, 230)
    step = int(CONFIG["gridStep"])
    xs = list(range(left, right, step))
    ys = list(range(top, bottom, step))
    if xs[-1] != right:
        xs.append(right)
    if ys[-1] != bottom:
        ys.append(bottom)
    vertices = [pixel_to_world(x, y, -0.012) for y in ys for x in xs]
    columns = len(xs)
    faces = []
    for row in range(len(ys) - 1):
        for column in range(columns - 1):
            index = row * columns + column
            faces.append((index, index + 1, index + columns + 1, index + columns))
    mesh = bpy.data.meshes.new("GoodRaiseArmData")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("GoodRaiseArm", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(texture_material("MAT_GOOD_RAISE_ARM", path))
    uv = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            row, column = divmod(vertex_index, columns)
            uv.data[loop_index].uv = (xs[column] / width, 1.0 - ys[row] / height)
    groups = {
        name: obj.vertex_groups.new(name=name)
        for name in ("upper.raise", "forearm.raise", "hand.raise")
    }
    for index, x in enumerate(px for _y in ys for px in xs):
        for name, weight in arm_weights(x).items():
            if weight > 0.0001:
                groups[name].add([index], weight, "REPLACE")
    modifier = obj.modifiers.new("GoodRaiseArmature", "ARMATURE")
    modifier.object = rig
    modifier.use_deform_preserve_volume = False
    obj.parent = rig
    return obj


def key_rotation(bone: bpy.types.PoseBone, frame: int, degrees: float) -> None:
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = (0.0, 0.0, math.radians(degrees))
    bone.keyframe_insert(data_path="rotation_euler", frame=frame, index=2)


def iter_action_fcurves(action: bpy.types.Action):
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                yield from channelbag.fcurves


def eased_linear(value: float, edge: float = 0.15) -> float:
    """Mostly linear travel with short quadratic acceleration/deceleration."""
    value = max(0.0, min(1.0, value))
    velocity = 1.0 / (1.0 - edge)
    if value < edge:
        return 0.5 * (velocity / edge) * value * value
    if value > 1.0 - edge:
        remaining = 1.0 - value
        return 1.0 - 0.5 * (velocity / edge) * remaining * remaining
    return 0.5 * velocity * edge + velocity * (value - edge)


def animate_good(rig: bpy.types.Object) -> None:
    rig.animation_data_create()
    action = bpy.data.actions.new("Good")
    rig.animation_data.action = action
    for frame in range(1, int(CONFIG["frames"]) + 1):
        if frame <= 3:
            anticipation = smoothstep(1, 3, frame)
            upper = 80.0 + 4.0 * anticipation
            forearm = -16.0 - 4.0 * anticipation
            hand = 5.0 + 2.0 * anticipation
        else:
            progress = eased_linear((frame - 3) / (CONFIG["frames"] - 3))
            upper = 84.0 * (1.0 - progress)
            forearm = -20.0 * (1.0 - progress)
            hand = 7.0 * (1.0 - progress)
        key_rotation(rig.pose.bones["upper.raise"], frame, upper)
        key_rotation(rig.pose.bones["forearm.raise"], frame, forearm)
        key_rotation(rig.pose.bones["hand.raise"], frame, hand)
    for fcurve in iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            point.interpolation = "BEZIER"
            point.handle_left_type = "AUTO_CLAMPED"
            point.handle_right_type = "AUTO_CLAMPED"


def configure_render(quick: bool = False) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    size = 512 if quick else int(CONFIG["sourceSize"])
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    scene.render.use_file_extension = True
    scene.render.filter_size = 0.5
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.fps = int(CONFIG["fps"])
    scene.render.fps_base = 1.0


def add_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("SpriteCameraData")
    camera = bpy.data.objects.new("SpriteCamera", data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.0, 0.0, 10.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    data.type = "ORTHO"
    data.ortho_scale = float(CONFIG["camera"]["orthographicScale"])
    bpy.context.scene.camera = camera
    return camera


def write_motion_report() -> None:
    scene = bpy.context.scene
    camera = bpy.data.objects["SpriteCamera"]
    rig = bpy.data.objects["VaultBoy2DRig"]
    tracks = {
        "shoulder": ("upper.raise", "head"),
        "elbow": ("upper.raise", "tail"),
        "wrist": ("forearm.raise", "tail"),
        "hand": ("hand.raise", "tail"),
        "root": ("root", "head"),
    }
    samples = []
    for frame in range(1, int(CONFIG["frames"]) + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        points = {}
        for label, (bone_name, endpoint) in tracks.items():
            bone = rig.pose.bones[bone_name]
            world = rig.matrix_world @ getattr(bone, endpoint)
            ndc = world_to_camera_view(scene, camera, world)
            points[label] = [round(ndc.x * 512, 4), round((1.0 - ndc.y) * 512, 4)]
        samples.append({"frame": frame, "points": points})
    scale = float(CONFIG["displaySize"]) / 512.0
    maximum = {}
    for label in tracks:
        steps = []
        for previous, current in zip(samples, samples[1:]):
            left = Vector(previous["points"][label])
            right = Vector(current["points"][label])
            steps.append((right - left).length * scale)
        maximum[label] = round(max(steps, default=0.0), 4)
    report = {
        "frames": CONFIG["frames"],
        "fps": CONFIG["fps"],
        "intervalMs": CONFIG["intervalMs"],
        "durationMs": (CONFIG["frames"] - 1) * CONFIG["intervalMs"],
        "maxConsecutiveStepDisplayPx": maximum,
        "samples": samples,
    }
    path = ROOT / "render" / "good" / "motion.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(1)


def build(quick: bool = False) -> None:
    clear_scene()
    rig = build_armature()
    build_raise_arm(rig)
    build_static_layer("GoodRestArm", "good-rest-arm.png", -0.012)
    build_static_layer("VaultBoy2DBody", "good-body.png", 0.0)
    animate_good(rig)
    add_camera()
    configure_render(quick)
    write_motion_report()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = int(CONFIG["frames"])
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), compress=True)


def render_good(quick: bool = False) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for stale in RAW_DIR.glob("*.png"):
        stale.unlink()
    configure_render(quick)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = int(CONFIG["frames"])
    scene.render.filepath = str(RAW_DIR) + "/"
    bpy.ops.render.render(animation=True)


def render_frame(frame: int, quick: bool = False) -> None:
    configure_render(quick)
    destination = ROOT / "previews" / f"good-frame-{frame:02d}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.frame_set(frame)
    bpy.context.scene.render.filepath = str(destination)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = parse_args()
    if args.build:
        build(args.quick)
    if args.render_good:
        render_good(args.quick)
    if args.render_frame is not None:
        render_frame(args.render_frame, args.quick)


if __name__ == "__main__":
    main()
