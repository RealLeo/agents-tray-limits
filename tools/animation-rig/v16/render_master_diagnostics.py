#!/usr/bin/env python3
"""Render non-runtime Blender rig and weight-map review images for master-v3."""

from __future__ import annotations

import json
import os
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
CONFIG_NAME = os.environ.get("AGENTS_TRAY_RIG_CONFIG", "master-rig-config.json")
CONFIG = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
OUTPUT = ROOT / CONFIG.get("previewDir", "previews/master-good")
PREFIX = CONFIG.get("previewPrefix", "master-v3")
ARM_FILE = CONFIG.get("armFile", "good-arm-master-v3.png")
OVERLAY_COLLECTION = "MasterV3DiagnosticOverlay"


def emission_material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return material


def curve_segment(collection, name: str, start: Vector, end: Vector, material, width=0.008):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = width
    data.bevel_resolution = 4
    spline = data.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (*start.xy, 0.18, 1.0)
    spline.points[1].co = (*end.xy, 0.18, 1.0)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def joint_marker(collection, name: str, point: Vector, material, radius=0.022):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "2D"
    data.resolution_u = 20
    data.bevel_depth = 0.004
    data.bevel_resolution = 3
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(3)
    kappa = 0.5522847498
    points = ((radius, 0), (0, radius), (-radius, 0), (0, -radius))
    for point_data, (x, y) in zip(spline.bezier_points, points):
        point_data.co = (point.x + x, point.y + y, 0.2)
        point_data.handle_left_type = "AUTO"
        point_data.handle_right_type = "AUTO"
    spline.use_cyclic_u = True
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def make_weight_material(arm: bpy.types.Object):
    color_attribute = arm.data.color_attributes.get("ForearmWeightReview")
    if color_attribute:
        arm.data.color_attributes.remove(color_attribute)
    color_attribute = arm.data.color_attributes.new(
        name="ForearmWeightReview", type="FLOAT_COLOR", domain="POINT"
    )
    group = arm.vertex_groups["forearm.raise"]
    for vertex in arm.data.vertices:
        try:
            weight = group.weight(vertex.index)
        except RuntimeError:
            weight = 0.0
        # Blue -> cyan -> yellow -> red, keeping the transition easy to read.
        red = min(1.0, max(0.0, 2.0 * weight))
        blue = min(1.0, max(0.0, 2.0 * (1.0 - weight)))
        green = 1.0 - abs(2.0 * weight - 1.0)
        color_attribute.data[vertex.index].color = (red, green, blue, 1.0)

    material = bpy.data.materials.new("MAT_MASTER_V3_WEIGHT_REVIEW")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    attribute = nodes.new("ShaderNodeVertexColor")
    attribute.layer_name = color_attribute.name
    texture = nodes.new("ShaderNodeTexImage")
    image = next(
        image for image in bpy.data.images
        if Path(bpy.path.abspath(image.filepath)).name == ARM_FILE
    )
    texture.image = image
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    mix = nodes.new("ShaderNodeMixShader")
    material.node_tree.links.new(attribute.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(texture.outputs["Alpha"], mix.inputs[0])
    material.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    material.node_tree.links.new(emission.outputs[0], mix.inputs[2])
    material.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    return material, color_attribute


def render_to(path: Path):
    scene = bpy.context.scene
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    original_frame = scene.frame_current
    original_transparent = scene.render.film_transparent
    original_resolution = (scene.render.resolution_x, scene.render.resolution_y)
    scene.frame_set(12)
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.film_transparent = False
    scene.world.color = (0.012, 0.02, 0.014)

    old_collection = bpy.data.collections.get(OVERLAY_COLLECTION)
    if old_collection:
        bpy.data.collections.remove(old_collection, do_unlink=True)
    collection = bpy.data.collections.new(OVERLAY_COLLECTION)
    scene.collection.children.link(collection)
    orange = emission_material("MAT_MASTER_V3_RIG_ORANGE", (1.0, 0.19, 0.03, 1.0))
    green = emission_material("MAT_MASTER_V3_RIG_GREEN", (0.25, 1.0, 0.3, 1.0))
    rig = bpy.data.objects["VaultBoyMasterRig"]
    for bone_name in ("upper.raise", "forearm.raise", "hand.raise"):
        bone = rig.pose.bones[bone_name]
        start = rig.matrix_world @ bone.head
        end = rig.matrix_world @ bone.tail
        curve_segment(collection, f"Review_{bone_name}", start, end, orange)
        joint_marker(collection, f"ReviewJoint_{bone_name}", start, green)
    hand_end = rig.matrix_world @ rig.pose.bones["hand.raise"].tail
    joint_marker(collection, "ReviewJoint_hand_end", hand_end, green)
    render_to(OUTPUT / f"good-rig-overlay-{PREFIX}.png")

    for obj in collection.objects:
        obj.hide_render = True
    arm = bpy.data.objects["VaultBoyMasterArm"]
    original_materials = list(arm.data.materials)
    arm.data.materials.clear()
    weight_material, color_attribute = make_weight_material(arm)
    arm.data.materials.append(weight_material)
    render_to(OUTPUT / f"good-weight-map-{PREFIX}.png")

    arm.data.materials.clear()
    for material in original_materials:
        arm.data.materials.append(material)
    arm.data.color_attributes.remove(color_attribute)
    bpy.data.collections.remove(collection, do_unlink=True)
    bpy.data.materials.remove(weight_material, do_unlink=True)
    scene.render.film_transparent = original_transparent
    scene.render.resolution_x, scene.render.resolution_y = original_resolution
    scene.frame_set(original_frame)
    return {
        "rig_overlay": str(OUTPUT / f"good-rig-overlay-{PREFIX}.png"),
        "weight_map": str(OUTPUT / f"good-weight-map-{PREFIX}.png"),
    }


if __name__ == "__main__":
    print(main())
