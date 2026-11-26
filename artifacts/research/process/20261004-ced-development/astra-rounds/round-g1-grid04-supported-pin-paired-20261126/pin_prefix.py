"""One render-free grid-04 replay using only archived native commands."""

import hashlib
import json
from collections import Counter, defaultdict
from unittest.mock import patch

import mujoco
import numpy as np
from pin_evidence import (
    HERE,
    ROOT,
    archived_frame,
    canonical,
    read,
    require,
    sha,
    source_module,
    write,
)
from scripts.graduation.dynamic_vision import plain

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import GripperCommand, JointCommand
from cloud_edge_robot_arm.simulation.mujoco import backend as native

COLLIDABLE = (
    "left_finger_geom",
    "right_finger_geom",
    "object_geom",
    *(f"g1_dual_id{tag}_{part}" for tag in (7, 8) for part in ("plate", "crossbar", "upright")),
)
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
ZERO = "no archived integration digest at RESET"
ANCHORS = (
    ("0000.json.gz", 1280, 235, "GRASP", "PRE", None),
    ("0001.json.gz", 1520, 236, "GRASP", "POST", None),
    ("0002.json.gz", 1520, 236, "LIFT", "PRE", None),
    ("0003.json.gz", 1520, 236, "LIFT", "FEEDBACK", "motion"),
)


def tick_index(rows, key, first, last):
    require(
        [row[key] for row in rows] == list(range(first, last + 1)),
        f"duplicate, missing or disordered {key} in {first}..{last}",
    )
    return {row[key]: row for row in rows}


def archived_samples(case, declarations, episode, *, index=None, labels=None):
    receipt = read(case / "sensor-receipt.json")
    index = read(case / "rgbd-index.json") if index is None else index
    rows = index["rows"]
    if labels is None:
        labels = read(case / "offline-physics.json")["frame_labels"]
    by_id = {row["frame_id"]: row for row in labels}
    by_file = {row["file"]: row for row in rows}
    require(
        len(by_id) == len(by_file) == len(labels) == len(rows)
        and receipt["index_sha256"] == sha(case / "rgbd-index.json")
        and receipt["episode_id"] == index["episode_id"] == episode
        and receipt["scene_id"] == index["scene_id"],
        "archived camera index identity differs",
    )
    samples = {}
    for filename, tick, seq, skill, phase, role in declarations:
        entry = by_file[filename]
        frame = archived_frame(case / filename)
        robot = entry["robot"]
        label = by_id[frame.frame_id]
        require(entry["file_sha256"] == sha(case / filename), f"{filename}: archived gzip SHA256")
        require(
            frame.episode_id == episode
            and frame.scene_id == index["scene_id"]
            and frame.frame_id == robot["frame_id"]
            and frame.checksum_sha256 == robot["checksum_sha256"] == label["checksum_sha256"],
            f"{filename}: archived camera/frame identity",
        )
        require(
            (entry["skill"], entry["phase"]) == (skill, phase)
            and (robot["skill"], robot["phase"], robot["research_role"]) == (skill, phase, role),
            f"{filename}: archived shutter role",
        )
        require(
            robot["physics_step"] == label["physics_step"] == tick
            and robot["native_last_command_seq"] == seq,
            f"{filename}: archived command phase",
        )
        require(
            frame.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"],
            f"{filename}: archived camera encoder clock",
        )
        require(
            len(robot["camera_finger_positions_m"]) == 2
            and len(robot["camera_joint_positions_rad"]) == 7
            and np.asarray(label["rotation"]).shape == (3, 3),
            f"{filename}: archived shutter geometry incomplete",
        )
        samples[filename] = (frame, robot, label)
    return samples


def state_digest(backend):
    model, data = backend._model, backend._data
    vector = np.empty(mujoco.mj_stateSize(model, STATE), dtype="<f8")
    mujoco.mj_getState(model, data, vector, STATE)
    return hashlib.sha256(vector.tobytes()).hexdigest()


def snapshot(backend, approach):
    model, data = backend._model, backend._data
    record = approach.snapshot(backend)
    contacts = backend._read_contacts()
    record["touching"] = sorted(sorted((item.geom1, item.geom2)) for item in contacts)
    record.update(
        phase_sha256=state_digest(backend),
        act=data.act.tolist(),
        arm_target=backend._target_positions.tolist(),
        pending=[[tick, value.tolist()] for tick, value in backend._pending_joint_targets],
        last_command_seq=backend.next_command_sequence - 1,
        gripper_open=backend._gripper_open,
        estop=backend.estop_engaged,
        guard_brake_state=backend._guard_brake_state,
        contact_details=[
            {
                "geoms": sorted((item.geom1, item.geom2)),
                "expected": item.expected,
                "illegal": item.illegal,
            }
            for item in contacts
        ],
        geometry={
            name: {
                "center_m": data.geom_xpos[model.geom(name).id].tolist(),
                "rotation": data.geom_xmat[model.geom(name).id].reshape(3, 3).tolist(),
            }
            for name in COLLIDABLE
        },
    )
    return record


