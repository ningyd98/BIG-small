"""Independent readback boundaries for the fixed-wrist, two-end-board development trial."""

import copy
import importlib.util
import math

import pytest
from scripts.graduation import g1_visibility_trials


def scorer():
    name = "scripts.graduation.g1_clearance_score"
    assert importlib.util.find_spec(name) is not None, "missing independent development scorer"
    return __import__(name, fromlist=["feedback_timing"])


def test_contacts_include_every_registered_structure_and_the_palm(tmp_path):
    xml = tmp_path / "scene.xml"
    xml.write_text(
        '<mujoco><worldbody><geom name="floor"/><body name="object">'
        '<geom name="object_geom"/><geom name="new_beam"/>'
        '<geom name="printed_quad" contype="0" conaffinity="0"/>'
        '<body name="fixed_end"><geom name="new_plate" contype="0" conaffinity="1"/></body>'
        "</body></worldbody></mujoco>"
    )
    samples = [
        {"physics_step": 10, "contact_pairs": [["new_beam", "hand"], ["hand", "new_beam"]]},
        {
            "physics_step": 11,
            "contact_pairs": [
                ["left_finger_geom", "object_geom"],
                ["object_geom", "right_finger_geom"],
            ],
        },
        {
            "physics_step": 12,
            "contact_pairs": [["right_finger_geom", "new_plate"], ["printed_quad", "hand"]],
        },
    ]
    found = scorer().registered_hand_contacts(xml, samples)
    assert found["board_or_support_hand_or_finger_steps"] == [10, 12]
    assert found["block_both_fingers_steps"] == [11]
    assert found["hand_contact_pairs"]["hand/new_beam"] == 1
    assert found["support_geoms"] == ["new_beam", "new_plate"]


STAGES = (
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
)


def completed_samples():
    actions, roles, audit = [], [], []
    for i, name in enumerate(STAGES):
        action = {"skill": name, "status": "PASS", "executor_entered": True}
        actions.append(action)
        if name in {"GRASP", "RELEASE"}:
            continue
        frame_id = f"frame-{i}"
        step = 10 * (i + 1)
        stamp = step / 240
        action["feedback_accepted"] = 1
        roles.append(
            {
                "label": name + "/feedback",
                "physics_step": step,
                "sim_time_s": stamp,
                "frame_id": frame_id,
                "checksum_sha256": str(i) * 64,
            }
        )
        audit.append(
            {
                "phase": "servo",
                "skill": name,
                "visual_samples": [
                    {
                        "observation_id": frame_id,
                        "checksum_sha256": str(i) * 64,
                        "sim_time_s": stamp,
                    }
                ],
                "control_samples": [
                    {"physics_step": step, "sim_time_s": stamp, "sample_and_ik_s": 0.1}
                ],
            }
        )
    return {"actions": actions, "frame_roles": roles}, audit


def test_feedback_pairs_each_current_packet_with_its_native_post_ik_measurement():
    run, audit = completed_samples()
    timing = scorer().feedback_timing(run, audit)
    assert timing["complete"]
    assert timing["captured"] == timing["measured"] == 6
    assert timing["max_sample_and_ik_ms"] == 100.0
    assert timing["over_100ms"] == []
    assert timing["by_stage"]["RELEASE"]["captured"] == 0
    assert timing["by_stage"]["RETREAT"]["captured"] == 1


@pytest.mark.parametrize("mistake", ["missing_ik", "crossed", "overrun", "no_samples", "nan"])
def test_each_missing_or_late_feedback_fails_the_complete_gate(mistake):
    run, audit = completed_samples()
    if mistake == "missing_ik":
        audit[-1]["control_samples"] = []
    if mistake == "crossed":
        audit[-1]["control_samples"][0]["physics_step"] -= 1
    if mistake == "overrun":
        audit[-1]["control_samples"][0]["sample_and_ik_s"] = 0.100001
    if mistake == "no_samples":
        audit, run["frame_roles"] = [], []
    if mistake == "nan":
        audit[-1]["control_samples"][0]["sample_and_ik_s"] = math.nan
    facts = scorer().feedback_timing(run, audit)
    assert not facts["complete"]
    if mistake == "overrun":
        assert facts["over_100ms"][0]["frame_id"] == "frame-7"
    elif mistake == "missing_ik":
        assert facts["by_stage"]["RETREAT"]["unmatched_frame_ids"] == ["frame-7"]


