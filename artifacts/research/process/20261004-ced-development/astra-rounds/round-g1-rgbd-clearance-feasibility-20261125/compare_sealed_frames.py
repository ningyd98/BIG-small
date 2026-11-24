"""Join sealed camera evidence to independently reconstructed clearances at the same step."""

import argparse
import gzip
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
from estimate_depth import BATCHES, PLAN_SHA, PRIVATE, ROUND, registered_boxes
from scripts.graduation.perception_io import pinned, read, sha, write

ESTIMATE_SHA = "c92cdc4b8df2f8cc3512e462e7cf91e976e06e22c915d12d6d1b1b6fa4639169"
HISTORY = ROUND.parent / "round-g1-dual-support-contact-diagnosis-20261125"
NATIVE_SOURCES = (
    "scripts/graduation/dynamic_vision.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
)


def gap_mm(pair):
    closed = pair["contact_count"] > 0
    return pair["largest_signed_gap_mm"] if closed else pair["nearest_disjoint"]["distance_mm"]


def field_names(record):
    if isinstance(record, dict):
        for key, value in record.items():
            yield key
            yield from field_names(value)
    elif isinstance(record, list):
        for value in record:
            yield from field_names(value)


def inspect_native(raw, generation):
    modules = read(raw / "imports.json")["project_after"]
    files = {item["file"]: item["sha256"] for item in modules.values()}
    tree = PRIVATE.parent / "builds" / generation / "runtime-source"
    sources = {name: sha(tree / name) for name in NATIVE_SOURCES}
    assert all(files[name] == digest for name, digest in sources.items())
    assert (
        "return MotionTarget(measured, previous.orientation_wxyz)"
        in (tree / NATIVE_SOURCES[0]).read_text()
    )
    assert (
        "visual servo orientation changes are unsupported" in (tree / NATIVE_SOURCES[1]).read_text()
    )
    assert "float(value) for value in self._data.qpos[:7]" in (tree / NATIVE_SOURCES[3]).read_text()
    rows = read(raw / "online-audit.json")
    approach = next(r for r in rows if r.get("phase") == "servo" and r.get("skill") == "APPROACH")
    commands = read(raw / "backend-commands.json")
    target_sources = {sample["target_source"] for sample in approach["visual_samples"]}
    assert target_sources == {"CURRENT_REGISTERED_MARKER_DEVELOPMENT_ESTIMATE"}
    assert all(
        sample["ground_truth_used_for_control"] is False for sample in approach["visual_samples"]
    )
    metrics = raw / "development-worker.db"
    with sqlite3.connect(metrics.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        metric_count = db.execute("select count(*) from simulation_metrics").fetchone()[0]
    assert metric_count == 0
    feedback = {r["frame_id"]: r for r in rows if r.get("phase") == "FEEDBACK"}
    sensor_fields = set(field_names(approach)) | set(field_names(list(feedback.values())))
    absent = {"joint_positions_rad", "finger_positions_m", "qpos", "jaw_width_m", "gripper_width_m"}
    assert absent.isdisjoint(sensor_fields)
    return feedback, dict(
        sources=sources,
        approach_target_source=sorted(target_sources),
        control_sample_fields=sorted(approach["control_samples"][-1]),
        online_feedback_fields=sorted(next(iter(feedback.values()))),
        absent_encoder_fields=sorted(absent),
        backend_joint_targets_present=any("target_positions_rad" in item for item in commands),
        worker_metric_count=metric_count,
        worker_db_sha256=sha(metrics),
        aligned_full_measured_arm_and_jaw_in_feedback=False,
    )


def compare():
    estimates = pinned(ROUND / "estimates.public.json", ESTIMATE_SHA)
    plan = pinned(ROUND / "plan.json", PLAN_SHA)
    archive = HISTORY / "local-contact-geometry.public.json.gz"
    identifier = archive.relative_to(Path.cwd()).as_posix()
    assert sha(archive) == plan["inputs_sha256"][identifier]
    historical = json.loads(gzip.decompress(archive.read_bytes()))["trajectories"]
    result = {}
    for key, offset, culprit in (
        ("115mm", "15", "g1_dual_id8_plate"),
        ("130mm", "30", "g1_dual_id7_crossbar"),
    ):
        raw = PRIVATE / BATCHES[key] / "d02" / "instance"
        case = pinned(
            raw.parent / "allocation.json",
            plan["inputs_sha256"][(raw.parent / "allocation.json").as_posix()],
        )
        boxes = registered_boxes(case)
        current = pinned(
            raw / "online-vision.json",
            plan["inputs_sha256"][(raw / "online-vision.json").as_posix()],
        )["frames"]
        native = historical["trajectory-" + offset]
        states = {row["step"]: row for row in native["poses"][offset]["states"]}
        frames = {row["step"]: row for row in native["frames"]}
        sensed, source = inspect_native(raw, case["runtime_build_sha256"])
        stop = native["native_stop"]["physics_step"]
        linked = []
        for entry in estimates["cases"][key]["frames"]:
            step = entry["step"]
            match = frames[step]
            assert entry["file_sha256"] == match["file_sha256"]
            state = states[step]
            support = entry["model"]
            evidence = dict(
                step=step,
                role=entry["role"],
                rgbd_sha256=entry["file_sha256"],
                simulation_ms_until_first_contact=(stop - step) * 1000 / 240,
                external_left_beam_gap_mm=gap_mm(state["pairs"]["left_beam"]),
                external_right_plate_gap_mm=gap_mm(state["pairs"]["right_plate"]),
                whole_frame_valid_points=entry["direct"]["valid_points"],
            )
            if support is not None:
                tag = current[match["frame_id"]]["measurement"]
                assert match["frame_id"] in sensed and tag["usable_ids"] == support["usable_ids"]
                part = support["objects"][culprit]["first_registered_surface"]
                estimated_rotation = np.reshape(tag["rotation_object_to_world"], (3, 3))
                actual_rotation = np.asarray(state["object_pose"]["r"])
                center = np.mean(boxes[culprit], axis=0)
                estimated_world = (
                    np.asarray(tag["object_center_world_m"]) + estimated_rotation @ center
                )
                actual_world = np.asarray(state["object_pose"]["c"]) + actual_rotation @ center
                difference = actual_rotation.T @ estimated_rotation
                evidence.update(
                    projected_fixture_pixels=part["pixels"],
                    nearer_by_5mm=part["tolerance_mm"]["5"]["nearer"],
                    nearer_by_20mm=part["tolerance_mm"]["20"]["nearer"],
                    invalid_depth=part["invalid"],
                    non_edge_fixture_pixels=support["objects"][culprit]["interior"]["pixels"],
                    offline_check_part_center_error_mm=1000
                    * float(np.linalg.norm(estimated_world - actual_world)),
                    offline_check_object_rotation_error_deg=math.degrees(
                        math.acos(np.clip((difference.trace() - 1) / 2, -1, 1))
                    ),
                )
            linked.append(evidence)
        result[key] = dict(
            registered_component=culprit, native_interface=source, contact_step=stop, frames=linked
        )
    return dict(
        schema="g1.rgbd.sealed-depth-comparison.v1",
        estimate_sha256=ESTIMATE_SHA,
        plan_sha256=PLAN_SHA,
        ground_truth_geometry_sha256=sha(archive),
        cases=result,
        elapsed_clock="simulation_time",
        predictive_alarm_tested=False,
        predictive_stop_or_avoidance_trials=0,
        new_physics_steps=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    write(args.output, compare())
    print(sha(args.output))
