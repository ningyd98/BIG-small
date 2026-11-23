"""Pixel-only positive and rejection controls for the frozen-frame audit."""

from datetime import timedelta

import numpy as np
import pytest
from scripts.phase7.frozen_vision import (
    MODES,
    Json,
    Mode,
    capture_step,
    color_measurement,
    marker_measurement,
)
from scripts.phase7.summarize_vision import failure_runs, step_coverage

from tests.test_opencv_target_evidence import scene, tracker
from tests.test_pose_marker_evidence import observation, registration


@pytest.mark.parametrize(
    ("damage", "sizes", "reason"),
    [
        (None, [36], None),
        ("decoy", [36, 36], "color_identity_ambiguous"),
        ("occluded", [12, 12], "color_identity_ambiguous"),
        ("depth", [36], "target_depth_incomplete"),
        ("missing", [], "target_missing"),
    ],
)
def test_retains_each_support_and_fails_closed(
    damage: str | None,
    sizes: list[int],
    reason: str | None,
) -> None:
    initial = scene()
    observed = scene("frozen", time=0.1, started=initial.captured_at, damage=damage)
    row = color_measurement(observed, tracker(initial))
    assert sorted(entry["area_px"] for entry in row["components"]) == sizes
    assert row["tracker_geometry_reason"] == reason
    assert row["full_extent"] is (reason is None)
    for component in row["components"]:
        assert sum(x1 - x0 + 1 for y, x0, x1 in component["row_runs_px"]) == component["area_px"]
    if damage == "depth":
        assert row["components"][0]["valid_depth_pixels"] == 35
    if damage == "decoy":
        # Both candidate orderings fit color, area and depth. No tie-breaker.
        assert {entry["median_optical_z_m"] for entry in row["components"]} == {
            float(np.float32(0.94))
        }
        assert row["same_target_identity"] == "UNKNOWN"


def test_unique_color_without_calibrated_depth_stays_metric_unknown() -> None:
    current = scene()
    row = color_measurement(current, tracker(current, depth_error_bound_m=None))
    assert len(row["components"]) == 1
    assert row["tracker_geometry_reason"] is None and row["full_extent"] is False


@pytest.mark.parametrize("mode", ["NONE", "SUBPIX"])
@pytest.mark.parametrize(
    ("kwargs", "status", "reason"),
    [
        ({}, "OBSERVED", "uncalibrated_single_frame_pose_estimate"),
        ({"marker_id": 9}, "UNKNOWN", "foreign_or_ambiguous_marker"),
        ({"duplicate": True}, "UNKNOWN", "foreign_or_ambiguous_marker"),
        ({"calibration": None}, "UNKNOWN", "registered_camera_context_missing"),
        ({"depth": 0.0}, "UNKNOWN", "marker_metric_depth_unavailable"),
        ({"depth": 2.0}, "UNKNOWN", "registered_marker_size_inconsistent"),
    ],
)
def test_marker_keeps_detector_verdict_and_cannot_certify_stability(
    mode: Mode,
    kwargs: Json,
    status: str,
    reason: str,
) -> None:
    row = marker_measurement(observation(**kwargs), registration(), mode)
    assert (row["status"], row["reason"]) == (status, reason)
    assert row["stability_status"] == "UNKNOWN"
    assert row["geometric_error_bound_m"] is None
    assert row["angular_velocity_bound_rad_s"] is None


def test_ordered_quarter_turns_only_resolve_sample_orientation() -> None:
    rows = [marker_measurement(observation(rotation=k), registration(), "NONE") for k in range(4)]
    assert len({round(row["yaw_world_rad"], 2) for row in rows}) == 4
    assert all(row["angular_velocity_bound_rad_s"] is None for row in rows)


