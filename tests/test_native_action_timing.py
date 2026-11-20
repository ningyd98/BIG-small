import pytest

from cloud_edge_robot_arm.research.native_action_timing import (
    ActionTiming,
    mark_timing,
    timed,
    use_action_timing,
)


def test_probe_retains_nested_same_thread_ranges_on_failure():
    timing = ActionTiming()
    mark_timing("inactive")
    with use_action_timing(timing):
        mark_timing("pre_start", physics_step=120)
        with pytest.raises(ValueError, match="original"), timed("owner_check", operation_id=12):
            with timed("sqlite"):
                raise ValueError("original")
        mark_timing("action_exit")
    mark_timing("inactive")
    payload = timing.payload()
    markers = payload["marks"]
    assert [row["label"] for row in markers] == ["pre_start", "action_exit"]
    outer, inner = payload["spans"]
    assert (outer["label"], inner["label"]) == ("owner_check", "sqlite")
    assert inner["parent"] == outer["seq"]
    assert inner["operation_id"] == outer["operation_id"] == 12
    assert markers[0]["physics_step"] == 120
    assert (
        markers[0]["ns"]
        <= outer["start_ns"]
        <= inner["start_ns"]
        <= inner["end_ns"]
        <= outer["end_ns"]
        <= markers[1]["ns"]
    )


def _timing_reader():
    from pathlib import Path
    from runpy import run_path

    return run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "artifacts/research/process/20261004-ced-development/astra-rounds"
            / "round-p0-teacher-whole-action-20261120/read_whole_action_timing.py"
        )
    )


def test_timing_readback_charges_nested_sql_once_and_covers_idle():
    reader = _timing_reader()
    timing = {
        "schema_version": "native.whole-action.timing.v1",
        "clock": "monotonic_ns",
        "thread_id": 1,
        "marks": [
            {"label": "pre_start", "ns": 100, "physics_step": 120},
            {"label": "action_exit", "ns": 150, "physics_step": None},
        ],
        "spans": [
            {
                "seq": 1,
                "parent": None,
                "label": "owner_check",
                "start_ns": 105,
                "end_ns": 145,
                "operation_id": None,
                "acquisition_id": None,
            },
            {
                "seq": 2,
                "parent": 1,
                "label": "sqlite",
                "start_ns": 110,
                "end_ns": 130,
                "operation_id": None,
                "acquisition_id": None,
            },
        ],
    }
    result = reader["read_timing"](timing, {}, {"step_started_at": 1e-7}, None)
    assert result["action"]["exclusive_ns"] == {"owner_check": 20, "sqlite": 20, "other": 10}
    assert result["action"]["wall_ns"] == 50
    assert result["post_elapsed_ms"] is None

    timing["spans"][1]["parent"] = None
    with pytest.raises(ValueError, match="same-thread nesting"):
        reader["read_timing"](timing, {}, {"step_started_at": 1e-7}, None)

    timing["spans"][1]["parent"] = 1
    with pytest.raises(ValueError, match="original Shield PRE"):
        reader["read_timing"](timing, {}, {"step_started_at": 2e-7}, None)


def test_complete_timing_requires_every_native_physics_operation():
    reader = _timing_reader()
    labels = (
        "pre_start",
        "pre_end",
        "dispatch",
        "executor_return",
        "controller_return",
        "hold_begin",
        "hold_end",
        "terminal_capture_begin",
        "terminal_capture_end",
        "post_context",
        "post_evaluated",
        "action_exit",
    )
    instants = (10, 15, 20, 1500, 1501, 1502, 4000, 4010, 4020, 4030, 4040, 4050)
    steps = (120, 120, 120, 860, 860, 860, 2040, 2040, 2040, 2040, 2040, None)
    timing = dict(
        schema_version="native.whole-action.timing.v1",
        clock="monotonic_ns",
        thread_id=1,
        marks=[
            dict(label=label, ns=instant, physics_step=step)
            for label, instant, step in zip(labels, instants, steps, strict=True)
        ],
        spans=[
            dict(
                seq=i,
                parent=None,
                label="mj_step",
                start_ns=2 * i + 19,
                end_ns=2 * i + 20,
                operation_id=i,
                acquisition_id=None,
            )
            for i in range(1, 1921)
        ],
    )
    raw = dict(
        horizons=[
            dict(
                skill="MOVE_ABOVE",
                dispatch_step=120,
                controller_return_step=860,
                terminal_step=2040,
                complete=True,
                terminal_acquisition_id="terminal",
            )
        ],
        physics=[
            dict(physics_step=120 + i, physics_interval_id=f"operation-{i}") for i in range(1, 1921)
        ],
        operational_events=[
            dict(acquisition_id="terminal", begin_step=2040, end_step=2040, operation_id=1921)
        ],
    )
    pre = {"step_started_at": 10e-9}
    post = {"step_started_at": 10e-9, "monotonic_now": 4030e-9}
    report = reader["read_timing"](timing, raw, pre, post)
    assert report["action"]["exclusive_ns"] == {"mj_step": 1920, "other": 2100}
    assert report["post_elapsed_ms"] == pytest.approx(0.00402)

    timing["spans"][-1]["operation_id"] = 1921
    with pytest.raises(ValueError, match="every original native physics step"):
        reader["read_timing"](timing, raw, pre, post)
