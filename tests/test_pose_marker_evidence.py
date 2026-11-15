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


def test_positive_depth_with_zero_mask_is_already_rejected_by_registered_pair_validator():
    current = observation()
    mask = bytearray(current.valid_mask_bytes())
    mask[56 * 160 + 56] = 0
    altered = current.model_copy(update={"valid_mask_base64": base64.b64encode(mask).decode()})
    with pytest.raises(ValueError, match="valid mask must match positive finite depth"):
        RGBDObservation.model_validate(altered.model_dump())
    assert api().detect_pose_marker(altered, registration()).status == "UNKNOWN"
    assert api().detect_pose_marker(altered, registration()).reason == "invalid_registered_rgbd"


@pytest.mark.parametrize("bad", ["intrinsics", "rotation", "checksum"])
def test_invalid_camera_calibration_or_frame_hash_rejects_before_pose_estimate(bad):
    current = observation()
    changes = {
        "intrinsics": {"intrinsics": (-200.0, 200.0, 79.5, 79.5)},
        "rotation": {
            "camera_to_world": (
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
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
            )
        },
        "checksum": {"checksum_sha256": "f" * 64},
    }[bad]
    estimate = api().detect_pose_marker(current.model_copy(update=changes), registration())
    assert estimate.status == "UNKNOWN" and estimate.rotation_marker_to_world is None


def test_nonplanar_center_depth_cannot_produce_ordered_metric_pose():
    current = observation()
    depths = np.ones((160, 160), dtype="<f4")
    depths[79:82, 79:82] = 1.2
    current = RGBDObservation.model_validate(
        {
            **current.model_dump(),
            "depth_float32_base64": base64.b64encode(depths.tobytes()).decode(),
            "checksum_sha256": "",
        }
    )
    assert api().detect_pose_marker(current, registration()).status == "UNKNOWN"


def test_saved_native_resolution_profiles_measure_detectability_without_truth_input():
    import json

    root = BASE.parents[3] / "artifacts/research/process/20261004-ced-development/t7b-pose-markers"
    asset = BASE.with_name("scene_pose_marker_v1.xml")
    registered = api().PoseMarkerRegistration(
        7, 0.0525, hashlib.sha256(asset.read_bytes()).hexdigest()
    )
    observations = []
    estimates = []
    for directory in ("actual-capture-1", "actual-capture-640"):
        data = json.loads((root / directory / "frame/observation-full.json").read_text())
        current = RGBDObservation.model_validate(data)
        observations.append(current)
        estimates.append(api().detect_pose_marker(current, registered))
    assert [(item.width, item.height) for item in observations] == [(320, 240), (640, 480)]
    assert observations[0].calibration_version != observations[1].calibration_version
    assert observations[0].intrinsics != observations[1].intrinsics
    assert [item.status for item in estimates] == ["UNKNOWN", "OBSERVED"]
    assert estimates[1].observed_marker_ids == (7,) and estimates[1].measured_min_side_px > 16
    assert all(
        item.angular_velocity_bound_rad_s is None
        and item.geometric_error_bound_m is None
        and item.stability_status == "UNKNOWN"
        for item in estimates
    )


def test_non_string_asset_identity_rejects_as_invalid_registration():
    with pytest.raises(ValueError):
        api().PoseMarkerRegistration(marker_id=7, marker_size_m=0.24, marked_asset_sha256=None)


