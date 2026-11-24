"""The preregistered low crossbars and uprights. Build only from the exact v1 inputs."""

from __future__ import annotations

import hashlib
import itertools
import math
from functools import lru_cache
from xml.etree import ElementTree as ET

import numpy as np

FAMILY = "g1_development_dual_id7_y100_id8_x100_low_bracket_v2"
REGISTRATION_ID = "g1-development-only-dual-7y-8x-low-bracket-v2"
ASSET_PATH = (
    "assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_low_bracket_v2.xml"
)
BODY_MASS_KG = 0.10078432
ASSET_SHA = "a0bf24bdf2c7142e9aaeebdaf5dec02255bf06885dde0e2e56f009aaf89f9803"
V1_XML_SHA = "5c8e97f5dd17cf719d579d1badeab85de2e8f52dd14f6be0ef5dd2ff28159e66"
V1_PROVIDER_SHA = "edc2acb13793119d72f5b4ee8b4ebab282fe1664091f871a17fa86339be184fc"
PARTS = ("plate", "crossbar", "upright")


def bracket_boxes(code):
    if code not in (7, 8):
        raise ValueError("unknown bracket side")
    # Object coordinates come from the preregistered radial/transverse intervals.
    # Printed plates and quiet zones retain the original positions and appearance.
    result = {}
    for name, lo, hi, mass in (
        ("crossbar", [0.035, -0.004, 0.017], [0.056, 0.004, 0.019], 0.000168),
        ("upright", [0.052, -0.004, 0.019], [0.056, 0.004, 0.03301], 0.00022416),
    ):
        if code == 7:
            lo[0], lo[1] = lo[1], lo[0]
            hi[0], hi[1] = hi[1], hi[0]
        lower, upper = np.array(lo), np.array(hi)
        result[f"g1_dual_id{code}_{name}"] = (lower, upper, mass)
    return result


def _bounds(node):
    if (
        node is None
        or node.get("type") != "box"
        or any(
            key in node.attrib
            for key in ("quat", "euler", "axisangle", "xyaxes", "zaxis", "fromto")
        )
    ):
        raise ValueError("expected named axis-aligned positive structural box")
    center = np.array([float(v) for v in node.get("pos", "0 0 0").split()])
    half = np.array([float(v) for v in node.attrib["size"].split()])
    if (
        center.shape != (3,)
        or half.shape != (3,)
        or not np.isfinite([center, half]).all()
        or min(half) <= 0
    ):
        raise ValueError("invalid bracket geometry")
    return center - half, center + half


def verify_parts(tree):
    """Check every positive-volume solid and each common face, independently of MJCF inertia."""
    body = tree.find("./worldbody/body[@name='object']")
    boxes = {}
    masses = {}
    for name in ["object_geom", *(f"g1_dual_id{i}_{suffix}" for i in (7, 8) for suffix in PARTS)]:
        nodes = body.findall(f"geom[@name='{name}']")
        if len(nodes) != 1:
            raise ValueError("missing or duplicate registered physical part " + name)
        node = nodes[0]
        lo, hi = _bounds(node)
        mass = float(node.attrib["mass"])
        if (
            (node.get("contype"), node.get("conaffinity")) != ("1", "3")
            or not math.isfinite(mass)
            or mass <= 0
        ):
            raise ValueError("invalid bracket collision shell or mass " + name)
        boxes[name] = (lo, hi)
        masses[name] = mass
    all_parts = bracket_boxes(7) | bracket_boxes(8)
    for name, (lo, hi, mass) in all_parts.items():
        actual_lo, actual_hi = boxes[name]
        node = body.find(f"geom[@name='{name}']")
        if not (
            np.allclose(actual_lo, lo, atol=1e-12, rtol=0)
            and np.allclose(actual_hi, hi, atol=1e-12, rtol=0)
            and math.isclose(masses[name], mass, rel_tol=0, abs_tol=1e-12)
            and math.isclose(
                masses[name] / np.prod(actual_hi - actual_lo), 500.0, rel_tol=0, abs_tol=1e-8
            )
            and node.get("rgba") == "0.4 0.4 0.4 1"
        ):
            raise ValueError("bracket intervals, finite mass or finish differs for " + name)
    if abs(sum(masses.values()) - BODY_MASS_KG) > 1e-12:
        raise ValueError("registered v2 assembly mass differs")
    return common_faces(boxes)


def common_faces(boxes):
    """Prove six designated attachment faces and exclude positive-volume intersections."""
    areas = {}
    for a, b in itertools.combinations(boxes, 2):
        l0, h0 = boxes[a]
        l1, h1 = boxes[b]
        overlap = np.minimum(h0, h1) - np.maximum(l0, l1)
        if np.all(overlap > 1e-12):
            raise ValueError(f"positive-volume structural interference: {a}/{b}")
    for code, radial in ((7, 1), (8, 0)):
        pre = f"g1_dual_id{code}_"
        for low, high, axis in (
            ("object_geom", pre + "crossbar", radial),
            (pre + "crossbar", pre + "upright", 2),
            (pre + "upright", pre + "plate", 2),
        ):
            l0, h0 = boxes[low]
            l1, h1 = boxes[high]
            overlaps = np.minimum(h0, h1) - np.maximum(l0, l1)
            transverse = np.delete(overlaps, axis)
            if abs(h0[axis] - l1[axis]) > 1e-12 or np.any(transverse <= 0):
                raise ValueError(f"missing finite common attachment face: {low}/{high}")
            areas[low + "/" + high] = float(np.prod(transverse))
    return areas


