"""Capture fixed MOVE_TCP development opportunities and independently label the originals."""

from __future__ import annotations

import argparse
import base64
import fcntl
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from pydantic import ValidationError
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.contracts.models import Pose, RobotState, TaskStep
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.edge.safety.rules import MOTION_SKILLS, SKILLS_WITH_TARGET_POSE
from cloud_edge_robot_arm.research.protocol_evidence import (
    _candidate,
    _execution,
    _label,
    _render_hash,
    _trace,
)
from cloud_edge_robot_arm.research.protocol_generation import (
    GenerationBudget,
    StepSpool,
    wall_deadline,
)
from cloud_edge_robot_arm.research.sol_molmo_components import check_component_hard_state
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.observations import RGBDObservation

BASE = Path("artifacts/research/process/20261004-ced-development")
DEV = BASE / "t8-real-raw-development"
EXEC = BASE / "astra-repair-execution/R07/producer/raw/recovery-0001/attempt-1/execution-plan.json"
RULES = DEV / "verified-development/evidence-rules.json"
HERE = Path(__file__).resolve()
SOURCE_DEPENDENCIES = (
    "src/cloud_edge_robot_arm/contracts/models.py",
    "src/cloud_edge_robot_arm/edge/safety/rules.py",
    "src/cloud_edge_robot_arm/research/sol_molmo_components.py",
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def cases():
    return [
        {
            "id": f"dev-move-tcp-opportunity-20261124-{i + 1:02d}",
            "ordinal": i + 1,
            "pair": i // 2 + 1,
            "waiting_steps": wait,
        }
        for i, wait in enumerate((0, 96, 96, 0))
    ]


def skill_support(candidate):
    """Exercise the actual product task-step boundary for the fixed command."""
    name = candidate["action_type"]
    try:
        TaskStep.model_validate(
            {
                "step_id": "fixed-move-tcp",
                "skill": name,
                "parameters": {
                    "target_pose": dict(
                        zip(("x", "y", "z"), candidate["target_position_m"], strict=True)
                    )
                },
                "expected_duration_ms": 8000,
                "timeout_ms": int(candidate["timeout_s"] * 1000),
                "retry_limit": 0,
            }
        )
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_input=False)
        require(
            len(errors) == 1 and errors[0]["loc"] == ("skill",),
            "unexpected contract validation failure",
        )
        rejection = errors[0]["type"]
    else:
        rejection = None
    return {
        "task_step_valid": rejection is None,
        "rejection_type": rejection,
        "production_motion_skill": name in MOTION_SKILLS,
        "production_target_pose_checks": name in SKILLS_WITH_TARGET_POSE,
    }


def ages(capture_step, submit_step, wait, capture_time, submit_time, capture_utc, submit_utc):
    require(
        submit_step - capture_step == wait and 0 <= wait and submit_time >= capture_time,
        "registered capture and submission clock mismatch",
    )
    before, after = map(datetime.fromisoformat, (capture_utc, submit_utc))
    require(
        before.utcoffset() is not None and after.utcoffset() is not None and before <= after,
        "missing or reversed UTC clock",
    )
    return {"sim_s": submit_time - capture_time, "wall_s": (after - before).total_seconds()}


def check_online_index(index, identity, candidate):
    allowed = {
        "opportunity_id",
        "candidate",
        "sha256",
        "allocation_sha256",
        "episode",
        "capture_step",
        "submit_step",
        "capture_sim_time",
        "submit_sim_time",
        "capture_utc",
        "submit_utc",
        "robot_state_capture",
        "robot_state_submit",
        "observation_id",
        "scene",
        "calibration_version",
        "observation_sha256",
        "commands_at_capture",
        "commands_at_submit",
        "wait_steps",
        "shared_skill_support",
    }
    require(
        set(index) <= allowed
        and index["opportunity_id"] == identity
        and index["candidate"] == candidate,
        "foreign candidate or unexpected offline fields in online inputs",
    )


