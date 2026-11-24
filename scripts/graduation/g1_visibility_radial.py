"""Registered 15 mm and 30 mm radial variants of the frozen low dual-marker assembly."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scripts.graduation import g1_dual_asset_v2 as v2
from scripts.graduation.perception_io import ROOT, sha

V2_PATH = (
    "assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_low_bracket_v2.xml"
)
V2_SHA = "a0bf24bdf2c7142e9aaeebdaf5dec02255bf06885dde0e2e56f009aaf89f9803"
V2_MASS = 0.10078432
DENSITY = 500.0
BEAM_WIDTH = 0.008
BEAM_HEIGHT = 0.002
AXES = ((7, 1), (8, 0))


def _distance(offset_mm):
    if type(offset_mm) is not int or offset_mm not in (15, 30):
        raise ValueError("a registered 15 mm or 30 mm radial displacement is required")
    return offset_mm / 1000


@lru_cache(maxsize=1)
def _parent():
    data = (ROOT / V2_PATH).read_bytes()
    if hashlib.sha256(data).hexdigest() != V2_SHA:
        raise ValueError("low-bracket parent XML differs from its registered digest")
    return data


def _vector(e, field):
    if field == "pos" and field not in e.attrib:
        return np.zeros(3)
    return np.array([float(v) for v in e.attrib[field].split()])


def _set_vector(e, field, value):
    e.set(field, " ".join(f"{v:.10f}" for v in value))


@lru_cache(maxsize=2, typed=True)
def build_xml(v2_xml, offset_mm):
    delta = _distance(offset_mm)
    if hashlib.sha256(v2_xml).hexdigest() != V2_SHA:
        raise ValueError("exact low-bracket v2 XML required")
    tree = ET.fromstring(v2_xml)
    obj = tree.find("./worldbody/body[@name='object']")
    for code, axis in AXES:
        prefix = f"g1_dual_id{code}_"
        for node in obj.findall("geom"):
            name = node.get("name", "")
            if not name.startswith(prefix):
                continue
            pos = _vector(node, "pos")
            if name == prefix + "crossbar":
                # The inner beam face stays on the cube. Its outer end follows the upright.
                half = _vector(node, "size")
                pos[axis] += delta / 2
                half[axis] += delta / 2
                _set_vector(node, "size", half)
                node.set("mass", f"{8 * np.prod(half) * DENSITY:.10f}")
            else:
                pos[axis] += delta
            _set_vector(node, "pos", pos)
    return ET.tostring(tree, encoding="utf-8") + b"\n"


def details(offset_mm):
    delta = _distance(offset_mm)
    radius = 100 + offset_mm
    family = f"g1_development_dual_id7_y{radius}_id8_x{radius}_low_bracket_v3"
    return {
        "family": family,
        "registration_id": f"g1-development-only-dual-7y{radius}-8x{radius}-low-bracket-v3",
        "asset_path": f"assets/robots/franka_panda/scene_{family}.xml",
        "asset_sha256": hashlib.sha256(build_xml(_parent(), offset_mm)).hexdigest(),
        "body_mass_kg": V2_MASS + 2 * BEAM_HEIGHT * BEAM_WIDTH * delta * DENSITY,
        "centers": {7: (0.0, radius / 1000, 0.03505), 8: (radius / 1000, 0.0, 0.03505)},
        "offset_mm": offset_mm,
    }


def _structural_names():
    return ["object_geom", *(f"g1_dual_id{code}_{part}" for code, _ in AXES for part in v2.PARTS)]


def verify_parts(tree, offset_mm):
    """Check the entire scene against the byte-pinned derivation and audit actual joining faces."""
    spec = details(offset_mm)
    root = tree.getroot() if isinstance(tree, ET.ElementTree) else tree
    if ET.tostring(root) != ET.tostring(ET.fromstring(build_xml(_parent(), offset_mm))):
        raise ValueError("scene differs from the registered radial assembly")
    obj = root.find("./worldbody/body[@name='object']")
    boxes = {}
    total = 0.0
    for name in _structural_names():
        node = obj.find(f"geom[@name='{name}']")
        center, half = _vector(node, "pos"), _vector(node, "size")
        mass = float(node.get("mass"))
        if (node.get("contype"), node.get("conaffinity")) != ("1", "3") or min(half) <= 0:
            raise ValueError(f"invalid contact geometry for {name}")
        if name != "object_geom" and not np.isclose(
            mass, DENSITY * 8 * np.prod(half), rtol=0, atol=1e-12
        ):
            raise ValueError(f"wrong material or dimensions for {name}")
        boxes[name] = (center - half, center + half)
        total += mass
    if abs(total - spec["body_mass_kg"]) > 1e-12:
        raise ValueError("total physical mass differs from the radial extension")
    return v2.common_faces(boxes)


def compiled_faces(model, offset_mm):
    """Independently check all seven massive pieces, their compiled inertia, and the six joins."""
    import mujoco

    spec = details(offset_mm)
    expected = ET.fromstring(build_xml(_parent(), offset_mm)).find(
        "./worldbody/body[@name='object']"
    )
    body_id = model.body("object").id
    boxes, components = {}, []
    for name in _structural_names():
        node = expected.find(f"geom[@name='{name}']")
        g = model.geom(name)
        pos, half = g.pos.copy(), g.size.copy()
        if not (
            g.bodyid[0] == body_id
            and (g.contype[0], g.conaffinity[0]) == (1, 3)
            and np.array_equal(g.quat, [1, 0, 0, 0])
            and np.allclose(pos, _vector(node, "pos"), atol=1e-12, rtol=0)
            and np.allclose(half, _vector(node, "size"), atol=1e-12, rtol=0)
        ):
            raise ValueError(f"compiled geometry differs for {name}")
        boxes[name] = (pos - half, pos + half)
        components.append((float(node.get("mass")), pos, half))
    total = sum(m for m, _, _ in components)
    com = sum(m * x for m, x, _ in components) / total
    tensor = np.zeros((3, 3))
    for mass, center, half in components:
        arm = center - com
        tensor += np.diag(mass / 3 * (half @ half - half * half)) + mass * (
            (arm @ arm) * np.eye(3) - np.outer(arm, arm)
        )
    rotation = np.zeros(9)
    mujoco.mju_quat2Mat(rotation, model.body_iquat[body_id])
    rotation = rotation.reshape(3, 3)
    compiled = rotation @ np.diag(model.body_inertia[body_id]) @ rotation.T
    if (
        abs(model.body_mass[body_id] - spec["body_mass_kg"]) > 1e-12
        or not np.allclose(model.body_ipos[body_id], com, rtol=0, atol=1e-12)
        or not np.allclose(compiled, tensor, rtol=0, atol=1e-9)
    ):
        raise ValueError("compiled object mass, center of mass or inertia differs")
    return v2.common_faces(boxes)


def geometry_for_screen(parent_v2_geometry, offset_mm):
    """Attach the new rigid transforms to the frozen camera for post-run static inspection."""
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration

    if (
        parent_v2_geometry["pose_marker"]["marked_asset_sha256"] != V2_SHA
        or parent_v2_geometry["marker_family"] != v2.FAMILY
    ):
        raise ValueError("static projection requires the frozen low dual registration")
    spec = details(offset_mm)
    result = deepcopy(parent_v2_geometry)
    result.update(
        marker_family=spec["family"],
        registration_id=spec["registration_id"],
        asset_path=spec["asset_path"],
    )
    result["pose_marker"]["marked_asset_sha256"] = spec["asset_sha256"]
    dual = result["development_dual"]
    dual["scene_asset_sha256"] = spec["asset_sha256"]
    dual["structure_mass_kg"] = spec["body_mass_kg"] - 0.08
    old_sources = dual["development_sources_sha256"]
    sources = {
        **old_sources,
        spec["asset_path"]: spec["asset_sha256"],
        "scripts/graduation/g1_visibility_radial.py": sha(Path(__file__)),
    }
    dual["development_sources_sha256"] = sources
    dual["development_source_generation"] = hashlib.sha256(
        json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    for code, _ in AXES:
        side = dual["markers"][str(code)]
        transform = np.eye(4)
        transform[:3, 3] = spec["centers"][code]
        side["object_T_marker"] = transform.ravel().tolist()
        side["marker_registration_hash"] = PoseMarkerRegistration(
            code, 0.075, spec["asset_sha256"]
        ).digest()
    result["marker_to_object"] = list(dual["markers"]["7"]["object_T_marker"])
    return result