def test_subpix_candidate_decode_recovers_small_marker_without_bit_repair():
    def render_small(bits: np.ndarray) -> RGBDObservation:
        src = np.repeat(np.repeat(bits, 20, axis=0), 20, axis=1)
        canvas = np.full((160, 160), 220, dtype=np.uint8)
        canvas[20:140, 20:140] = src
        mat = cv2.getRotationMatrix2D((80, 80), 5.0, 14.0 / 120.0)
        mat[0, 2] += 100.5 - 80.0
        mat[1, 2] += 100.5 - 80.0
        warped = cv2.warpAffine(canvas, mat, (320, 240), flags=cv2.INTER_AREA, borderValue=220)
        out = io.BytesIO()
        Image.fromarray(warped).convert("RGB").save(out, format="PNG")
        return RGBDObservation(
            frame_id="subpix-small",
            captured_at=datetime(2026, 10, 4, tzinfo=UTC),
            sim_time_s=0.0,
            width=320,
            height=240,
            rgb_png_base64=base64.b64encode(out.getvalue()).decode(),
            depth_float32_base64=base64.b64encode(
                np.full((240, 320), 1.33, dtype="<f4").tobytes()
            ).decode(),
            intrinsics=(350.0, 350.0, 159.5, 119.5),
            camera_to_world=(
                1.0, 0.0, 0.0, 0.0,
                0.0, -1.0, 0.0, 0.0,
                0.0, 0.0, -1.0, 1.33,
                0.0, 0.0, 0.0, 1.0,
            ),
            source="rgbd_camera",
            episode_id="SOFTWARE_ONLY",
            calibration_version="synthetic-cal",
        )

    reg = api().PoseMarkerRegistration(
        marker_id=7, marker_size_m=0.0525, marked_asset_sha256="a" * 64
    )
    obs = render_small(BITS7)
    assert api().detect_pose_marker(obs, reg, corner_refinement="NONE").status == "UNKNOWN"
    est = api().detect_pose_marker(obs, reg, corner_refinement="SUBPIX")
    assert est.status == "OBSERVED"
    assert est.observed_marker_ids == (7,)

    corrupted = BITS7.copy()
    corrupted[1, 3] = 255
    corrupted_est = api().detect_pose_marker(
        render_small(corrupted), reg, corner_refinement="SUBPIX"
    )
    assert corrupted_est.status == "UNKNOWN"


def _subpix_rejected_scene(
    marker_ids: tuple[int, ...],
    *,
    quarter_turns: int = 0,
    side_px: float = 14.0,
    damaged: str | None = None,
) -> tuple[RGBDObservation, np.ndarray]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    gray = np.full((240, 320), 220, dtype=np.uint8)
    for index, marker_id in enumerate(marker_ids):
        bits = BITS7.copy() if marker_id == 7 else cv2.aruco.generateImageMarker(
            dictionary, marker_id, 6
        )
        if damaged == "bit":
            bits[1, 3] = 255
        elif damaged == "border":
            bits[0, :] = 255
        if damaged:
            assert not any(
                np.array_equal(np.rot90(bits, rotation), cv2.aruco.generateImageMarker(
                    dictionary, candidate_id, 6
                ))
                for rotation in range(4)
                for candidate_id in range(50)
            )
        bits = np.rot90(bits, quarter_turns)
        canvas = np.full((160, 160), 220, dtype=np.uint8)
        canvas[20:140, 20:140] = np.repeat(np.repeat(bits, 20, axis=0), 20, axis=1)
        transform = cv2.getRotationMatrix2D((80, 80), 5.0, side_px / 120.0)
        transform[0, 2] += 100.5 + index * 100.0 - 80.0
        transform[1, 2] += 100.5 - 80.0
        gray = np.minimum(gray, cv2.warpAffine(
            canvas, transform, (320, 240), flags=cv2.INTER_AREA, borderValue=220
        ))
    image = io.BytesIO()
    Image.fromarray(gray).convert("RGB").save(image, format="PNG")
    current = RGBDObservation(
        frame_id="subpix-identity-controls",
        captured_at=datetime(2026, 10, 4, tzinfo=UTC),
        sim_time_s=0.0,
        width=320,
        height=240,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(
            np.full((240, 320), 1.33, dtype="<f4").tobytes()
        ).decode(),
        intrinsics=(350.0, 350.0, 159.5, 119.5),
        camera_to_world=(
            1.0, 0.0, 0.0, 0.0,
            0.0, -1.0, 0.0, 0.0,
            0.0, 0.0, -1.0, 1.33,
            0.0, 0.0, 0.0, 1.0,
        ),
        source="rgbd_camera",
        episode_id="SOFTWARE_ONLY",
        calibration_version="synthetic-cal",
    )
    return current, gray


def _assert_unknown_has_no_pose(estimate):
    assert estimate.status == "UNKNOWN"
    assert estimate.ordered_corners_px is None
    assert estimate.marker_center_world_m is None
    assert estimate.rotation_marker_to_world is None
    assert estimate.yaw_world_rad is None