def allocate(plan_path, plan_sha, raw, out):
    import mujoco
    from OpenGL import GL

    plan = pinned(plan_path, plan_sha)
    for n, v in plan["input_sha256"].items():
        require(sha(ROOT / n) == v, "frozen input SHA differs: " + n)
    require(sha(plan_path.with_suffix(".md")) == plan["plan_md_sha256"], "Astra plan text differs")
    previous = read(ROOT / EXEC)
    assignment = read(ROOT / DEV / "assignment.json")
    require(
        os.environ.get("MUJOCO_GL") == "egl"
        and shutil.disk_usage(raw).free
        > previous["budgets"]["min_free_bytes"] + 4 * previous["budgets"]["retained_bytes"],
        "EGL/free space",
    )
    context = mujoco.GLContext(320, 240)
    try:
        context.make_current()
        renderer = GL.glGetString(GL.GL_RENDERER).decode()
    finally:
        context.free()
    candidate = _candidate(assignment)
    support = skill_support(candidate)
    require(
        not support["task_step_valid"] and not support["production_motion_skill"],
        "native registry now accepts fixed skill, recheck actual supported contract",
    )
    write(
        out,
        {
            "schema": "graduation.fixed-opportunity.allocation.v1",
            "plan_sha256": plan_sha,
            "created_utc": datetime.now(UTC).isoformat(),
            "baseline": plan["baseline"],
            "script_sha256": sha(HERE),
            "source_sha256": {
                **plan["input_sha256"],
                **{n: sha(ROOT / n) for n in SOURCE_DEPENDENCIES},
            },
            "source_assignment": assignment,
            "config": previous["config"],
            "budgets": previous["budgets"],
            "settle_steps": 120,
            "cases": cases(),
            "candidate": candidate,
            "common_skill_support": support,
            "independent_scenes": 1,
            "formal_claims": 0,
            "renderer": renderer,
            "mujoco": mujoco.__version__,
            "root_name": raw.name,
            "suite_name": raw.parent.name,
        },
    )


def source_files(directory):
    return {
        str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob("*")) if p.is_file()
    }


def snapshot_render(backend):
    data = backend._data
    return {
        "time_s": float(data.time),
        **{k: [float(v) for v in getattr(data, k)] for k in ("qpos", "qvel", "act", "ctrl")},
    }


def write_candidate_trace(oracle, assignment, candidate, states, controls, commands, action):
    raw = [asdict(s) for s in states]
    with (oracle / "physical-observations.json").open("x") as f:
        from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json

        f.write(canonical_json(raw) + "\n")
    write(oracle / "candidate-actions.json", [action] if action else [])
    if not controls or not action:
        write(oracle / "available-raw-controls.json", [asdict(s) for s in controls])
        write(oracle / "available-raw-commands.json", commands)
        return
    require(
        action["candidate_spec"] == candidate and action["source"] == "OFFLINE_CANDIDATE",
        "candidate action binding",
    )
    typed = []
    for index, row in enumerate(commands, 1):
        require(
            row["command_seq"] == index
            and row["episode_id"] == action["episode_id"]
            and action["command_seq_start"] <= index < action["command_seq_end"],
            "unassigned candidate command",
        )
        typed.append(
            {
                "command_id": f"command-{index}",
                "action_id": action["action_id"],
                "source": action["source"],
                "backend_record": row,
                **{
                    k: row[k]
                    for k in ("episode_id", "physics_step", "sim_time_s", "type", "accepted")
                },
                **{k: row[k] for k in ("target_positions_rad", "target_open") if k in row},
            }
        )
    write(oracle / "commands.json", typed)
    steps = []
    cursor = 0
    joint = gripper = None
    for sample in controls:
        step = sample.physics_step
        while cursor < len(typed) and typed[cursor]["physics_step"] < step:
            cmd = typed[cursor]
            if cmd["accepted"] and cmd["type"] in {"joint_target", "hold_current_joints"}:
                joint = cmd["command_id"]
            if cmd["accepted"] and cmd["type"] == "gripper":
                gripper = cmd["command_id"]
            cursor += 1
        steps.append(
            {
                **asdict(sample),
                "joint_command_id": joint,
                "gripper_command_id": gripper,
                "action_id": action["action_id"]
                if action["start_step"] < step <= action["end_step"]
                else None,
            }
        )
    initial = steps[0]
    write(
        oracle / "actuator-provenance.json",
        {
            "schema_version": "rgbd.actuator-provenance.v1",
            "episode_id": raw[0]["episode_id"],
            "controller_parameters": {
                "actuator_gains": initial["actuator_gains"],
                "actuator_ctrl_ranges": initial["actuator_ctrl_ranges"],
                "initial_joint_targets_rad": initial["applied_joint_targets_rad"],
                "initial_finger_targets_m": initial["finger_control_targets_m"],
                "actuator_delay_steps": 0,
            },
            "steps": steps,
        },
    )
    write(
        oracle / "context.json",
        {
            "schema_version": "rgbd.raw-episode.v2",
            "group_id": assignment["scene"]["group_id"],
            "scene_hash": assignment["scene_hash"],
            "assignment_hash": content_digest(assignment),
            "episode_id": raw[0]["episode_id"],
            "reset_step": raw[0]["physics_step"],
            "terminal_step": raw[-1]["physics_step"],
            "reset_sim_time_s": raw[0]["sim_time_s"],
            "terminal_sim_time_s": raw[-1]["sim_time_s"],
            "physics_dt_s": raw[1]["sim_time_s"] - raw[0]["sim_time_s"],
            "reset_observation_hash": content_digest(raw[0]),
            "terminal_observation_hash": content_digest(raw[-1]),
        },
    )


