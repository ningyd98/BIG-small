"""Exercise the native fingers against independently labeled foreign fixtures."""

import argparse
import gzip
import inspect
import json
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from read_gripper_preload import ASSET, HERE, RAW, calibration, read, sha
from scripts.graduation.g1_complete_cv_geometry import Model

REGISTRATION = HERE / "gripper-preload-control-registration.json"
PREFLIGHT_PLAN = HERE.parent / "round-g1-gripper-fixture-preflight-20261125/plan.json"
PREFLIGHT_PLAN_SHA = "f671c6ce66731e442bc1c693a0881b339e4cee6b3122305262dcc3c40641d2a8"
FIRST_ATTEMPT = RAW.parent / "preload-controls-01/initial-preflight.py"
BACKEND = Path("src/cloud_edge_robot_arm/simulation/mujoco/backend.py")
PAD_NAMES = ("left_finger_geom", "right_finger_geom")
TCP_TOLERANCE_M = 1e-7
ROTATION_TOLERANCE = 1e-7


def dump(path, value, *, compressed=False):
    encoded = (
        json.dumps(value, allow_nan=False, indent=None if compressed else 2, sort_keys=True) + "\n"
    ).encode()
    with path.open("xb") as stream:
        stream.write(gzip.compress(encoded, mtime=0) if compressed else encoded)


def registration(root):
    if sha(PREFLIGHT_PLAN) != PREFLIGHT_PLAN_SHA:
        raise ValueError("registered fixture preflight plan changed")
    for name, digest in read(PREFLIGHT_PLAN)["input_sha256"].items():
        path = FIRST_ATTEMPT if name.endswith("/gripper_preload_control.py") else Path(name)
        if sha(root / path) != digest:
            raise ValueError(f"frozen fixture preflight input changed: {path}")
    spec = read(REGISTRATION)
    course = root / RAW / spec["reference_case"]
    manifold = course / "transport-contact-manifolds.json.gz"
    inputs = {
        "parent_plan": HERE / "plan.json",
        "positive_fit": HERE / "gripper-preload-fit.public.json",
        "reference_manifold": manifold,
    }
    for key, path in inputs.items():
        if sha(path) != spec[f"{key}_sha256"]:
            raise ValueError(f"registered {key} changed")
    table = read(manifold)
    matches = [row for row in table["rows"] if row[0] == spec["reference_step"]]
    if len(matches) != 1 or set(table["columns"]) != {
        "step",
        "workpiece_world_com",
        "workpiece_world_geom_center",
        "R_object_to_world",
        "arm_finger_q",
        "arm_finger_dq",
        "exposures",
        "loaded_contact_rows",
    }:
        raise ValueError("registered manifold row or schema does not match")
    reference = dict(zip(table["columns"], matches[0], strict=True))
    q = np.asarray(reference["arm_finger_q"], dtype=float)
    if q.shape != (9,) or not np.isfinite(q).all():
        raise ValueError("registered arm and finger positions must be finite")
    reference["arm_joints"] = q[:7]
    archive = root / read(course / "replay.json")["source_dir"]
    dwells = [
        robot
        for row in read(archive / "rgbd-index.json")["rows"]
        if row["phase"] == "DWELL"
        and row["skill"] == "LIFT"
        and (robot := row["robot"])["physics_step"] == reference["step"]
    ]
    if len(dwells) != 1:
        raise ValueError("missing uniquely identified source dwell exposure")
    frame = dwells[0]
    previous = max(
        row["command_seq"]
        for row in read(archive / "native-commands.json")
        if row["physics_step"] < reference["step"] and row["accepted"]
    )
    if (
        ["DWELL", frame["frame_id"], frame["native_last_command_seq"]] not in reference["exposures"]
        or frame["native_last_command_seq"] != previous
        or not np.array_equal(reference["arm_joints"], frame["joint_positions_rad"])
        or not np.array_equal(q[7:9], frame["finger_positions_m"])
        or not np.isfinite(frame["tcp_position_m"]).all()
    ):
        raise ValueError("source exposure and registered manifold state do not match")
    reference["exposure"] = frame
    return spec, reference


def mj_numbers(values):
    return " ".join(format(value, ".17g") for value in values)