def compiled_faces(model):
    names = ["object_geom", *(f"g1_dual_id{i}_{s}" for i in (7, 8) for s in PARTS)]
    boxes = {}
    obj = model.body("object").id
    if not math.isclose(float(model.body_mass[obj]), BODY_MASS_KG, rel_tol=0, abs_tol=1e-12):
        raise ValueError("compiled v2 total mass differs")
    for name in names:
        g = model.geom(name)
        if (int(g.contype[0]), int(g.conaffinity[0]), int(g.bodyid[0])) != (1, 3, obj):
            raise ValueError("compiled structural collision shell or body differs for " + name)
        if not np.array_equal(g.quat, [1.0, 0, 0, 0]):
            raise ValueError("unexpected bracket axes " + name)
        boxes[name] = (g.pos - g.size, g.pos + g.size)
    return common_faces(boxes)


@lru_cache(maxsize=1)
def replace_v1_xml(xml):
    if hashlib.sha256(xml).hexdigest() != V1_XML_SHA:
        raise ValueError("exact original supported dual v1 asset required")
    tree = ET.fromstring(xml)
    body = tree.find("./worldbody/body[@name='object']")
    for code in (7, 8):
        old = body.find(f"geom[@name='g1_dual_id{code}_support']")
        at = list(body).index(old)
        for j, (name, (lo, hi, mass)) in enumerate(bracket_boxes(code).items()):
            attrs = dict(old.attrib, name=name, mass=str(mass))
            attrs["pos"] = " ".join(f"{x:.10f}" for x in ((lo + hi) / 2))
            attrs["size"] = " ".join(f"{x:.10f}" for x in ((hi - lo) / 2))
            body.insert(at + j, ET.Element("geom", attrs))
        body.remove(old)
    verify_parts(tree)
    ET.indent(tree, space="  ")
    return ET.tostring(tree, encoding="utf-8") + b"\n"


def provider_source(original):
    """Specialize the exact v1 provider in the exported tree, leaving its W source untouched."""
    if hashlib.sha256(original).hexdigest() != V1_PROVIDER_SHA:
        raise ValueError("exact verified separated-clearance v1 provider required")
    text = original.decode()

    def change(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("ambiguous v2 provider source anchor")
        text = text.replace(before, after)

    change(
        "import numpy as np\n",
        "import numpy as np\nfrom scripts.graduation import g1_dual_asset_v2 as _low_bracket\n",
    )
    for name in ("FAMILY", "REGISTRATION_ID", "ASSET_PATH", "ASSET_SHA", "BODY_MASS_KG"):
        line = next(s for s in text.splitlines() if s.startswith(name + " = "))
        change(line, name + " = _low_bracket." + name)
    change(
        '("asset", "observer", "runtime_adapter")',
        '("asset", "observer", "runtime_adapter", "asset_v2")',
    )
    change('            "support",\n', '            "crossbar",\n            "upright",\n')
    change("def build_xml(r593):", "@lru_cache(maxsize=1)\ndef build_xml(r593):")
    change(
        '    return ET.tostring(tree, encoding="utf-8") + b"\\n"',
        '    return _low_bracket.replace_v1_xml(ET.tostring(tree, encoding="utf-8") + b"\\n")',
    )
    change(
        'schema="g1.development.dual-registration.v1",',
        'schema="g1.development.dual-registration.v2",\n'
        "                structure_parts_per_side=list(_low_bracket.PARTS),",
    )
    change(
        '    require(set(nodes) == box_names() and len(body.findall("geom")) == 79, '
        '"79 named direct boxes")',
        '    require(set(nodes) == box_names() and len(body.findall("geom")) == 81,\n'
        '            "81 named direct boxes")\n'
        "    xml_faces = _low_bracket.verify_parts(xml)",
    )
    change('for s in ("plate", "support")', "for s in _low_bracket.PARTS")
    change(
        "        plate, bridge, quiet, cube = (\n"
        "            model.geom(n)\n"
        '            for n in (prefix + "plate", prefix + "support", '
        'prefix + "quiet", "object_geom")\n'
        "        )",
        '        plate, quiet = model.geom(prefix + "plate"), model.geom(prefix + "quiet")',
    )
    start = text.index("        axis = 1 if code == 7 else 0\n")
    end = text.index("    (lo0, hi0), (lo1, hi1) = plate_bounds", start)
    change(
        text[start:end],
        "    faces = _low_bracket.compiled_faces(model)\n"
        "    require(faces.keys() == xml_faces.keys() and all(\n"
        '        abs(faces[k] - xml_faces[k]) < 1e-12 for k in faces), "compiled joint faces")\n',
    )
    change(
        'schema="g1.development.compiled-dual-asset.v1",',
        'schema="g1.development.compiled-dual-asset.v2",\n        structural_face_areas_m2=faces,',
    )
    return text.encode()
