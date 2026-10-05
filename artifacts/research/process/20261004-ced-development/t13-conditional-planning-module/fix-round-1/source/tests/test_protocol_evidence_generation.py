"""Adversarial raw-evidence contracts; fixtures are software examples, not proofs."""

import base64
import hashlib
import importlib
import importlib.util
import json
import math
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec, content_digest
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def api():
    name = "cloud_edge_robot_arm.research.protocol_evidence"
    assert importlib.util.find_spec(name) is not None, "offline evidence producer is missing"
    return importlib.import_module(name)


def write_json(path, data):
    path.write_text(json.dumps(data))


def inputs(tmp_path):
    config = DatasetConfig(dataset_id="fixture", groups=1)
    rows = []
    for seed in (10001, 10002):
        scene = sample_scene(config, seed)
        parameters = dict(scene.scene_parameters)
        parameters["target"] = {
            **parameters["target"],
            "position": [0.39 if seed == 10001 else 0.4, 0, 0.03],
            "half_size": [0.03] * 3,
        }
        parameters["destination"] = {
            **parameters["destination"],
            "position": [0.4, 0.02, 0.01],
            "half_size": [0.1, 0.1, 0.01],
        }
        scene = SceneSpec.from_parameters(parameters, scene.asset_family_hash, seed)
        rows.append(
            {
                "assignment_id": "formal-0001" if seed == 10001 else "recovery-0001",
                "stratum_id": "STATIC_RTT0",
                "scene": scene.model_dump(),
                "scene_hash": scene.scene_hash,
                "perturbation": {
                    "noise_m": 0.0,
                    "movement_speed_m_s": 0.0,
                    "invalid_fraction": 0.0,
                    "occlusion_fraction": 0.0,
                },
            }
        )
    history = tmp_path / "history"
    history.mkdir()
    write_json(history / "used.json", {"records": [{"group_id": "previous-used"}]})
    metadata = {
        "history_roots": [str(history)],
        "excluded_groups": ["previous-used"],
        "opportunity_sources": {},
        "recovery_sources": {},
    }
    return {"formal": [rows[0]], "recovery": [rows[1]], "_evidence": metadata}


def fixture_scope():
    names = ["base", "link1", "link2", "link3", "link4", "link5", "link6", "hand"]
    return [(a, b) for i, a in enumerate(names) for b in names[i + 2 :]] + [
        (a, b) for a in names[:6] for b in ("left_finger_geom", "right_finger_geom")
    ]


def episode_header(row, observations):
    return {
        "schema_version": "rgbd.raw-episode.v2",
        "assignment_hash": content_digest(row),
        "group_id": row["scene"]["group_id"],
        "scene_hash": row["scene_hash"],
        "episode_id": observations[0]["episode_id"],
        "reset_step": 0,
        "reset_sim_time_s": 0.0,
        "terminal_step": observations[-1]["physics_step"],
        "terminal_sim_time_s": observations[-1]["sim_time_s"],
        "physics_dt_s": 0.002,
        "reset_observation_hash": content_digest(observations[0]),
        "terminal_observation_hash": content_digest(observations[-1]),
    }


