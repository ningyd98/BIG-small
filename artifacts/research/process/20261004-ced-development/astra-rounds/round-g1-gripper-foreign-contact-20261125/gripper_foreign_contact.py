"""Capture one registered foreign-contact fixture and cold-read four sealed traces."""

import argparse
import inspect
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from gripper_preload_control import (
    ASSET,
    BACKEND,
    Model,
    calibration,
    configuration,
    contact_rows,
    dump,
    read,
    registration,
    sha,
    verify_site,
)

PLAN = Path(__file__).with_name("plan.json")
PLAN_SHA = "457f3d7f080b22ef9076369e188544523c43de6ded7ef7c45498d3a4b7ab6f6d"
OLD_RUN = Path("experiments/results/g1-payload-pad-overlap-20261125/preload-controls-02")
LEFT = "diagnostic_preload_left"


def verified_plan(root):
    if sha(PLAN) != PLAN_SHA:
        raise ValueError("single-side control plan differs")
    plan = read(PLAN)
    for name, digest in plan["input_sha256"].items():
        if sha(root / name) != digest:
            raise ValueError(f"frozen single-side control input changed: {name}")
    return plan["registration"]


def assert_geometry(root, path, backend, expected, center, rotation):
    old = ElementTree.parse(root / OLD_RUN / "one-side" / "fixture.xml").getroot()
    new = ElementTree.parse(path).getroot()
    for root_element in (old, new):
        geom = root_element.find(f"./worldbody/geom[@name='{LEFT}']")
        if geom is None:
            raise ValueError("world fixture missing")
        del geom.attrib["pos"]
        del geom.attrib["size"]
    if ElementTree.tostring(old) != ElementTree.tostring(new):
        raise ValueError("the single-side XML differs beyond the registered position and size")

    model, data = backend._model, backend._data
    geom = model.geom(LEFT)
    physical = data.geom(LEFT)
    local_center = (physical.xpos - center) @ rotation
    face_y = local_center[1] + np.array([-1.0, 1.0]) * geom.size[1]
    actual_rotation = physical.xmat.reshape(3, 3)
    expected_center = [0, expected["new_center_y_m"], 0]
    if (
        int(geom.bodyid[0]) != 0
        or int(geom.contype[0]) != expected["contype"]
        or int(geom.conaffinity[0]) != expected["conaffinity"]
        or not np.allclose(geom.size, expected["new_foreign_half_size_m"], atol=1e-12, rtol=0)
        or not np.allclose(local_center, expected_center, atol=1e-12, rtol=0)
        or not np.allclose(actual_rotation, rotation, atol=1e-12, rtol=0)
        or not np.allclose(
            face_y, [expected["inner_y_m"], expected["outer_y_m"]], atol=1e-12, rtol=0
        )
    ):
        raise ValueError("compiled fixture does not match the sealed width, surfaces or masks")
    return {
        "center_initial_wrist_m": local_center.tolist(),
        "half_size_initial_wrist_m": geom.size.tolist(),
        "inner_outer_wrist_y_m": face_y.tolist(),
        "rotation_world": actual_rotation.tolist(),
        "contype": int(geom.contype[0]),
        "conaffinity": int(geom.conaffinity[0]),
    }