def configuration(asset, spec, case, wrist_rotation, center, archives):
    # The known position is solely the offline fixture placement.
    import mujoco

    quaternion = np.empty(4)
    mujoco.mju_mat2Quat(quaternion, np.ascontiguousarray(wrist_rotation).ravel())
    tree = ElementTree.parse(asset)
    world = tree.getroot().find("worldbody")
    for side in case["sides"]:
        direction = {"left": 1.0, "right": -1.0}[side]
        position = np.asarray(center) + (
            direction
            * spec["foreign_wrist_y_offset_from_reference_center_m"]
            * wrist_rotation[:, 1]
        )
        ElementTree.SubElement(
            world,
            "geom",
            name=f"diagnostic_preload_{side}",
            type="box",
            size=mj_numbers(spec["foreign_half_size_wrist_xyz_m"]),
            pos=mj_numbers(position),
            quat=mj_numbers(quaternion),
            contype="2",
            conaffinity="2",
        )
    xml = ElementTree.tostring(tree.getroot(), encoding="unicode")
    with (archives / "fixture.xml").open("x", encoding="utf-8") as stream:
        stream.write(xml)
    return xml


def verify_site(site, position, rotation):
    native_position = site.xpos.copy()
    native_rotation = site.xmat.reshape(3, 3)
    distance = float(np.linalg.norm(native_position - position))
    angle_matrix_error = float(np.linalg.norm(native_rotation - rotation))
    if not np.isfinite(distance) or distance > TCP_TOLERANCE_M:
        raise ValueError("native held-pose fixture does not match the same-joint analytical TCP")
    if not np.isfinite(angle_matrix_error) or angle_matrix_error > ROTATION_TOLERANCE:
        raise ValueError("native held-pose fixture has a different TCP rotation")
    return native_position, distance, angle_matrix_error


def contact_rows(backend):
    import mujoco

    model, data = backend._model, backend._data
    flags = {
        frozenset((contact.geom1, contact.geom2)): (contact.expected, contact.illegal)
        for contact in backend.get_contacts()
    }
    rows = []
    for index, contact in enumerate(data.contact):
        wrench = np.empty(6)
        mujoco.mj_contactForce(model, data, index, wrench)
        if wrench[0] > 1e-7:
            names = [model.geom(int(identifier)).name for identifier in contact.geom]
            expected, illegal = flags[frozenset(names)]
            rows.append(
                {
                    "geometries": names,
                    "normal_n": float(wrench[0]),
                    "expected_workpiece": expected,
                    "illegal": illegal,
                }
            )
    return rows