def run(alloc, alloc_sha, case, directory):
    online, oracle = directory / "online", directory / "oracle"
    online.mkdir()
    oracle.mkdir()
    states, controls = [], []
    commands = []
    errors = []
    action = cap = frame = index = None
    guards = 0
    intent = alloc["candidate"]
    row = alloc["source_assignment"]
    scene = SceneSpec.model_validate(row["scene"])
    target = Pose(**dict(zip(("x", "y", "z"), intent["target_position_m"], strict=True)))
    support = skill_support(intent)
    require(support == alloc["common_skill_support"], "production registration changed")
    guard = GenerationBudget(alloc["budgets"], directory)
    journal = StepSpool(directory / "journal.jsonl")
    db = sqlite3.connect(directory / "development-evidence.sqlite")
    db.execute(
        "CREATE TABLE events (ordinal INTEGER PRIMARY KEY, opportunity TEXT, kind TEXT,"
        " step INTEGER, utc TEXT)"
    )

    def register(kind, step):
        db.execute(
            "INSERT INTO events(opportunity,kind,step,utc) VALUES (?,?,?,?)",
            (case["id"], kind, step, datetime.now(UTC).isoformat()),
        )
        db.commit()

    def observe(state):
        states.append(state)
        journal.append("PHYSICS", asdict(state))
        guard.check(state.sim_time_s, 16384 * (len(states) + len(controls)))

    def actuator(pre):
        controls.append(pre)
        journal.append("ACTUATOR_PRE", asdict(pre))

    try:
        with (
            wall_deadline(alloc["budgets"]["wall_s"]),
            MuJoCoCaptureSession(SimulatorConfig(**alloc["config"])) as capture,
        ):
            capture.apply_scene(scene)
            b = capture._backend
            robot = MuJoCoSkillRobot(b)

            def hard():
                nonlocal guards
                check_component_hard_state(b, robot)
                guards += 1

            observe(b.current_physics_observation())
            register("RESET", 0)
            try:
                with b.observe_physics_steps(observe), b.observe_actuator_steps(actuator):
                    b.step(alloc["settle_steps"])
                    cap_step = b.total_physics_steps
                    cap_robot = robot.get_state().model_dump(mode="json")
                    state = snapshot_render(b)
                    before_n = len(b.command_records)
                    frame = capture.capture_with_instances()
                    obs = frame.observation
                    require(
                        _render_hash(state) == frame.physics_state_hash
                        and frame.pass_state_hashes == (frame.physics_state_hash,) * 3
                        and b.total_physics_steps == cap_step == alloc["settle_steps"],
                        "capture/three-pass state differs",
                    )
                    register("CAPTURE", cap_step)
                    # Ground-truth masks and simulation arrays stay in the offline bundle.
                    registration = {
                        k: v for k, v in frame.instance_labels.items() if v == "object_geom"
                    }
                    require(len(registration) == 1, "ambiguous captured instance registration")
                    cap = {
                        "group_id": scene.group_id,
                        "scene_hash": row["scene_hash"],
                        "assignment_hash": content_digest(row),
                        "action_spec": intent,
                        "episode_id": obs.episode_id,
                        "frame_id": obs.frame_id,
                        "physics_step": cap_step,
                        "captured_at_s": obs.sim_time_s,
                        "physical_observation_hash": content_digest(asdict(states[-1])),
                        "render_state": state,
                        "physics_state_hash": frame.physics_state_hash,
                        "pass_state_hashes": list(frame.pass_state_hashes),
                        "instance_labels": frame.instance_labels,
                        "object_instance_id": next(iter(registration)),
                    }
                    if case["waiting_steps"]:
                        b.step(case["waiting_steps"])
                    submit = b.total_physics_steps
                    submit_time = b.get_sim_time()
                    submit_robot = robot.get_state().model_dump(mode="json")
                    hard()
                    before = len(b.command_records)
                    submitted_at = datetime.now(UTC)
                    cap["submitted_at_s"] = submit_time
                    require(
                        submit == cap_step + case["waiting_steps"]
                        and before_n == before == 0
                        and obs.episode_id == states[-1].episode_id,
                        "unexpected candidate commit context",
                    )
                    index = {
                        "opportunity_id": case["id"],
                        "allocation_sha256": alloc_sha,
                        "candidate": intent,
                        "episode": obs.episode_id,
                        "scene": obs.scene_id,
                        "capture_step": cap_step,
                        "submit_step": submit,
                        "capture_sim_time": obs.sim_time_s,
                        "submit_sim_time": submit_time,
                        "capture_utc": obs.captured_at.isoformat(),
                        "submit_utc": submitted_at.isoformat(),
                        "robot_state_capture": cap_robot,
                        "robot_state_submit": submit_robot,
                        "observation_id": obs.observation_id,
                        "calibration_version": obs.calibration_version,
                        "observation_sha256": obs.checksum_sha256,
                        "commands_at_capture": before_n,
                        "commands_at_submit": before,
                        "wait_steps": case["waiting_steps"],
                        "shared_skill_support": support,
                    }
                    register("REFERENCE_DISPATCH", submit)
                    result = robot._move(
                        "MOVE_TCP",
                        target,
                        timeout_ms=int(intent["timeout_s"] * 1000),
                        tcp_velocity=None,
                        acceleration=None,
                        state_guard=hard,
                    )
                    action = {
                        "action_id": result.action_id,
                        "action_type": result.action_type,
                        "result": result.model_dump(mode="json"),
                        "episode_id": obs.episode_id,
                        "source": "OFFLINE_CANDIDATE",
                        "candidate_spec": intent,
                        "start_step": submit,
                        "end_step": b.total_physics_steps,
                        "command_seq_start": before + 1,
                        "command_seq_end": len(b.command_records) + 1,
                    }
                    register("REFERENCE_RETURN", b.total_physics_steps)
            finally:
                commands = b.command_records
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        journal.close()
        db.close()
    if frame is not None:
        obs = frame.observation
        write(online / "observation.json", obs.model_dump(mode="json"))
        shutil.copyfile(online / "observation.json", oracle / "observation.json")
        with (oracle / "rgb.png").open("xb") as f:
            f.write(base64.b64decode(obs.rgb_png_base64))
        depth = np.frombuffer(base64.b64decode(obs.depth_float32_base64), dtype="<f4").reshape(
            obs.height, obs.width
        )
        np.save(oracle / "depth.npy", depth, allow_pickle=False)
        np.save(
            oracle / "instances.npy",
            np.asarray(frame.instance_ids, dtype="<i4").reshape(depth.shape),
            allow_pickle=False,
        )
    if cap is not None:
        write(oracle / "capture.json", cap)
    if index is not None:
        write(online / "index.json", index)
    write_candidate_trace(oracle, row, intent, states, controls, commands, action)
    write(
        directory / "terminal.json",
        {
            "case": case,
            "errors": errors,
            "states": len(states),
            "actuators": len(controls),
            "commands": len(commands),
            "hard_guard_checks": guards,
            "episode": states[0].episode_id if states else None,
            "actual_action_status": None if action is None else action["result"]["success"],
        },
    )
    for folder in (online, oracle):
        write(
            directory / (folder.name + "-seal.json"),
            {"case_id": case["id"], "allocation_sha256": alloc_sha, "files": source_files(folder)},
        )
    write(
        directory / "acquisition-seal.json",
        {
            "allocation_sha256": alloc_sha,
            "case_id": case["id"],
            "online": sha(directory / "online-seal.json"),
            "oracle": sha(directory / "oracle-seal.json"),
            "terminal": sha(directory / "terminal.json"),
            "begin": sha(directory / "begin.json"),
            "database": sha(directory / "development-evidence.sqlite"),
            "journal": sha(directory / "journal.jsonl"),
        },
    )