def execution_records(observations, actions, source):
    commands = []
    desired = 0.0
    for action in actions:
        step = action["start_step"]
        if action["action_type"] == "OBSERVE":
            continue
        kind = "gripper" if action["action_type"] in {"GRASP", "RELEASE"} else "joint_target"
        command = {
            "command_id": f"cmd-{len(commands) + 1}",
            "action_id": action["action_id"],
            "episode_id": observations[0]["episode_id"],
            "source": source,
            "physics_step": step,
            "sim_time_s": observations[step]["sim_time_s"],
            "accepted": True,
            "type": kind,
            "backend_record": {
                "type": kind,
                "accepted": True,
                "reason": "",
                "after_emergency_stop": False,
                "sim_time_s": observations[step]["sim_time_s"],
            },
        }
        if kind == "joint_target":
            before = desired
            desired += 0.002
            command["target_positions_rad"] = [desired] + [0.0] * 6
            span = action["end_step"] - step
            for index in range(step + 1, action["end_step"] + 1):
                q = before + (desired - before) * (index - step) / span
                observations[index]["joint_positions_rad"] = [q] + [0.0] * 6
                observations[index]["joint_velocities_rad_s"] = [
                    (desired - before) / (span * 0.002)
                ] + [0.0] * 6
            for index in range(action["end_step"] + 1, len(observations)):
                observations[index]["joint_positions_rad"] = [desired] + [0.0] * 6
                observations[index]["joint_velocities_rad_s"] = [0.0] * 7
        else:
            command["target_open"] = action["action_type"] == "RELEASE"
        command["backend_record"].update(
            episode_id=command["episode_id"], physics_step=step, command_seq=len(commands) + 1
        )
        if kind == "joint_target":
            command["backend_record"].update(
                target_positions_rad=command["target_positions_rad"],
                applied_target_positions_rad=command["target_positions_rad"],
            )
        else:
            command["backend_record"]["target_open"] = command["target_open"]
        commands.append(command)
    sequence_cursor = 1
    for action in actions:
        matched = [command for command in commands if command["action_id"] == action["action_id"]]
        action["command_seq_start"] = sequence_cursor
        sequence_cursor += len(matched)
        action["command_seq_end"] = sequence_cursor
        action["result"] = {
            "success": True,
            "action_id": action["action_id"],
            "action_type": action["action_type"],
            "started_at": "2026-10-04T00:00:00Z",
            "finished_at": "2026-10-04T00:00:00Z",
            "duration_ms": 2 * (action["end_step"] - action["start_step"]),
            "state_before": {},
            "state_after": {},
            "details": {
                "physics_steps": action["end_step"] - action["start_step"],
                "teacher_source": source,
            },
        }
    controls = []
    targets, fingers, joint_id, gripper_id = [0.0] * 7, [0.039] * 2, None, None
    for index in range(1, len(observations)):
        for command in commands:
            if command["physics_step"] == index - 1:
                if command["type"] == "joint_target":
                    targets = command["target_positions_rad"]
                    joint_id = command["command_id"]
                else:
                    fingers = [0.039 if command["target_open"] else 0.0] * 2
                    gripper_id = command["command_id"]
        pre = observations[index - 1]["joint_positions_rad"]
        ctrl = [q + min(0.1, max(-0.1, target - q)) for q, target in zip(pre, targets, strict=True)]
        controls.append(
            {
                "physics_step": index,
                "sim_time_s": observations[index - 1]["sim_time_s"],
                "action_id": next(
                    (
                        action["action_id"]
                        for action in actions
                        if action["start_step"] < index <= action["end_step"]
                    ),
                    None,
                ),
                "joint_command_id": joint_id,
                "gripper_command_id": gripper_id,
                "applied_joint_targets_rad": targets,
                "finger_control_targets_m": fingers,
                "pre_joint_positions_rad": pre,
                "pre_gravity_bias_nm": [0.0] * 7,
                "control_rad": ctrl,
                "episode_id": observations[0]["episode_id"],
                "actuator_gains": [1.0] * 7,
                "actuator_ctrl_ranges": [[-2.8, 2.8]] * 7,
            }
        )
    provenance = {
        "schema_version": "rgbd.actuator-provenance.v1",
        "episode_id": observations[0]["episode_id"],
        "controller_parameters": {
            "actuator_gains": [1.0] * 7,
            "actuator_ctrl_ranges": [[-2.8, 2.8]] * 7,
            "initial_joint_targets_rad": [0.0] * 7,
            "initial_finger_targets_m": [0.039] * 2,
            "actuator_delay_steps": 0,
        },
        "steps": controls,
    }
    return commands, provenance


def add_execution_fixture(source, row, observations):
    kinds = [
        "MOVE_ABOVE",
        "APPROACH",
        "GRASP",
        "LIFT",
        "OBSERVE",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "OBSERVE",
    ]
    boundaries = [520, 523, 526, 530, 535, 801, 806, 811, 815, 1401]
    actions = [
        {
            "action_id": f"action-{i + 1}",
            "action_type": kind,
            "episode_id": "recovery-episode",
            "source": "GROUND_TRUTH_TEACHER",
            "start_step": boundaries[i],
            "end_step": boundaries[i + 1],
        }
        for i, kind in enumerate(kinds)
    ]
    commands, provenance = execution_records(observations, actions, "GROUND_TRUTH_TEACHER")
    header = episode_header(row, observations)
    header["recovery_start_step"] = 520
    write_json(source / "attempt.json", header)
    write_json(source / "teacher-actions.json", actions)
    write_json(source / "commands.json", commands)
    write_json(source / "actuator-provenance.json", provenance)


