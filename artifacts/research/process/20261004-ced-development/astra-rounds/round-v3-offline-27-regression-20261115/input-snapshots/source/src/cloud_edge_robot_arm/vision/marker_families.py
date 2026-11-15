"""Immutable, explicitly selected marker assets; no detector or execution authority."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from xml.etree import ElementTree as ET

LEGACY_FAMILY = "outboard_id7_45mm_v3"
PREPARE_ONLY_FAMILY = "outboard_id7_75mm_r579"
SIDE_PREPARE_ONLY_FAMILY = "side_y_plus_id7_75mm_r593"
COMPONENT_DIAGNOSTIC_FAMILY = "side_y_plus_id7_75mm_component_v1"
_PREFIX = "pose_marker_outboard_v3_"
_ATTACHMENT = (1, 0, 0, 0.1, 0, 1, 0, 0, 0, 0, 1, 0.03505, 0, 0, 0, 1)
_SIDE_ATTACHMENT = (1, 0, 0, 0, 0, 1, 0, 0.1, 0, 0, 1, 0.03505, 0, 0, 0, 1)
_PREPARE_FAMILIES = (PREPARE_ONLY_FAMILY, SIDE_PREPARE_ONLY_FAMILY)


@dataclass(frozen=True)
class MarkerFamily:
    """固定标记资产及其完整刚性安装登记。"""

    family_id: str
    asset_path: str
    asset_sha256: str
    marker_id: int
    dictionary: str
    marker_size_m: float
    registration_id: str
    marker_to_object: tuple[float, ...]


_FAMILIES = MappingProxyType(
    {
        LEGACY_FAMILY: MarkerFamily(
            LEGACY_FAMILY,
            "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml",
            "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23",
            7,
            "DICT_4X4_50",
            0.045,
            "native-r439-outboard-v3",
            _ATTACHMENT,
        ),
        PREPARE_ONLY_FAMILY: MarkerFamily(
            PREPARE_ONLY_FAMILY,
            "assets/robots/franka_panda/scene_pose_marker_outboard_75mm_r579.xml",
            "bc7a40dc3cfcb843154375feb1c0689749f1376be32da3d9aef0bb96472a18bd",
            7,
            "DICT_4X4_50",
            0.075,
            "native-r579-outboard-75mm",
            _ATTACHMENT,
        ),
        SIDE_PREPARE_ONLY_FAMILY: MarkerFamily(
            SIDE_PREPARE_ONLY_FAMILY,
            "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml",
            "1e95054dc74e1c8ff51042290450b5e01e7410dd653870c553f056892efca140",
            7,
            "DICT_4X4_50",
            0.075,
            "native-r593-side-y-plus-75mm",
            _SIDE_ATTACHMENT,
        ),
        # Component-only variant: deliberately absent from native prepare/release policies.
        COMPONENT_DIAGNOSTIC_FAMILY: MarkerFamily(
            COMPONENT_DIAGNOSTIC_FAMILY,
            "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_component_v1.xml",
            "18049666e288ce3992d44e8a520ee5b4101a4fa89dc825bcd75f78e408a198f0",
            7, "DICT_4X4_50", 0.075, "component-side-y-plus-75mm-140mm-v1",
            (1, 0, 0, 0, 0, 1, 0, 0.14, 0, 0, 1, 0.03505, 0, 0, 0, 1),
        ),
    }
)


def marker_family(family_id: str) -> MarkerFamily:
    """仅解析已登记的显式版本，拒绝任意路径或尺寸覆盖。"""
    if type(family_id) is not str or family_id not in _FAMILIES:
        raise ValueError("unknown registered marker family")
    return _FAMILIES[family_id]


def _geometry_family(data: Mapping[str, Any]) -> MarkerFamily | None:
    """Recognize every new-family identifier before any generic legacy fallback."""
    pose = data.get("pose_marker", {})
    if not isinstance(pose, Mapping):
        raise ValueError("complete registered marker descriptor required")
    strict = (
        "marker_family" in data
        or any(
            data.get("asset_path") == _FAMILIES[family_id].asset_path
            or pose.get("marked_asset_sha256") == _FAMILIES[family_id].asset_sha256
            or data.get("registration_id") == _FAMILIES[family_id].registration_id
            for family_id in _PREPARE_FAMILIES
        )
        or data.get("marker_to_object") == list(_SIDE_ATTACHMENT)
    )
    if not strict:
        return None
    if data.get("marker_family") not in _PREPARE_FAMILIES:
        raise ValueError("complete exact marker family/asset/geometry binding required")
    family = marker_family(data["marker_family"])
    if (
        data.get("marker_family") != family.family_id
        or data.get("asset_path") != family.asset_path
        or data.get("registration_id") != family.registration_id
        or dict(pose)
        != dict(
            marker_id=family.marker_id,
            dictionary=family.dictionary,
            marker_size_m=family.marker_size_m,
            marked_asset_sha256=family.asset_sha256,
        )
        or data.get("marker_to_object") != list(family.marker_to_object)
    ):
        raise ValueError("complete exact marker family/asset/geometry binding required")
    return family


def _numbers(text: str | None, expected: tuple[float, ...]) -> None:
    try:
        actual = tuple(float(v) for v in (text or "").split())
    except ValueError as error:
        raise ValueError("registered marker numeric structure required") from error
    if len(actual) != len(expected) or any(
        not math.isfinite(a) or not math.isclose(a, b, abs_tol=1e-12, rel_tol=0)
        for a, b in zip(actual, expected, strict=True)
    ):
        raise ValueError("registered marker numeric structure differs")


def _canonical(element: ET.Element) -> tuple[Any, ...]:
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or "").strip(),
        tuple(_canonical(child) for child in element),
    )


def _validate_75mm_structure(
    candidate: bytes, legacy: bytes, *, family_id: str = PREPARE_ONLY_FAMILY
) -> None:
    """Validate static marker cells and preserve every nonmarker XML element."""
    if family_id not in _PREPARE_FAMILIES:
        raise ValueError("registered prepare-only marker family required")
    attachment = marker_family(family_id).marker_to_object
    center_x, center_y = attachment[3], attachment[7]
    tree, original = ET.fromstring(candidate), ET.fromstring(legacy)
    objects = tree.findall(".//body[@name='object']")
    direct = tree.findall("./worldbody/body[@name='object']")
    if len(objects) != 1 or len(direct) != 1 or objects[0] is not direct[0]:
        raise ValueError("one direct rigid object attachment required")
    body = direct[0]
    names = {_PREFIX + "quiet"} | {f"{_PREFIX}r{r}c{c}" for r in range(6) for c in range(6)}
    nodes = [g for g in tree.iter() if g.get("name", "").startswith(_PREFIX)]
    if len(nodes) != 37 or {g.get("name") for g in nodes} != names:
        raise ValueError("complete unique marker grid and quiet border required")
    bits = ("000000", "011000", "001000", "011110", "000100", "000000")
    for node in nodes:
        if (
            node.tag != "geom"
            or node not in list(body)
            or set(node.attrib)
            != {
                "name",
                "type",
                "pos",
                "size",
                "mass",
                "density",
                "contype",
                "conaffinity",
                "group",
                "rgba",
            }
            or node.get("type") != "box"
        ):
            raise ValueError("direct visual-only unrotated box marker required")
        for key in ("mass", "density", "contype", "conaffinity"):
            if node.get(key) != "0":
                raise ValueError("marker must have zero mass and contact")
        if node.get("group") != "2":
            raise ValueError("registered visual marker group required")
        name = node.attrib["name"]
        if name == _PREFIX + "quiet":
            _numbers(node.get("pos"), (center_x, center_y, 0.03502))
            _numbers(node.get("size"), (0.05, 0.05, 0.00001))
            white = True
        else:
            r, c = int(name[-3]), int(name[-1])
            _numbers(
                node.get("pos"),
                (center_x + (c - 2.5) * 0.0125, center_y + (2.5 - r) * 0.0125, 0.03504),
            )
            _numbers(node.get("size"), (0.00625, 0.00625, 0.00001))
            white = bits[r][c] == "1"
        _numbers(node.get("rgba"), (0.98, 0.98, 0.98, 1) if white else (0.01, 0.01, 0.01, 1))
    for root in (tree, original):
        removed = []
        for parent in root.iter():
            for child in list(parent):
                if child.get("name") in names:
                    parent.remove(child)
                    removed.append(child.get("name"))
        if len(removed) != 37 or set(removed) != names:
            raise ValueError("complete original visual marker surface required")
    if _canonical(tree) != _canonical(original):
        raise ValueError("nonmarker physical/camera/controller XML differs")
