"""A rigid, mass-bearing pair of end-mounted ArUco boards for the fixed-wrist development scene."""

from __future__ import annotations

import hashlib
import itertools
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

FAMILY = "g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1"
REGISTRATION_ID = "g1-development-only-dual-7minusx130-8plusx130-end-wings-v1"
ASSET_PATH = f"assets/robots/franka_panda/scene_{FAMILY}.xml"
PARENT_ASSET = (
    "assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml"
)
PARENT_ASSET_SHA = "14a1a9fc2d2993fa28fbb873e25d1e9672c07b7433b3cb9ad27f07434c75efbe"
PARENT_PROVIDER_SHA = "56b028d0f8463ab75d0e693f8f4299c516bce1f68b9161fa86fdd073b7e73115"
PARENT_GENERATION = "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212"
PROVIDER = "scripts/graduation/g1_dual_asset.py"
HELPER = "scripts/graduation/g1_clearance_mount.py"
CENTERS = {7: (-0.130, 0.0, 0.03505), 8: (0.130, 0.0, 0.03505)}
BODY_MASS_KG = 0.10126432
PARTS = ("plate", "crossbar", "upright")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _vector(node, field):
    return np.fromstring(node.get(field, "0 0 0"), sep=" ")


def _set_vector(node, field, vector):
    node.set(field, " ".join(f"{x:.10f}" for x in vector))


@lru_cache(maxsize=1)
def build_xml(parent):
    """Move ID7 from +Y to −X, retaining ink orientation and the remaining scene."""
    if _sha(parent) != PARENT_ASSET_SHA:
        raise ValueError("exact 130 mm parent MJCF required")
    root = ET.fromstring(parent)
    obj = root.find("./worldbody/body[@name='object']")
    for node in obj.findall("geom"):
        name = node.get("name", "")
        if not name.startswith("g1_dual_id7_"):
            continue
        x, y, z = _vector(node, "pos")
        if name in ("g1_dual_id7_crossbar", "g1_dual_id7_upright"):
            _set_vector(node, "pos", (-y, x, z))
            _set_vector(node, "size", _vector(node, "size")[[1, 0, 2]])
        else:
            # Translating the complete print preserves its orientation, including ordered corners.
            _set_vector(node, "pos", (x - 0.130, y - 0.130, z))
    return ET.tostring(root, encoding="utf-8") + b"\n"


def _names():
    return ["object_geom", *(f"g1_dual_id{i}_{s}" for i in CENTERS for s in PARTS)]


def _joining_faces(boxes):
    """Measure the six mechanical interfaces from axis-aligned bounds in object coordinates."""
    for a, b in itertools.combinations(boxes, 2):
        lo0, hi0 = boxes[a]
        lo1, hi1 = boxes[b]
        if min(np.minimum(hi0, hi1) - np.maximum(lo0, lo1)) > 1e-12:
            raise ValueError(f"positive-volume overlap: {a}/{b}")
    areas = {}
    for code, sign in ((7, -1), (8, 1)):
        prefix = f"g1_dual_id{code}_"
        for first, second, axis in (
            ("object_geom", prefix + "crossbar", 0),
            (prefix + "crossbar", prefix + "upright", 2),
            (prefix + "upright", prefix + "plate", 2),
        ):
            lo0, hi0 = boxes[first]
            lo1, hi1 = boxes[second]
            gap = lo0[axis] - hi1[axis] if axis == 0 and sign < 0 else lo1[axis] - hi0[axis]
            contact = np.delete(np.minimum(hi0, hi1) - np.maximum(lo0, lo1), axis)
            if abs(gap) > 1e-12 or min(contact) <= 0:
                raise ValueError(f"disconnected load path: {first}/{second}")
            areas[first + "/" + second] = float(np.prod(contact))
    return areas


def verify_parts(root):
    expected = build_xml((Path(__file__).resolve().parents[2] / PARENT_ASSET).read_bytes())
    if ET.tostring(root) != ET.tostring(ET.fromstring(expected)):
        raise ValueError("unregistered physical end-wing assembly")
    obj = root.find("./worldbody/body[@name='object']")
    boxes = {}
    mass = 0.0
    for name in _names():
        node = obj.find(f"geom[@name='{name}']")
        center, half = _vector(node, "pos"), _vector(node, "size")
        piece_mass = float(node.get("mass"))
        if (node.get("contype"), node.get("conaffinity")) != ("1", "3"):
            raise ValueError("wrong structural collision settings: " + name)
        if name != "object_geom" and abs(piece_mass - 500 * 8 * np.prod(half)) > 1e-12:
            raise ValueError("wrong structural material mass: " + name)
        mass += piece_mass
        boxes[name] = (center - half, center + half)
    if abs(mass - BODY_MASS_KG) > 1e-12:
        raise ValueError("wrong assembly mass")
    return _joining_faces(boxes)