def prepare(plan):
    rounds = HERE.parent
    references = {
        "approach": rounds
        / "round-g1-grid04-approach-offset-transmission-20261126/compare_approach.py",
        "braking": rounds / "round-g1-grid04-lift-midcourse-braking-20261126/screen_braking.py",
        "rebound": rounds / "round-g1-release-terminal-rebound-20261125/terminal_rebound.py",
    }
    return {key: source_module(path) for key, path in references.items()}


def validate_prefix(plan, tools):
    approach = tools["approach"]
    asset, scenario, commands, _, _, _ = approach.validate()
    require(sha(asset) == plan["runtime"]["asset_sha256"], "wrong prefix asset")
    declared = plan["prefix"]
    require(
        (scenario.seed, scenario.scenario_id) == (declared["physics_seed"], declared["scenario"]),
        "wrong prefix scenario",
    )
    case = ROOT / plan["roots"]["old"] / plan["roots"]["case_under_old"]
    source_receipt = read(case / "sensor-receipt.json")
    (move,) = [row for row in source_receipt["actions"] if row["skill"] == "MOVE_ABOVE"]
    require((move["end_step"], move["status"]) == (872, "PASS"), "wrong original MOVE_ABOVE return")
    samples = archived_samples(case, ANCHORS, declared["old_episode"])
    last_seq = declared["commands_inclusive"][1]
    endpoint = declared["all_output_ticks_inclusive"][1]
    prefix = commands[:last_seq]
    require(
        [row["command_seq"] for row in prefix] == list(range(1, last_seq + 1)),
        "original command IDs not contiguous",
    )
    require(
        commands[last_seq]["command_seq"] == 237 and commands[last_seq]["physics_step"] == endpoint,
        "wrong boundary before the first LIFT command",
    )
    require(
        all(
            row["accepted"]
            and not row["after_emergency_stop"]
            and row["episode_id"] == declared["old_episode"]
            for row in prefix
        ),
        "original prefix contains an unaccepted or foreign command",
    )
    require(
        [row["physics_step"] for row in prefix] == sorted(row["physics_step"] for row in prefix)
        and 0 <= prefix[0]["physics_step"] <= prefix[-1]["physics_step"] < endpoint,
        "original command tick order differs",
    )
    require(
        Counter(row["type"] for row in prefix)
        == Counter({"joint_target": 233, "hold_current_joints": 2, "gripper": 1}),
        "original command kinds differ",
    )
    require(
        (
            prefix[151]["physics_step"],
            prefix[151]["type"],
            prefix[152]["physics_step"],
            prefix[234]["physics_step"],
            prefix[234]["type"],
            prefix[235]["target_open"],
        )
        == (872, "hold_current_joints", 872, 1280, "hold_current_joints", False),
        "original same-tick command order differs",
    )

    directory = ROOT / plan["roots"]["approach"] / "native-02"
    recorded = read(directory / "A.json")
    wrong = read(directory / "B.json")
    require(
        recorded["commands"] == [approach.clean(row) for row in prefix[152:235]],
        "original approach command comparison differs",
    )
    require(
        wrong["commands"] != recorded["commands"] and wrong["states"] != recorded["states"],
        "wrong branch negative control unexpectedly matches A",
    )
    require(
        read(directory / "receipt.json")["reviewed_prefix_state"]
        == declared["compare_872_after_seq152"],
        "wrong recorded 872 integration state",
    )
    normal = read(ROOT / plan["roots"]["native"] / "normal.json")[0]
    require(
        normal["tick"] == endpoint
        and normal["phase_sha256"] == declared["compare_1520_before_seq237_phase_sha256"],
        "wrong recorded 1520 integration state",
    )
    return {
        "asset": asset,
        "case": case,
        "scenario": scenario,
        "samples": samples,
        "commands": prefix,
        "normal": normal,
        "states": tick_index(recorded["states"], "step", 872, 1280),
        "controls": tick_index(recorded["applied"], "step", 873, 1280),
    }


