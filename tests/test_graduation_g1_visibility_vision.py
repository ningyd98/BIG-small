"""Current-pixel positive and adverse controls for the registered G1 observer."""

import base64
import io
import json
from datetime import UTC, datetime

import cv2
import numpy as np
import pytest
from PIL import Image
from scripts.graduation import g1_dual_asset

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def fixture_frame(marks, *, damage=None, mirror=False, turns=0, depth_mode=None):
    """Independently paint the registered prints at 5 real source pixels per cell."""
    geometry = g1_dual_asset.geometry_descriptor()
    image = np.full((240, 320), 220, np.uint8)
    depth = np.full(image.shape, 0.645, dtype="<f4")
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for code, x, y in marks:
        im = cv2.aruco.generateImageMarker(dictionary, code, 30)
        if mirror is True or (type(mirror) is int and mirror == code):
            im = np.fliplr(im).copy()
        im = np.rot90(im, turns).copy()
        if damage == "erase_cell":
            im[5:10, 5:10] = 127
        if damage == "low_contrast":
            im = np.where(im > 0, 144, 124)
        if damage == "no_quiet":
            image[y - 28 : y + 30, x - 26 : x + 26] = 0
        image[y - 15 : y + 15, x - 15 : x + 15] = im
        if depth_mode == "missing":
            depth[y - 19 : y + 19, x - 19 : x + 19] = 0
        if depth_mode == "split":
            depth[y - 15 : y + 15, x - 15 : x] -= 0.15
    stream = io.BytesIO()
    Image.fromarray(image).convert("RGB").save(stream, format="PNG")
    return RGBDObservation(
        **geometry["camera"],
        frame_id="current-control",
        episode_id="development",
        scene_id="development",
        captured_at=datetime(2026, 11, 24, tzinfo=UTC),
        sim_time_s=0,
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
    ), geometry


def read(marks, **options):
    from scripts.graduation.g1_visibility_vision import measure_frame

    frame, geometry = fixture_frame(marks, **options)
    return measure_frame(frame, geometry)


@pytest.mark.parametrize("marks", [[(7, 90, 55)], [(8, 185, 108)], [(7, 80, 70), (8, 120, 110)]])
def test_positive_registered_front_face_and_internal_evidence(marks):
    r = read(marks)
    assert r["usable"] and r["selected_id"] == marks[0][0]
    for code, x, y in marks:
        side = r["by_id"][str(code)]
        mean = np.asarray(side["ordered_corners_px"]).mean(axis=0)
        assert mean == pytest.approx([x - 0.5, y - 0.5], abs=0.35)
        support = side["grid_support"]
        assert support["exact_dictionary_matches"] == 1
        assert support["contrast_gray"] >= 32 and len(support["cell_values"]) == 36
        assert len(support["transition_points"]) >= 4 and support["heldout_rms_px"] <= 0.75
        assert side["plane"]["inlier_cells"] >= 12


def test_internal_search_with_entire_white_surround_absent():
    r = read([(7, 101, 151)], damage="no_quiet")
    assert r["usable"] and r["observed_ids"] == [7]
    assert r["by_id"]["7"]["origins"] == ["internal_white_component"]


@pytest.mark.parametrize(
    ("marks", "options"),
    [
        ([], {}),
        ([(7, 150, 82)], {"damage": "low_contrast"}),
        ([(7, 150, 82)], {"damage": "erase_cell"}),
        ([(7, 150, 82)], {"mirror": True}),
        ([(7, 150, 82)], {"depth_mode": "missing"}),
        ([(8, 150, 82)], {"depth_mode": "split"}),
        ([(13, 150, 82)], {}),
        ([(7, 110, 82), (13, 175, 108)], {}),
        ([(7, 90, 65), (7, 160, 140)], {}),
    ],
)
def test_no_target_on_unsupported_or_nonunique_pixels_or_depth(marks, options):
    r = read(marks, **options)
    assert not r["usable"] and r["grasp_world_m"] is None and r["selected_id"] is None


def test_real_pixels_yield_two_independent_targets_before_conflict_refusal():
    r = read([(7, 80, 70), (8, 132, 110)])
    assert r["reason"] == "dual_marker_grasp_conflict"
    assert r["usable_ids"] == [7, 8] and not r["usable"] and r["selected_id"] is None
    p7, p8 = [np.asarray(r["by_id"][str(k)]["grasp_world_m"]) for k in (7, 8)]
    assert np.linalg.norm(p7 - p8) == pytest.approx(r["target_disagreement_m"])
    assert r["target_disagreement_m"] > 0.025


def test_registered_front_face_and_mirrored_print_in_one_image_refuses():
    r = read([(8, 88, 90), (7, 148, 142)], mirror=7)
    assert (
        not r["usable"] and r["reason"] == "ambiguous_marker_identity" and r["selected_id"] is None
    )


@pytest.mark.parametrize("turn", range(4))
def test_each_foreign_dictionary_word_with_a_registered_mark_stops(turn):
    for code in sorted(set(range(50)) - {7, 8}):
        r = read([(7, 88, 85), (code, 178, 145)], turns=turn)
        assert r["observed_ids"] == sorted((7, code))
        assert r["reason"] == "foreign_marker_id" and not r["usable"] and r["grasp_world_m"] is None


@pytest.mark.parametrize("turn", [0, 1, 2, 3])
def test_dictionary_quarter_rotations_preserve_metric_winding(turn):
    r = read([(7, 85, 179)], turns=turn)
    assert r["usable"]
    rotation = np.reshape(r["by_id"]["7"]["rotation_marker_to_world"], (3, 3))
    assert rotation[:, 0] == pytest.approx(
        [np.cos(turn * np.pi / 2), np.sin(turn * np.pi / 2), 0], abs=0.02
    )
    assert np.linalg.det(rotation) == pytest.approx(1)


def test_id8_self_reflection_equals_a_legitimate_quarter_turn_pixel_for_pixel():
    a, _ = fixture_frame([(8, 145, 91)], mirror=True)
    b, _ = fixture_frame([(8, 145, 91)], turns=3)
    assert a.rgb_png_base64 == b.rgb_png_base64 and a.checksum_sha256 == b.checksum_sha256
    r = read([(8, 145, 91)], mirror=True)
    assert (
        r["usable"]
        and r["by_id"]["8"]["grid_support"]["reflection_equals_same_dictionary_rotation"]
    )


def test_nonfinite_depth_cells_can_be_serialized_as_rejected_measurements():
    from scripts.graduation.g1_visibility_vision import _plane

    frame, _ = fixture_frame([(7, 100, 75)])
    depth = np.full((frame.height, frame.width), np.nan)
    depth[70:, :] = np.inf
    side = {}
    grid = {"basis": np.diag([5.0, 5.0]), "center": [100.0, 75.0]}
    assert _plane(frame, grid, depth, side) == "marker_metric_depth_unavailable"
    assert all(not item["valid"] and item["optical_z_m"] is None for item in side["depth_samples"])
    json.dumps(side, allow_nan=False)