def test_repeats_wrong_times_and_missing_boundaries() -> None:
    first = scene()
    later = first.captured_at + timedelta(seconds=0.05)
    assert capture_step(1, 1, first.captured_at, later) == "SAME_STEP_REACQUISITION"
    assert capture_step(2, 1, first.captured_at, later) == "OUT_OF_ORDER_PHYSICS"
    assert capture_step(1, 2, later, first.captured_at) == "OUT_OF_ORDER_CAPTURE"
    assert capture_step(1, 2, first.captured_at, later) == "ADVANCED"
    assert step_coverage([3, 3, 4, 6], 2, 7) == {
        "expected_unique_steps": 6,
        "observed_unique_steps": 3,
        "acquisitions": 4,
        "same_step_extra_acquisitions": 1,
        "missing_step_ranges": [[2, 2], [5, 5], [7, 7]],
        "both_endpoints_present": False,
    }


def test_marker_failures_span_acquisitions_and_include_internal_gaps() -> None:
    # Two independently acquired frames at step 3 have different verdicts.
    records = [(1, 2, False), (2, 3, False), (3, 3, True), (4, 4, False)]
    spans = failure_runs(records)
    assert spans == [
        {
            "first_acquisition": 1,
            "last_acquisition": 2,
            "first_step": 2,
            "last_step": 3,
            "acquisitions": 2,
        },
        {
            "first_acquisition": 4,
            "last_acquisition": 4,
            "first_step": 4,
            "last_step": 4,
            "acquisitions": 1,
        },
    ]


def test_same_pixel_links_preserve_two_paths_and_never_join_a_physics_gap() -> None:
    from scripts.phase7.summarize_vision import same_pixel_links

    first = [{"row_runs_px": [[1, 1, 3]]}, {"row_runs_px": [[5, 1, 3]]}]
    later = [{"row_runs_px": [[5, 2, 4]]}, {"row_runs_px": [[1, 1, 3]]}]
    assert same_pixel_links(3, first, 4, later) == [
        {"previous_index": 0, "current_index": 1, "common_pixels": 3},
        {"previous_index": 1, "current_index": 0, "common_pixels": 2},
    ]
    assert same_pixel_links(3, first, 5, later) == []
    assert same_pixel_links(3, first, 3, first) == []


def test_fake_plain_black_quad_has_no_decoded_id_in_either_mode() -> None:
    import base64
    import io

    from PIL import Image

    initial = observation()
    pixels = np.full((160, 160, 3), 255, dtype=np.uint8)
    pixels[56:104, 56:104] = 0
    output = io.BytesIO()
    Image.fromarray(pixels).save(output, format="PNG")
    current = type(initial).model_validate(
        {
            **initial.model_dump(),
            "rgb_png_base64": base64.b64encode(output.getvalue()).decode(),
            "checksum_sha256": "",
        }
    )
    for mode in MODES:
        result = marker_measurement(current, registration(), mode)
        assert result["status"] == "UNKNOWN"
        assert result["observed_marker_ids"] == ()


def test_expired_evaluation_and_missing_calibration_cannot_establish_identity() -> None:
    current = scene()
    original = tracker(current)
    assert (
        original._binding_reason_at(current, current.captured_at + timedelta(seconds=5.1))
        == "capture_time_not_fresh"
    )
    wrong = current.model_copy(update={"calibration_version": None})
    assert (
        original._binding_reason_at(wrong, current.captured_at)
        == "observation_calibration_version_changed"
    )


def test_grounding_clock_is_bound_to_the_recorded_acquisition() -> None:
    from scripts.phase7.frozen_vision import grounding_clock

    base: Json = {
        "index": 1,
        "step_id": "step-2",
        "observation_id": "obs-7",
        "checksum_sha256": "1" * 64,
        "source_generation": "2" * 64,
        "acquisition": {"acquisition_id": "acquisition-7", "path": "frames/7", "sha256": "3" * 64},
    }
    clock = {**base, "purpose": "GROUNDING", "evaluated_at": "2026-10-07T00:00:00+00:00"}
    record = {**base, "tracker_evaluated_at": clock["evaluated_at"], "tracker_clock": clock}
    assert grounding_clock(record, 1, "step-2") == clock
    for key, bad in (
        ("observation_id", "other"),
        ("purpose", "ADMISSION_PRE"),
        ("acquisition", {**base["acquisition"], "acquisition_id": "acquisition-8"}),
    ):
        with pytest.raises(ValueError, match="grounding clock"):
            grounding_clock({**record, "tracker_clock": {**clock, key: bad}}, 1, "step-2")