@pytest.mark.parametrize("marker_ids", [(7, 0), (0, 7)])
def test_subpix_rejected_candidates_preserve_foreign_marker_ambiguity(marker_ids):
    current, gray = _subpix_rejected_scene(marker_ids)
    parameters = cv2.aruco.DetectorParameters()
    parameters.errorCorrectionRate = 0.0
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    _, native_ids, rejected = cv2.aruco.ArucoDetector(dictionary, parameters).detectMarkers(gray)
    assert native_ids is None and len(rejected) >= 2
    result = api().detect_pose_marker(
        current, api().PoseMarkerRegistration(7, 0.0525, "a" * 64), corner_refinement="SUBPIX"
    )
    _assert_unknown_has_no_pose(result)
    assert result.reason == "foreign_or_ambiguous_marker"
    assert sorted(result.observed_marker_ids) == [0, 7]


@pytest.mark.parametrize("marker_ids,status,observed_ids", [
    ((7,), "OBSERVED", (7,)),
    ((0,), "UNKNOWN", (0,)),
    ((7, 7), "UNKNOWN", (7, 7)),
])
def test_subpix_rejected_candidates_identity_controls(marker_ids, status, observed_ids):
    current, _ = _subpix_rejected_scene(marker_ids)
    result = api().detect_pose_marker(
        current, api().PoseMarkerRegistration(7, 0.0525, "a" * 64), corner_refinement="SUBPIX"
    )
    assert result.status == status
    assert result.observed_marker_ids == observed_ids
    if status == "UNKNOWN":
        _assert_unknown_has_no_pose(result)


@pytest.mark.parametrize("quarter_turns", range(4))
def test_subpix_rejected_candidates_preserve_ordered_pose(quarter_turns):
    current, gray = _subpix_rejected_scene((7,), quarter_turns=quarter_turns)
    parameters = cv2.aruco.DetectorParameters()
    parameters.errorCorrectionRate = 0.0
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    _, native_ids, rejected = cv2.aruco.ArucoDetector(dictionary, parameters).detectMarkers(gray)
    assert native_ids is None and len(rejected) > 0
    result = api().detect_pose_marker(
        current, api().PoseMarkerRegistration(7, 0.0525, "a" * 64), corner_refinement="SUBPIX"
    )
    assert result.status == "OBSERVED"
    assert result.observed_marker_ids == (7,)
    # 图像 y 向下；验证 canonical 四角身份，不为14px未标定估计承诺角度精度。
    expected_quadrants = (
        ((-1, -1), (1, -1), (1, 1), (-1, 1)),
        ((-1, 1), (-1, -1), (1, -1), (1, 1)),
        ((1, 1), (-1, 1), (-1, -1), (1, -1)),
        ((1, -1), (1, 1), (-1, 1), (-1, -1)),
    )
    points = np.asarray(result.ordered_corners_px)
    assert np.isfinite(points).all()
    assert np.array_equal(np.sign(points - points.mean(axis=0)), expected_quadrants[quarter_turns])
    assert result.geometric_error_bound_m is None
    assert result.angular_velocity_bound_rad_s is None
    assert result.stability_status == "UNKNOWN"


@pytest.mark.parametrize("damaged", [None, "bit", "border"])
def test_subpix_rejected_candidates_blank_and_invalid_codes_stay_unknown(damaged):
    current, _ = _subpix_rejected_scene(() if damaged is None else (7,), damaged=damaged)
    result = api().detect_pose_marker(
        current, api().PoseMarkerRegistration(7, 0.0525, "a" * 64), corner_refinement="SUBPIX"
    )
    _assert_unknown_has_no_pose(result)


def test_subpix_rejected_candidates_native_mixed_markers_stay_unknown():
    current, _ = _subpix_rejected_scene((7, 0), side_px=48.0)
    result = api().detect_pose_marker(
        current, api().PoseMarkerRegistration(7, 0.0525, "a" * 64), corner_refinement="SUBPIX"
    )
    _assert_unknown_has_no_pose(result)
    assert sorted(result.observed_marker_ids) == [0, 7]
