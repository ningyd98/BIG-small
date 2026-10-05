"""A separate DEVELOPMENT_ONLY outboard visual marker for observability trials.

The 100mm rigid offset is an excluded simulated visual attachment. Its mass and
contacts are absent, as in the existing marker assets. It preserves the cube's
physical extent, camera and controller; it does not certify a physical mount,
object association, calibration or continuous movement.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from cloud_edge_robot_arm.vision.pose_marker_assets import build_colored_pose_marker_xml

OUTBOARD_OFFSET_M = (0.1, 0.0, 0.0)


def build_outboard_pose_marker_xml(base_xml: bytes) -> bytes:
    """Move the existing strict ID7 pattern beyond the top-face hand occlusion.

    The immutable builder authenticates the unmodified physical v2 base. Only
    its 37 newly added zero-mass/no-contact geometries move; all original named
    nodes and their properties remain identical. Earlier generated assets stay
    separate and are never edited by this function.
    """
    tree = ET.fromstring(build_colored_pose_marker_xml(base_xml))
    body = tree.find("./worldbody/body[@name='object']")
    if body is None:
        raise ValueError("registered object body missing")
    moved = 0
    for geom in body.findall("geom"):
        name = geom.get("name", "")
        if not name.startswith("pose_marker_color_v2"):
            continue
        if any(geom.get(key) != "0" for key in ("mass", "density", "contype", "conaffinity")):
            raise ValueError("only visual-only marker geometry may move")
        x, y, z = (float(value) for value in geom.attrib["pos"].split())
        geom.set("pos", f"{x + OUTBOARD_OFFSET_M[0]:.10f} {y:.10f} {z:.10f}")
        geom.set("name", name.replace("pose_marker_color_v2", "pose_marker_outboard_v3", 1))
        moved += 1
    if moved != 37:
        raise ValueError("complete immutable marker pattern required")
    tree.insert(
        0,
        ET.Comment(
            "EXCLUDED DEVELOPMENT OUTBOARD V3: visual attachment; same physics/camera/controller; "
            "no physical mount, native or calibration admission"
        ),
    )
    ET.indent(tree, space="  ")
    return bytes(ET.tostring(tree, encoding="utf-8")) + b"\n"
