#!/usr/bin/env python3
"""Build and render the registered master-v3 2D Vault Boy rig in Blender."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
CONFIG_NAME = os.environ.get("AGENTS_TRAY_RIG_CONFIG", "master-rig-config.json")
CONFIG = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
SOURCE_DIR = ROOT / CONFIG.get("sourceDir", "sources/master-v3")
BLEND_PATH = ROOT / CONFIG.get("blendFile", "vault-boy-2d-rig-master-v3.blend")
RENDER_DIR = ROOT / CONFIG.get("renderDir", "render/master-good")
RAW_DIR = RENDER_DIR / "raw"
PREVIEW_DIR = ROOT / CONFIG.get("previewDir", "previews/master-good")
PREVIEW_PREFIX = CONFIG.get("previewPrefix", "master-v3")
REFERENCE_FILE = CONFIG.get("referenceFile", "good-reference-master-v3.png")
BODY_FILE = CONFIG.get("bodyFile", "good-body-master-v3.png")
ARM_FILE = CONFIG.get("armFile", "good-arm-master-v3.png")


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in (
        bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
        bpy.data.armatures, bpy.data.actions, bpy.data.images,
    ):
        for datablock in list(collection):
            if datablock.users == 0:
                collection.remove(datablock)


def pixel_to_world(x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
    center_x, center_y = CONFIG["camera"]["centerPixel"]
    scale = float(CONFIG["pixelScale"])
    return ((x - center_x) * scale, (center_y - y) * scale, z)


def world_from_pixel(point: list[int] | tuple[int, int], z: float = 0.0) -> Vector:
    return Vector(pixel_to_world(float(point[0]), float(point[1]), z))


def texture_material(
    name: str, path: Path, render_method: str = "DITHERED",
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(path), check_existing=True)
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
        material.surface_render_method = render_method
    return material


def add_full_canvas_plane(
    name: str, source_name: str, z: float, render_method: str = "DITHERED",
) -> bpy.types.Object:
    path = SOURCE_DIR / source_name
    width, height = CONFIG["canvas"]
    vertices = [
        pixel_to_world(0, 0, z), pixel_to_world(width, 0, z),
        pixel_to_world(width, height, z), pixel_to_world(0, height, z),
    ]
    mesh = bpy.data.meshes.new(f"{name}Data")
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(
        texture_material(f"MAT_{name.upper()}", path, render_method)
    )
    uv = mesh.uv_layers.new(name="UVMap")
    for loop_index, value in enumerate(((0, 1), (1, 1), (1, 0), (0, 0))):
        uv.data[loop_index].uv = value
    return obj


def add_edit_bone(edit_bones, name: str, head, tail, parent=None, connected=False):
    bone = edit_bones.new(name)
    bone.head = world_from_pixel(head)
    bone.tail = world_from_pixel(tail)
    if parent:
        bone.parent = edit_bones[parent]
        bone.use_connect = bool(connected)
    return bone


def build_armature() -> bpy.types.Object:
    arm = CONFIG["arm"]
    data = bpy.data.armatures.new("VaultBoyMasterRigData")
    rig = bpy.data.objects.new("VaultBoyMasterRig", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = data.edit_bones
    add_edit_bone(bones, "root", (256, 476), (256, 300))
    add_edit_bone(bones, "torso", (256, 300), (256, 170), "root")
    add_edit_bone(bones, "neck", (256, 170), (256, 115), "torso")
    add_edit_bone(bones, "upper.raise", arm["shoulder"], arm["elbow"], "torso")
    add_edit_bone(
        bones, "forearm.raise", arm["elbow"], arm["wrist"],
        "upper.raise", connected=True,
    )
    add_edit_bone(
        bones, "hand.raise", arm["wrist"], arm["hand"],
        "forearm.raise", connected=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    # Keep the single thumbs-up drawing at a stable screen orientation while
    # its wrist follows the IK chain. Inheriting forearm rotation caused a
    # branch-dependent 180-degree hand flip during the behind-body exit.
    data.bones["hand.raise"].use_inherit_rotation = False
    rig.show_in_front = True
    return rig


def add_control(name: str, point: list[int], display: str) -> bpy.types.Object:
    control = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(control)
    control.location = world_from_pixel(point)
    control.empty_display_type = display
    control.empty_display_size = 0.12
    control.hide_render = True
    control.lock_location[2] = True
    return control


def configure_ik(rig: bpy.types.Object) -> tuple[bpy.types.Object, bpy.types.Object]:
    arm = CONFIG["arm"]
    ik_target = add_control("CTRL_IK_Raise", arm["wrist"], "CIRCLE")
    pole_target = add_control("CTRL_Pole_Raise", arm["pole"], "SPHERE")
    constraint = rig.pose.bones["forearm.raise"].constraints.new("IK")
    constraint.name = "GoodRaiseIK"
    constraint.target = ik_target
    constraint.pole_target = pole_target
    constraint.chain_count = 2
    constraint.use_tail = True
    # The chain is drawn left-to-right in image space; pi selects the bind-pose
    # elbow branch instead of mirroring the elbow above the shoulder-wrist line.
    constraint.pole_angle = float(arm.get("poleAngle", math.pi))
    return ik_target, pole_target


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def point_segment_distance(point: Vector, start: Vector, end: Vector) -> float:
    segment = end - start
    if segment.length_squared <= 1e-9:
        return (point - start).length
    amount = max(0.0, min(1.0, (point - start).dot(segment) / segment.length_squared))
    return (point - (start + segment * amount)).length


def arm_weights(x: float, y: float | None = None) -> dict[str, float]:
    if CONFIG["arm"].get("weightMode") == "rigid":
        return {"upper.raise": 1.0}
    if CONFIG["arm"].get("weightMode") == "segments" and y is not None:
        arm = CONFIG["arm"]
        point = Vector((x, y))
        segments = {
            "upper.raise": (Vector(arm["shoulder"]), Vector(arm["elbow"])),
            "forearm.raise": (Vector(arm["elbow"]), Vector(arm["wrist"])),
            "hand.raise": (Vector(arm["wrist"]), Vector(arm["hand"])),
        }
        falloff = float(arm.get("weightFalloff", 20.0))
        scores = {
            name: math.exp(
                -point_segment_distance(point, *segment) ** 2 /
                (2.0 * falloff ** 2)
            )
            for name, segment in segments.items()
        }
        total = sum(scores.values())
        return {name: score / total for name, score in scores.items()}
    hand = 1.0 - smoothstep((x - 142.0) / 22.0)
    upper = smoothstep((x - 176.0) / 34.0)
    forearm = max(0.0, 1.0 - hand - upper)
    total = hand + forearm + upper
    if total <= 0.0:
        return {"forearm.raise": 1.0}
    return {
        "upper.raise": upper / total,
        "forearm.raise": forearm / total,
        "hand.raise": hand / total,
    }


def build_arm_mesh(rig: bpy.types.Object) -> bpy.types.Object:
    path = SOURCE_DIR / ARM_FILE
    left, top, right, bottom = CONFIG["arm"]["bbox"]
    step = int(CONFIG["gridStep"])
    xs = list(range(left, right, step))
    ys = list(range(top, bottom, step))
    if xs[-1] != right:
        xs.append(right)
    if ys[-1] != bottom:
        ys.append(bottom)
    front_z = float(CONFIG["arm"].get("frontZ", 0.02))
    projection_scale = 1.0
    if (
        CONFIG["arm"].get("registerFrontPlane", False)
        and CONFIG.get("camera", {}).get("type") == "PERSP"
    ):
        camera_distance = float(CONFIG["camera"]["distance"])
        projection_scale = (camera_distance - front_z) / camera_distance
    vertices = []
    for y in ys:
        for x in xs:
            vertex = Vector(pixel_to_world(x, y, front_z))
            vertex.x *= projection_scale
            vertex.y *= projection_scale
            vertices.append(tuple(vertex))
    columns = len(xs)
    faces = []
    for row in range(len(ys) - 1):
        for column in range(columns - 1):
            index = row * columns + column
            faces.append((index, index + 1, index + columns + 1, index + columns))
    mesh = bpy.data.meshes.new("VaultBoyMasterArmData")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("VaultBoyMasterArm", mesh)
    bpy.context.collection.objects.link(obj)
    arm_render_method = CONFIG.get("materials", {}).get("arm", "DITHERED")
    obj.data.materials.append(
        texture_material("MAT_VAULT_BOY_MASTER_ARM", path, arm_render_method)
    )

    width, height = CONFIG["canvas"]
    uv = mesh.uv_layers.new(name="UVMap")
    vertex_pixels: list[tuple[int, int]] = []
    for y in ys:
        for x in xs:
            vertex_pixels.append((x, y))
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            x, y = vertex_pixels[mesh.loops[loop_index].vertex_index]
            uv.data[loop_index].uv = (x / width, 1.0 - y / height)

    groups = {
        name: obj.vertex_groups.new(name=name)
        for name in ("upper.raise", "forearm.raise", "hand.raise")
    }
    for index, (x, y) in enumerate(vertex_pixels):
        for name, weight in arm_weights(float(x), float(y)).items():
            if weight > 0.0001:
                groups[name].add([index], weight, "REPLACE")

    obj.shape_key_add(name="Basis")
    shoulder_key = obj.shape_key_add(name="ShoulderCorrective")
    elbow_key = obj.shape_key_add(name="ElbowCorrective")
    shoulder = Vector(CONFIG["arm"]["shoulder"])
    elbow = Vector(CONFIG["arm"]["elbow"])
    scale = float(CONFIG["pixelScale"])
    for index, (x, y) in enumerate(vertex_pixels):
        point = Vector((x, y))
        shoulder_weight = max(0.0, 1.0 - (point - shoulder).length / 38.0) ** 2
        elbow_weight = max(0.0, 1.0 - (point - elbow).length / 34.0) ** 2
        shoulder_key.data[index].co.x += 3.0 * scale * shoulder_weight
        elbow_key.data[index].co.y -= 2.0 * scale * elbow_weight

    modifier = obj.modifiers.new("VaultBoyMasterArmature", "ARMATURE")
    modifier.object = rig
    modifier.use_deform_preserve_volume = False
    depth_config = CONFIG["arm"].get("depth", {})
    for label, group_name in (
        ("Upper", "upper.raise"),
        ("Forearm", "forearm.raise"),
        ("Hand", "hand.raise"),
    ):
        depth_modifier = obj.modifiers.new(f"Depth{label}", "DISPLACE")
        depth_modifier.vertex_group = group_name
        # The arm object and rig have identity transforms, so post-armature
        # object-space Z is the camera/depth axis for every pose.
        depth_modifier.direction = "Z"
        depth_modifier.mid_level = 0.0
        depth_modifier.strength = float(depth_config.get(label.lower(), 0.0))
    obj.parent = rig
    return obj


def keyframe_object_location(obj: bpy.types.Object, frame: int, point: Vector) -> None:
    obj.location = point
    obj.keyframe_insert(data_path="location", frame=frame)


def keyframe_shape(key, frame: int, value: float) -> None:
    key.value = value
    key.keyframe_insert(data_path="value", frame=frame)


def depth_values(value: object) -> dict[str, float]:
    if isinstance(value, dict):
        return {
            label: float(value[label]) for label in ("upper", "forearm", "hand")
        }
    scalar = float(value)
    return {label: scalar for label in ("upper", "forearm", "hand")}


def keyframe_depth_modifiers(
    obj: bpy.types.Object, frame: int, values: dict[str, float],
) -> None:
    depth_config = CONFIG["arm"]["depth"]
    for label in ("Upper", "Forearm", "Hand"):
        modifier = obj.modifiers[f"Depth{label}"]
        modifier.strength = (
            float(depth_config[label.lower()]) * float(values[label.lower()])
        )
        modifier.keyframe_insert(data_path="strength", frame=frame)


def interpolate_trajectory(frame: int) -> dict[str, object]:
    trajectory = sorted(CONFIG["arm"]["trajectory"], key=lambda item: item["frame"])
    if frame <= int(trajectory[0]["frame"]):
        return dict(trajectory[0])
    if frame >= int(trajectory[-1]["frame"]):
        return dict(trajectory[-1])
    for left, right in zip(trajectory, trajectory[1:]):
        left_frame = int(left["frame"])
        right_frame = int(right["frame"])
        if left_frame <= frame <= right_frame:
            progress = smoothstep((frame - left_frame) / (right_frame - left_frame))
            left_target = Vector(left["target"])
            right_target = Vector(right["target"])
            target = left_target.lerp(right_target, progress)
            left_depth = depth_values(left["depth"])
            right_depth = depth_values(right["depth"])
            return {
                "frame": frame,
                "target": [target.x, target.y],
                "depth": {
                    label: left_depth[label]
                    + (right_depth[label] - left_depth[label]) * progress
                    for label in ("upper", "forearm", "hand")
                },
                "shoulderCorrective": float(left["shoulderCorrective"]) + (
                    float(right["shoulderCorrective"])
                    - float(left["shoulderCorrective"])
                ) * progress,
                "elbowCorrective": float(left["elbowCorrective"]) + (
                    float(right["elbowCorrective"])
                    - float(left["elbowCorrective"])
                ) * progress,
            }
    raise ValueError(f"frame {frame} is outside the configured trajectory")


def iter_action_fcurves(action: bpy.types.Action):
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                yield from channelbag.fcurves


def animate_good(rig: bpy.types.Object, target: bpy.types.Object, arm_obj: bpy.types.Object) -> None:
    rig.animation_data_create()
    action_prefix = CONFIG.get("previewPrefix", "master-v3")
    rig.animation_data.action = bpy.data.actions.new(f"Good_{action_prefix}")
    target.animation_data_create()
    target.animation_data.action = bpy.data.actions.new(f"GoodTarget_{action_prefix}")
    frames = int(CONFIG["frames"])
    shoulder_key = arm_obj.data.shape_keys.key_blocks["ShoulderCorrective"]
    elbow_key = arm_obj.data.shape_keys.key_blocks["ElbowCorrective"]

    for frame in range(1, frames + 1):
        pose = interpolate_trajectory(frame)
        point = world_from_pixel(pose["target"])
        keyframe_object_location(target, frame, point)
        keyframe_depth_modifiers(arm_obj, frame, depth_values(pose["depth"]))
        keyframe_shape(shoulder_key, frame, float(pose["shoulderCorrective"]))
        keyframe_shape(elbow_key, frame, float(pose["elbowCorrective"]))

    for animated in (
        target.animation_data.action,
        arm_obj.animation_data.action,
        arm_obj.data.shape_keys.animation_data.action,
    ):
        for fcurve in iter_action_fcurves(animated):
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = "BEZIER"
                keyframe.handle_left_type = "AUTO_CLAMPED"
                keyframe.handle_right_type = "AUTO_CLAMPED"


def add_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("SpriteCameraData")
    camera = bpy.data.objects.new("SpriteCamera", data)
    bpy.context.collection.objects.link(camera)
    camera_config = CONFIG["camera"]
    camera_distance = float(camera_config.get("distance", 10.0))
    camera.location = (0.0, 0.0, camera_distance)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_type = camera_config.get("type", "ORTHO")
    data.type = camera_type
    if camera_type == "PERSP":
        data.sensor_fit = "VERTICAL"
        plane_height = float(camera_config["planeHeight"])
        data.angle_y = 2.0 * math.atan(plane_height / (2.0 * camera_distance))
        data.clip_start = 0.01
        data.clip_end = 100.0
    else:
        data.ortho_scale = float(camera_config["orthographicScale"])
    bpy.context.scene.camera = camera
    return camera


def configure_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    size = int(CONFIG["renderSize"])
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    scene.render.use_file_extension = True
    scene.render.filter_size = 0.01
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.fps = int(CONFIG["fps"])
    scene.render.fps_base = 1.0


def lock_reference(reference: bpy.types.Object) -> None:
    reference.hide_render = True
    reference.hide_set(True)
    reference.lock_location = (True, True, True)
    reference.lock_rotation = (True, True, True)
    reference.lock_scale = (True, True, True)
    reference["role"] = "locked-pixel-registration-reference"


def write_motion_report(rig: bpy.types.Object, arm_obj: bpy.types.Object) -> None:
    scene = bpy.context.scene
    camera = bpy.data.objects["SpriteCamera"]
    tracks = {
        "shoulder": ("upper.raise", "head"),
        "elbow": ("upper.raise", "tail"),
        "wrist": ("forearm.raise", "tail"),
        "hand": ("hand.raise", "tail"),
        "root": ("root", "head"),
    }
    samples = []
    camera_distance = float(CONFIG["camera"].get("distance", 10.0))
    hand_depth = float(CONFIG["arm"].get("depth", {}).get("hand", 0.0))
    front_z = float(CONFIG["arm"].get("frontZ", 0.02))
    for frame in range(1, int(CONFIG["frames"]) + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        points = {}
        for label, (bone_name, endpoint) in tracks.items():
            bone = rig.pose.bones[bone_name]
            world = rig.matrix_world @ getattr(bone, endpoint)
            ndc = world_to_camera_view(scene, camera, world)
            points[label] = [round(ndc.x * 512, 4), round((1.0 - ndc.y) * 512, 4)]
        segment_depths = {}
        for label in ("Upper", "Forearm", "Hand"):
            modifier = arm_obj.modifiers[f"Depth{label}"]
            configured = float(
                CONFIG["arm"].get("depth", {}).get(label.lower(), 0.0)
            )
            segment_depths[label.lower()] = (
                modifier.strength / configured if abs(configured) > 1e-9 else 0.0
            )
        hand_modifier = arm_obj.modifiers["DepthHand"]
        depth_strength = segment_depths["hand"]
        hand_z = front_z + hand_modifier.strength
        registration_scale = (
            (camera_distance - front_z) / camera_distance
            if CONFIG["arm"].get("registerFrontPlane", False) else 1.0
        )
        apparent_hand_scale = (
            camera_distance / (camera_distance - hand_z) * registration_scale
        )
        samples.append({
            "frame": frame,
            "points": points,
            "depthStrength": round(depth_strength, 6),
            "depthStrengths": {
                name: round(value, 6) for name, value in segment_depths.items()
            },
            "handZ": round(hand_z, 6),
            "apparentHandScale": round(apparent_hand_scale, 6),
        })
    display_scale = float(CONFIG["displaySize"]) / 512.0
    maximum = {}
    for label in tracks:
        steps = []
        for previous, current in zip(samples, samples[1:]):
            left = Vector(previous["points"][label])
            right = Vector(current["points"][label])
            steps.append((right - left).length * display_scale)
        maximum[label] = round(max(steps, default=0.0), 4)
    report = {
        "frames": CONFIG["frames"],
        "fps": CONFIG["fps"],
        "intervalMs": CONFIG["intervalMs"],
        "durationMs": (CONFIG["frames"] - 1) * CONFIG["intervalMs"],
        "maxConsecutiveStepDisplayPx": maximum,
        "samples": samples,
    }
    path = RENDER_DIR / "motion.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(1)


def build() -> dict[str, object]:
    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    reference = add_full_canvas_plane(
        "VaultBoyMasterReference", REFERENCE_FILE, -0.04,
    )
    lock_reference(reference)
    body_render_method = CONFIG.get("materials", {}).get("body", "DITHERED")
    add_full_canvas_plane(
        "VaultBoyMasterBody", BODY_FILE, 0.0, body_render_method,
    )
    rig = build_armature()
    ik_target, _pole_target = configure_ik(rig)
    arm_obj = build_arm_mesh(rig)
    animate_good(rig, ik_target, arm_obj)
    add_camera()
    configure_render()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = int(CONFIG["frames"])
    scene.frame_set(int(CONFIG["frames"]))
    bpy.context.view_layer.update()
    write_motion_report(rig, arm_obj)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), compress=True)
    bpy.ops.file.pack_all()
    for image in bpy.data.images:
        if image.source == "FILE" and image.filepath:
            image.filepath = f"//{CONFIG.get('sourceDir', 'sources/master-v3')}/{Path(image.filepath).name}"
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), compress=True)
    return {
        "blend": str(BLEND_PATH),
        "objects": len(bpy.data.objects),
        "bones": len(rig.data.bones),
        "frames": int(CONFIG["frames"]),
    }


def render_good() -> dict[str, object]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for stale in RAW_DIR.glob("*.png"):
        stale.unlink()
    configure_render()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = int(CONFIG["frames"])
    scene.render.filepath = str(RAW_DIR) + "/"
    bpy.ops.render.render(animation=True)
    return {"raw_dir": str(RAW_DIR), "frames": len(list(RAW_DIR.glob("*.png")))}


def render_review_frame(frame: int) -> dict[str, object]:
    configure_render()
    destination = PREVIEW_DIR / f"good-frame-{PREVIEW_PREFIX}-{frame:02d}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.frame_set(frame)
    bpy.context.scene.render.filepath = str(destination)
    bpy.ops.render.render(write_still=True)
    return {"frame": frame, "path": str(destination)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--render-good", action="store_true")
    parser.add_argument("--review-frames", action="store_true")
    arguments = parser.parse_args(
        __import__("sys").argv[__import__("sys").argv.index("--") + 1:]
        if "--" in __import__("sys").argv else []
    )
    if arguments.build:
        print(build())
    if arguments.render_good:
        print(render_good())
    if arguments.review_frames:
        review_frames = sorted({1, 6, 14, 24, int(CONFIG["frames"])})
        print([render_review_frame(frame) for frame in review_frames])
    if not (arguments.build or arguments.render_good or arguments.review_frames):
        parser.error("select --build, --render-good, or --review-frames")


if __name__ == "__main__":
    main()