def side(directory, kind, alloc_sha, identity):
    seal_path = directory / (kind + "-seal.json")
    acquisition = read(directory / "acquisition-seal.json")
    v = pinned(seal_path, acquisition[kind])
    require(
        v["allocation_sha256"] == alloc_sha == acquisition["allocation_sha256"]
        and v["case_id"] == identity == acquisition["case_id"],
        "wrong opportunity seal",
    )
    require(v["files"] == source_files(directory / kind), "sealed input missing or changed")
    return directory / kind


def gate(alloc, alloc_sha, raw, out):
    rows = []
    for case in alloc["cases"]:
        c = case["id"]
        folder = side(raw / c, "online", alloc_sha, c)
        if not (folder / "index.json").exists():
            rows.append({"id": c, "method_eligible": False, "reason": "source commitment missing"})
            continue
        online = read(folder / "index.json")
        check_online_index(online, c, alloc["candidate"])
        obs = RGBDObservation.model_validate(read(folder / "observation.json"))
        require(
            online["allocation_sha256"] == alloc_sha
            and obs.episode_id == online["episode"]
            and obs.scene_id == online["scene"] == alloc["source_assignment"]["scene"]["group_id"]
            and obs.observation_id == online["observation_id"]
            and obs.checksum_sha256 == online["observation_sha256"]
            and obs.calibration_version == online["calibration_version"]
            and obs.sim_time_s == online["capture_sim_time"]
            and obs.captured_at.isoformat() == online["capture_utc"],
            "source capture or camera mismatch",
        )
        states = [
            RobotState.model_validate(online["robot_state_" + p]) for p in ("capture", "submit")
        ]
        support = skill_support(online["candidate"])
        require(
            support == alloc["common_skill_support"] == online["shared_skill_support"]
            and not support["task_step_valid"],
            "different registered gate boundary",
        )
        age = ages(
            online["capture_step"],
            online["submit_step"],
            case["waiting_steps"],
            online["capture_sim_time"],
            online["submit_sim_time"],
            online["capture_utc"],
            online["submit_utc"],
        )
        rows.append(
            {
                "id": c,
                "method_eligible": False,
                "episode": obs.episode_id,
                "observation_sha256": obs.checksum_sha256,
                "source_observation_id": obs.observation_id,
                "camera_version": obs.calibration_version,
                "rgbd_positive_depth_pixels": sum(d > 0 for d in obs.depth_values()),
                "robot_connected_capture_submit": [s.connected for s in states],
                "ages": age,
                "skill_support": support,
                "shield_pre": "NOT_ESTABLISHED",
                "shield_post": "NOT_ESTABLISHED",
                "B3": None,
                "JOINT": None,
                "reason": "MOVE_TCP lacks a TaskStep and target-pose/motion registrations",
                "gate_input_source_sha256": sha(folder / "index.json"),
            }
        )
    write(
        out,
        {
            "schema": "graduation.fixed-opportunity.blind-gates.v1",
            "allocation_sha256": alloc_sha,
            "oracle_reads": 0,
            "gate_invocations": {"B3": 0, "JOINT": 0},
            "rows": rows,
        },
    )