def compiled_faces(model):
    import mujoco

    boxes = {}
    obj = model.body("object").id
    for name in _names():
        geom = model.geom(name)
        if not (
            int(geom.type[0]) == mujoco.mjtGeom.mjGEOM_BOX
            and geom.bodyid[0] == obj
            and (geom.contype[0], geom.conaffinity[0]) == (1, 3)
            and np.array_equal(geom.quat, [1, 0, 0, 0])
        ):
            raise ValueError("unexpected compiled structural geometry: " + name)
        boxes[name] = (geom.pos - geom.size, geom.pos + geom.size)
    return _joining_faces(boxes)


def provider_bytes(original):
    """Adapt the pinned native provider and retain its assembly and source audits."""
    if _sha(original) != PARENT_PROVIDER_SHA:
        raise ValueError("exact frozen 130 mm parent provider required")
    source = original.decode()
    start = source.index("from scripts.graduation import g1_visibility_radial as _radial")
    end = source.index("BASE_ASSET_PATH =", start)
    source = (
        source[:start]
        + (
            "from scripts.graduation import g1_clearance_mount as _mount\n\n"
            "FAMILY = _mount.FAMILY\nREGISTRATION_ID = _mount.REGISTRATION_ID\n"
            "ASSET_PATH = _mount.ASSET_PATH\n"
        )
        + source[end:]
    )
    edits = {
        'ASSET_SHA = _radial_spec["asset_sha256"]': (
            "ASSET_SHA = hashlib.sha256(_mount.build_xml(\n"
            "    (Path(__file__).resolve().parents[2] / _mount.PARENT_ASSET).read_bytes()\n"
            ")).hexdigest()"
        ),
        '{int(k): tuple(v) for k,v in _radial_spec["centers"].items()}': "_mount.CENTERS",
        'BODY_MASS_KG = _radial_spec["body_mass_kg"]': "BODY_MASS_KG = _mount.BODY_MASS_KG",
        "POSES = ": "SOURCE_FILES += (_mount.HELPER, _mount.PARENT_ASSET)\nPOSES = ",
        " / _low_bracket.ASSET_PATH).read_bytes()": " / _mount.PARENT_ASSET).read_bytes()",
        "_low_bracket.ASSET_SHA:": "_mount.PARENT_ASSET_SHA:",
        "exact low-bracket V2 source required": "exact 130 mm end-wing parent required",
        "return _radial.build_xml(original, RADIAL_OFFSET_MM)": "return _mount.build_xml(original)",
        (
            'schema="g1.development.dual-registration.radial.v3",\n'
            "                radial_offset_mm=RADIAL_OFFSET_MM,"
        ): ('schema="g1.development.dual-registration.end-wings.v1",'),
        "_radial.verify_parts(xml, RADIAL_OFFSET_MM)": "_mount.verify_parts(xml)",
        "_radial.compiled_faces(model, RADIAL_OFFSET_MM)": "_mount.compiled_faces(model)",
        "g1.development.compiled-dual-asset.v2": "g1.development.compiled-end-wings.v1",
    }
    for old, new in edits.items():
        if source.count(old) != 1:
            raise ValueError("nonunique frozen end-wing source anchor: " + old)
        source = source.replace(old, new)
    return source.encode()


def overlays(parent_runtime: Path) -> dict[str, bytes]:
    """Return paths/bytes to install in a separate content-addressed development generation."""
    if _sha((parent_runtime / "runtime-build.json").read_bytes()) != PARENT_GENERATION:
        raise ValueError("unknown parent runtime generation")
    xml = build_xml((parent_runtime / PARENT_ASSET).read_bytes())
    if xml != (Path(__file__).resolve().parents[2] / ASSET_PATH).read_bytes():
        raise ValueError("published development MJCF differs from reproducible derivation")
    return {
        PROVIDER: provider_bytes((parent_runtime / PROVIDER).read_bytes()),
        ASSET_PATH: xml,
        HELPER: Path(__file__).read_bytes(),
    }
