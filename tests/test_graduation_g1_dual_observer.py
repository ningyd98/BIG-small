"""Development registration and full-frame dual ArUco pixels, without a simulated scene."""

import base64
import copy
import hashlib
import importlib
import importlib.util
import io
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

ROOT = Path(__file__).resolve().parents[1]


def development_module(name):
    path = "scripts.graduation.g1_dual_" + name
    assert importlib.util.find_spec(path) is not None, "missing registered development " + name
    return importlib.import_module(path)


def software_frame(marks, *, missing_depth=()):
    """Independent projected print at 0.645 m range. Mark centers relative to (159.5,119.5)."""
    asset = development_module("asset")
    descriptor = asset.geometry_descriptor()
    gray = np.full((240, 320), 240, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    depth = np.full(gray.shape, 0.645, dtype="<f4")
    for marker_id, x, y in marks:
        gray[y - 15 : y + 15, x - 15 : x + 15] = cv2.aruco.generateImageMarker(
            dictionary, marker_id, 30
        )
    for x, y in missing_depth:
        depth[y - 3 : y + 3, x - 3 : x + 3] = 0
    output = io.BytesIO()
    Image.fromarray(gray).convert("RGB").save(output, format="PNG")
    return RGBDObservation(
        **descriptor["camera"],
        frame_id="software-dual",
        episode_id="SOFTWARE_ONLY",
        scene_id="S01_NORMAL_STATIC",
        captured_at=datetime.now(UTC),
        sim_time_s=0,
        rgb_png_base64=base64.b64encode(output.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
    )


@pytest.mark.parametrize(
    ("marks", "missing", "wanted", "usable_ids", "reason"),
    [
        ([(7, 160, 80), (8, 200, 120)], [], 7, [7, 8], None),
        ([(7, 160, 80)], [], 7, [7], None),
        ([(8, 200, 120)], [], 8, [8], None),
        ([(7, 160, 80), (8, 200, 120)], [(160, 80)], 8, [8], None),
        ([(7, 160, 80), (8, 200, 120)], [(200, 120)], 7, [7], None),
        ([(7, 160, 80), (8, 220, 120)], [], None, [7, 8], "dual_marker_grasp_conflict"),
        ([(7, 160, 80), (7, 200, 120)], [], None, [], "duplicate_marker_id"),
        ([(7, 160, 80), (13, 200, 120)], [], None, [], "foreign_marker_id"),
        ([(8, 200, 120)], [(200, 120)], None, [], "marker_metric_depth_unavailable"),
        ([], [], None, [], "known_marker_not_observed"),
    ],
)
def test_original_rgbd_decides_identity_validity_and_tcp(
    marks, missing, wanted, usable_ids, reason
):
    observer = development_module("observer")
    asset = development_module("asset")
    frame = software_frame(marks, missing_depth=missing)
    geometry = asset.geometry_descriptor()
    result = observer.measure_frame(frame, geometry)
    assert (result["frame_id"], result["observation_id"], result["checksum"]) == (
        frame.frame_id,
        frame.observation_id,
        frame.checksum_sha256,
    )
    assert sorted(result["observed_ids"]) == sorted(i for i, _, _ in marks)
    assert result["selected_id"] == wanted and result["usable_ids"] == usable_ids
    assert result["usable"] is (wanted is not None)
    if reason:
        assert result["reason"] == reason and result["grasp_world_m"] is None
    else:
        assert result["grasp_world_m"] == pytest.approx([0.35, 0, 0.72995], abs=0.001)
        side = result["by_id"][str(wanted)]
        assert len(side["ordered_corners_px"]) == 4 and len(side["depth_samples"]) == 5
        assert side["plane"]["max_corner_residual_m"] < 1e-9
        assert side["object_top_world_m"] == pytest.approx([0.35, 0, 0.75495], abs=0.001)
        if len(marks) == 1:
            expected = detect_pose_marker(
                frame,
                PoseMarkerRegistration(
                    wanted, 0.075, geometry["pose_marker"]["marked_asset_sha256"]
                ),
                corner_refinement="SUBPIX",
            )
            assert expected.status == "OBSERVED"
            assert np.asarray(side["ordered_corners_px"]) == pytest.approx(
                np.asarray(expected.ordered_corners_px)
            )
            assert side["marker_center_world_m"] == pytest.approx(expected.marker_center_world_m)
    if missing:
        failed = "7" if missing[0][0] == 160 else "8"
        assert result["by_id"][failed]["reason"] == "marker_metric_depth_unavailable"
        assert len(result["by_id"][failed]["depth_samples"]) == 5
    if len(usable_ids) == 2:
        assert (result["target_disagreement_m"] <= 0.010) is (wanted is not None)


def test_development_geometry_rejects_swapped_rigid_transform_and_wrong_camera():
    asset, observer = development_module("asset"), development_module("observer")
    g = asset.geometry_descriptor()
    frame = software_frame([(8, 200, 120)])
    swapped = copy.deepcopy(g)
    swapped["development_dual"]["markers"]["8"]["object_T_marker"] = g["marker_to_object"]
    with pytest.raises(ValueError):
        observer.measure_frame(frame, swapped)
    camera = frame.model_dump()
    camera.update(calibration_version="different", checksum_sha256="")
    result = observer.measure_frame(RGBDObservation.model_validate(camera), g)
    assert not result["usable"] and result["reason"] == "registered_camera_mismatch"
    wrong_scene = frame.model_dump() | {"scene_id": "foreign", "checksum_sha256": ""}
    result = observer.measure_frame(RGBDObservation.model_validate(wrong_scene), g)
    assert not result["usable"] and result["reason"] == "registered_scene_mismatch"


def test_physical_board_supports_and_true_ordered_dictionary_symbols():
    asset = development_module("asset")
    original = (ROOT / asset.BASE_ASSET_PATH).read_bytes()
    new = asset.build_xml(original)
    assert (
        hashlib.sha256(new).hexdigest()
        == asset.geometry_descriptor()["pose_marker"]["marked_asset_sha256"]
    )
    body = ET.fromstring(new).find("./worldbody/body[@name='object']")
    assert len(body.findall("geom")) == 79
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for marker_id, x, y in ((7, 0, 0.1), (8, 0.1, 0)):
        prefix = f"g1_dual_id{marker_id}_"
        for part in ("plate", "support"):
            geom = body.find(f"geom[@name='{prefix}{part}']")
            assert float(geom.attrib["mass"]) > 0
            assert (geom.attrib["contype"], geom.attrib["conaffinity"]) == ("1", "3")
        for r, row in enumerate(cv2.aruco.generateImageMarker(dictionary, marker_id, 6)):
            for c, value in enumerate(row):
                geom = body.find(f"geom[@name='{prefix}r{r}c{c}']")
                assert float(geom.attrib["mass"]) == 0
                assert np.fromstring(geom.attrib["pos"], sep=" ") == pytest.approx(
                    [x + (c - 2.5) * 0.0125, y + (2.5 - r) * 0.0125, 0.03504]
                )
                assert float(geom.attrib["rgba"].split()[0]) == (0.98 if value else 0.01)
    with pytest.raises(ValueError):
        asset.build_xml(original.replace(b'mass="0.08"', b'mass="0.09"'))


def test_isolated_hooks_require_the_original_source_bytes_and_compile():
    adapter = development_module("runtime_adapter")
    for path in adapter.SOURCE_SHA256:
        original = (ROOT / path).read_bytes()
        changed = adapter.adapt_source(path, original)
        assert changed != original
        compile(changed, path, "exec")
        with pytest.raises(ValueError):
            adapter.adapt_source(path, original + b"\n")


def test_only_a_cross_decoder_repeat_of_the_same_oriented_print_is_deduplicated():
    observer = development_module("observer")
    corners = np.asarray([[20, 20], [40, 20], [40, 40], [20, 40]])
    direct = [(7, corners)]
    candidates, ambiguous = observer.physical_candidates(direct, [(7, corners + 0.2)])
    assert not ambiguous and len(candidates) == 1
    assert candidates[0]["origins"] == ["direct", "exact_rejected"]
    _, ambiguous = observer.physical_candidates(direct * 2, [])
    assert ambiguous
    _, ambiguous = observer.physical_candidates(direct, [(8, corners)])
    assert ambiguous


def test_unadapted_worktree_cannot_claim_to_supply_development_runtime_sources():
    asset = development_module("asset")
    adapter = development_module("runtime_adapter")
    geometry = asset.geometry_descriptor()
    declared = geometry["development_dual"]["development_sources_sha256"]
    catalog = {
        **declared,
        **adapter.SOURCE_SHA256,
        asset.ASSET_PATH: asset.ASSET_SHA,
        asset.BASE_ASSET_PATH: asset.BASE_SHA,
    }
    with pytest.raises(ValueError):
        asset.check_source_binding(geometry, catalog)
