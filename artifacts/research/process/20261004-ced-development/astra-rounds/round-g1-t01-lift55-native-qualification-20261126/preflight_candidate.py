"""Check the actual locked candidate against the sealed t01 entry without motion or rendering."""

import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation import g1_clearance_score as scorer
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.g1_lift55_qualification import reference_class
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
OUT = REPO / PLAN["output"]


def prohibited(*args, **kwargs):
    raise AssertionError("zero-step qualification preflight attempted motion or rendering")


def rejects(message, function):
    try:
        function()
    except ValueError as error:
        if message in str(error):
            return
        raise
    raise ValueError(f"missing reference rejection: {message}")


def check_references(raw, allocation):
    entry = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    robot = entry["robot"]
    scorer.require(
        sha(raw / "local-clearance.json") == entry["source_sha256"], "wrong entry source"
    )
    model = mujoco.MjModel.from_xml_path(str(ROOT / allocation["case"]["asset_path"]))
    data = mujoco.MjData(model)
    data.qpos[:7] = robot["joint_positions_rad"]
    data.qpos[7:9] = robot["finger_positions_m"]
    data.qvel[:7] = robot["joint_velocities_rad_s"]
    data.qvel[7:9] = robot["finger_velocities_m_s"]
    data.ctrl[:7] = entry["drive"]["entry_target_rad"]
    data.ctrl[7:9] = entry["drive"]["entry_finger_target_m"]
    data.time = robot["sim_time_s"]
    mujoco.mj_forward(model, data)
    backend = SimpleNamespace(
        _mujoco=mujoco,
        _model=model,
        _data=data,
        _config=SimulatorConfig(physics_dt_s=1 / 240),
        _joint_names=[f"joint{i}" for i in range(1, 8)],
        total_physics_steps=entry["step"],
    )
    start = tuple(robot["tcp_position_m"])
    target = tuple(entry["target"][axis] for axis in "xyz")
    lift = VerticalClearancePath("sealed-t01", "LIFT", "LIFT", start, target, 0.08)
    retreat = VerticalClearancePath("sealed-t01", "RETREAT", "RETREAT", start, target, 0.08)
    scorer.require(
        reference_class(None) is reference_class(retreat) is CartesianMotionReference,
        "a non-LIFT path acquired the new reference",
    )

    def construct(cls):
        return cls(
            backend,
            start,
            target,
            np.array(robot["tcp_quaternion_wxyz"]),
            control_steps=5,
            timeout_s=8.0,
            max_velocity=0.5,
            max_acceleration=5 / 3,
        )

    proof = {}
    original = pinned(
        REPO / "experiments/results/g1-t01-owner-lift-corridor-20261126/native.json",
        "fcf124d81293f5824eb3370cf65ff27c7b76172657bf66f1244d437d5c7e44ff",
    )["reference_profiles"]
    for cls, duration in ((reference_class(None), 4.0), (reference_class(lift), 5.5)):
        reference = construct(cls)
        digest = hashlib.sha256()
        for array in (reference.positions, reference.velocities, reference.accelerations):
            digest.update(np.asarray(array, dtype="<f8").tobytes())
        key = str(duration)
        proof[key] = digest.hexdigest()
        scorer.require(
            reference.duration_s == duration
            and reference.settle_s == 0.5
            and proof[key] == original[f"{duration:g}"]["state_vectors_sha256"],
            "candidate reference differs from the registered 1632-step design",
        )
    rejects(
        "identified LIFT or RETREAT",
        lambda: VerticalClearancePath("sealed-t01", "PLACE", "PLACE", start, target, 0.08),
    )
    rejects(
        "target must be vertical",
        lambda: VerticalClearancePath(
            "sealed-t01", "LIFT", "LIFT", start, (target[0] + 0.001, *target[1:]), 0.08
        ),
    )
    data.qvel[0] = 0.021
    rejects("settled arm joints", lambda: construct(reference_class(lift)))
    return proof


def check_scoped_pixels(raw, allocation):
    path = Path(scorer.__file__)
    tree = ast.parse(path.read_bytes())
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.With)
        and ast.unparse(node.items[0].context_expr) == "bind_scene(row['scene_id'])"
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "replay_payload_pixels"
            for call in ast.walk(node)
        )
    ]
    scorer.require(len(matches) == 1, "candidate reader lacks the registered pixel scope")
    receipt = read(raw / "receipt.json")
    seal = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    local_seal = read(raw / "local-clearance-seal.json")
    local = pinned(raw / "local-clearance.json", local_seal["local_clearance_sha256"])
    index = pinned(raw / "pixel-index.json", seal["index_sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    run = pinned(raw / "run.json", seal["run_sha256"])
    commands = pinned(raw / "backend-commands.json", receipt["full_commands_sha256"])
    events = scorer.payload_replay_events(
        local["rows"], local["passive_payload_samples"], run["frame_roles"]
    )
    with bind_scene(allocation["case"]["scene_id"]):
        proof = scorer.replay_payload_pixels(
            raw,
            index,
            allocation,
            receipt,
            allocation["runtime_build_sha256"],
            events,
            {row["physics_step"]: row for row in truth["samples"]},
            commands,
        )
    scorer.require(
        proof == {"replayed": 18, "by_relation": {"held": 17, "unknown": 1}},
        "candidate pixel reader altered the frozen t01 comparison",
    )
    return proof


def main():
    build = read(OUT / "build.json")
    scorer.require(ROOT == Path.cwd(), "run the check inside the locked candidate runtime")
    scorer.verify_generation(ROOT, build["generation"])
    raw = REPO / PLAN["original_case"] / "instance"
    allocation = read(raw.parent / "allocation.json")
    with patch.multiple(
        mujoco,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
        Renderer=prohibited,
        mjr_render=prohibited,
    ):
        references = check_references(raw, allocation)
        pixels = check_scoped_pixels(raw, allocation)
    write(
        OUT / "preflight.json",
        {
            "candidate": build["generation"],
            "source_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
            "build_sha256": sha(OUT / "build.json"),
            "reference_arrays_sha256": references,
            "wrong_action_path_and_motion_entry_rejected": True,
            "cold_frozen_original_payload_pixels": pixels,
            "new_physics_steps": 0,
            "new_native_camera_requests": 0,
        },
    )


if __name__ == "__main__":
    main()