def opportunity(tmp_path, row, *, legacy=False, start_step=0):
    source = tmp_path / "opportunity"
    source.mkdir()
    if legacy:
        Image.new("RGB", (8, 8), "red").save(source / "rgb.png")
        np.save(source / "depth.npy", np.ones((8, 8)))
        np.save(source / "instances.npy", np.ones((8, 8), dtype=np.uint16))
        write_json(
            source / "capture.json",
            {
                "group_id": row["scene"]["group_id"],
                "scene_hash": row["scene_hash"],
                "object_instance_id": 1,
                "action_spec": {
                    "action_type": "MOVE_TCP",
                    "target_position_m": [0.4, 0, 0.2],
                    "radius_m": 0.01,
                },
            },
        )
        return source
    support = tmp_path / "opportunity-support"
    support.mkdir()
    recovery_source = recovery(support, row)
    observations = json.loads((recovery_source / "physical-observations.json").read_text())[
        : start_step + 6
    ]
    params = row["scene"]["scene_parameters"]
    target = params["target"]["position"]
    candidate = {
        "candidate_id": f"candidate-{row['assignment_id']}",
        "action_type": "MOVE_TCP",
        "object_id": "object",
        "target_position_m": [target[0], target[1], 0.16],
        "radius_m": 0.02,
        "timeout_s": 8.0,
    }
    for raw in observations:
        raw["episode_id"] = "fixture-episode"
        raw["object_position_m"] = target
        raw["object_geom_position_m"] = target
        raw["object_linear_velocity_m_s"] = [0.0] * 3
        raw["joint_positions_rad"] = [0.0] * 7
        raw["joint_velocities_rad_s"] = [0.0] * 7
        fraction = min(1.0, max(0.0, (raw["physics_step"] - start_step) / 5))
        raw["tcp_position_m"] = [
            0.3 + (target[0] - 0.3) * fraction,
            target[1] * fraction,
            0.2 + (0.16 - 0.2) * fraction,
        ]
    actions = [
        {
            "action_id": "candidate-action",
            "action_type": "MOVE_TCP",
            "candidate_spec": candidate,
            "episode_id": "fixture-episode",
            "source": "OFFLINE_CANDIDATE",
            "start_step": start_step,
            "end_step": start_step + 5,
        }
    ]
    commands, provenance = execution_records(observations, actions, "OFFLINE_CANDIDATE")
    write_json(source / "physical-observations.json", observations)
    write_json(source / "candidate-actions.json", actions)
    write_json(source / "commands.json", commands)
    write_json(source / "actuator-provenance.json", provenance)
    write_json(source / "context.json", episode_header(row, observations))
    camera = params["camera"]
    assert camera["quaternion"] == [1.0, 0.0, 0.0, 0.0]
    focal = 120 / math.tan(math.radians(camera["fovy"]) / 2)
    transform = np.diag([1.0, -1.0, -1.0, 1.0])
    transform[:3, 3] = camera["position"]
    z = camera["position"][2] - target[2] - 0.03
    ys, xs = np.indices((240, 320))
    world_x = (xs - 159.5) * z / focal + camera["position"][0]
    world_y = -(ys - 119.5) * z / focal + camera["position"][1]
    mask = (np.abs(world_x - target[0]) <= 0.028) & (np.abs(world_y - target[1]) <= 0.028)
    depth = np.zeros((240, 320), dtype="<f4")
    depth[mask] = z
    instances = np.full((240, 320), -1, dtype=np.int32)
    instances[mask] = 1
    Image.new("RGB", (320, 240), "red").save(source / "rgb.png")
    np.save(source / "depth.npy", depth)
    np.save(source / "instances.npy", instances)
    intrinsics = [focal, focal, 159.5, 119.5]
    calibration = hashlib.sha256(
        np.asarray((*intrinsics, *transform.ravel()), dtype="<f8").tobytes()
    ).hexdigest()[:16]
    obs = RGBDObservation.model_validate(
        {
            "frame_id": "frame-1",
            "captured_at": "2026-10-04T00:00:00Z",
            "sim_time_s": 0.0,
            "width": 320,
            "height": 240,
            "rgb_png_base64": base64.b64encode((source / "rgb.png").read_bytes()).decode(),
            "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
            "intrinsics": intrinsics,
            "camera_to_world": list(transform.ravel()),
            "depth_convention": "optical_z_m",
            "source": "mujoco_camera",
            "scene_id": row["scene"]["group_id"],
            "episode_id": "fixture-episode",
            "calibration_version": calibration,
        }
    )
    write_json(source / "observation.json", obs.model_dump(mode="json"))
    state = {
        "time_s": 0.0,
        "qpos": [0.0] * 7 + [0.04, 0.04] + target + [1.0, 0.0, 0.0, 0.0],
        "qvel": [0.0] * 15,
        "act": [],
        "ctrl": [0.0] * 7 + [0.039, 0.039],
    }
    digest = hashlib.sha256(struct.pack("<d", 0.0))
    for key in ("qpos", "qvel", "act", "ctrl"):
        values = np.asarray(state[key], dtype="<f8")
        digest.update(struct.pack("<I", values.size))
        digest.update(values.tobytes())
    state_hash = digest.hexdigest()
    write_json(
        source / "capture.json",
        {
            "group_id": row["scene"]["group_id"],
            "scene_hash": row["scene_hash"],
            "assignment_hash": content_digest(row),
            "episode_id": "fixture-episode",
            "frame_id": "frame-1",
            "object_instance_id": 1,
            "instance_labels": {"1": "object_geom"},
            "physics_step": 0,
            "captured_at_s": 0.0,
            "submitted_at_s": start_step * 0.002,
            "physical_observation_hash": content_digest(observations[0]),
            "render_state": state,
            "physics_state_hash": state_hash,
            "pass_state_hashes": [state_hash] * 3,
            "action_spec": candidate,
        },
    )
    return source


