"""精确标记资产的开发仿真结构核对；不授予正式标定或原生协议资格。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

ROOT = Path(__file__).resolve().parents[3]
_PREFIX = "pose_marker_outboard_v3_"
_NAMES = {_PREFIX + "quiet"} | {f"{_PREFIX}r{r}c{c}" for r in range(6) for c in range(6)}


def validate_episode_asset(
    asset_path: Path, profile: str, *, development_family: str | None = None
) -> dict[str, Any]:
    """默认保持精确校准资产门，开发标记策略必须显式指定。"""
    if development_family is not None:
        return validate_development_marker_asset(asset_path, profile, development_family)
    actual = hashlib.sha256(Path(asset_path).read_bytes()).hexdigest()
    expected = calibration_asset_sha256(profile)
    if expected is None or actual != expected:
        raise ValueError("backend asset differs from calibrated upright-box profile")
    return {"scope": "EXACT_CALIBRATED_ASSET", "calibrated_asset_sha256": actual}


def _structure(node: ET.Element) -> tuple[Any, ...]:
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        (node.text or "").strip(),
        tuple(_structure(child) for child in node),
    )


def validate_marker_physics_equivalence(marked: bytes, calibrated: bytes) -> dict[str, Any]:
    """只移除完整的零质量、零接触标记，逐项比较其余XML结构。"""
    candidate, reference = ET.fromstring(marked), ET.fromstring(calibrated)
    objects = candidate.findall("./worldbody/body[@name='object']")
    if len(objects) != 1:
        raise ValueError("one registered direct object body required")
    body = objects[0]
    markers = [n for n in candidate.iter() if n.get("name", "").startswith(_PREFIX)]
    if len(markers) != 37 or {n.get("name") for n in markers} != _NAMES:
        raise ValueError("complete registered marker geometry required")
    for node in markers:
        if (
            node.tag != "geom"
            or node not in body
            or node.get("type") != "box"
            or node.get("group") != "2"
            or any(node.get(key) != "0" for key in ("mass", "density", "contype", "conaffinity"))
        ):
            raise ValueError("marker must remain directly attached, massless and contact-free")
        body.remove(node)
    if _structure(candidate) != _structure(reference):
        raise ValueError("nonmarker physics/camera/controller structure differs")
    return {"physics_equivalent": True, "marker_geoms": len(markers)}


def validate_development_marker_asset(
    asset_path: Path, profile: str, family_id: str
) -> dict[str, Any]:
    """显式开发入口仅接受当前已登记路径和字节；校准SHA保持不变。"""
    if profile != "mujoco_upright_box_v2":
        raise ValueError("current v2 profile required for development marker geometry")
    family = marker_family(family_id)
    path = Path(asset_path)
    expected = ROOT / family.asset_path
    if path.resolve() != expected.resolve() or path.is_symlink():
        raise ValueError("exact registered marker asset path required")
    marked = path.read_bytes()
    calibrated = (ROOT / "assets/robots/franka_panda/scene.xml").read_bytes()
    marker_hash = hashlib.sha256(marked).hexdigest()
    calibration_hash = hashlib.sha256(calibrated).hexdigest()
    if marker_hash != family.asset_sha256 or calibration_hash != calibration_asset_sha256(profile):
        raise ValueError("registered marker or calibration source bytes changed")
    return validate_marker_physics_equivalence(marked, calibrated) | {
        "scope": "MUJOCO_DEVELOPMENT_ONLY",
        "marker_family": family_id,
        "marked_asset_sha256": marker_hash,
        "calibrated_asset_sha256": calibration_hash,
        "formal_qualification": "NOT_GRANTED",
    }