def same_reset(actual, recorded):
    def remove_episode(row):
        row = {**row, "episode_id": None}
        if row["result"]:
            row["result"] = {
                **row["result"],
                "physics_state": {
                    **row["result"]["physics_state"],
                    "episode_id": None,
                },
            }
        return row

    require(len(actual) == len(recorded) == 2, "RESET boundary omitted")
    require(
        actual[0]["episode_id"] is None
        and actual[1]["episode_id"]
        and actual[1]["episode_id"] != recorded[1]["episode_id"],
        "RESET reused the original episode",
    )
    require(
        [remove_episode(row) for row in actual] == [remove_episode(row) for row in recorded],
        "native RESET request, controller target or physical state differs",
    )


def pulse(backend, command):
    kind = command["type"]
    if kind == "joint_target":
        backend.apply_joint_targets(JointCommand(positions=command["target_positions_rad"]))
    elif kind == "hold_current_joints":
        backend.hold_current_joints()
    elif kind == "gripper":
        backend.apply_gripper_command(GripperCommand(open=command["target_open"]))
    else:
        raise ValueError(f"unregistered original command {kind}")


def replay(plan, tools, expected, output, counters, journal):
    approach, braking, rebound = (tools[key] for key in ("approach", "braking", "rebound"))
    backend = native.MuJoCoPhysicsBackend()
    step_cap = plan["budgets_max_including_failed_attempts"]["prefix_mj_steps"]
    require(step_cap == plan["prefix"]["all_output_ticks_inclusive"][1], "wrong prefix step cap")
    original_step = mujoco.mj_step
    commands_at = defaultdict(list)
    for command in expected["commands"]:
        commands_at[command["physics_step"]].append(command)
    sampled = defaultdict(list)
    for _, robot, label in expected["samples"].values():
        sampled[robot["physics_step"], robot["native_last_command_seq"]].append((robot, label))
    seen, resets, checks = set(), [], {}
    camera_used = native.MuJoCoRGBDCamera

    def step(model, data):
        require(counters["physics_steps"] < step_cap, "registered prefix step cap exceeded")
        counters["physics_steps"] += 1
        return original_step(model, data)

    def deny(*args, **kwargs):
        counters["render_or_capture_attempts"] += 1
        raise RuntimeError("render or capture attempted during CPU prefix")

    def suppress_update():
        counters["suppressed_sensor_updates"] += 1

    def observe_drive(row):
        actual = {
            "step": row.physics_step,
            "applied_joint_targets": list(row.applied_joint_targets_rad),
            "ctrl": [*row.control_rad, *row.finger_control_targets_m],
        }
        if row.physics_step in expected["controls"]:
            require(
                actual == expected["controls"][row.physics_step],
                f"original approach applied control differs at {row.physics_step}",
            )
            counters["archived_applied_controls_checked"] += 1
        journal["actuator"].write(canonical(actual))

    class TestScope(Exception):
        pass

    def lifecycle():
        empty_frame = backend._sensor_frame
        error = TestScope()
        for stop in (None, error):
            try:
                with backend.sensor_capture_on_demand():
                    require(backend._sensor_capture_on_demand, "capture scope failed to enter")
                    if stop:
                        raise stop
            except TestScope as exc:
                require(exc is stop, "wrong capture scope exception")
            require(
                not backend._sensor_capture_on_demand
                and backend._camera is None
                and backend._sensor_frame is empty_frame
                and not backend.command_records
                and backend.total_physics_steps
                == counters["physics_steps"]
                == counters["render_or_capture_attempts"]
                == 0,
                "zero-step sensor scope did not close",
            )
        checks["zero_step_sensor_scope"] = "normal and exceptional exits closed"

    def audit(tick):
        seq = backend.next_command_sequence - 1
        if (tick, seq) not in sampled:
            return
        braking.audit_samples(backend, sampled, seen)
        site = backend._data.site("tcp")
        quaternion = np.empty(4)
        mujoco.mju_mat2Quat(quaternion, site.xmat)
        for robot, _ in sampled[tick, seq]:
            require(
                site.xpos.tolist() == robot["tcp_position_m"]
                and quaternion.tolist() == robot["tcp_quaternion_wxyz"],
                f"archived TCP buffer differs at tick {tick}, command {seq}",
            )

    with (
        patch.multiple(mujoco, mj_step=step, Renderer=deny, mjr_render=deny),
        patch.object(native, "MuJoCoRGBDCamera", deny),
        patch.object(camera_used, "_capture", deny),
        patch.multiple(
            backend,
            _update_sensor_frame=suppress_update,
            capture_sensor_frame=deny,
            capture_sensor_frame_with_instances=deny,
            _capture_cached_observed=deny,
        ),
    ):
        try:
            backend.initialize(
                SimulatorConfig(
                    model_path=str(expected["asset"]),
                    seed=expected["scenario"].seed,
                    physics_dt_s=1 / 240,
                    render_rgb=True,
                    render_depth=True,
                    camera_width=320,
                    camera_height=240,
                    domain_randomization=False,
                )
            )
            with backend.observe_operation_boundaries(lambda event: resets.append(plain(event))):
                counters["resets"] += 1
                backend.reset(expected["scenario"])
            write(output / "native-resets.json", resets)
            same_reset(resets, read(expected["case"] / "native-resets.json"))
            checks["0"] = {"reset_exact_except_episode": True, "integration_sha256": ZERO}
            lifecycle()

            with backend.observe_actuator_steps(observe_drive):
                for tick in range(step_cap + 1):
                    row = snapshot(backend, approach)
                    require(
                        row["step"] == tick and counters["physics_steps"] == tick,
                        f"native endpoint count differs at {tick}",
                    )
                    journal["endpoints"].write(canonical(row))
                    counters["endpoints"] += 1
                    if tick in expected["states"]:
                        archived = expected["states"][tick]
                        require(
                            {key: row[key] for key in archived} == archived,
                            f"archived approach state differs at {tick}",
                        )
                        counters["archived_approach_endpoints_checked"] += 1
                    audit(tick)
                    for command in commands_at[tick]:
                        seq = command["command_seq"]
                        require(
                            counters["command_reissues"] < len(expected["commands"]),
                            "original command budget exceeded",
                        )
                        before = snapshot(backend, approach)
                        counters["command_reissues"] += 1
                        pulse(backend, command)
                        actual = backend.command_records[-1]
                        journal["commands"].write(canonical(actual))
                        braking.command_match(actual, command)
                        after = snapshot(backend, approach)
                        journal["phases"].write(
                            canonical({"seq": seq, "before": before, "after": after})
                        )
                        audit(tick)
                        if seq == 152:
                            digest = rebound.integration_digest(backend, mujoco)
                            require(
                                not backend._pending_joint_targets
                                and digest == plan["prefix"]["compare_872_after_seq152"],
                                "872 post-HOLD native/integration digest differs",
                            )
                            checks["872"] = digest
                        if seq == 235:
                            checks["1280"] = {"last_seq": 235, "frame_id": next(iter(seen))}
                    if tick < step_cap:
                        require(
                            backend.step(1).physics_steps == 1, "native prefix step count differs"
                        )

            normal = expected["normal"]
            require(
                [
                    row[key]
                    for key in ("q", "dq", "ctrl", "time_s", "touching", "tcp", "phase_sha256")
                ]
                == [
                    normal[key]
                    for key in ("q", "dq", "ctrl", "t", "contacts", "tcp", "phase_sha256")
                ]
                and row["geometry"]["object_geom"]["center_m"] == normal["cube"]
                and len(row["pending"]) == normal["pending_count"] == 0
                and not row["estop"]
                and row["last_command_seq"] == 236,
                "1520 pre-LIFT command integration and recorder state differ",
            )
            require(
                seen == {frame.frame_id for frame, _, _ in expected["samples"].values()},
                "archived RESET/GRASP/LIFT anchors were not all checked",
            )
            checks["1520"] = {
                "phase_sha256": row["phase_sha256"],
                "frame_ids": {
                    name: frame.frame_id
                    for name, (frame, _, _) in expected["samples"].items()
                    if name != "0000.json.gz"
                },
                "last_seq": row["last_command_seq"],
                "contacts": row["touching"],
            }
            require(
                counters["resets"] == 1
                and counters["physics_steps"] == step_cap
                and counters["endpoints"] == step_cap + 1
                and counters["command_reissues"] == 236
                and counters["archived_approach_endpoints_checked"] == 409
                and counters["archived_applied_controls_checked"] == 408
                and counters["render_or_capture_attempts"] == 0
                and backend._camera is None
                and not backend._sensor_capture_on_demand,
                "prefix budget, archived comparison count or sensor closure differs",
            )
        finally:
            backend.shutdown()
    return {
        "old_episode": plan["prefix"]["old_episode"],
        "new_episode": resets[-1]["episode_id"],
        "anchors": checks,
        "counts": dict(counters),
    }


def load_lines(path):
    with path.open("rb") as stream:
        return [json.loads(line) for line in stream]