def run(root, native_runtime, output, preflight_only):
    import mujoco

    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import GripperCommand, PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import (
        GRIPPER_OPEN_TARGET_M,
        MuJoCoPhysicsBackend,
    )

    spec, reference = registration(root)
    asset = native_runtime / ASSET
    backend_source = Path(inspect.getfile(MuJoCoPhysicsBackend)).resolve()
    if (
        sha(native_runtime / "runtime-build.json") != spec["native_runtime_sha256"]
        or backend_source != (native_runtime / BACKEND).resolve()
        or sha(backend_source) != spec["native_backend_sha256"]
        or sha(asset) != spec["asset_sha256"]
        or sha(Path(inspect.getfile(Model)))
        != sha(root / "scripts/graduation/g1_complete_cv_geometry.py")
    ):
        raise ValueError("control must use the frozen native implementation and calibrated scene")
    output.mkdir(parents=True)
    joint_positions = reference["arm_joints"]
    expected_tcp, expected_rotation, _ = Model(asset).forward(joint_positions)
    archive_tcp = reference["exposure"]["tcp_position_m"]
    archive_com = reference["workpiece_world_com"]
    prepared = {}
    for key, case in spec["cases"].items():
        archives = output / key
        archives.mkdir()
        xml = configuration(
            asset,
            spec,
            case,
            expected_rotation,
            reference["workpiece_world_geom_center"],
            archives,
        )
        backend = MuJoCoPhysicsBackend()
        backend.initialize(
            SimulatorConfig(
                model_path=str(asset),
                seed=spec["seed"],
                physics_dt_s=1 / spec["native_hz"],
                domain_randomization=False,
                render_rgb=False,
                render_depth=False,
            ),
            model_xml=xml,
        )
        backend.reset(
            PhysicalScenarioConfig(
                scenario_id=f"diagnostic-gripper-preload-{key}",
                seed=spec["seed"],
                object_pose=Pose(**dict(zip("xyz", spec["workpiece_away_xyz_m"], strict=True))),
            )
        )
        data = backend._data
        data.qpos[:7] = joint_positions
        data.qpos[7:9] = GRIPPER_OPEN_TARGET_M
        mujoco.mj_forward(backend._model, data)
        site = data.site("tcp")
        initial_tcp, site_distance, rotation_error = verify_site(
            site, expected_tcp, expected_rotation
        )
        try:
            verify_site(site, archive_com, expected_rotation)
        except ValueError:
            wrong_source_rejected = True
        else:
            raise ValueError("workpiece center of mass was allowed as a TCP reference")
        if backend.total_physics_steps != 0 or backend._command_records:
            raise ValueError("preflight ran after a native command or time advance")
        preflight = {
            "case": key,
            "registration_sha256": sha(REGISTRATION),
            "preflight_plan_sha256": PREFLIGHT_PLAN_SHA,
            "native_physics_steps": 0,
            "fixture_sha256": sha(archives / "fixture.xml"),
            "source_dwell_frame_id": reference["exposure"]["frame_id"],
            "source_last_command_seq": reference["exposure"]["native_last_command_seq"],
            "source_arm_joint_positions_rad": joint_positions.tolist(),
            "archive_post_step_tcp_m": archive_tcp,
            "same_joint_analytical_tcp_m": expected_tcp.tolist(),
            "native_initial_tcp_m": initial_tcp.tolist(),
            "same_joint_site_distance_m": site_distance,
            "same_joint_rotation_frobenius_error": rotation_error,
            "archive_to_analytical_tcp_distance_m": float(
                np.linalg.norm(archive_tcp - expected_tcp)
            ),
            "rejected_workpiece_com_as_tcp": wrong_source_rejected,
            "workpiece_com_to_native_tcp_distance_m": float(
                np.linalg.norm(archive_com - initial_tcp)
            ),
        }
        dump(archives / "zero-step-preflight.json", preflight)
        prepared[key] = (backend, initial_tcp)
    if preflight_only:
        return

    for key, (backend, initial_tcp) in prepared.items():
        archives = output / key
        data = backend._data
        backend.hold_current_joints()
        backend.apply_gripper_command(GripperCommand(open=False))
        rows = []
        for step in range(1, spec["step_count"] + 1):
            result = backend.step(1)
            if result.physics_steps != 1 or backend.total_physics_steps != step:
                raise ValueError("native jaw trace clock gap")
            rows.append(
                {
                    "step": step,
                    "jaw_position_m": data.qpos[7:9].tolist(),
                    "jaw_velocity_m_s": data.qvel[7:9].tolist(),
                    "jaw_effective_target_m": data.ctrl[7:9].tolist(),
                    "native_actuator_force_n": data.actuator_force[7:9].tolist(),
                    "tcp_displacement_m": float(
                        np.linalg.norm(data.site("tcp").xpos - initial_tcp)
                    ),
                    "contacts": contact_rows(backend),
                }
            )
        dump(
            archives / "native-jaw-trace.json.gz",
            {
                "case": key,
                "registration_sha256": sha(REGISTRATION),
                "preflight_plan_sha256": PREFLIGHT_PLAN_SHA,
                "zero_step_preflight_sha256": sha(archives / "zero-step-preflight.json"),
                "script_sha256": sha(Path(__file__)),
                "fixture_sha256": sha(archives / "fixture.xml"),
                "mujoco_version": mujoco.__version__,
                "commands": backend._command_records,
                "rows": rows,
            },
            compressed=True,
        )


