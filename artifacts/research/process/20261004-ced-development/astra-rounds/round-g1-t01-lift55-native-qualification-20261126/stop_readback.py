"""Check the locked t01 LIFT prefix and its original 8+240 stop envelopes."""

import importlib.util
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_handoff import authorized_pair
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    PayloadClearance,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
SIGNATURE = mujoco.mjtState.mjSTATE_INTEGRATION
ALLOWED_FINGERS = {
    ("left_finger_geom", "object_geom"),
    ("object_geom", "right_finger_geom"),
}
TABLE_PAIR = ("object_geom", "table")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def no_render(*args, **kwargs):
    raise AssertionError("CPU stop verification attempted rendering")


def state_bytes(model, data):
    packed = np.empty(mujoco.mj_stateSize(model, SIGNATURE), dtype="<f8")
    mujoco.mj_getState(model, data, packed, SIGNATURE)
    return packed


def contacts(model, data):
    return Counter(
        tuple(sorted((model.geom(row.geom1).name, model.geom(row.geom2).name)))
        for row in data.contact
    )


def exact_normal(backend, trace, truth):
    """One-step closure from the actual effective drive, before restoring the next command."""
    model, data = backend._model, backend._data
    rows = trace["before_integrations"]
    frames = {row["state"]["physics_step"]: row["state"] for row in trace["frames"]}
    entry = trace["reference"]["start_step"]
    normal = {entry: frames[entry]}
    for row, next_row in zip(rows, [*rows[1:], None], strict=True):
        tick = row["physics_step"]
        live = normal[tick]
        packed = np.asarray(row["integration"])
        mujoco.mj_setState(model, data, packed, SIGNATURE)
        saved_ctrl = data.ctrl.copy()
        data.ctrl[:] = live["ctrl"]
        require(
            np.array_equal(state_bytes(model, data), live["integration"])
            and np.array_equal(live["qfrc_bias_arm"], row["qfrc_bias_arm"])
            and row["sim_time_s"] == data.time
            and row["pending"] == []
            and row["actuator_delay_steps"] == 0
            and not row["estop"],
            f"non-control state or simulation clock changed before step {tick + 1}",
        )
        data.ctrl[:] = saved_ctrl
        mujoco.mj_step(model, data)
        observed = truth[tick + 1]
        require(
            observed["physics_step"] == tick + 1
            and data.time == observed["sim_time_s"]
            and np.array_equal(data.qpos[:7], observed["joint_positions_rad"])
            and np.array_equal(data.qpos[7:9], observed["finger_positions_m"])
            and np.array_equal(data.qvel[:7], observed["joint_velocities_rad_s"])
            and np.array_equal(data.qvel[7:9], observed["finger_velocities_m_s"])
            and contacts(model, data)
            == Counter(tuple(sorted(pair)) for pair in observed["contact_pairs"]),
            f"native dynamics or contact closure failed at {tick + 1}",
        )
        endpoint = dict(
            row,
            physics_step=tick + 1,
            sim_time_s=float(data.time),
            integration=state_bytes(model, data).tolist(),
            qfrc_bias_arm=data.qfrc_bias[:7].tolist(),
            ctrl=data.ctrl.tolist(),
        )
        normal[tick + 1] = endpoint
        if (exposure := frames.get(tick + 1)) is not None:
            require(exposure == endpoint, f"post-integration exposure differs at {tick + 1}")
        if next_row is not None:
            require(next_row["physics_step"] == tick + 1, "noncontiguous LIFT inputs")
    return normal


