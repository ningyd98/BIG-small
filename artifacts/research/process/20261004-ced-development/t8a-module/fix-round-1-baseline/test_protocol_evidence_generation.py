"""Adversarial raw-evidence contracts; fixtures are software examples, not proofs."""

import importlib
import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene


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
                "assignment_id": f"fixture-{seed}",
                "scene": scene.model_dump(),
                "scene_hash": scene.scene_hash,
                "perturbation": {"noise_m": 0},
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


def opportunity(tmp_path, row):
    source = tmp_path / "opportunity"
    source.mkdir()
    Image.new("RGB", (8, 8), "red").save(source / "rgb.png")
    np.save(source / "depth.npy", np.ones((8, 8)))
    np.save(source / "instances.npy", np.ones((8, 8), dtype=np.uint16))
    write_json(
        source / "capture.json",
        {
            "group_id": row["scene"]["group_id"],
            "scene_hash": row["scene_hash"],
            "episode_id": "fixture-episode",
            "frame_id": "frame-1",
            "object_instance_id": 1,
            "captured_at_s": 1.0,
            "submitted_at_s": 1.1,
            "tcp_position_m": [0.3, 0, 0.2],
            "action_spec": {
                "action_type": "MOVE_TCP",
                "target_position_m": [0.4, 0, 0.2],
                "radius_m": 0.01,
            },
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
                "object_position_m": [0.4, y, 0.15 if held else 0.03],
                "object_geom_position_m": [0.4, y, 0.15 if held else 0.03],
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
                "self_collision_distances_m": [["link1_geom", "link3_geom", 0.1]],
                "estop_engaged": False,
            }
        )
        if placed:
            observations[-1]["object_position_m"] = [0.4, 0.02, 0.03]
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
    write_json(
        source / "teacher-actions.json",
        [
            {
                "action_type": "PICK_PLACE",
                "start_step": 520,
                "end_step": 1401,
                "source": "GROUND_TRUTH_TEACHER",
            }
        ],
    )
    write_json(
        source / "commands.json",
        [
            {
                "type": "move_joints",
                "accepted": True,
                "reason": "accepted",
                "after_emergency_stop": False,
                "sim_time_s": 1.04,
            }
        ],
    )
    write_json(
        source / "attempt.json",
        {
            "group_id": row["scene"]["group_id"],
            "scene_hash": row["scene_hash"],
            "episode_id": "recovery-episode",
            "recovery_start_step": 520,
        },
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
    "alteration,want", [("depth", "UNKNOWN"), ("expiry", "INVALID"), ("workspace", "INVALID")]
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
