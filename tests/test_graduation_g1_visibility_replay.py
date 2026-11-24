from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from scripts.graduation import g1_visibility_replay as replay


def test_distinct_same_step_acquisitions_allowed_but_stale_and_repeated_packets_refused():
    start = datetime(2026, 11, 24, tzinfo=UTC)
    previous = SimpleNamespace(frame_id="first", sim_time_s=1.0, captured_at=start)
    current = SimpleNamespace(
        frame_id="second", sim_time_s=1.0, captured_at=start + timedelta(microseconds=1)
    )
    replay.check_acquisition(current, {"first"}, previous)
    with pytest.raises(ValueError, match="duplicate"):
        replay.check_acquisition(previous, {"first"}, current)
    with pytest.raises(ValueError, match="clock"):
        replay.check_acquisition(previous, set(), current)
    earlier = SimpleNamespace(
        frame_id="third", sim_time_s=0.9, captured_at=current.captured_at + timedelta(seconds=1)
    )
    with pytest.raises(ValueError, match="clock"):
        replay.check_acquisition(earlier, set(), current)


def test_per_id_estimate_uses_independent_registered_attachment_and_checks_reported_top():
    eye = np.eye(4)
    mount = eye.copy()
    mount[:3, 3] = [0.1, 0, 0.035]
    tcp = eye.copy()
    tcp[2, 3] = 0.010
    geometry = {
        "object_half_extent_m": [0.035] * 3,
        "object_to_tcp": tcp.ravel().tolist(),
        "development_dual": {
            "markers": {"8": {"object_T_marker": mount.ravel().tolist(), "marker_size_m": 0.075}}
        },
    }
    side = {
        "marker_center_world_m": [0.5, 0.025, 0.071],
        "rotation_marker_to_world": np.eye(3).ravel().tolist(),
        "object_center_world_m": [0.4, 0.025, 0.036],
        "object_top_world_m": [0.4, 0.025, 0.071],
        "grasp_world_m": [0.4, 0.025, 0.046],
    }
    assert np.allclose(replay.independent_pose(geometry, 8, side)["top_m"], [0.4, 0.025, 0.071])
    with pytest.raises(ValueError, match="rigid"):
        replay.independent_pose(geometry, 8, {**side, "object_top_world_m": [0.4, 0.025, 0.046]})


def test_truth_join_detects_valid_registered_id_assigned_to_wrong_physical_square():
    camera = {"camera_to_world": np.eye(4).ravel().tolist(), "intrinsics": [100, 100, 20, 20]}

    def marker(x):
        return {
            "object_T_marker": [1, 0, 0, x, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            "marker_size_m": 0.08,
        }

    geometry = {
        "camera": camera,
        "development_dual": {"markers": {"7": marker(-0.1), "8": marker(0.1)}},
    }
    truth = {
        "object_geom_position_m": [0, 0, 1],
        "object_geom_rotation_row_major": np.eye(3).ravel().tolist(),
    }
    quad = [[6, 16], [14, 16], [14, 24], [6, 24]]
    assert replay.identity_in_print(geometry, truth, 7, quad)
    assert not replay.identity_in_print(geometry, truth, 8, quad)


def test_genuine_conflict_control_requires_two_qualified_independent_grasp_estimates():
    a = {
        "observed_ids": [7, 8],
        "usable": False,
        "selected_id": None,
        "reason": "dual_marker_grasp_conflict",
        "usable_ids": [7, 8],
        "per_id": {"7": {"tcp_m": [0, 0, 0]}, "8": {"tcp_m": [0.025, 0, 0]}},
        "target_disagreement_m": 0.025,
    }
    assert replay.conflict_demonstrated(a)
    for bad in [
        {"usable_ids": [7]},
        {"target_disagreement_m": 0.012},
        {"reason": "known_marker_not_observed"},
        {"per_id": {"7": {"tcp_m": [0, 0, 0]}, "8": {"tcp_m": [0.009, 0, 0]}}},
    ]:
        assert not replay.conflict_demonstrated({**a, **bad})