def checked_original_helpers():
    rounds = HERE.parent
    h = rounds / "round-g1-skill-handoff-20261125"
    paths = (
        (
            h / "handoff-physics-stops.py",
            "25d7dba4451ec393c22fec82373dd36e9307d306e60e3d32163ccec3af765559",
        ),
        (
            h / "handoff-physics-native.py",
            "ed914843bd0c2c73a3d3f6fb10b17611684753988ec5e6181bcccd093433fe2c",
        ),
        (
            h / "handoff-physics-preregistration.json",
            "eb1f01cb7591ddcf31ae10a1b1de78a17f44a5688d97204b91b29d98bf1619bc",
        ),
        (
            rounds / "round-g1-braking-envelope-20261125/brake-physics-replay.py",
            "f13b5ea7469b706b6cd4dffe786235a4bdefdd504e99d9756e8250214197a6f7",
        ),
    )
    for path, expected in paths:
        require(sha(path) == expected, f"original stop helper changed: {path.name}")
    spec = importlib.util.spec_from_file_location("original_stop", h / "handoff-physics-stops.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_branch(backend, helper, source, truth, path, instrument=None):
    model, data = backend._model, backend._data
    tick = source["physics_step"]
    state = np.asarray(source["integration"])
    helper.io.restore(
        backend, (state, np.asarray(source["arm_target"]), source["gripper_open"], tick)
    )
    require(np.array_equal(state_bytes(model, data), state), "native checkpoint restore differs")
    # mj_forward provides the derived buffers. The live RK4 cache supplied this
    # exact arm bias for the first control write at the captured boundary.
    data.qfrc_bias[:7] = source["qfrc_bias_arm"]
    backend.emergency_stop()
    require(
        [row["type"] for row in backend.command_records]
        == ["hold_current_joints", "emergency_stop"]
        and backend.estop_engaged
        and np.array_equal(backend._target_positions, data.qpos[:7]),
        "original native stop does not hold the restored joints",
    )
    q = np.empty((241, model.nq))
    dq = np.empty((241, model.nv))
    ctrl = np.empty((241, model.nu))
    measured = Counter(tuple(sorted(pair)) for pair in truth[tick]["contact_pairs"])
    contact_rows = []
    handoff_geometry = []
    for offset in range(241):
        q[offset], dq[offset], ctrl[offset] = data.qpos, data.qvel, data.ctrl
        contact_rows.append(measured)
        if instrument is not None:
            row, _ = instrument.sample(backend)
            handoff_geometry.append(row)
        if offset < 240:
            advance = backend.step()
            require(advance.physics_steps == 1, "stop advanced outside its original one-step clock")
            measured = contacts(model, data)
    names = sorted({pair for row in contact_rows for pair in row})
    with path.open("xb") as f:
        np.savez_compressed(
            f,
            q=q,
            qvel=dq,
            ctrl=ctrl,
            pair_names=np.asarray(names, dtype="U"),
            contact_counts=np.array([[row[pair] for pair in names] for row in contact_rows]),
        )
    return q, dq, contact_rows, handoff_geometry


def observed_payload_support(motion, q, dq, anchor, axes):
    vertices, speed, relative, relative_speed = snapshot(
        motion, q, dq, q[:, 9:12], object_matrix(q)
    )
    return (
        positive_support(vertices, speed, anchor[0], AXES),
        positive_support(relative, relative_speed, anchor[1], axes),
    )


def min_reserve(allowance, observed, names, directions):
    residual = allowance - observed
    body, axis = np.unravel_index(residual.argmin(), residual.shape)
    return {
        "body": names[body],
        "direction": directions[axis].tolist(),
        "margin_m": float(residual[body, axis]),
    }


def compare_handoff(stage, instrument, baseline, geometry):
    live = np.stack([row["pair_gap"] for row in geometry])
    closing = np.maximum(0, baseline["pair_gap"] - live.min(axis=0))
    closing += 0.5 * abs(np.diff(live, axis=0)).max(axis=0)
    active = [not authorized_pair("LIFT", *pair) for pair in instrument.pairs]
    residual = np.where(active, np.array(stage["pair_closing_m"]) - closing, np.inf)
    j = int(residual.argmin())
    center = np.stack([row["centers"] for row in geometry])
    rotation = np.stack([row["rotation"] for row in geometry])
    points = center[:, :, None] + instrument.scene.local @ rotation.transpose(0, 1, 3, 2)
    anchor = baseline["centers"][:, None] + instrument.scene.local @ baseline["rotation"].transpose(
        0, 2, 1
    )
    allowance = np.array([stage["body_pad_xyz_m"][n] for n in instrument.io_names])
    return {
        "handoff_pair": {"pair": instrument.pairs[j], "margin_m": float(residual[j])},
        "handoff_body": min_reserve(
            allowance, abs(points - anchor).max(axis=(0, 2)), instrument.io_names, np.eye(3)
        ),
    }


def readback(backend, asset, trace, truth, area, result):
    original = checked_original_helpers()
    model, data = backend._model, backend._data
    normal = exact_normal(backend, trace, truth)
    result["verified_normal_reintegration_steps"] = len(normal) - 1
    initial = trace["reference"]["start_step"]
    motion = MotionGeometry(Model(asset))
    profiles = ROOT / "scripts/graduation"
    gate = PayloadClearance(
        motion,
        read(profiles / "g1_complete_cv_payload_profile.json"),
        read(profiles / "g1_complete_cv_source_motion_profile.json"),
    )
    stage = read(profiles / "g1_complete_cv_handoff_profile.json")["stages"]["LIFT"]
    instrument = original.Instrument(backend)
    instrument.io_names = original.io.NAMES
    entry_frame = next(frame for frame in trace["frames"] if frame["phase"] == "FEEDBACK")
    handoff_baseline = None
    cache = {}
    for frame in trace["frames"]:
        if frame["status"] != "CLEAR" or frame["phase"] != "FEEDBACK":
            continue
        start = frame["state"]["physics_step"]
        allowed = set(ALLOWED_FINGERS)
        support = frame["source_support"] or {}
        if support.get("qualified") and support.get("registered_pair") == list(TABLE_PAIR):
            allowed.add(TABLE_PAIR)
        entry = start == initial
        frame_motion = frame["motion"]
        if entry:
            require(
                frame == entry_frame and frame_motion["plan"] == "continuous_native_handoff",
                "wrong frozen LIFT entry window",
            )
        else:
            allowance = gate.data["LIFT"]["classes"][frame_motion["speed_class"]]
            source_class = frame_motion.get("registered_source_speed_class")
            world = gate.source_classes[source_class][0] if source_class else allowance["world"]
        mujoco.mj_setState(model, data, np.asarray(normal[start]["integration"]), SIGNATURE)
        q0, dq0 = data.qpos[None].copy(), data.qvel[None].copy()
        xyz, _, rel, _ = snapshot(motion, q0, dq0, q0[:, 9:12], object_matrix(q0))
        anchor = xyz[0], rel[0]
        for delay in range(9):
            tick = start + delay
            if tick not in normal:
                result["unobserved_delays"].append([start, delay])
                continue
            # The original handoff fitter finishes accepted same-tick dispatch
            # before delay zero. Subsequent delays use the post-integration state.
            key = (tick, "entry_dispatch" if entry and delay == 0 else "after_integration")
            if key not in cache:
                require(len(cache) < PLAN["limits"]["stop_branches_max"], "stop budget exceeded")
                source = (
                    trace["before_integrations"][0] if key[1] == "entry_dispatch" else normal[tick]
                )
                path = area / f"{tick}-{key[1]}.npz"
                cache[key] = run_branch(
                    backend, original, source, truth, path, instrument if entry else None
                )
                result["branches"][path.name] = sha(path)
                result["stop_integration_steps"] += 240
            q, dq, hits, rows = cache[key]
            if entry:
                if handoff_baseline is None:
                    handoff_baseline = rows[0]
                margins = compare_handoff(stage, instrument, handoff_baseline, rows)
            else:
                w, rel_extent = observed_payload_support(motion, q, dq, anchor, gate.axes)
                margins = {
                    "world": min_reserve(world, w, motion.names, AXES),
                    "relative": min_reserve(
                        allowance["relative"], rel_extent, motion.names, gate.axes
                    ),
                }
            bad = next(
                (
                    (i, sorted(row.keys() - allowed))
                    for i, row in enumerate(hits)
                    if row.keys() - allowed
                ),
                None,
            )
            check = dict(window=start, delay=delay, tick=tick, margins=margins, forbidden=bad)
            result["checks"].append(check)
            if bad is not None or any(row["margin_m"] < 0 for row in margins.values()):
                result["first_uncovered"] = check
                return


def main():
    registration = read(HERE / "experiment-registration.json")
    build = read(REPO / PLAN["output"] / "build.json")
    require(sha(ROOT / "runtime-build.json") == build["generation"], "wrong stop runtime")
    case = REPO / registration["batch"] / registration["case"]
    raw = case / "instance"
    trace_file = case / "lift-qualification-trace.json"
    trace = pinned(trace_file, "60288fabe209bac8547d9a7f80a05d37bd22a3a35ab24becb42d38e0738343ac")
    receipt = pinned(
        raw / "receipt.json", "62a8336911852a6c9d67d2ea129290ef085dcd09adecccc9a4a5d2988643e694"
    )
    seal = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])["samples"]
    allocation = pinned(case / "allocation.json", receipt["allocation_sha256"])
    asset = ROOT / allocation["case"]["asset_path"]
    require(
        sha(asset) == allocation["asset_sha256"] and trace["state_signature"] == SIGNATURE,
        "physical stop input differs from original assembly or state signature",
    )
    area = REPO / PLAN["output"] / "stop-readback-01"
    area.mkdir()
    result = {
        "trace_sha256": sha(trace_file),
        "source_sha256": sha(Path(__file__)),
        "receipt_sha256": sha(raw / "receipt.json"),
        "branches": {},
        "checks": [],
        "unobserved_delays": [],
        "first_uncovered": None,
        "stop_integration_steps": 0,
    }
    backend = MuJoCoPhysicsBackend()
    try:
        with patch.multiple(mujoco, Renderer=no_render, mjr_render=no_render):
            backend.initialize(
                SimulatorConfig(
                    model_path=str(asset),
                    physics_dt_s=1 / 240,
                    render_rgb=False,
                    render_depth=False,
                    domain_randomization=False,
                )
            )
            cfg = allocation["case"]
            backend.reset(
                PhysicalScenarioConfig(
                    scenario_id=cfg["scene_id"],
                    seed=cfg["visual_seed"],
                    object_mass_kg=trace["native_scenario_mass_kg"],
                    friction_coefficient=trace["native_scenario_friction_coefficient"],
                )
            )
            with backend.sensor_capture_on_demand():
                readback(backend, asset, trace, truth, area, result)
    except BaseException as exc:
        result["verification_error"] = str(exc)
        raise
    finally:
        backend.shutdown()
        write(area / "result.json", result)


if __name__ == "__main__":
    main()