def capture(root, runtime, archive):
    import mujoco

    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import GripperCommand, PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import (
        GRIPPER_OPEN_TARGET_M,
        MuJoCoPhysicsBackend,
    )

    expected = verified_plan(root)
    original, reference = registration(root)
    asset = runtime / ASSET
    backend_path = Path(inspect.getfile(MuJoCoPhysicsBackend)).resolve()
    if (
        sha(runtime / "runtime-build.json") != original["native_runtime_sha256"]
        or backend_path != (runtime / BACKEND).resolve()
        or sha(backend_path) != original["native_backend_sha256"]
        or sha(asset) != original["asset_sha256"]
        or sha(Path(inspect.getfile(Model)))
        != sha(root / "scripts/graduation/g1_complete_cv_geometry.py")
    ):
        raise ValueError("runtime is outside the sealed independent fixture plan")
    joints = reference["arm_joints"]
    center = reference["workpiece_world_geom_center"]
    target = expected["target_away_xyz_m"]
    predicted_tcp, rotation, _ = Model(asset).forward(joints)
    fixture_spec = {
        **original,
        "foreign_half_size_wrist_xyz_m": expected["new_foreign_half_size_m"],
        "foreign_wrist_y_offset_from_reference_center_m": expected["new_center_y_m"],
    }
    archive.mkdir(parents=True)
    xml = configuration(asset, fixture_spec, {"sides": ["left"]}, rotation, center, archive)
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(
            model_path=str(asset),
            seed=expected["seed"],
            physics_dt_s=1 / expected["native_hz"],
            domain_randomization=False,
            render_rgb=False,
            render_depth=False,
        ),
        model_xml=xml,
    )
    backend.reset(
        PhysicalScenarioConfig(
            scenario_id=expected["case_id"],
            seed=expected["seed"],
            object_pose=Pose(**dict(zip("xyz", target, strict=True))),
        )
    )
    data = backend._data
    initial_q = np.r_[joints, GRIPPER_OPEN_TARGET_M, GRIPPER_OPEN_TARGET_M]
    data.qpos[:9] = initial_q
    mujoco.mj_forward(backend._model, data)
    site = data.site("tcp")
    initial_tcp, tcp_distance, rotation_error = verify_site(site, predicted_tcp, rotation)
    try:
        verify_site(site, reference["workpiece_world_com"], rotation)
    except ValueError:
        pass
    else:
        raise ValueError("the workpiece center of mass was accepted as a wrist")
    if (
        backend.total_physics_steps != 0
        or backend._command_records
        or not np.array_equal(data.qpos[:9], initial_q)
        or np.any(data.qvel[:9])
        or np.any(data.ctrl[7:9] != GRIPPER_OPEN_TARGET_M)
        or not np.allclose(data.geom("object_geom").xpos, target, atol=1e-12, rtol=0)
    ):
        raise ValueError("native zero-step fixture differs")
    preflight = archive / "zero-step-preflight.json"
    model_path = archive / "fixture.xml"
    geometry = assert_geometry(root, model_path, backend, expected, center, rotation)
    dump(
        preflight,
        {
            "case": expected["case_id"],
            "plan_sha256": PLAN_SHA,
            "fixture_sha256": sha(model_path),
            "native_steps": 0,
            "source_dwell_frame": reference["exposure"]["frame_id"],
            "source_previous_command": reference["exposure"]["native_last_command_seq"],
            "initial_q": initial_q.tolist(),
            "site_error_m": tcp_distance,
            "rotation_frobenius_error": rotation_error,
            "fixture_geometry": geometry,
            "same_joint_analytical_tcp_m": predicted_tcp.tolist(),
            "archive_post_step_tcp_m": reference["exposure"]["tcp_position_m"],
            "archive_to_analytical_tcp_distance_m": float(
                np.linalg.norm(predicted_tcp - reference["exposure"]["tcp_position_m"])
            ),
            "native_initial_tcp_m": initial_tcp.tolist(),
            "rejected_workpiece_com_as_tcp": True,
        },
    )
    rows = []
    try:
        backend.hold_current_joints()
        backend.apply_gripper_command(GripperCommand(open=False))
        for step in range(1, expected["steps"] + 1):
            result = backend.step(1)
            if result.physics_steps != 1 or backend.total_physics_steps != step:
                raise ValueError("native clock did not advance by the registered step")
            displacement = data.site("tcp").xpos - initial_tcp
            rows.append(
                {
                    "step": step,
                    "jaw_position_m": data.qpos[7:9].tolist(),
                    "jaw_velocity_m_s": data.qvel[7:9].tolist(),
                    "jaw_effective_target_m": data.ctrl[7:9].tolist(),
                    "native_actuator_force_n": data.actuator_force[7:9].tolist(),
                    "tcp_displacement_m": float(np.linalg.norm(displacement)),
                    "tcp_displacement_initial_wrist_m": (displacement @ rotation).tolist(),
                    "contacts": contact_rows(backend),
                    "touches": [
                        {
                            "geometries": [c.geom1, c.geom2],
                            "expected_workpiece": c.expected,
                            "illegal": c.illegal,
                        }
                        for c in result.contacts
                    ],
                }
            )
    finally:
        dump(
            archive / "native-jaw-trace.json.gz",
            {
                "plan_sha256": PLAN_SHA,
                "case": expected["case_id"],
                "mujoco_version": mujoco.__version__,
                "script_sha256": sha(Path(__file__)),
                "fixture_sha256": sha(model_path),
                "zero_step_preflight_sha256": sha(preflight),
                "commands": backend._command_records,
                "rows": rows,
            },
            compressed=True,
        )


def contact_pairs(entries):
    return tuple(sorted({tuple(sorted(c["geometries"])) for c in entries if c["illegal"]}))


