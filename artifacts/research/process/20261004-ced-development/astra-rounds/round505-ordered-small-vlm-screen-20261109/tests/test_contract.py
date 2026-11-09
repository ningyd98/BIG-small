"""Predeclared R505 CPU contracts; no model or original experiment is mutated."""

import importlib.util
import math
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "implementation/score_native.py"
if MODULE.exists():
    spec = importlib.util.spec_from_file_location("r505_score_native", MODULE)
    subject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subject)
else:
    subject = None


def api(name):
    assert subject is not None, "R505 normalization/scoring implementation not yet written"
    return getattr(subject, name)


def test_point_uses_xy_not_yx():
    assert api("point_pixel")([250, 750], 320, 240, "normalized_1000") == (80, 180)


def test_normalized_endpoint_is_last_pixel():
    assert api("point_pixel")([1000, 1000], 320, 240, "normalized_1000") == (319, 239)


def test_unit_and_continuous_pixels():
    assert api("point_pixel")([0.25, 0.75], 320, 240, "unit") == (80, 180)
    assert api("point_pixel")([19.9, 20.1], 320, 240, "pixel") == (19, 20)


@pytest.mark.parametrize("point,space", [([-1, 0], "normalized_1000"), ([1001, 2], "normalized_1000"), ([math.nan, 2], "pixel"), ([math.inf, 2], "pixel"), ([320, 5], "pixel"), ([True, 4], "pixel"), ([1, 2], "unknown")])
def test_invalid_points_are_not_clamped(point, space):
    with pytest.raises(ValueError):
        api("point_pixel")(point, 320, 240, space)


def test_box_center_is_geometric_and_not_selected_by_oracle():
    box, point = api("box_pixel")([250, 250, 750, 750], 320, 240, "normalized_1000")
    assert box == (80.0, 60.0, 240.0, 180.0)
    assert point == (160, 120)


@pytest.mark.parametrize("box", [[500, 0, 100, 10], [0, 0, 0, 4], [-1, 0, 100, 10]])
def test_reversed_or_invalid_boxes_rejected(box):
    with pytest.raises(ValueError):
        api("box_pixel")(box, 320, 240, "normalized_1000")


def test_mask_point_is_foreground_nearest_own_centroid_tie_yx():
    # The center (1,1) is a hole; never use a box center outside the mask.
    value = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    mask, point = api("mask_pixel")(value, 3, 3, kind="probability", threshold=0.5)
    assert point == (1, 0)
    assert mask[point[1]][point[0]]


def test_mask_nearest_resize_threshold_and_empty():
    mask, point = api("mask_pixel")([[0.49, 0.5]], 4, 2, kind="probability", threshold=0.5)
    assert mask == [[False, False, True, True], [False, False, True, True]]
    assert point == (2, 0)
    assert api("mask_pixel")([[0, 0]], 2, 1, kind="probability", threshold=0.5)[1] is None


def test_mask_logit_zero_boundary():
    mask, point = api("mask_pixel")([[-0.1, 0]], 2, 1, kind="logit", threshold=0)
    assert mask == [[False, True]] and point == (1, 0)


def test_candidate_selection_uses_scores_then_original_order():
    select = api("select_candidate")
    assert select([{"id": "first"}, {"id": "oracle-perfect"}])["id"] == "first"
    assert select([{"score": 0.1}, {"score": 0.9}])["score"] == 0.9
    assert select([{"score": 0.9, "id": 1}, {"score": 0.9, "id": 2}])["id"] == 1


def test_absence_is_distinct_from_invalid_output():
    assert api("native_status")([], explicit_absence=True, parse_error=None) == "REFUSAL"
    assert api("native_status")([], explicit_absence=False, parse_error="bad syntax") == "INVALID"
    assert api("native_status")([{}], explicit_absence=False, parse_error=None) == "DETECTED"


def test_model_manifest_rejects_oracle_and_labeled_paths():
    good = {"schema": "r505-public-v1", "cases": [{"index": 1, "id": "case-0001", "rgb_path": "cache/case-0001/rgb.png", "rgb_sha256": "a" * 64, "rgb_bytes": 100, "instruction": "Pick up the red block and place it in the green region.", "target_phrase": "red block", "destination_phrase": "green region"}]}
    check = api("assert_public_inputs")
    check(good)
    for key in ["instance_ids", "expected_geom_label", "kind", "old_prediction"]:
        bad = {**good, "cases": [{**good["cases"][0], key: "LEAK_SENTINEL"}]}
        with pytest.raises(ValueError):
            check(bad)
    with pytest.raises(ValueError):
        check({**good, "cases": [{**good["cases"][0], "rgb_path": "negative_absent-01/rgb.png"}]})


def test_manifest_rejects_case_identity_mix_or_duplicates():
    check = api("assert_public_inputs")
    with pytest.raises(ValueError):
        check({"schema": "r505-public-v2", "cases": []})
    with pytest.raises(ValueError):
        check({"schema": "r505-public-v1", "cases": [{"id": "positive-01"}]})


def test_strict_json_does_not_remove_fences():
    assert api("strict_json")('{"target_pixel":null}') == {"target_pixel": None}
    with pytest.raises(ValueError):
        api("strict_json")('```json\n{"target_pixel":null}\n```')


def test_iou_and_depth_validity_separate_from_instance_hit():
    assert api("box_iou")([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert api("pixel_assessment")((1, 0), [11, 0], [True, True], [1.0, 1.0], 2, 1, 11) == {"hit": False, "valid_depth": True, "actual_geom_id": 0}
