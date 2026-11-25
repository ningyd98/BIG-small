"""Recompute every corrected candidate and check the original native clock and capture traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from recovery_readback import check_one
from recovery_route_v2 import (
    PLAN,
    ROUND,
    RUN,
    SUPPLEMENT_SHA,
    V1_SHA,
    WORK,
    elapsed_windows,
    load_screen,
)
from scripts.graduation.perception_io import pinned, read, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def inspect():
    prior = pinned(ROUND / "recovery-readback-v1.public.json", V1_SHA)
    native = check_one(RUN.name)
    screen, inventory = load_screen(RUN, create=False)
    assert inventory == read(RUN / "dependency-sha256.json")
    sources = read(RUN / "observations.json")
    inputs = {s["frame_id"]: (s["number"], s["started"], s["finished"]) for s in sources}
    operation = read(RUN / "operation-boundaries.json")
    capture_ends = [e for e in operation if e["kind"] == "CAPTURE" and e["phase"] == "END"]
    states = read(RUN / "robot-measurements.json")
    setup = read(RUN / "allocation.json")
    frozen_xml = Path(next(k for k in inventory if "/runtime-source/" in k)).parts
    frozen_root = WORK / Path(*frozen_xml[: frozen_xml.index("runtime-source") + 1])
    raw_rows = read(RUN / "controls.json")
    assert [r["case"] for r in raw_rows] == ["full_normal", "full_recovery"]
    assert len(native["rows"]) == 2 and not native["native_pre_and_ik_reads"]
    outcomes = []
    for r, out in zip(raw_rows, native["rows"], strict=True):
        s = r["sweep"]
        event = s["frame_id"]
        number, start, finish = inputs[event]
        frame = RGBDObservation.model_validate_json((RUN / f"frame-{number:03}.json").read_bytes())
        new = screen(
            frame,
            setup["geometry"],
            frozen_root / setup["geometry"]["asset_path"],
            robot_measurement=states[event],
        )
        assert canonical(new) == canonical(s)
        positions = [x["source_step"] for x in prior["historical_hard_stop"]["rows"][-2:]]
        assert positions == [1227, 1228]
        stamps = r["monotonic_ns"]
        assert r["windows_ms"] == elapsed_windows(stamps)
        assert stamps["selected_start"] / 1e9 <= start < finish <= stamps["screen_start"] / 1e9
        assert inputs[r["initial_native_acquisition"]][1] >= stamps["first_start"] / 1e9
        assert r["finished_monotonic"] == stamps["decision_end"] / 1e9
        passing = [
            c
            for c in capture_ends
            if stamps["first_start"] / 1e9 <= c["monotonic"] <= r["finished_monotonic"]
        ]
        expected = ["full_normal", "full_recovery"].index(r["case"]) + 1
        assert len(passing) == expected and passing[-1]["frame_id"] == event
        assert [c["frame_id"] for c in passing] == r["native_captures"][-expected:]
        assert r["physics_end"] - r["physics_origin"] == (16 if expected == 2 else 0)
        assert out["command_types"] == (["hold_current_joints"] if expected == 2 else [])
        assert r["sweep"]["selected"] is None and r["actual_skill_dispatches"] == 0
        assert out["refusal"]["reason"] == "current sweep has no executable CLEAR"
        assert r["original_action_timeout_ms"] == 8000
        assert math.isclose(
            r["windows_ms"]["action_wall_ms"] + r["remaining_original_action_s"] * 1000,
            r["original_action_timeout_ms"],
            rel_tol=0,
            abs_tol=1e-5,
        )
        if expected == 2:
            assert out["stationarity"]["sample_steps"] == [128, 136, 144]
            assert out["stationarity"]["max_arm_velocity_rad_s"] <= 0.02
            assert out["measured_ids"] == [[], [7, 8]]
        else:
            assert out["measured_ids"] == [[7, 8]]
        out.update(
            full_clock_ns=stamps,
            elapsed_windows_ms=r["windows_ms"],
            offline_full_table_recomputed_sha256=hashlib.sha256(canonical(s)).hexdigest(),
            full_reasons_counts=dict(
                Counter(
                    reason for candidate in s["candidates"] for reason in candidate["full_reasons"]
                )
            ),
            nominal_counts=s["nominal_counts"],
            capture_ids_in_window=[c["frame_id"] for c in passing],
            direct_high_routes={
                k: {
                    "status": v["status"],
                    "segments": v["segments"],
                    "max_vertex_motion_mm": v["max_vertex_motion_mm"],
                }
                for k, v in s["initial_routes"].items()
            },
            confirmed_remaining_ms=r["remaining_original_action_s"] * 1000,
            active_sample_limit_exceeded_before_decision=r["windows_ms"][
                "selected_capture_to_decision_ms"
            ]
            > 100,
        )
        outcomes.append(out)
    return dict(
        schema="g1.cv.stationary-recovery.corrected-route-readback.v2",
        parent_plan_sha256=PLAN,
        geometry_plan_sha256=SUPPLEMENT_SHA,
        execution_authority="parent development qualification",
        prior_release_sha256=V1_SHA,
        prior_negative_controls_reused=True,
        environment=read(RUN / "run-context.json"),
        qualified_settings=setup["qualification_pose"],
        scene=setup["case"]["scene_id"],
        sqlite_owner=native["sqlite_owner"],
        input_artifacts_sha256=native["input_artifacts_sha256"],
        loaded_dependency_sha256=inventory,
        rows=outcomes,
        native_explicit_acquisitions=native["saved_explicit_acquisitions"],
        independently_verified_servo_measurements=native["independently_verified_vision_frames"],
        physics_steps=native["physics_steps"],
        actual_completed_motion_recoveries=0,
        real_skill_dispatches=0,
        new_formal_trials=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, inspect())
