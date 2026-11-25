"""Read raw independent owner, camera operation, physical and registered pixel evidence."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from recovery_native import GEN, PLAN, RAW, WORK, bind_scene

# isort: split
# recovery_native pins the frozen worker before these imports.
from scripts.graduation.g1_dual_observer import measure_frame
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def check_one(label):
    root = RAW / label
    allocation = read(root / "allocation.json")
    assert allocation["plan_sha256"] == PLAN and allocation["runtime_build_sha256"] == GEN
    controls = read(root / "controls.json")
    events = read(root / "observations.json")
    operations = read(root / "operation-boundaries.json")
    raws = read(root / "native-pixels.json")
    verified = []
    packets = {}
    for e in events:
        packet = RGBDObservation.model_validate_json(
            (root / f"frame-{e['number']:03}.json").read_bytes()
        )
        assert packet.frame_id == e["frame_id"] and packet.checksum_sha256 == e["checksum_sha256"]
        assert (
            packet.captured_at.isoformat() == e["captured_at"]
            and packet.sim_time_s == e["sim_time_s"]
        )
        packets[packet.frame_id] = packet
    assert len(packets) == len(events)
    with bind_scene(allocation["case"]["scene_id"]):
        for ident, online in raws.items():
            result = measure_frame(packets[ident], allocation["geometry"])
            assert (
                json.loads(json.dumps(result, allow_nan=False)) == online["measurement"]
                and online["callers"].get("servo_measure") is not None
            )
            verified.append(ident)
    with closing(
        sqlite3.connect(
            (root / "development-worker.db").resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        )
    ) as db:
        db.row_factory = sqlite3.Row
        (job,) = db.execute("select * from simulation_jobs")
        (lease,) = db.execute("select * from simulation_job_leases")
        (attempt,) = db.execute("select * from simulation_job_attempts")
        assert (
            job["job_id"] == attempt["job_id"] == lease["job_id"]
            and attempt["attempt"] == 1
            and lease["released_at"]
        )
    phy = read(root / "telemetry.json")
    assert [x["step"] for x in phy] == list(range(len(phy)))
    commands = read(root / "commands.json")
    assert all(
        x["type"] in {"hold_current_joints", "camera_position", "emergency_stop"} for x in commands
    )
    result = []
    for row in controls:
        if "initial_native_acquisition" not in row:
            assert row["commands_after"] == []
            result.append(dict(case=row["case"], reason=row["refusal"], subsequent_commands=0))
            continue
        selected_ops = [
            e["frame_id"]
            for e in operations[row["operations_before"] :]
            if e["monotonic"] < row["finished_monotonic"]
            and e["kind"] == "CAPTURE"
            and e["phase"] == "END"
        ]
        assert selected_ops == row["native_captures"] and len(selected_ops) == row["acquisitions"]
        assert (
            row["owner"]["lease_id"] == lease["lease_id"]
            and row["owner"]["job_id"] == job["job_id"]
            and row["owner"]["attempt"] == 1
        )
        measured = row["native_measurements"]
        assert all(m["frame_id"] in verified for m in measured)
        upper = row.get("sweep_timing")
        screen = row.get("sweep")
        if screen:
            assert (
                screen["frame_id"] == measured[-1]["frame_id"]
                and screen["checksum_sha256"] == packets[screen["frame_id"]].checksum_sha256
            )
            assert screen["source_sha256"] == {
                k: v
                for k, v in read(root / "screen-sources.json").items()
                if k != "surface_pilot.py"
            }
        stop = row.get("stationarity")
        idx = selected_ops.index(row["initial_native_acquisition"])
        item = dict(
            case=row["case"],
            status=row["status"],
            refusal=row["refusal"],
            registered_target_probes=[m["reason"] for m in measured],
            measured_ids=[m["observed_ids"] for m in measured],
            dual_disagreement_mm=[
                1000 * m["disagreement_m"] if m["disagreement_m"] is not None else None
                for m in measured
            ],
            initial_frame_id=row["initial_native_acquisition"],
            native_camera_events_after_initial=len(selected_ops[idx + 1 :]),
            new_frame_id=measured[-1]["frame_id"] if len(measured) > 1 else None,
            recapture_attempts=row["recaptures_attempted"],
            command_types=[c["type"] for c in row["commands"]],
            physics_before=row["physics_origin"],
            physics_after=row["physics_end"],
            actual_skill_dispatches=row["actual_skill_dispatches"],
            elapsed_ms=1000 * row["elapsed_wall_s"],
            ms_from_first_source=row["acquisition_full_window_ms"],
            original_action_limit_ms=row["original_action_timeout_ms"],
            original_action_remaining_ms=1000 * row["remaining_original_action_s"],
            second_recovery_request_refusal=row["second_request_refusal"],
        )
        if stop:
            item["stationarity"] = {k: v for k, v in stop.items() if k != "readings"}
            for sample in stop["readings"]:
                original = phy[sample["step"]]
                assert (
                    original["joint_velocities"] == sample["joint_velocities"]
                    and original["tcp"] == sample["tcp"]
                )
        if screen:
            item["screen"] = dict(
                status=screen["status"],
                reason=screen["reason"],
                selected=screen["selected"],
                candidates=len(screen["candidates"]),
                counts=screen["counts"],
                robot=screen.get("measured_robot", {}).get("status"),
                source_sha256=screen["source_sha256"],
                capture_to_sweep_wall=upper,
            )
        result.append(item)
    reported = []
    for r in read(root / "shield-ik.json"):
        assert all(c["status"] == "PASS" for c in r["conditions"]["conditions"])
        assert (
            r["conditions"]["shield"]["allowed"]
            and r["conditions"]["shield"]["unmodified"]
            and all(isinstance(q, float) for q in r["native_ik_joint_positions_rad"])
        )
        reported.append(
            {
                k: r[k]
                for k in (
                    "frame_id",
                    "checksum_sha256",
                    "native_binding",
                    "issued_sequence",
                    "ik_ms",
                    "fresh_capture_to_ik_ms",
                    "capture_to_final_pre_recheck_ms",
                    "original_task_deadline",
                )
            }
        )
    return dict(
        label=label,
        rows=result,
        native_pre_and_ik_reads=reported,
        saved_explicit_acquisitions=len(packets),
        independently_verified_vision_frames=len(verified),
        physics_steps=phy[-1]["step"],
        recoverable_raw=sorted(verified),
        sqlite_owner=dict(
            job_id=job["job_id"],
            lease_id=lease["lease_id"],
            attempt=attempt["attempt"],
            status=job["status"],
        ),
        input_artifacts_sha256={
            str(p.relative_to(WORK)): sha(p)
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(".lock")
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    p.add_argument("--full", default="qualifications4")
    a = p.parse_args()
    samples = [check_one("qualifications3"), check_one(a.full)]
    legacy = read(RAW / "qualifications2/controls.json")
    bad = read(RAW / "qualifications1/exception.json")
    hard = read(RAW / "historical-hard-state.json")
    prior = {rawcase["case"]: rawcase for rawcase in legacy}
    assert "distinct same-step original registration captures required" in bad["traceback"]
    assert prior["normal"]["refusal"]["reason"].endswith("capture_not_new_and_monotonic")
    core = {r["case"]: r for r in samples[0]["rows"]}
    assert core["normal"]["status"] == core["missing_then_visible"]["status"] == "ADMITTED"
    assert (
        core["normal"]["native_camera_events_after_initial"] == 0
        and core["missing_then_visible"]["native_camera_events_after_initial"] == 1
    )
    assert (
        core["foreign"]["measured_ids"] == [[7, 9]]
        and core["conflict"]["dual_disagreement_mm"][0] > 10
        and core["conflict"]["measured_ids"] == [[7, 8]]
    )
    assert (
        core["released_sqlite_lease"]["reason"] == "COMPONENT_LEASE_SOURCE_INVALID"
        and core["latched_estop"]["reason"] == "ROBOT_HARD_SAFETY_STOP"
    )
    full = {r["case"]: r for r in samples[1]["rows"]}
    assert full["fresh_repeated_native"]["refusal"]["reason"] == "servo repeated frame"
    for name, n in (("full_normal", 0), ("full_recovery", 1)):
        r = full[name]
        assert (
            r["native_camera_events_after_initial"] == n
            and "screen" in r
            and r["actual_skill_dispatches"] == 0
        )
    assert (
        hard["rows"][-1]["hard_state_refusal"] == "ROBOT_HARD_SAFETY_STOP"
        and hard["original_run_stop"]["physics_step"] == 1228
        and hard["moving_refusal"] == "arm joints or TCP not settled"
    )
    write(
        a.output,
        dict(
            schema="g1.cv.stationary-recovery.readback.v1",
            plan_sha256=PLAN,
            generation=GEN,
            real_skill_dispatches=0,
            actual_completed_motion_recoveries=0,
            new_formal_trials=0,
            qualified_stop_and_reobservation_component_controls=1,
            physical_sweep_gate_observed=samples[1]["rows"][:2],
            qualifications=samples,
            historical_hard_stop=hard,
            baseline_refusals={
                "registration_at_zero": (
                    "distinct same-step original registration captures required"
                ),
                "fresh_new_identity_at_same_sim_tick": prior["normal"]["refusal"]["reason"],
                "repeated_failed_acquisition": prior["replayed_failed_frame"]["refusal"]["reason"],
            },
            preserved_earlier_evidence={
                str(p.relative_to(WORK)): sha(p)
                for p in [
                    RAW / "historical-hard-state.json",
                    RAW / "qualifications2/controls.json",
                    RAW / "qualifications1/exception.json",
                ]
            },
        ),
    )


if __name__ == "__main__":
    main()