def recovery(tmp_path, row, *, injected=True):
    source = tmp_path / "recovery"
    source.mkdir()
    observations = []
    for step in range(1402):
        held = 530 <= step <= 800
        placed = step > 800
        y = 0.02 * min(max(step - 20, 0), 500) * 0.002
        observations.append(
            {
                "episode_id": "recovery-episode",
                "physics_step": step,
                "sim_time_s": step * 0.002,
                "object_position_m": [
                    row["scene"]["scene_parameters"]["target"]["position"][0],
                    y,
                    0.15 if held else 0.03,
                ],
                "object_geom_position_m": [
                    row["scene"]["scene_parameters"]["target"]["position"][0],
                    y,
                    0.15 if held else 0.03,
                ],
                "object_geom_rotation_row_major": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "object_half_extent_m": [0.03, 0.03, 0.03],
                "object_bottom_z_m": 0.12 if held else 0,
                "object_linear_velocity_m_s": [0, 0.02 if 20 < step < 520 else 0, 0],
                "object_angular_velocity_rad_s": [0, 0, 0],
                "region_center_m": [0.4, 0.02, 0.01],
                "region_half_extent_m": [0.1, 0.1, 0.01],
                "table_top_m": 0,
                "tcp_position_m": [0.4, 0, 0.2],
                "gripper_open": not held,
                "finger_positions_m": [0.02, 0.02] if held else [0.04, 0.04],
                "finger_velocities_m_s": [0, 0],
                "finger_ranges_m": [[0, 0.05], [0, 0.05]],
                "joint_positions_rad": [0] * 7,
                "joint_velocities_rad_s": [0] * 7,
                "joint_ranges_rad": [[-2, 2]] * 7,
                "contact_pairs": [
                    ["left_finger_geom", "object_geom"],
                    ["right_finger_geom", "object_geom"],
                ]
                if held
                else [],
                "self_collision_distances_m": [[a, b, 0.1] for a, b in fixture_scope()],
                "estop_engaged": False,
            }
        )
        if placed:
            observations[-1]["object_position_m"] = [0.4, 0.02, 0.03]
    add_execution_fixture(source, row, observations)
    write_json(source / "physical-observations.json", observations)
    write_json(
        source / "fault-events.json",
        [
            {
                "event": "TARGET_MOTION_STARTED",
                "physics_step": 20,
                "sim_time_s": 0.04,
                "speed_m_s": 0.02,
                "direction_y": 1.0,
                "duration_s": 1.0,
                "mechanism": "external horizontal force with velocity feedback; no pose writes",
            },
            {
                "event": "TARGET_MOTION_FINISHED",
                "physics_step": 520,
                "sim_time_s": 1.04,
                "reason": "scheduled_end",
            },
        ]
        if injected
        else [],
    )
    return source


def test_absent_physics_preserves_full_denominator_and_reports_incomplete(tmp_path):
    pools = inputs(tmp_path)
    result = api().prepare_protocol_evidence(pools, tmp_path / "output")
    assert result["status"] == "INCOMPLETE"
    assert result["required_recovery_groups"] == 200
    assert result["recovery_proven"] == 0
    assert len(json.loads((tmp_path / "output" / "generation-attempts.json").read_text())) == 1
    assert api().verify_protocol_evidence(tmp_path / "output")["status"] == "INCOMPLETE"


def test_opportunity_label_is_recomputed_from_raw_evidence(tmp_path):
    pools = inputs(tmp_path)
    row = pools["formal"][0]
    pools["_evidence"]["opportunity_sources"][row["assignment_id"]] = str(
        opportunity(tmp_path, row)
    )
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    path = tmp_path / "output" / "opportunities.json"
    manifest = json.loads(path.read_text())
    assert manifest[0]["seed"]["oracle_label"] == "VALID"
    manifest[0]["seed"]["oracle_label"] = "INVALID"
    manifest[0]["independent_label_evidence"]["geometry_safe"] = False
    write_json(path, manifest)
    result = api().verify_protocol_evidence(tmp_path / "output")
    assert result["status"] == "INVALID"
    assert any("label" in error for error in result["errors"])


@pytest.mark.parametrize(
    "alteration,want", [("depth", "UNKNOWN"), ("expiry", "UNKNOWN"), ("workspace", "UNKNOWN")]
)
def test_labels_follow_actual_sensor_geometry_and_time(tmp_path, alteration, want):
    pools = inputs(tmp_path)
    row = pools["formal"][0]
    source = opportunity(tmp_path, row)
    capture = json.loads((source / "capture.json").read_text())
    if alteration == "depth":
        np.save(source / "depth.npy", np.zeros((8, 8)))
    elif alteration == "expiry":
        capture["submitted_at_s"] = 2.0
    else:
        capture["action_spec"]["target_position_m"] = [2.0, 0, 0.2]
    write_json(source / "capture.json", capture)
    pools["_evidence"]["opportunity_sources"][row["assignment_id"]] = str(source)
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    rows = json.loads((tmp_path / "output" / "opportunities.json").read_text())
    assert rows[0]["seed"]["oracle_label"] == want