def label(alloc, alloc_sha, raw, out, gate_file, gate_sha):
    gates = pinned(gate_file, gate_sha)
    require(
        gates["allocation_sha256"] == alloc_sha
        and [g["id"] for g in gates["rows"]] == [c["id"] for c in alloc["cases"]],
        "unsealed or incomplete prior gate pass",
    )
    rows = []
    assignment = alloc["source_assignment"]
    rules = pinned(ROOT / RULES, alloc["source_sha256"][str(RULES)])
    for case in alloc["cases"]:
        c = case["id"]
        root = raw / c
        oracle = side(root, "oracle", alloc_sha, c)
        acquisition = read(root / "acquisition-seal.json")
        terminal = pinned(root / "terminal.json", acquisition["terminal"])
        required = (
            "capture.json",
            "context.json",
            "physical-observations.json",
            "candidate-actions.json",
            "actuator-provenance.json",
            "commands.json",
        )
        if not all((oracle / n).is_file() for n in required):
            rows.append(
                {
                    "id": c,
                    "oracle": "UNKNOWN",
                    "provenance": "INCOMPLETE_CAPTURE",
                    "terminal": terminal,
                }
            )
            continue
        capture = read(oracle / "capture.json")
        (action,) = read(oracle / "candidate-actions.json")
        require(
            action["candidate_spec"] == _candidate(assignment) == alloc["candidate"]
            and action["action_type"] == "MOVE_TCP",
            "actual command differs from fixed intent",
        )
        label_value, proof, candidate = _label(oracle, assignment, rules)
        states = _trace(oracle, assignment, read(oracle / "context.json"))
        try:
            _execution(oracle, states, [action], action["start_step"], "OFFLINE_CANDIDATE")
        except ValueError as exc:
            typed = "REJECTED"
            execution_error = str(exc)
        else:
            typed = "VERIFIED"
            execution_error = None
        require(
            capture["physics_step"] == alloc["settle_steps"]
            and action["start_step"] == capture["physics_step"] + case["waiting_steps"]
            and action["end_step"] == states[-1].physics_step
            and capture["submitted_at_s"] == states[action["start_step"]].sim_time_s,
            "actual capture, submission or terminal physics step differs",
        )
        residual = np.asarray(states[-1].tcp_position_m) - candidate["target_position_m"]
        rows.append(
            {
                "id": c,
                "episode": states[-1].episode_id,
                "oracle": label_value,
                "proof": proof,
                "asset_sha256": assignment["scene"]["asset_family_hash"],
                "pass_state_hashes": capture["pass_state_hashes"],
                "physical_trace": "VERIFIED",
                "typed_execution": typed,
                "typed_execution_error": execution_error,
                "start_step": action["start_step"],
                "terminal_step": states[-1].physics_step,
                "action_id": action["action_id"],
                "action_result_success": action["result"]["success"],
                "capture_step": capture["physics_step"],
                "raw_commands": terminal["commands"],
                "actuator_rows": terminal["actuators"],
                "physical_states": len(states),
                "hard_guard_checks": terminal["hard_guard_checks"],
                "capture_to_terminal_sim_s": states[-1].sim_time_s - capture["captured_at_s"],
                "terminal_tcp_minus_target_m": residual.tolist(),
                "oracle_source_seal_sha256": acquisition["oracle"],
            }
        )
    write(
        out,
        {
            "schema": "graduation.fixed-opportunity.oracle.v1",
            "allocation_sha256": alloc_sha,
            "prior_gate_seal_sha256": gate_sha,
            "rows": rows,
        },
    )


