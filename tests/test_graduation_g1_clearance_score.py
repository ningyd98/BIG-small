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


def release_readback_fixture():
    roles, samples, frames, physics = [], [], {}, {}
    native = [
        dict(skill="GRASP", controller_return_step=340, controller_result={"success": True}),
        dict(skill="LIFT", controller_return_step=360, controller_result={"success": True}),
        dict(
            skill="MOVE_TO_REGION", controller_return_step=490, controller_result={"success": True}
        ),
        dict(skill="PLACE", controller_return_step=500, controller_result={"success": True}),
        dict(skill="RELEASE", controller_return_step=740, controller_result={"success": True}),
    ]
    receipts = [
        dict(
            skill="GRASP",
            command_seq_half_open=[2, 3],
            backend_return_step=340,
            receipt_success=True,
        ),
        dict(
            skill="LIFT",
            command_seq_half_open=[3, 4],
            backend_return_step=360,
            receipt_success=True,
        ),
        dict(
            skill="MOVE_TO_REGION",
            command_seq_half_open=[4, 7],
            backend_return_step=490,
            receipt_success=True,
        ),
        dict(
            skill="PLACE",
            command_seq_half_open=[4, 10],
            backend_return_step=500,
            receipt_success=True,
        ),
        dict(
            skill="RELEASE",
            command_seq_half_open=[10, 11],
            backend_return_step=740,
            receipt_success=True,
        ),
    ]
    commands = [
        dict(command_seq=2, type="gripper", accepted=True, target_open=False, physics_step=100),
        dict(command_seq=9, type="joint_target", accepted=True, physics_step=492),
        dict(command_seq=10, type="gripper", accepted=True, target_open=True, physics_step=500),
    ]
    times = [
        ("GRASP/POST", 340),
        *((f"LIFT/dwell-{i}", 360 + i) for i in range(0, 121, 8)),
        ("LIFT/POST", 480),
        ("MOVE_TO_REGION/POST", 490),
        ("PLACE/POST", 500),
        *((f"RELEASE/dwell-{i}", 740 + i) for i in range(0, 241, 8)),
        ("RELEASE/POST", 980),
    ]
    for label, step in times:
        skill = label.split("/")[0]
        releasing = skill == "RELEASE"
        base = dict(
            frame_id=str(step),
            checksum_sha256=f"{step:064x}",
            physics_step=step,
            sim_time_s=step / 240,
        )
        role = dict(
            base, label=label, acquired_for_this_role=label not in {"LIFT/POST", "RELEASE/POST"}
        )
        roles.append(role)
        frames[str(step)] = dict(base)
        state = dict(
            joint_positions_rad=[0.3] * 7,
            joint_velocities_rad_s=[0.0] * 7,
            finger_positions_m=[0.03] * 2,
            finger_velocities_m_s=[0.0] * 2,
            tcp_position_m=[0.45, 0.01, 0.04],
        )
        physics[step] = dict(state, physics_step=step, sim_time_s=step / 240)
        robot = dict(
            base,
            **state,
            native_last_command_seq={
                "GRASP": 2,
                "LIFT": 3,
                "MOVE_TO_REGION": 6,
                "PLACE": 9,
                "RELEASE": 10,
            }[skill],
            previous_native_successful_skill=skill,
            previous_native_return_step={
                "GRASP": 340,
                "LIFT": 360,
                "MOVE_TO_REGION": 490,
                "PLACE": 500,
                "RELEASE": 740,
            }[skill],
            previous_native_terminal_step=None,
            last_accepted_gripper_open=releasing,
            last_accepted_gripper_command_step=500 if releasing else 100,
        )
        samples.append(
            dict(
                base,
                label=label,
                robot=robot,
                elapsed_ms=20.0,
                evidence=dict(relation="supported_and_separated" if releasing else "held"),
            )
        )
    return samples, roles, frames, physics, native, commands, receipts


def test_passive_rgbd_dwell_joins_original_frame_physics_and_command_boundaries():
    samples, roles, frames, physics, native, commands, receipts = release_readback_fixture()
    check = scorer().passive_payload_readback
    result = check(samples, roles, frames, physics, native, commands, receipts)
    assert result["complete"]
    assert result["lift_distinct_exposures"] == 16
    assert result["release_distinct_exposures"] == 31
    assert result["release_elapsed_physics_steps"] == 240
    assert not check([], [], {}, {}, [], [], [])["complete"]


def test_payload_history_replays_actual_roles_including_two_uses_of_one_capture():
    roles = [
        dict(label=k, frame_id=f)
        for k, f in [
            ("GRASP/PRE", "a"),
            ("GRASP/POST", "b"),
            ("LIFT/PRE", "b"),
            ("LIFT/feedback", "c"),
        ]
    ]
    rows = [
        dict(
            skill=s,
            phase=p,
            frame_id=f,
            status="CLEAR",
            evidence={"payload_observation": {"relation": r}},
        )
        for s, p, f, r in [
            ("GRASP", "PRE", "a", "unknown"),
            ("LIFT", "PRE", "b", "held"),
            ("LIFT", "FEEDBACK", "c", "held"),
        ]
    ]
    passive = [dict(label="GRASP/POST", frame_id="b", evidence={"relation": "held"})]
    ordered = scorer().payload_replay_events(rows, passive, roles)
    assert [(s, p, v["frame_id"]) for s, p, v, e in ordered] == [
        ("GRASP", "PRE", "a"),
        ("GRASP", "POST", "b"),
        ("LIFT", "PRE", "b"),
        ("LIFT", "FEEDBACK", "c"),
    ]
    with pytest.raises(ValueError, match="role"):
        scorer().payload_replay_events(rows, passive, roles[:-1])
    with pytest.raises(ValueError, match="missing"):
        scorer().payload_replay_events([rows[-1] | {"evidence": {}}], [], roles)


@pytest.mark.parametrize(
    "damage",
    [
        "skipped",
        "duplicate",
        "missing_role",
        "checksum",
        "encoder",
        "same_step_command",
        "missing_support",
        "retained_as_fresh",
    ],
)
def test_passive_rgbd_dwell_detects_missing_substituted_and_stale_sources(damage):
    samples, roles, frames, physics, native, commands, receipts = release_readback_fixture()
    if damage == "skipped":
        del samples[3]
    elif damage == "duplicate":
        samples[4] = samples[3]
    elif damage == "missing_role":
        del roles[3], samples[3]
    elif damage == "checksum":
        samples[3]["checksum_sha256"] = "0" * 64
    elif damage == "encoder":
        samples[3]["robot"]["finger_positions_m"] = [0.0, 0.0]
    elif damage == "same_step_command":
        samples[1]["robot"]["last_accepted_gripper_open"] = True
    elif damage == "retained_as_fresh":
        roles[-1]["frame_id"] = "fake-new"
    else:
        samples[-1]["evidence"]["relation"] = "unknown"
        assert not scorer().passive_payload_readback(
            samples, roles, frames, physics, native, commands, receipts
        )["complete"]
        return
    with pytest.raises(ValueError):
        scorer().passive_payload_readback(
            samples, roles, frames, physics, native, commands, receipts
        )
