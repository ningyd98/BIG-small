"""The decision timer must include both acquisition and the gate's final refusal."""

import pytest
from recovery_route_v2 import elapsed_windows


def test_recovery_uses_original_and_second_acquisition_origins():
    ns = 1_000_000
    rows = elapsed_windows(
        {
            k: v * ns
            for k, v in dict(
                action_start=0,
                first_start=12,
                selected_start=37,
                screen_start=55,
                screen_end=3570,
                decision_end=3573,
            ).items()
        }
    )
    assert rows == {
        "action_wall_ms": 3573,
        "initial_capture_to_decision_ms": 3561,
        "selected_capture_to_decision_ms": 3536,
        "initial_capture_to_screen_end_ms": 3558,
        "selected_capture_to_screen_end_ms": 3533,
        "pure_screen_ms": 3515,
    }


def test_normal_single_acquisition_and_reversed_clock_refused():
    times = dict(
        action_start=10,
        first_start=20,
        selected_start=20,
        screen_start=30,
        screen_end=40,
        decision_end=45,
    )
    row = elapsed_windows(times)
    assert row["initial_capture_to_decision_ms"] == row["selected_capture_to_decision_ms"]
    with pytest.raises(ValueError, match="chronology"):
        elapsed_windows(times | {"selected_start": 19})
