import pytest
from scripts.graduation.proposal_terminal_visibility import bucket


def test_only_registered_normal_views_can_qualify_a_terminal():
    assert bucket(True, {"nominal": False, "translated": True}) == "translated_only"
    assert bucket(False, {"nominal": False, "translated": True}) == "reconstruction_unknown"
    assert bucket(True, {"nominal": False, "translated": False}) == "neither"
    with pytest.raises(ValueError):
        bucket(True, {"nominal": False, "hidden": True})


def test_view_switch_rejects_cross_step_stale_id_foreign_calibration_and_expiry():
    import time
    from datetime import UTC, datetime, timedelta

    from scripts.graduation.proposal_terminal_visibility_switch import check_attempts, deadline

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    base = observation_payload()
    t = datetime.now(UTC)

    def frame(id_, stamp, version):
        return RGBDObservation.model_validate(
            {
                **base,
                "frame_id": id_,
                "episode_id": "dev",
                "captured_at": stamp,
                "calibration_version": version,
            }
        )

    a, b = frame("a", t, "a"), frame("b", t + timedelta(milliseconds=1), "b")
    g = {
        v: {"camera": {"calibration_version": k}}
        for v, k in (("nominal", "a"), ("translated", "b"))
    }
    first = ("nominal", 0, a)
    second = ("translated", 0, b)
    check_attempts([first, second], 0, 0.0, g)
    for other in (
        ("translated", 1, b),
        ("translated", 0, a),
        ("nominal", 0, b),
        ("translated", 0, frame("c", t, "b")),
        ("translated", 0, frame("c", b.captured_at, "a")),
    ):
        with pytest.raises(ValueError):
            check_attempts([first, other], 0, 0.0, g)
    with pytest.raises(ValueError):
        check_attempts([first, second, second], 0, 0.0, g)
    with pytest.raises(ValueError):
        deadline(time.perf_counter() - 0.101)
