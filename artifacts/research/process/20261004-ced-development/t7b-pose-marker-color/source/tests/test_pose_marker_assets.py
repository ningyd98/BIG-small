"""SOFTWARE_ONLY colored-rim asset generation/CPU physical-equivalence tests."""

from __future__ import annotations

import hashlib
import importlib
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "assets/robots/franka_panda/scene.xml"
V1 = ROOT / "assets/robots/franka_panda/scene_pose_marker_v1.xml"


def api():
    return importlib.import_module("cloud_edge_robot_arm.vision.pose_marker_assets")


def test_new_colored_marker_has_real_rim_and_full_white_quiet_cell_without_mutating_base_or_v1():
    original = BASE.read_bytes()
    v1 = V1.read_bytes()
    generated = api().build_colored_pose_marker_xml(original)
    assert generated == api().build_colored_pose_marker_xml(original)
    tree = ET.fromstring(generated)
    quiet = tree.find("./worldbody/body[@name='object']/geom[@name='pose_marker_color_v2_quiet']")
    assert quiet is not None
    assert [float(value) for value in quiet.get("size").split()] == pytest.approx(
        [0.03, 0.03, 0.00001]
    )
    cells = [
        node
        for node in tree.iter("geom")
        if node.get("name", "").startswith("pose_marker_color_v2_r")
    ]
    assert len(cells) == 36
    extents = []
    for node in cells:
        x, y, _ = map(float, node.get("pos").split())
        sx, sy, _ = map(float, node.get("size").split())
        extents.append((x - sx, x + sx, y - sy, y + sy))
        assert sx == pytest.approx(0.00375) and sy == pytest.approx(0.00375)
    assert min(row[0] for row in extents) == pytest.approx(-0.0225)
    assert max(row[1] for row in extents) == pytest.approx(0.0225)
    assert min(row[2] for row in extents) == pytest.approx(-0.0225)
    assert max(row[3] for row in extents) == pytest.approx(0.0225)
    # Literal extents: cube edge35mm minus quiet30mm leaves5mm observed-color rim;
    # quiet edge30mm minus marker22.5mm leaves one7.5mm bit cell.
    old = {node.get("name"): node for node in ET.fromstring(original).iter() if node.get("name")}
    new = {node.get("name"): node for node in tree.iter() if node.get("name")}
    for name, node in old.items():
        assert new[name].attrib == node.attrib
    additions = [node for name, node in new.items() if name not in old]
    assert len(additions) == 37
    assert all(
        node.tag == "geom"
        and node.get("mass") == "0"
        and node.get("density") == "0"
        and node.get("contype") == "0"
        and node.get("conaffinity") == "0"
        for node in additions
    )
    assert tree.find("asset") is None
    assert BASE.read_bytes() == original and V1.read_bytes() == v1
    assert (
        hashlib.sha256(original).hexdigest()
        == "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
    )


def test_changed_base_cannot_acquire_colored_marker_source_binding():
    with pytest.raises(ValueError):
        api().build_colored_pose_marker_xml(
            BASE.read_bytes().replace(b'mass="0.08"', b'mass="0.09"')
        )


def test_compiled_colored_marker_has_identical_physical_dynamics_controller_and_camera():
    import mujoco

    original = mujoco.MjModel.from_xml_path(str(BASE))
    marked = mujoco.MjModel.from_xml_string(
        api().build_colored_pose_marker_xml(BASE.read_bytes()).decode()
    )
    for field in ("nq", "nv", "nu", "nbody", "njnt", "ncam", "nsite"):
        assert getattr(marked, field) == getattr(original, field)
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
        assert np.array_equal(getattr(marked, field), getattr(original, field)), field
    for index in range(original.ngeom):
        name = mujoco.mj_id2name(original, mujoco.mjtObj.mjOBJ_GEOM, index)
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
            assert np.array_equal(getattr(original, field)[index], getattr(marked, field)[other]), (
                name,
                field,
            )
    a, b = mujoco.MjData(original), mujoco.MjData(marked)
    for _ in range(20):
        mujoco.mj_step(original, a)
        mujoco.mj_step(marked, b)
    assert np.array_equal(a.qpos, b.qpos) and np.array_equal(a.qvel, b.qvel)


def test_saved_colored_asset_frame_has_native_tag_and_observed_red_without_admission():
    import base64
    import io
    import json

    import cv2
    from PIL import Image

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

    asset = BASE.with_name("scene_pose_marker_color_v2.xml")
    directory = (
        ROOT
        / "artifacts/research/process/20261004-ced-development/t7b-pose-marker-color"
        / "actual-capture-640"
    )
    current = RGBDObservation.model_validate(
        json.loads((directory / "frame/observation-full.json").read_text())
    )
    registered = PoseMarkerRegistration(7, 0.045, hashlib.sha256(asset.read_bytes()).hexdigest())
    estimate = detect_pose_marker(current, registered)
    assert estimate.status == "OBSERVED" and estimate.observed_marker_ids == (7,)
    rgb = np.asarray(
        Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))).convert("RGB")
    )
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    red = ((hsv[:, :, 0] < 12) | (hsv[:, :, 0] > 168)) & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 40)
    assert (
        int(red.sum()) >= 100
    )  # v1 was0; meaningful observed-color regression, not native acceptance
    assert (
        estimate.geometric_error_bound_m is None and estimate.angular_velocity_bound_rad_s is None
    )
    assert estimate.stability_status == "UNKNOWN"
    assert current.width == 640 and current.height == 480
