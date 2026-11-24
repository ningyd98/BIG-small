from datetime import UTC, datetime

import pytest
from scripts.graduation import proposal_gate_windows as windows


def marker(z, bound=None):
    return {
        "z_m": z,
        "error_m": bound,
        "stability_status": "UNKNOWN",
        "reason": "observed" if z is not None else "missing",
    }


def test_grid_includes_the_real_post_once_and_handles_an_incomplete_final_stride():
    assert windows.endpoints(4200, 6240) == list(range(4200, 6241, 120))
    assert windows.endpoints(3, 125) == [3, 123, 125]


def test_bounds_unavailable_and_missing_early_frames_are_unknown():
    series = {i: marker(0.060) for i in range(53, 175)}
    series[80] = marker(None)
    missing = windows.pixel_window(series, marker(0.0), 53, 173)
    assert missing["missing_marker_steps"] == [80]
    assert missing["height_sample_points"] == "UNKNOWN"
    assert missing["certified_joint"] == "UNKNOWN"
    initial = windows.pixel_window(series, marker(0.0), 53, 53)
    assert initial["window_samples"] == 1
    assert initial["height_sample_points"] == "UNKNOWN"
    series[80] = marker(0.060)
    series[174] = marker(-1.0)
    result = windows.pixel_window(series, marker(0.0), 53, 173)
    assert result["height_sample_points"] == "VALID"
    assert result["bounded_height"] == result["certified_joint"] == "UNKNOWN"
    assert result["bounded_stability"] == "UNKNOWN"


def test_height_intervals_use_reset_and_per_sample_errors():
    series = {i: marker(0.077, 0.002) for i in range(121)}
    reset = marker(0.02, 0.005)
    assert windows.pixel_window(series, reset, 0, 120)["bounded_height"] == "VALID"
    series[76] = marker(0.072, 0.002)
    assert windows.pixel_window(series, reset, 0, 120)["bounded_height"] == "UNKNOWN"
    series[76] = marker(0.052, 0.002)
    assert windows.pixel_window(series, reset, 0, 120)["bounded_height"] == "INVALID"


def test_source_checks_fail_for_wrong_episode_clock_asset_and_endpoint_coverage():
    frame = {
        "episode": "ep",
        "step": 12,
        "sim_time_s": 0.05,
        "calibration_version": "camera",
        "captured_at": datetime.now(UTC).isoformat(),
    }
    windows.check_frame(frame, "ep", "camera")
    for corrupted in ({"episode": "other"}, {"sim_time_s": 0.051}, {"calibration_version": "x"}):
        with pytest.raises(ValueError):
            windows.check_frame({**frame, **corrupted}, "ep", "camera")
    allocation = {"episode": "ep", "asset_sha256": "A", "end_steps": [3, 123]}
    report = {"episode": "ep", "asset_sha256": "A", "windows": [{"end": 3}, {"end": 123}]}
    windows.check_rows(report, allocation)
    for corrupted in (
        {"asset_sha256": "B"},
        {"windows": [{"end": 123}]},
        {"windows": [{"end": 3}, {"end": 3}]},
    ):
        with pytest.raises(ValueError):
            windows.check_rows({**report, **corrupted}, allocation)


def test_offline_labels_and_foreign_geometry_are_rejected_on_the_pixel_path():
    row = {
        "episode": "E",
        "step": 12,
        "sim_time_s": 0.05,
        "calibration_version": "camera",
        "captured_at": datetime.now(UTC).isoformat(),
    }
    with pytest.raises(ValueError, match="offline"):
        windows.check_frame({**row, "offline_labels": {}}, "E", "camera")
    mark = {
        "status": "OBSERVED",
        "observed_marker_ids": [8],
        "registered_sample_object_pose": {"center_world_m": [0, 0, 0.1]},
    }
    with pytest.raises(ValueError, match="identity"):
        windows.marker_sample(mark, 7)


def test_three_way_tables_keep_all_rows_and_all_unknowns():
    pairs = [("INVALID", "UNKNOWN"), ("VALID", "UNKNOWN"), ("UNKNOWN", "UNKNOWN")]
    result = windows.matrix(pairs)
    assert all(result[t]["UNKNOWN"] == 1 for t in windows.LABELS)
    assert sum(count for row in result.values() for count in row.values()) == 3