def test_no_dispatch_or_missing_original_release_window_cannot_be_promoted():
    good = {
        "evidence_status": "SCORED",
        "dispatched": 8,
        "verified_posts": 8,
        "online_success": True,
        "physical_success": True,
        "joint_success": True,
        "both_windows_qualified": True,
        "registered_windows": {"lift": {"qualified": True}, "release": {"qualified": True}},
        "independent_physical_outcome": {
            "success": True,
            "safety_assessment": "SCOPED_NO_VIOLATION",
            "measured_lift_m": 0.05,
            "hold_s": 0.5,
            "placed_stable_s": 1,
        },
        "contacts": {"bilateral_cube_steps": 1},
        "hand_contacts": {"board_or_support_hand_or_finger_steps": []},
    }
    assert g1_visibility_trials.training_success(good)
    assert scorer().qualified(good, True)
    assert not scorer().qualified(good, False)
    for key, value in [
        ("dispatched", 0),
        ("verified_posts", 7),
        ("registered_windows", {"lift": {"qualified": True}, "release": {"qualified": False}}),
        ("hand_contacts", {"board_or_support_hand_or_finger_steps": [1221]}),
    ]:
        result = copy.deepcopy(good)
        result[key] = value
        assert not scorer().qualified(result, True)


def test_runtime_source_catalog_requires_pinned_private_bytes(tmp_path):
    import hashlib
    import json

    runtime = tmp_path / "runtime-source"
    runtime.mkdir()
    module = runtime / "independent_reader.py"
    module.write_bytes(b"registered reader")
    file_digest = hashlib.sha256(module.read_bytes()).hexdigest()
    lock = runtime / "runtime-build.json"
    lock.write_text(json.dumps({"runtime_files_sha256": {module.name: file_digest}}))
    generation = hashlib.sha256(lock.read_bytes()).hexdigest()
    assert (
        scorer().verify_generation(runtime, generation)["runtime_files_sha256"][module.name]
        == file_digest
    )
    module.write_bytes(b"stale checkout reader")
    with pytest.raises(ValueError, match="independent_reader.py"):
        scorer().verify_generation(runtime, generation)


def test_native_targets_are_rebuilt_using_registered_center_and_region():
    check = scorer().check_issued_endpoint
    inputs = {
        "object_center_world_m": [0.45, 0, 0.035],
        "grasp_tcp_world_m": [0.45, 0, 0.045],
        "destination_world_m": [0.55, 0.11, 0.0004],
        "nominal_support_height_m": 0.0,
    }
    marker = {
        "usable": True,
        "selected_id": 7,
        "tcp_m": [0.45, 0, 0.045],
        "per_id": {"7": {"center_m": [0.45, 0, 0.035]}},
    }
    issue = {
        "grounded_step": {
            "skill": "PLACE",
            "parameters": {"target_pose": {"x": 0.55, "y": 0.11, "z": 0.0454}},
        },
        "inputs": inputs,
        "policy": {"minimum_height_m": 0.16, "clearance_m": 0.1},
        "online": {"robot_state": {"tcp_pose": {"x": 0.45, "y": 0, "z": 0.125}}},
    }
    check(issue, marker, [0.55, 0.11, 0.0004])
    wrong = copy.deepcopy(issue)
    wrong["grounded_step"]["parameters"]["target_pose"]["x"] = 0.45
    with pytest.raises(ValueError):
        check(wrong, marker, [0.55, 0.11, 0.0004])
    with pytest.raises(ValueError):
        check(issue, marker, [0.45, 0, 0.045])


def test_local_gate_requires_every_actual_feedback_frame_and_refuses_crossed_identity():
    run, audit = completed_samples()
    frames = {r["frame_id"]: r for r in run["frame_roles"]}
    rows = [
        {
            "phase": "FEEDBACK",
            "skill": r["label"].split("/")[0],
            "frame_id": r["frame_id"],
            "checksum_sha256": r["checksum_sha256"],
            "physics_step": r["physics_step"],
            "status": "CLEAR",
            "reason": None,
            "gate_ms": 3.6,
        }
        for r in run["frame_roles"]
    ]
    complete = scorer().local_gate_readback(rows, frames, run)["all_captured_feedback_clear"]
    assert complete
    assert not scorer().local_gate_readback(rows[:-1], frames, run)["all_captured_feedback_clear"]
    rows[-1]["status"] = "UNKNOWN"
    facts = scorer().local_gate_readback(rows, frames, run)
    assert not facts["all_captured_feedback_clear"]
    assert facts["refusals"][0]["frame_id"] == "frame-7"
    rows[-1]["checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frame"):
        scorer().local_gate_readback(rows, frames, run)


def test_cli_refuses_unfrozen_batch_before_creating_any_score(tmp_path):
    import json
    import subprocess
    import sys

    batch = tmp_path / "batches" / "attempt-01"
    batch.mkdir(parents=True)
    (batch / "allocation.json").write_text(
        json.dumps(
            {
                "plan_sha256": "0" * 64,
                "runtime_build_sha256": "0" * 64,
                "cases": [{"id": "cvfix-t01"}],
            }
        )
    )
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.graduation.g1_clearance_score", str(batch), "cvfix-t01"],
        text=True,
        capture_output=True,
    )
    assert proc.returncode != 0
    assert "plan" in proc.stderr.lower()
    assert not list(batch.rglob("independent-score.json"))
