"""Versioned developmental colored-rim asset; no tracker or grasp admission.

The immutable v1 builder supplies the registered portable ID7 pattern. This
refinement changes only newly added zero-mass/no-contact visual geometry.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from cloud_edge_robot_arm.vision.pose_markers import MARKER_SIZE_M, build_pose_marked_xml

COLOR_MARKER_SIZE_M = 0.045
COLOR_QUIET_EXTENT_M = 0.060
COLOR_RIM_WIDTH_M = 0.005


def build_colored_pose_marker_xml(base_xml: bytes) -> bytes:
    """Require frozen v2 base and retain a visible5mm rim around a known ID7.

    Source/geometry bindings and actual decode/color observations are separate.
    Reproducible visual appearance and physical equivalence do not certify
    native whole-object association, sensor error bounds or continuous motion.
    """
    tree = ET.fromstring(build_pose_marked_xml(base_xml))
    body = tree.find("./worldbody/body[@name='object']")
    if body is None:
        raise ValueError("registered object body missing")
    changed = 0
    ratio = COLOR_MARKER_SIZE_M / MARKER_SIZE_M
    for geom in body.findall("geom"):
        name = geom.get("name", "")
        if name == "pose_marker_quiet_v1":
            geom.set("name", "pose_marker_color_v2_quiet")
            geom.set(
                "size",
                f"{COLOR_QUIET_EXTENT_M / 2:.10f} {COLOR_QUIET_EXTENT_M / 2:.10f} 0.0000100000",
            )
            changed += 1
        elif name.startswith("pose_marker_v1_r"):
            geom.set("name", "pose_marker_color_v2" + name.removeprefix("pose_marker_v1"))
            for key in ("pos", "size"):
                x, y, z = (float(value) for value in geom.attrib[key].split())
                geom.set(key, f"{x * ratio:.10f} {y * ratio:.10f} {z:.10f}")
            changed += 1
    if changed != 37:
        raise ValueError("immutable marker generation layout unavailable")
    tree.insert(
        0,
        ET.Comment(
            "DEVELOPMENTAL COLOR RIM MARKER V2: visual only; no grasp/native calibration acceptance"
        ),
    )
    ET.indent(tree, space="  ")
    return bytes(ET.tostring(tree, encoding="utf-8")) + b"\n"
