"""Calibrated top grasps use measured surfaces and reject unsafe geometry."""

from __future__ import annotations

import base64
import io
import json
import struct
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _observation(
    *, height: float = 0.08, support: float = 0.2,
    changed_depths: dict[tuple[int, int], float] | None = None,
    side_view: bool = False,
) -> RGBDObservation:
    png = io.BytesIO()
    Image.new("RGB", (5, 5), (220, 40, 20)).save(png, format="PNG")
    depths = [1.0] * 25
    for (u, v), value in (changed_depths or {}).items():
        depths[v * 5 + u] = value
    transform = (
        (1, 0, 0, 0.3, 0, 0, -1, 0.1, 0, 1, 0, support + height, 0, 0, 0, 1)
        if side_view else
        (1, 0, 0, 0.3, 0, -1, 0, 0.1, 0, 0, -1, support + height + 1, 0, 0, 0, 1)
    )
    return RGBDObservation.model_validate({
        "frame_id": "SECRET_ORACLE_FRAME", "scene_id": "SECRET_ORACLE_SCENE",
        "episode_id": "SECRET_ORACLE_EPISODE", "captured_at": datetime.now(UTC),
        "sim_time_s": 0.0, "width": 5, "height": 5,
        "rgb_png_base64": base64.b64encode(png.getvalue()).decode(),
        "depth_float32_base64": base64.b64encode(struct.pack("<25f", *depths)).decode(),
        "intrinsics": (100, 100, 2, 2), "camera_to_world": transform,
        "source": "rgbd_camera",
    })


def test_top_grasp_estimates_center_and_tcp_from_measured_top_and_support() -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    evidence = resolve_top_grasp(_observation(), (2, 2), 0.2)
    assert evidence["top_grasp_offset_status"] == "CALIBRATED_RGBD_TOP_GRASP_V1"
    assert evidence["estimated_object_height_m"] == pytest.approx(0.08)
    assert evidence["top_grasp_offset_from_surface_m"] == pytest.approx(-0.03)
    assert evidence["resolved_top_grasp_tcp"] == pytest.approx({"x": 0.3, "y": 0.1, "z": 0.25})
    assert evidence["estimated_object_center"] == pytest.approx({"x": 0.3, "y": 0.1, "z": 0.24})
    assert evidence["estimated_object_center_semantics"] == (
        "RGBD_GEOMETRIC_ESTIMATE_NOT_GROUND_TRUTH"
    )
    assert "upright" in str(evidence["grasp_geometry_assumption"])
    assert "rigid box" in str(evidence["grasp_geometry_assumption"])
    assert evidence["estimated_fingertip_clearance_m"] == pytest.approx(0.02)
    assert evidence["top_patch_world_z_span_m"] == pytest.approx(0)
    wire = json.dumps(evidence)
    assert "SECRET_ORACLE" not in wire
    assert "object_geom" not in wire


@pytest.mark.parametrize("height", [0.05, 0.08, 0.10])
def test_calibrated_height_family_keeps_actual_scene_fingertips_above_support(
    height: float,
) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    # A stale tool calibration must fail when the actual MJCF fingertips move.
    path = Path(__file__).resolve().parents[1] / "assets/robots/franka_panda/scene.xml"
    root = ET.parse(path).getroot()
    tcp = root.find(".//site[@name='tcp']")
    assert tcp is not None
    tcp_x = float(tcp.attrib["pos"].split()[0])
    finger_extensions: list[float] = []
    for name in ("left_finger", "right_finger"):
        finger = root.find(f".//body[@name='{name}']")
        assert finger is not None
        geom = finger.find("geom")
        assert geom is not None
        finger_tip = sum(float(node.attrib[key].split()[0]) for node, key in (
            (finger, "pos"), (geom, "pos"), (geom, "size"),
        ))
        finger_extensions.append(finger_tip - tcp_x)

    support = 1.0 - height
    evidence = resolve_top_grasp(_observation(height=height, support=support), (2, 2), support)
    tcp_pose = evidence["resolved_top_grasp_tcp"]
    assert isinstance(tcp_pose, dict)
    actual_clearance = tcp_pose["z"] - max(finger_extensions) - support
    assert actual_clearance >= 0.002
    assert evidence["estimated_fingertip_clearance_m"] == pytest.approx(actual_clearance)