def summarize(root, native_runtime, output, receipt):
    spec, _ = registration(root)
    kp, kv = calibration(native_runtime / ASSET)
    results = {}
    for key, case in spec["cases"].items():
        path = output / key / "native-jaw-trace.json.gz"
        fixture = output / key / "fixture.xml"
        preflight_path = output / key / "zero-step-preflight.json"
        preflight = read(preflight_path)
        trace = read(path)
        expected_binding = (key, sha(REGISTRATION), sha(Path(__file__)), sha(fixture))
        if (
            tuple(
                trace[field]
                for field in ("case", "registration_sha256", "script_sha256", "fixture_sha256")
            )
            != expected_binding
        ):
            raise ValueError(f"misbound native trace {key}")
        if (
            trace["preflight_plan_sha256"] != PREFLIGHT_PLAN_SHA
            or preflight["preflight_plan_sha256"] != PREFLIGHT_PLAN_SHA
            or trace["zero_step_preflight_sha256"] != sha(preflight_path)
            or preflight["case"] != key
            or preflight["fixture_sha256"] != sha(fixture)
            or preflight["native_physics_steps"] != 0
            or preflight["same_joint_site_distance_m"] > TCP_TOLERANCE_M
            or preflight["same_joint_rotation_frobenius_error"] > ROTATION_TOLERANCE
            or not preflight["rejected_workpiece_com_as_tcp"]
        ):
            raise ValueError(f"missing matched-joint zero-step preflight {key}")
        commands = trace["commands"]
        if (
            [row["type"] for row in commands] != ["hold_current_joints", "gripper"]
            or any(not row["accepted"] or row["physics_step"] != 0 for row in commands)
            or commands[1]["target_open"]
        ):
            raise ValueError(f"wrong initial command sequence {key}")
        rows = trace["rows"]
        if [r["step"] for r in rows] != list(range(1, spec["step_count"] + 1)):
            raise ValueError(f"wrong native clock {key}")
        if any(r["jaw_effective_target_m"] != [0.0, 0.0] for r in rows):
            raise ValueError(f"gripper's applied close setpoint changed {key}")
        tail = rows[-spec["settled_tail_steps"] :]
        effort = np.asarray([kp * r["jaw_position_m"] + kv * r["jaw_velocity_m_s"] for r in tail])
        flags = (effort >= spec["minimum_per_pad_n"]).all(axis=1)
        pads = dict(zip(("left", "right"), PAD_NAMES, strict=True))
        expected_pairs = {
            frozenset((pads[side], f"diagnostic_preload_{side}")) for side in case["sides"]
        }
        for row in rows:
            if any(c["expected_workpiece"] for c in row["contacts"]):
                raise ValueError(f"diagnostic case unexpectedly held the workpiece {key}")
        for row in tail:
            if {
                frozenset(c["geometries"]) for c in row["contacts"] if c["illegal"]
            } != expected_pairs:
                raise ValueError(f"unexpected settled contacts {key} at step {row['step']}")
        if not np.all(flags == case["expected_bilateral_comparator"]):
            raise ValueError(f"registered comparator outcome not witnessed in {key}")
        results[key] = {
            "native_steps": len(rows),
            "tail_steps": len(tail),
            "fixture_sha256": sha(fixture),
            "zero_step_preflight_sha256": sha(preflight_path),
            "same_joint_site_distance_m": preflight["same_joint_site_distance_m"],
            "same_joint_rotation_frobenius_error": preflight["same_joint_rotation_frobenius_error"],
            "archive_to_analytical_tcp_distance_m": preflight[
                "archive_to_analytical_tcp_distance_m"
            ],
            "workpiece_com_to_native_tcp_distance_m": preflight[
                "workpiece_com_to_native_tcp_distance_m"
            ],
            "private_trace_sha256": sha(path),
            "mujoco_version": trace["mujoco_version"],
            "min_inward_encoder_effort_n": effort.min(axis=0).tolist(),
            "max_inward_encoder_effort_n": effort.max(axis=0).tolist(),
            "max_tcp_excursion_mm": 1000 * max(r["tcp_displacement_m"] for r in rows),
            "bilateral_encoder_comparator_true_in_tail": int(flags.sum()),
            "expected_workpiece_contact_in_entire_trace": 0,
            "illegal_derived_contact_pairs_through_tail": sorted(
                sorted(pair) for pair in expected_pairs
            ),
        }
    dump(
        receipt,
        {
            "schema": "g1.pad.encoder-effort.control-readback.v1",
            "registration_sha256": sha(REGISTRATION),
            "preflight_plan_sha256": PREFLIGHT_PLAN_SHA,
            "script_sha256": sha(Path(__file__)),
            "encoder_comparator_threshold_per_pad_n": spec["minimum_per_pad_n"],
            "cases": results,
            "qualification": False,
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=Path.cwd())
    cli.add_argument("--runtime", type=Path, required=True)
    cli.add_argument("--archive", type=Path, required=True)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--receipt", type=Path)
    mode.add_argument("--preflight-only", action="store_true")
    args = cli.parse_args()
    if args.receipt is None:
        run(
            args.root.resolve(), args.runtime.resolve(), args.archive.resolve(), args.preflight_only
        )
    else:
        summarize(args.root.resolve(), args.runtime.resolve(), args.archive.resolve(), args.receipt)