def trace_result(directory, expected, gains, threshold, *, fresh):
    path = directory / "native-jaw-trace.json.gz"
    trace = read(path)
    preflight = directory / "zero-step-preflight.json"
    fixture = directory / "fixture.xml"
    if trace["fixture_sha256"] != sha(fixture) or trace["zero_step_preflight_sha256"] != sha(
        preflight
    ):
        raise ValueError(f"trace and zero-step fixture differ {directory}")
    raw = trace["rows"]
    commands = trace["commands"]
    if (
        [cmd["type"] for cmd in commands] != ["hold_current_joints", "gripper"]
        or any(cmd["physics_step"] != 0 or not cmd["accepted"] for cmd in commands)
        or commands[1]["target_open"]
        or [row["step"] for row in raw] != list(range(1, len(raw) + 1))
        or any(row["jaw_effective_target_m"] != expected["actuator_target_m"] for row in raw)
    ):
        raise ValueError(f"invalid command or step clock {directory}")
    tail = [
        row
        for row in raw
        if expected["tail_inclusive"][0] <= row["step"] <= expected["tail_inclusive"][1]
    ]
    kp, kv = gains
    forces = np.asarray([kp * row["jaw_position_m"] + kv * row["jaw_velocity_m_s"] for row in tail])
    flags = (forces >= threshold).all(axis=1).tolist() if tail else []
    required_pair = tuple(
        sorted(tuple(sorted(pair)) for pair in expected["expected_actual_tail_pairs"])
    )
    unexpected = [
        row["step"]
        for row in tail
        if contact_pairs(row["contacts"]) != required_pair
        or contact_pairs(row.get("touches", row["contacts"])) != required_pair
    ]
    target_touched = [
        row["step"]
        for row in raw
        if any(c["expected_workpiece"] for c in row.get("touches", row["contacts"]))
    ]
    unexpected_extras = [
        row["step"]
        for row in raw
        if fresh and any(c["illegal"] and LEFT not in c["geometries"] for c in row["touches"])
    ]
    occupied = Counter(contact_pairs(row["contacts"]) for row in tail)
    complete = len(raw) == expected["steps"] and len(tail) == (
        expected["tail_inclusive"][1] - expected["tail_inclusive"][0] + 1
    )
    result = {
        "native_steps": len(raw),
        "tail_steps": len(tail),
        "private_trace_sha256": sha(path),
        "fixture_sha256": sha(fixture),
        "zero_step_preflight_sha256": sha(preflight),
        "max_tcp_excursion_mm": 1000 * max((r["tcp_displacement_m"] for r in raw), default=0),
        "min_encoder_effort_N": forces.min(axis=0).tolist() if tail else [],
        "max_encoder_effort_N": forces.max(axis=0).tolist() if tail else [],
        "comparator_true": sum(flags),
        "comparator_by_tail_step": flags,
        "first_comparator_true": next(
            (r["step"] for r, flag in zip(tail, flags, strict=True) if flag), None
        ),
        "observed_loaded_illegal_pairs": [
            {"pairs": pairs, "steps": count} for pairs, count in sorted(occupied.items())
        ],
        "target_touch_steps": target_touched,
    }
    if fresh:
        if trace["plan_sha256"] != PLAN_SHA or trace["script_sha256"] != sha(Path(__file__)):
            raise ValueError("fresh fixture trace lacks current plan and capture identity")
        start = read(preflight)
        if (
            start["plan_sha256"] != PLAN_SHA
            or start["native_steps"] != 0
            or not start["rejected_workpiece_com_as_tcp"]
            or start["site_error_m"] > 1e-7
            or start["rotation_frobenius_error"] > 1e-7
            or commands[0]["applied_target_positions_rad"] != start["initial_q"][:7]
        ):
            raise ValueError("fresh fixture did not run from the sealed matched-joint pose")
        measured = complete and not (unexpected or target_touched or unexpected_extras)
        result.update(
            {
                "tail_single_sided_confirmed": measured,
                "first_tail_pair_mismatch": next(iter(unexpected), None),
                "first_extra_illegal_touch": next(iter(unexpected_extras), None),
                "compare_result": (
                    "TRUE_SINGLE_SIDE_COMPARATOR_FALSE_POSITIVE"
                    if any(flags)
                    else "TRUE_SINGLE_SIDE_COMPARATOR_REJECTED"
                )
                if measured
                else "NO_VALID_SINGLE_SIDE_CONTROL",
            }
        )
    return result


def readback(root, runtime, archive, output):
    expected = verified_plan(root)
    orig, _ = registration(root)
    gains = calibration(runtime / ASSET)
    threshold = orig["minimum_per_pad_n"]
    cases = {
        name: trace_result(root / OLD_RUN / name, expected, gains, threshold, fresh=False)
        for name in orig["cases"]
    }
    cases[expected["case_id"]] = trace_result(archive, expected, gains, threshold, fresh=True)
    dump(
        output,
        {
            "schema": "g1.pad.foreign-contact.control-readback.v1",
            "plan_sha256": PLAN_SHA,
            "reader_sha256": sha(Path(__file__)),
            "cases": cases,
            "online_qualification": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.receipt is None:
        capture(args.root.resolve(), args.runtime.resolve(), args.archive.resolve())
    else:
        readback(args.root.resolve(), args.runtime.resolve(), args.archive.resolve(), args.receipt)
