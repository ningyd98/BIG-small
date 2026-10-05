"""SOFTWARE_ONLY marker fixtures and CPU compiled physical equivalence; no render."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import math
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation

BASE = Path(__file__).resolve().parents[1] / "assets/robots/franka_panda/scene.xml"
# Independently checked canonical ID7 bits, including the black one-cell border.
BITS7 = (
    np.array(
        [
            [0, 0, 0, 0, 0, 0],
            [0, 1, 1, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 1, 1, 1, 1, 0],
            [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ],
        dtype=np.uint8,
    )
    * 255
)


def api():
    return importlib.import_module("cloud_edge_robot_arm.vision.pose_markers")


def observation(
    *,
    rotation=0,
    marker_id=7,
    duplicate=False,
    clipped=False,
    depth=1.0,
    calibration="synthetic-cal",
):
    image = np.full((160, 160), 255, dtype=np.uint8)
    glyph = (
        BITS7
        if marker_id == 7
        else cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), marker_id, 6
        )
    )
    glyph = np.repeat(np.repeat(glyph, 8, axis=0), 8, axis=1)
    if duplicate:
        image[56:104, 10:58] = glyph
        image[56:104, 102:150] = glyph
    elif clipped:
        image[56:104, 0:48] = glyph
    else:
        image[56:104, 56:104] = glyph
    image = np.rot90(image, rotation)
    output = io.BytesIO()
    Image.fromarray(image).convert("RGB").save(output, format="PNG")
    depths = np.full((160, 160), depth, dtype="<f4")
    return RGBDObservation(
        frame_id=f"software-{rotation}",
        captured_at=datetime(2026, 10, 4, tzinfo=UTC),
        sim_time_s=0.0,
        width=160,
        height=160,
        rgb_png_base64=base64.b64encode(output.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depths.tobytes()).decode(),
        intrinsics=(200.0, 200.0, 79.5, 79.5),
        camera_to_world=(
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            1.5,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        source="rgbd_camera",
        episode_id="SOFTWARE_ONLY",
        calibration_version=calibration,
    )


def registration():
    return api().PoseMarkerRegistration(
        marker_id=7, marker_size_m=0.24, marked_asset_sha256="a" * 64
    )


def test_ordered_known_marker_rotation_distinguishes_cube_quarter_turns():
    estimates = [
        api().detect_pose_marker(observation(rotation=k), registration()) for k in (0, 1, 2, 3)
    ]
    assert all(item.status == "OBSERVED" for item in estimates)
    expected = (0.0, math.pi / 2, math.pi, -math.pi / 2)
    for k, (item, yaw) in enumerate(zip(estimates, expected, strict=True)):
        assert math.atan2(
            math.sin(item.yaw_world_rad - yaw), math.cos(item.yaw_world_rad - yaw)
        ) == pytest.approx(0.0, abs=0.025)
        assert item.marker_center_world_m == pytest.approx((0.0, 0.0, 0.5), abs=0.004)
        assert len(item.ordered_corners_px) == 4
        assert item.geometric_error_bound_m is None and item.angular_velocity_bound_rad_s is None
        assert item.stability_status == "UNKNOWN"
        assert item.observation_checksum_sha256 == observation(rotation=k).checksum_sha256


@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "foreign",
        "duplicate",
        "clipped",
        "zero_depth",
        "wrong_scale",
        "no_calibration",
        "bytes",
    ],
)
def test_missing_or_ambiguous_or_unregistered_measurement_stays_unknown(bad):
    options = {
        "foreign": {"marker_id": 8},
        "duplicate": {"duplicate": True},
        "clipped": {"clipped": True},
        "zero_depth": {"depth": 0.0},
        "wrong_scale": {"depth": 2.0},
        "no_calibration": {"calibration": None},
    }
    current = observation(**options.get(bad, {}))
    if bad == "missing":
        image = io.BytesIO()
        Image.new("RGB", (160, 160), "white").save(image, format="PNG")
        current = RGBDObservation.model_validate(
            {
                **current.model_dump(),
                "rgb_png_base64": base64.b64encode(image.getvalue()).decode(),
                "checksum_sha256": "",
            }
        )
    if bad == "bytes":
        current = current.model_copy(update={"depth_float32_base64": "AAAA"})
    result = api().detect_pose_marker(current, registration())
    assert result.status == "UNKNOWN"
    assert result.marker_center_world_m is None and result.yaw_world_rad is None
    assert result.geometric_error_bound_m is None and result.angular_velocity_bound_rad_s is None


def test_registered_geometry_cannot_use_empty_asset_binding():
    with pytest.raises(ValueError):
        api().PoseMarkerRegistration(marker_id=7, marker_size_m=0.24, marked_asset_sha256="")


def test_builder_binds_exact_base_and_is_portable_xml_with_only_visual_additions():
    import xml.etree.ElementTree as ET

    base = BASE.read_bytes()
    marked = api().build_pose_marked_xml(base)
    original = ET.fromstring(base)
    new = ET.fromstring(marked)
    old_nodes = {node.get("name"): node for node in original.iter() if node.get("name")}
    new_nodes = {node.get("name"): node for node in new.iter() if node.get("name")}
    for name, node in old_nodes.items():
        assert new_nodes[name].attrib == node.attrib
    additions = [node for name, node in new_nodes.items() if name not in old_nodes]
    assert additions and all(node.tag == "geom" for node in additions)
    assert all(
        node.get("mass") == "0"
        and node.get("density") == "0"
        and node.get("contype") == "0"
        and node.get("conaffinity") == "0"
        for node in additions
    )
    assert new.find("asset") is None  # no texture file path dependency
    assert (
        hashlib.sha256(BASE.read_bytes()).hexdigest()
        == "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
    )
    with pytest.raises(ValueError):
        api().build_pose_marked_xml(base.replace(b'mass="0.08"', b'mass="0.09"'))


def test_compiled_marker_preserves_mass_inertia_joint_controller_camera_and_existing_contacts():
    import mujoco

    base = mujoco.MjModel.from_xml_path(str(BASE))
    marked = mujoco.MjModel.from_xml_string(api().build_pose_marked_xml(BASE.read_bytes()).decode())
    for field in ("nq", "nv", "nu", "nbody", "njnt", "ncam", "nsite"):
        assert getattr(marked, field) == getattr(base, field)
    for field in (
        "body_mass",
        "body_inertia",
        "body_ipos",
        "body_iquat",
        "body_pos",
        "body_quat",
        "jnt_type",
        "jnt_axis",
        "jnt_pos",
        "jnt_range",
        "dof_damping",
        "dof_armature",
        "actuator_gainprm",
        "actuator_biasprm",
        "actuator_ctrlrange",
        "actuator_trnid",
        "cam_pos",
        "cam_quat",
        "cam_fovy",
        "site_pos",
        "site_size",
        "qpos0",
    ):
        assert np.array_equal(getattr(marked, field), getattr(base, field)), field
    for geom_id in range(base.ngeom):
        name = mujoco.mj_id2name(base, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        other = marked.geom(name).id
        for field in (
            "geom_type",
            "geom_size",
            "geom_pos",
            "geom_quat",
            "geom_contype",
            "geom_conaffinity",
            "geom_friction",
            "geom_solref",
            "geom_solimp",
            "geom_margin",
            "geom_gap",
            "geom_rgba",
        ):
            assert np.array_equal(getattr(base, field)[geom_id], getattr(marked, field)[other]), (
                name,
                field,
            )
    left, right = mujoco.MjData(base), mujoco.MjData(marked)
    for _ in range(20):
        mujoco.mj_step(base, left)
        mujoco.mj_step(marked, right)
    assert np.array_equal(left.qpos, right.qpos) and np.array_equal(left.qvel, right.qvel)