def test_success_without_fault_cannot_prove_recoverability(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [
        str(recovery(tmp_path, row, injected=False))
    ]
    result = api().prepare_protocol_evidence(pools, tmp_path / "output")
    assert result["recovery_proven"] == 0
    attempts = json.loads((tmp_path / "output" / "generation-attempts.json").read_text())
    assert "injection" in attempts[0]["reason"]


def test_success_requires_measured_defect_and_post_fault_teacher(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    result = api().prepare_protocol_evidence(pools, tmp_path / "output")
    assert result["recovery_proven"] == 1
    assert result["status"] == "INCOMPLETE"  # A unit fixture never supplies 200 proofs.
    assert api().verify_protocol_evidence(tmp_path / "output")["recovery_proven"] == 1
    events = tmp_path / "output" / "raw" / row["assignment_id"] / "attempt-1" / "fault-events.json"
    write_json(events, [])
    assert api().verify_protocol_evidence(tmp_path / "output")["status"] == "INVALID"


def test_development_cannot_read_formal_opportunity_labels(tmp_path):
    pools = inputs(tmp_path)
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    with pytest.raises(PermissionError, match="formal"):
        api().load_protocol_opportunities(tmp_path / "output", consumer_role="development")


def test_all_previous_used_groups_are_excluded(tmp_path):
    pools = inputs(tmp_path)
    write_json(
        Path(pools["_evidence"]["history_roots"][0]) / "used.json",
        {"assignments": [{"scene": pools["formal"][0]["scene"]}]},
    )
    with pytest.raises(ValueError, match="previous|excluded"):
        api().prepare_protocol_evidence(pools, tmp_path / "output")


def test_repeated_attempts_cannot_exceed_preregistered_bound(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)] * 6
    with pytest.raises(ValueError, match="bound"):
        api().prepare_protocol_evidence(pools, tmp_path / "output")


def test_cli_denies_development_and_returns_nonzero_for_incomplete(tmp_path):
    pools = inputs(tmp_path)
    input_path = tmp_path / "pools.json"
    write_json(input_path, pools)
    script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_rgbd_protocol_evidence.py"
    command = [
        str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"),
        str(script),
        "--pools",
        str(input_path),
        "--output",
        str(tmp_path / "output"),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 3
    assert json.loads(completed.stdout)["status"] == "INCOMPLETE"


@pytest.mark.parametrize("change", ["no_motion", "teacher_before_fault", "unsafe", "nonfinite"])
def test_recorded_markers_do_not_replace_physical_defect_and_safe_recovery(tmp_path, change):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    observations = json.loads((source / "physical-observations.json").read_text())
    if change == "no_motion":
        for item in observations:
            item["object_position_m"][1] = 0.0
    elif change == "teacher_before_fault":
        write_json(
            source / "teacher-actions.json",
            [
                {
                    "source": "GROUND_TRUTH_TEACHER",
                    "action_type": "PICK_PLACE",
                    "start_step": 1,
                    "end_step": 1401,
                }
            ],
        )
    elif change == "unsafe":
        observations[600]["joint_velocities_rad_s"][0] = 100.0
    else:
        observations[600]["joint_velocities_rad_s"][0] = float("nan")
    write_json(source / "physical-observations.json", observations)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    report = api().prepare_protocol_evidence(pools, tmp_path / "output")
    assert report["recovery_proven"] == 0


def test_manifest_cannot_drop_failed_attempt_or_replace_its_scene(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row, injected=False)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    write_json(tmp_path / "output" / "generation-attempts.json", [])
    report = api().verify_protocol_evidence(tmp_path / "output")
    assert report["status"] == "INVALID"


def test_cli_denies_development_before_writing_files(tmp_path):
    api()
    script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_rgbd_protocol_evidence.py"
    python = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    command = [
        str(python),
        str(script),
        "--consumer-role",
        "development",
        "--output",
        str(tmp_path / "output"),
        "--verify",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 3
    assert "denied" in result.stderr
    assert not (tmp_path / "output").exists()


def test_recovery_source_cannot_relabel_foreign_geometry_as_assigned_scene(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    observations = json.loads((source / "physical-observations.json").read_text())
    observations[0]["object_position_m"][0] = 0.7
    write_json(source / "physical-observations.json", observations)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    assert api().prepare_protocol_evidence(pools, tmp_path / "output")["recovery_proven"] == 0


def reseal(directory):
    """Independent bytes-only reseal so regressions exercise semantic validation."""
    import hashlib

    manifest = json.loads((directory / "protocol-evidence.json").read_text())
    manifest["payload_hashes"] = {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file() and p.name != "protocol-evidence.json"
    }
    write_json(directory / "protocol-evidence.json", manifest)


def test_review_partial_pool_has_explicit_incomplete_locked_v2_topology(tmp_path):
    report = api().prepare_protocol_evidence(inputs(tmp_path), tmp_path / "output")
    assert report.get("protocol_version") == "ced.research.v2"
    assert report.get("topology_complete") is False
    assert report.get("required_formal_groups") == 2400


def test_review_unbound_small_capture_cannot_be_formal_valid(tmp_path):
    pools = inputs(tmp_path)
    row = pools["formal"][0]
    pools["_evidence"]["opportunity_sources"][row["assignment_id"]] = str(
        opportunity(tmp_path, row, legacy=True)
    )
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    manifest = json.loads((tmp_path / "output" / "opportunities.json").read_text())
    assert manifest[0]["seed"]["oracle_label"] == "UNKNOWN"


@pytest.mark.parametrize(
    "change", ["trim_reset", "trim_tail", "nan_time", "fake_teacher", "false_finger_contact"]
)
def test_review_incomplete_or_unjoined_recovery_cannot_count(tmp_path, change):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    observations = json.loads((source / "physical-observations.json").read_text())
    events = json.loads((source / "fault-events.json").read_text())
    if change == "trim_reset":
        observations = observations[20:]
    elif change == "trim_tail":
        observations = observations[:-20]
        actions = json.loads((source / "teacher-actions.json").read_text())
        actions[-1]["end_step"] -= 20
        write_json(source / "teacher-actions.json", actions)
    elif change == "nan_time":
        events[0]["sim_time_s"] = float("nan")
    elif change == "false_finger_contact":
        events[-1]["reason"] = "finger_contact"
    else:
        write_json(
            source / "teacher-actions.json",
            [
                {
                    "source": "GROUND_TRUTH_TEACHER",
                    "action_type": "NOOP",
                    "start_step": 900,
                    "end_step": 901,
                }
            ],
        )
    write_json(source / "physical-observations.json", observations)
    write_json(source / "fault-events.json", events)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    assert api().prepare_protocol_evidence(pools, tmp_path / "output")["recovery_proven"] == 0


@pytest.mark.parametrize("change", ["duplicate", "foreign", "omitted_hash", "changed_assignment"])
def test_review_resealed_manifest_still_checks_semantics_and_coverage(tmp_path, change):
    pools = inputs(tmp_path)
    output = tmp_path / "output"
    api().prepare_protocol_evidence(pools, output)
    if change in {"duplicate", "foreign"}:
        entries = json.loads((output / "generation-attempts.json").read_text())
        extra = dict(entries[0])
        if change == "foreign":
            extra["assignment_id"] = "foreign"
        entries.append(extra)
        write_json(output / "generation-attempts.json", entries)
    elif change == "changed_assignment":
        rows = json.loads((output / "evidence-pools.json").read_text())
        rows["formal"][0]["stratum_id"] = "UNREGISTERED"
        write_json(output / "evidence-pools.json", rows)
    reseal(output)
    if change == "omitted_hash":
        manifest = json.loads((output / "protocol-evidence.json").read_text())
        manifest["payload_hashes"].pop("evidence-pools.json")
        write_json(output / "protocol-evidence.json", manifest)
    assert api().verify_protocol_evidence(output)["status"] == "INVALID"


def test_review_existing_destination_is_rejected_before_writing(tmp_path):
    pools = inputs(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "unrelated").write_text("preserve")
    with pytest.raises((ValueError, FileExistsError)):
        api().prepare_protocol_evidence(pools, output)
    assert sorted(p.name for p in output.iterdir()) == ["unrelated"]


def test_review_dot_assignment_id_is_rejected(tmp_path):
    pools = inputs(tmp_path)
    pools["formal"][0]["assignment_id"] = ".."
    with pytest.raises(ValueError, match="identity"):
        api().prepare_protocol_evidence(pools, tmp_path / "output")


@pytest.mark.parametrize(
    "change", ["calibration", "mapping", "context", "candidate", "scope", "controls"]
)
def test_review_calibrated_pixels_cannot_override_missing_independent_bindings(tmp_path, change):
    pools = inputs(tmp_path)
    row = pools["formal"][0]
    source = opportunity(tmp_path, row)
    capture = json.loads((source / "capture.json").read_text())
    if change == "mapping":
        capture["instance_labels"] = {"1": "dataset_distractor_0_geom"}
    elif change == "candidate":
        capture["action_spec"]["target_position_m"] = [2.0, 0, 0.16]
    elif change == "context":
        capture["pass_state_hashes"][0] = "0" * 64
    elif change == "calibration":
        data = json.loads((source / "observation.json").read_text())
        data["intrinsics"][0] += 1
        data["checksum_sha256"] = ""
        write_json(
            source / "observation.json",
            RGBDObservation.model_validate(data).model_dump(mode="json"),
        )
    elif change == "scope":
        rows = json.loads((source / "physical-observations.json").read_text())
        for raw in rows:
            raw["self_collision_distances_m"] = raw["self_collision_distances_m"][:1]
        write_json(source / "physical-observations.json", rows)
        write_json(source / "context.json", episode_header(row, rows))
    else:
        controls = json.loads((source / "actuator-provenance.json").read_text())
        controls["steps"][0]["control_rad"][0] += 1.0
        write_json(source / "actuator-provenance.json", controls)
    write_json(source / "capture.json", capture)
    pools["_evidence"]["opportunity_sources"][row["assignment_id"]] = str(source)
    report = api().prepare_protocol_evidence(pools, tmp_path / "output")
    manifest = json.loads((tmp_path / "output" / "opportunities.json").read_text())
    assert manifest[0]["seed"]["oracle_label"] == "UNKNOWN"
    assert report["status"] == "INCOMPLETE"


def test_review_calibrated_complete_candidate_can_be_observably_invalid(tmp_path):
    pools = inputs(tmp_path)
    row = pools["formal"][0]
    source = opportunity(tmp_path, row, start_step=150)  # .3s exceeds locked .25s validity.
    pools["_evidence"]["opportunity_sources"][row["assignment_id"]] = str(source)
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    manifest = json.loads((tmp_path / "output" / "opportunities.json").read_text())
    assert manifest[0]["seed"]["oracle_label"] == "INVALID"


def test_review_recovery_control_targets_join_typed_dispatches(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    controls = json.loads((source / "actuator-provenance.json").read_text())
    controls["steps"][530]["joint_command_id"] = "unrelated-command"
    write_json(source / "actuator-provenance.json", controls)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    assert api().prepare_protocol_evidence(pools, tmp_path / "output")["recovery_proven"] == 0


def test_review_selected_fault_must_use_first_proven_attempt(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source), str(source)]
    output = tmp_path / "output"
    api().prepare_protocol_evidence(pools, output)
    faults = json.loads((output / "recovery-faults.json").read_text())
    assert len(faults) == 1
    faults[0]["raw_bundle"] = faults[0]["raw_bundle"].replace("attempt-1", "attempt-2")
    faults[0]["recoverability_evidence_path"] = faults[0]["recoverability_evidence_path"].replace(
        "attempt-1", "attempt-2"
    )
    write_json(output / "recovery-faults.json", faults)
    reseal(output)
    report = api().verify_protocol_evidence(output)
    assert report["status"] == "INVALID"
    assert any("first successful" in error for error in report["errors"])


def test_review_symlink_destination_never_writes_outside_root(tmp_path):
    pools = inputs(tmp_path)
    destination = tmp_path / "external"
    destination.mkdir()
    link = tmp_path / "output"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises((ValueError, FileExistsError)):
        api().prepare_protocol_evidence(pools, link)
    assert not list(destination.iterdir())


def test_passive_adapter_preserves_raw_backend_hook_values_without_executing(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    observations = json.loads((source / "physical-observations.json").read_text())
    actions = json.loads((source / "teacher-actions.json").read_text())
    commands = json.loads((source / "commands.json").read_text())
    provenance = json.loads((source / "actuator-provenance.json").read_text())
    backend_commands = []
    events = []
    for action in actions:
        first = len(backend_commands) + 1
        for command in commands:
            if command["action_id"] == action["action_id"]:
                raw = {
                    **command["backend_record"],
                    "episode_id": command["episode_id"],
                    "physics_step": command["physics_step"],
                    "command_seq": len(backend_commands) + 1,
                }
                if command["type"] == "joint_target":
                    raw["target_positions_rad"] = command["target_positions_rad"]
                    raw["applied_target_positions_rad"] = command["target_positions_rad"]
                else:
                    raw["target_open"] = command["target_open"]
                backend_commands.append(raw)
        events.append(
            {
                "episode_id": action["episode_id"],
                "start_step": action["start_step"],
                "end_step": action["end_step"],
                "command_seq_start": first,
                "command_seq_end": len(backend_commands) + 1,
                "result": action["result"],
            }
        )
    adapter = getattr(api(), "write_recovery_source", None)
    assert adapter is not None, "passive root-hook adapter is missing"
    raw_controls = []
    for step in provenance["steps"]:
        raw_controls.append(
            {
                **step,
                "episode_id": "recovery-episode",
                "actuator_gains": [1.0] * 7,
                "actuator_ctrl_ranges": [[-2.8, 2.8]] * 7,
            }
        )
    output = tmp_path / "adapted"
    adapter(
        row=row,
        observations=observations,
        action_events=events,
        backend_commands=backend_commands,
        actuator_steps=raw_controls,
        fault_events=json.loads((source / "fault-events.json").read_text()),
        recovery_start_step=520,
        output=output,
    )
    assert json.loads((output / "physical-observations.json").read_text()) == observations
    retained = json.loads((output / "actuator-provenance.json").read_text())
    assert retained["steps"][530]["control_rad"] == raw_controls[530]["control_rad"]
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(output)]
    assert api().prepare_protocol_evidence(pools, tmp_path / "evidence")["recovery_proven"] == 1


@pytest.mark.parametrize("change", ["action_result_id", "command_range", "gain_scope"])
def test_review_actual_dispatch_results_and_ranges_are_not_optional_markers(tmp_path, change):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    if change == "gain_scope":
        provenance = json.loads((source / "actuator-provenance.json").read_text())
        provenance["steps"][600]["actuator_gains"] = [2.0] * 7
        write_json(source / "actuator-provenance.json", provenance)
    else:
        actions = json.loads((source / "teacher-actions.json").read_text())
        if change == "action_result_id":
            actions[0]["result"]["action_id"] = "unrelated-return"
        else:
            actions[0]["command_seq_end"] += 1
        write_json(source / "teacher-actions.json", actions)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    assert api().prepare_protocol_evidence(pools, tmp_path / "output")["recovery_proven"] == 0


def test_actual_successful_terminal_hold_dispatch_is_supported(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    commands = json.loads((source / "commands.json").read_text())
    actions = json.loads((source / "teacher-actions.json").read_text())
    observations = json.loads((source / "physical-observations.json").read_text())
    target = observations[523]["joint_positions_rad"]
    hold = {
        "command_id": "terminal-hold",
        "action_id": actions[0]["action_id"],
        "episode_id": "recovery-episode",
        "source": "GROUND_TRUTH_TEACHER",
        "physics_step": 523,
        "sim_time_s": 1.046,
        "type": "hold_current_joints",
        "accepted": True,
        "target_positions_rad": target,
        "backend_record": {
            "type": "hold_current_joints",
            "accepted": True,
            "after_emergency_stop": False,
            "reason": "motion_terminated",
            "sim_time_s": 1.046,
            "episode_id": "recovery-episode",
            "physics_step": 523,
            "command_seq": 2,
            "target_positions_rad": target,
            "applied_target_positions_rad": target,
        },
    }
    commands.insert(1, hold)
    for index, command in enumerate(commands):
        command["backend_record"]["command_seq"] = index + 1
    actions[0]["command_seq_end"] += 1
    for action in actions[1:]:
        action["command_seq_start"] += 1
        action["command_seq_end"] += 1
    write_json(source / "commands.json", commands)
    write_json(source / "teacher-actions.json", actions)
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    assert api().prepare_protocol_evidence(pools, tmp_path / "output")["recovery_proven"] == 1


def test_missing_collector_file_is_preserved_as_incomplete_not_a_success(tmp_path):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    (source / "actuator-provenance.json").unlink()
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    report = api().prepare_protocol_evidence(pools, tmp_path / "output")
    assert report["status"] == "INCOMPLETE"
    assert report["recovery_proven"] == 0
    attempts = json.loads((tmp_path / "output" / "generation-attempts.json").read_text())
    assert attempts[0]["status"] == "INCOMPLETE"
    assert "physical-observations.json" in attempts[0]["payload_hashes"]


def test_assignment_layers_cannot_silently_replace_locked_perturbation_cycle(tmp_path):
    pools = inputs(tmp_path)
    from cloud_edge_robot_arm.research.protocol import STRATA

    config = DatasetConfig(dataset_id="cycle-fixture", groups=25)
    rows = []
    for index in range(25):
        scene = sample_scene(config, 21000 + index)
        ordinal = index // 12
        rows.append(
            {
                "assignment_id": f"formal-{index + 1:04d}",
                "stratum_id": STRATA[index % 12],
                "scene": scene.model_dump(),
                "scene_hash": scene.scene_hash,
                "perturbation": {
                    "noise_m": (0.0, 0.002, 0.005)[ordinal % 3],
                    "movement_speed_m_s": (0.0, 0.02, 0.04)[ordinal % 3],
                    "invalid_fraction": (0.0, 0.1, 0.3)[ordinal % 3],
                    "occlusion_fraction": (0.0, 0.2, 0.4)[ordinal % 3],
                },
            }
        )
    rows[24]["perturbation"]["noise_m"] = 0.002  # Legal value, wrong balanced cycle.
    pools["formal"] = rows
    with pytest.raises(ValueError, match="perturbation"):
        api().prepare_protocol_evidence(pools, tmp_path / "output")


def test_observable_depth_defect_remains_unknown_with_verified_whole_action(tmp_path):
    pools = inputs(tmp_path)
    row = pools["formal"][0]
    source = opportunity(tmp_path, row)
    depth = np.zeros((240, 320), dtype="<f4")
    np.save(source / "depth.npy", depth)
    data = json.loads((source / "observation.json").read_text())
    data.update(
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
    )
    write_json(
        source / "observation.json", RGBDObservation.model_validate(data).model_dump(mode="json")
    )
    pools["_evidence"]["opportunity_sources"][row["assignment_id"]] = str(source)
    api().prepare_protocol_evidence(pools, tmp_path / "output")
    manifest = json.loads((tmp_path / "output" / "opportunities.json").read_text())
    assert manifest[0]["seed"]["oracle_label"] == "UNKNOWN"
    assert manifest[0]["independent_label_evidence"]["geometry_applicable"] is True


@pytest.mark.parametrize("change", ["shifted", "omitted_first", "empty"])
def test_reset_complete_command_history_cannot_omit_its_first_dispatch(tmp_path, change):
    pools = inputs(tmp_path)
    row = pools["recovery"][0]
    source = recovery(tmp_path, row)
    commands = json.loads((source / "commands.json").read_text())
    actions = json.loads((source / "teacher-actions.json").read_text())
    pools["_evidence"]["recovery_sources"][row["assignment_id"]] = [str(source)]
    if change == "empty":
        commands = []
        for action in actions:
            action["command_seq_start"] = action["command_seq_end"] = 1
    else:
        for command in commands:
            command["backend_record"]["command_seq"] += 1
        for action in actions:
            action["command_seq_start"] += 1
            action["command_seq_end"] += 1
        if change == "omitted_first":
            # Two actual same-step dispatches apply identical targets. The retained
            # second command accounts for every control row, so actuator matching
            # alone cannot expose removal of the first command from episode history.
            omitted = json.loads(json.dumps(commands[0]))
            omitted["command_id"] = "omitted-first-dispatch"
            omitted["backend_record"]["command_seq"] = 1
            actions[0]["command_seq_start"] = 1
            write_json(source / "commands.json", [omitted, *commands])
            write_json(source / "teacher-actions.json", actions)
            assert api().prepare_protocol_evidence(pools, tmp_path / "complete-history")[
                "recovery_proven"
            ] == 1
            # Remove actual command1 and consistently shift only its first action
            # range start. Physical steps/controls and all other ranges stay exact.
            actions[0]["command_seq_start"] = 2
    write_json(source / "commands.json", commands)
    write_json(source / "teacher-actions.json", actions)
    report = api().prepare_protocol_evidence(pools, tmp_path / "output")
    assert report["recovery_proven"] == 0
    attempts = json.loads((tmp_path / "output" / "generation-attempts.json").read_text())
    assert attempts[0]["status"] != "PROVEN"