def score(alloc, alloc_sha, gate_file, gate_sha, label_file, label_sha, out):
    g = pinned(gate_file, gate_sha)
    y = pinned(label_file, label_sha)
    require(
        g["allocation_sha256"] == y["allocation_sha256"] == alloc_sha
        and y["prior_gate_seal_sha256"] == gate_sha,
        "incorrect gate/oracle seal",
    )
    counts = {s: 0 for s in ("VALID", "INVALID", "UNKNOWN")}
    paired = []
    for case, gg, yy in zip(alloc["cases"], g["rows"], y["rows"], strict=True):
        require(
            case["id"] == gg["id"] == yy["id"]
            and (
                not gg.get("episode")
                or gg["episode"] == yy.get("episode", yy.get("terminal", {}).get("episode"))
            ),
            "case/episode mismatch",
        )
        counts[yy["oracle"]] += 1
        paired.append({**case, **gg, **yy})
    empty = {truth: {v: 0 for v in counts} for truth in counts}
    methods = {
        m: {
            "paired": 0,
            "unavailable_by_oracle": counts,
            "contingency": empty,
            "false_accept_count": None,
            "false_rejection_count": None,
            "false_accept_rate": None,
            "false_rejection_rate": None,
            "method_unknown_rate": None,
        }
        for m in ("B3", "JOINT")
    }
    write(
        out,
        {
            "schema": "graduation.fixed-opportunity-results.v1",
            "allocation_sha256": alloc_sha,
            "gate_sha256": gate_sha,
            "oracle_sha256": label_sha,
            "distinct_scenes": 1,
            "allocated": len(paired),
            "independent_resets": len({p.get("episode") for p in paired if p.get("episode")}),
            "oracle_counts": counts,
            "observed_gate_pairs": 0,
            "methods": methods,
            "rows": paired,
            "formal_g3": False,
            "cloud_calls": 0,
            "formal_claims": 0,
            "hardware_actions": 0,
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    n = commands.add_parser("allocate")
    n.add_argument("plan", type=Path)
    n.add_argument("plan_sha")
    n.add_argument("raw", type=Path)
    n.add_argument("out", type=Path)
    for cmd in ("capture", "gates", "label", "score"):
        q = commands.add_parser(cmd)
        q.add_argument("allocation", type=Path)
        q.add_argument("allocation_sha")
        if cmd != "score":
            q.add_argument("raw", type=Path)
        if cmd == "capture":
            q.add_argument("ordinal", type=int)
        if cmd in ("label", "score"):
            q.add_argument("gate", type=Path)
            q.add_argument("gate_sha")
        if cmd == "score":
            q.add_argument("labels", type=Path)
            q.add_argument("label_sha")
        if cmd != "capture":
            q.add_argument("out", type=Path)
    a = p.parse_args()
    if a.command == "allocate":
        allocate(a.plan, a.plan_sha, a.raw, a.out)
        return
    alloc = pinned(a.allocation, a.allocation_sha)
    require(
        sha(HERE) == alloc["script_sha256"]
        and all(sha(ROOT / n) == s for n, s in alloc["source_sha256"].items()),
        "script or registered input differs",
    )
    if a.command == "capture":
        require(
            a.raw.name == alloc["root_name"]
            and a.raw.parent.name == alloc["suite_name"]
            and 1 <= a.ordinal <= len(alloc["cases"])
            and os.environ.get("MUJOCO_GL") == "egl",
            "wrong root/case/EGL",
        )
        case = alloc["cases"][a.ordinal - 1]
        require(
            all(
                (a.raw / c["id"] / "acquisition-seal.json").is_file()
                for c in alloc["cases"][: a.ordinal - 1]
            ),
            "prior allocated case not sealed",
        )
        directory = a.raw / case["id"]
        with (a.raw.parent / "active-egl.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            directory.mkdir()
            write(
                directory / "begin.json",
                {
                    "case": case,
                    "allocation_sha256": a.allocation_sha,
                    "utc": datetime.now(UTC).isoformat(),
                    "argv": sys.argv[1:],
                },
            )
            run(alloc, a.allocation_sha, case, directory)
    elif a.command == "gates":
        gate(alloc, a.allocation_sha, a.raw, a.out)
    elif a.command == "label":
        label(alloc, a.allocation_sha, a.raw, a.out, a.gate, a.gate_sha)
    else:
        score(alloc, a.allocation_sha, a.gate, a.gate_sha, a.labels, a.label_sha, a.out)


if __name__ == "__main__":
    main()