@pytest.mark.parametrize("height", [0.0, 0.049, 0.101, 0.2, -0.01])
def test_unsupported_height_is_rejected_without_clamping(height: float) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    with pytest.raises(ValueError, match="height|calibrat"):
        resolve_top_grasp(_observation(height=height), (2, 2), 0.2)


@pytest.mark.parametrize("height,allowed", [
    (0.05, True), (0.10, True), (0.049999, False), (0.100001, False),
])
def test_float32_depth_representation_preserves_calibration_boundaries(
    height: float, allowed: bool,
) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    # Camera at world z=3, support at optical depth=2 (world z=1).
    # Packing the 1.9 m top depth to float32 yields height=0.10000002384 m;
    # the 1.95 m lower-bound top yields height=0.04999995232 m.
    payload = _observation().model_dump()
    payload.update(
        depth_float32_base64=base64.b64encode(
            struct.pack("<25f", *([2.0 - height] * 25))
        ).decode(),
        camera_to_world=(1, 0, 0, 0.3, 0, -1, 0, 0.1, 0, 0, -1, 3, 0, 0, 0, 1),
        valid_mask_base64=None, checksum_sha256="",
    )
    observation = RGBDObservation.model_validate(payload)
    if allowed:
        result = resolve_top_grasp(observation, (2, 2), 1.0)
        assert result["estimated_object_height_m"] == pytest.approx(height, abs=1e-7)
        tcp_pose = result["resolved_top_grasp_tcp"]
        assert isinstance(tcp_pose, dict)
        assert tcp_pose["z"] - 0.03 - 1.0 >= 0.002
    else:
        with pytest.raises(ValueError, match="height|calibrat"):
            resolve_top_grasp(observation, (2, 2), 1.0)


@pytest.mark.parametrize("support", [float("nan"), float("inf"), -float("inf"), True, "0.2"])
def test_support_must_be_a_finite_metric_measurement(support: Any) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    with pytest.raises(ValueError, match="support"):
        resolve_top_grasp(_observation(), (2, 2), support)


@pytest.mark.parametrize("pixel", [(0, 2), (4, 2), (2, 0), (2, 4), (-1, 2), (True, 2), (1.5, 2)])
def test_grasp_requires_a_complete_interior_three_by_three_patch(pixel: Any) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    with pytest.raises(ValueError, match="pixel|patch|edge"):
        resolve_top_grasp(_observation(), pixel, 0.2)


@pytest.mark.parametrize("missing", [(1, 1), (2, 2), (3, 3)])
def test_invalid_depth_anywhere_in_top_patch_rejects_grasp(missing: tuple[int, int]) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    observation = _observation(changed_depths={missing: 0})
    with pytest.raises(ValueError, match="depth"):
        resolve_top_grasp(observation, (2, 2), 0.2)


@pytest.mark.parametrize("depth,allowed", [(0.994, True), (0.991, False)])
def test_top_patch_world_height_variation_is_bounded(depth: float, allowed: bool) -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    observation = _observation(changed_depths={(1, 1): depth})
    if allowed:
        result = resolve_top_grasp(observation, (2, 2), 0.2)
        assert result["top_patch_world_z_span_m"] == pytest.approx(0.006, abs=1e-7)
    else:
        with pytest.raises(ValueError, match="flat|planar|variation"):
            resolve_top_grasp(observation, (2, 2), 0.2)


def test_constant_camera_depth_does_not_prove_a_world_horizontal_top() -> None:
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    # Under this calibrated camera rotation, a constant optical-depth patch spans
    # 20 mm in world z and is a vertical surface, despite zero raw-depth spread.
    with pytest.raises(ValueError, match="flat|planar|variation"):
        resolve_top_grasp(_observation(side_view=True), (2, 2), 0.2)
