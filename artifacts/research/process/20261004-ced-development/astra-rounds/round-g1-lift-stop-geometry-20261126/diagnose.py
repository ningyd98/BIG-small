"""Diagnose four immutable LIFT first stops without rendering or advancing the plant."""

import argparse
import gzip
import itertools
import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import BAND, CAMERA_FIELDS, axial
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, _covers
from scripts.graduation.g1_complete_cv_geometry import Box
from scripts.graduation.g1_complete_cv_handoff import binding_error
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "plan.json"
VIEWS = ("panel-primary", "panel-start")
TOL = 1e-9


def require(condition, error):
    if not condition:
        raise ValueError(error)


def preflight(plan):
    for relative, expected in plan["sha256"].items():
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == expected, f"source pin: {relative}")
    capture = ROOT / plan["capture"]
    seal = read(capture / "seal.json")
    members = seal["sealed_sha256"]
    require(len(members) == 233, "frozen member count changed")
    for relative, expected in members.items():
        path = (capture / relative).resolve()
        require(path.is_relative_to(capture) and sha(path) == expected, f"capture pin: {relative}")
    registration = read(capture / "registration.json")
    prior = HERE.parent / "round-g1-lift-native-full-clearance-20261126"
    calibration = ROOT / plan["calibration"] / "manifest.json"
    cases = [slot["case"] for slot in plan["slots"]]
    require(
        seal["cases"] == cases == [slot["id"] for slot in registration["slots"]]
        and registration["asset_sha256"] == sha(ROOT / plan["asset"])
        and sha(capture / "registration.json") == seal["registration_sha256"]
        and registration["plan_sha256"] == sha(prior / "plan.json")
        and registration["driver_sha256"] == sha(prior / "gate_lift.py")
        and registration["camera"] == read(calibration)["primary_camera"],
        "unbound capture registration, model or camera",
    )
    return capture, registration


def paired_frames(capture, registration, slot):
    folder = capture / slot["case"]
    checks = read(folder / "clearance-gate.json")["checks"]
    index_path = folder / "rgbd-index.json"
    index = read(index_path)
    receipt = read(folder / "sensor-receipt.json")
    previous, stop = checks[-2:]
    require(
        receipt["id"] == slot["case"]
        and receipt["slot"] in registration["slots"]
        and receipt["registration_sha256"] == sha(capture / "registration.json")
        and receipt["index_sha256"] == sha(index_path)
        and receipt["physics_steps"] == stop["step"] == slot["first_stop"]
        and receipt["termination"] == "original_current_clearance_refused"
        and previous["step"] == slot["previous_clear"]
        and previous["status"] == "CLEAR"
        and stop["status"] == slot["status"]
        and stop["reason"] == slot["reason"]
        and stop["current"]["depth"]["unmatched_pixels_uv"] == slot["pixels"]
        and previous["current"]["depth"]["unmatched_pixels_uv"] == [],
        f"first-stop binding: {slot['case']}",
    )
    for gate in (previous, stop):
        require((gate["skill"], gate["phase"]) == ("LIFT", "FEEDBACK"), "not LIFT feedback")
        (row,) = [r for r in index["rows"] if r["robot"]["frame_id"] == gate["frame_id"]]
        robot = row["robot"]
        raw = folder / row["file"]
        require(sha(raw) == row["file_sha256"], "compressed frame differs")
        frame = RGBDObservation.model_validate_json(gzip.decompress(raw.read_bytes()))
        camera = frame.model_dump(include=set(CAMERA_FIELDS), mode="json")
        require(
            camera == registration["camera"]
            and frame.scene_id == receipt["scene_id"] == index["scene_id"]
            and frame.episode_id == receipt["episode_id"] == index["episode_id"]
            and frame.frame_id == gate["frame_id"] == robot["frame_id"]
            and frame.checksum_sha256 == gate["checksum_sha256"] == robot["checksum_sha256"]
            and robot["physics_step"] == gate["step"]
            and robot["sim_time_s"] == robot["camera_encoder_sim_time_s"] == frame.sim_time_s
            and abs(frame.sim_time_s - gate["step"] / 240.0) < TOL
            and receipt["camera_calls"].count({"step": gate["step"], "time_s": frame.sim_time_s})
            == 1
            and robot["native_last_command_seq"] == gate["native_last_command_seq"]
            and binding_error(robot["handoff"], "LIFT", "FEEDBACK", frame) is None
            and robot["handoff"]["current_step"] == gate["step"]
            and robot["handoff"]["last_command_seq"] == gate["native_last_command_seq"],
            f"shutter, calibration or handoff mismatch: {slot['case']}/{gate['step']}",
        )
        yield gate, robot, frame


def view_witness(points, camera, depth, floor_contact):
    covered = _covers(points, camera, depth, floor_contact)
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    local = (points - tf[:3, 3]) @ tf[:3, :3]
    far = int(local[:, 2].argmax())
    result = {
        "covered": covered,
        "axial_range_m": [float(local[:, 2].min()), float(local[far, 2])],
        "far_world_corner_m": points[far].tolist(),
        "floor_contact_m": floor_contact,
    }
    if local[:, 2].min() <= 0:
        return result | {"limitation": "behind_camera"}
    fx, fy, cx, cy = camera["intrinsics"]
    uv = local[:, :2] / local[:, 2, None] * [fx, fy] + [cx, cy]
    lo = np.floor(uv.min(axis=0) - 0.5).astype(int)
    hi = np.ceil(uv.max(axis=0) + 0.5).astype(int)
    result["roi_uv"] = [lo.tolist(), hi.tolist()]
    if (lo < 0).any() or (hi >= depth.shape[::-1]).any():
        return result | {"limitation": "outside_image"}
    roi = depth[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1]
    v, u = np.unravel_index(roi.argmin(), roi.shape)
    near = float(roi[v, u])
    margin = float(roi.min() + floor_contact) - float(local[far, 2])
    require(covered == (margin >= 0.0), "coverage witness disagrees with original predicate")
    return result | {
        "limitation": None if covered else ("no_registered_depth" if near == 0.0 else "depth"),
        "nearest_registered_return_m": near,
        "weakest_pixel_uv": (lo + [u, v]).tolist(),
        "missing_pixels": int(np.count_nonzero(roi == 0)),
        "margin_m": margin,
    }


def volume_views(cert, points, tolerance):
    return {key: view_witness(points, *cert.maps[key], tolerance) for key in VIEWS}


def volume_replay(cert, gate, robot):
    current = gate["current"]
    support = current["source_table_support"]["qualified"]
    require(type(support) is bool, "source support permission is missing")
    visited = {}

    def volume_check(box, pad):
        require(
            box.name not in visited
            and np.array_equal(box.r, np.eye(3))
            and np.array_equal(pad, np.zeros(3)),
            "unexpected original loaded-box callback",
        )
        original = Box(box.name, box.c, box.h + abs(box.r).T @ pad, box.r).corners()
        points = original.copy()
        allow = box.name == "object_geom" and support
        if allow:
            floor = cert.model.table.c[2] + cert.model.table.h[2]
            points[:, 2] = np.maximum(points[:, 2], floor)
        records = volume_views(cert, points, 2 * BAND if allow else 0.0)
        visited[box.name] = {
            "bounds_m": [points.min(0).tolist(), points.max(0).tolist()],
            "uncropped_bounds_m": [original.min(0).tolist(), original.max(0).tolist()],
            "floor_contact_m": 2 * BAND if allow else 0.0,
            "floor_clipped": bool(np.any(points != original)),
            "views": records,
        }
        return any(view["covered"] for view in records.values())

    motion = cert.payload_gate.check(
        "LIFT",
        np.asarray(robot["joint_positions_rad"]),
        np.asarray(robot["finger_positions_m"]),
        np.asarray(robot["joint_velocities_rad_s"]),
        np.asarray(robot["finger_velocities_m_s"]),
        robot["handoff"],
        current["payload_observation"],
        volume_check,
        allow_grasp_station_contact=support,
        native_target=np.asarray(current["commanded_target_xyz_m"]),
    )
    require(
        motion == current["short_motion"], f"original short-motion result differs: {gate['step']}"
    )
    return {
        "step": gate["step"],
        "original_status": gate["status"],
        "original_reason": gate["reason"],
        "checksum_sha256": gate["checksum_sha256"],
        "source_support_qualified": support,
        "observed_relation": current["payload_observation"]["relation"],
        "target_m": current["commanded_target_xyz_m"],
        "short_motion": motion,
        "boxes": visited,
    }


def partition(cert, box, levels):
    low, high = np.asarray(box["bounds_m"])
    require(np.isfinite([low, high]).all() and (low < high).all(), "degenerate parent box")
    count = 2**levels
    cuts = np.linspace(low, high, count + 1)
    require(
        np.array_equal(cuts[0], low)
        and np.array_equal(cuts[-1], high)
        and (np.diff(cuts, axis=0) > 0).all(),
        "partition endpoints or common interfaces differ",
    )
    leaves = []
    for indices in itertools.product(range(count), repeat=3):
        left = np.asarray([cuts[i, axis] for axis, i in enumerate(indices)])
        right = np.asarray([cuts[i + 1, axis] for axis, i in enumerate(indices)])
        points = np.asarray(list(itertools.product(*zip(left, right, strict=True))))
        records = volume_views(cert, points, box["floor_contact_m"])
        leaves.append(
            {
                "cell": list(indices),
                "bounds_m": [left.tolist(), right.tolist()],
                "views": records,
                "covered": any(view["covered"] for view in records.values()),
            }
        )
    return leaves


def complete_partition(leaves, levels):
    cells = set(itertools.product(range(2**levels), repeat=3))
    return (
        len(leaves) == len(cells)
        and {tuple(leaf["cell"]) for leaf in leaves} == cells
        and all(leaf["covered"] for leaf in leaves)
    )


def volume_diagnostic(plan, capture, registration):
    slot = plan["slots"][0]
    allocation = read(capture / slot["case"] / "optical-allocation.json")
    calib = ROOT / plan["calibration"]
    calibration_hash = plan["sha256"][f"{plan['calibration']}/manifest.json"]
    require(
        allocation["case"]["scene_id"] == f"g1.continuous-payload/{slot['case']}"
        and allocation["geometry"]["camera"] == registration["camera"]
        and allocation["calibration_sha256"] == calibration_hash
        and allocation["asset_sha256"] == registration["asset_sha256"],
        "optical allocation differs",
    )
    cert = LocalClearance(
        allocation["geometry"],
        ROOT / plan["asset"],
        calib,
        calibration_sha256=calibration_hash,
        isolated_scene=True,
    )
    previous, stop = [
        volume_replay(cert, gate, robot)
        for gate, robot, _ in paired_frames(capture, registration, slot)
    ]
    require(
        previous["short_motion"]["reason"] is None
        and stop["short_motion"]["limiting_body"] == "object_geom"
        and stop["short_motion"]["minimum_gap_m"] == plan["recorded_first_stop_min_gap_m"],
        "original failure witness changed",
    )
    clear_box = previous["boxes"]["object_geom"]
    denied_box = stop["boxes"]["object_geom"]
    positive = partition(cert, clear_box, 1)
    outside = dict(clear_box, bounds_m=[[10.0, 10.0, 0.1], [10.1, 10.1, 0.2]])
    require(
        complete_partition(positive, 1)
        and not complete_partition(positive[:-1], 1)
        and not any(leaf["covered"] for leaf in partition(cert, outside, 1)),
        "volume positive or negative control failed",
    )
    partitions = []
    for level in range(1, plan["partition_max_levels"] + 1):
        leaves = partition(cert, denied_box, level)
        partitions.append(
            {
                "level": level,
                "covered": complete_partition(leaves, level),
                "leaves": leaves,
            }
        )
    return {
        "case": slot["case"],
        "previous_clear": previous,
        "first_stop": stop,
        "controls": {
            "clear_partition": True,
            "omitted_cell_rejected": True,
            "outside_rejected": True,
        },
        "partitions": partitions,
    }


def read_ray_inputs(plan, capture, registration):
    inputs = []
    for slot in plan["slots"][1:]:
        for gate, robot, frame in paired_frames(capture, registration, slot):
            depth = axial(frame)
            pixels = [{"uv": [u, v], "depth_m": float(depth[v, u])} for u, v in slot["pixels"]]
            require(all(p["depth_m"] > 0 for p in pixels), "missing archived comparison depth")
            inputs.append(
                {
                    "case": slot["case"],
                    "step": gate["step"],
                    "native_time_s": frame.sim_time_s,
                    "original_status": gate["status"],
                    "original_reason": gate["reason"],
                    "original_depth_evidence": gate["current"]["depth"],
                    "per_pixel_reference_residuals": None,
                    "frame_id": frame.frame_id,
                    "checksum_sha256": frame.checksum_sha256,
                    "joint_positions_rad": robot["camera_joint_positions_rad"],
                    "finger_positions_m": robot["camera_finger_positions_m"],
                    "pixels": pixels,
                }
            )
    return {"camera": registration["camera"], "inputs": inputs}


def restore(mj, model, row, label, camera):
    data = mj.MjData(model)
    names = ["joint" + str(i) for i in range(1, 8)] + ["finger_left_joint", "finger_right_joint"]
    addresses = [model.joint(name).qposadr[0] for name in names]
    addr = model.joint("object_free").qposadr[0]
    require(
        model.njnt == 10
        and model.nq == 16
        and set(addresses + list(range(addr, addr + 7))) == set(range(model.nq)),
        "unrecorded position coordinate",
    )
    values = np.array(row["joint_positions_rad"] + row["finger_positions_m"])
    require(values.shape == (9,) and np.isfinite(values).all(), "invalid exposure encoders")
    data.qpos[addresses] = values
    center = np.asarray(label["center_m"])
    rotation = np.asarray(label["rotation"])
    geom = model.geom("object_geom")
    require(
        np.array_equal(geom.pos, [0, 0, 0])
        and np.array_equal(geom.quat, [1, 0, 0, 0])
        and int(geom.bodyid[0]) == int(model.joint("object_free").bodyid[0])
        and np.isfinite(center).all()
        and np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=TOL)
        and abs(np.linalg.det(rotation) - 1.0) < TOL,
        "unbound body-to-geometry transform",
    )
    data.qpos[addr : addr + 3] = center
    mj.mju_mat2Quat(data.qpos[addr + 3 : addr + 7], np.ascontiguousarray(rotation).ravel())
    data.time = row["native_time_s"]
    before = data.qpos.copy()
    mj.mj_forward(model, data)
    optical = data.camera("rgbd").xmat.reshape(3, 3) * [1, -1, -1]
    tf = np.eye(4)
    tf[:3, 3] = data.camera("rgbd").xpos
    tf[:3, :3] = optical
    focal = (camera["height"] / 2) / math.tan(math.radians(model.camera("rgbd").fovy[0]) / 2)
    intrinsics = [focal, focal, (camera["width"] - 1) / 2, (camera["height"] - 1) / 2]
    require(
        np.max(abs(tf.ravel() - camera["camera_to_world"])) < TOL
        and np.max(abs(np.asarray(intrinsics) - camera["intrinsics"])) < TOL
        and np.linalg.norm(data.geom("object_geom").xpos - center) < TOL
        and np.linalg.norm(data.geom("object_geom").xmat.reshape(3, 3) - rotation) < TOL
        and np.array_equal(before, data.qpos)
        and data.time == row["native_time_s"],
        "static camera, pose or clock did not close",
    )
    return data, tf


def hit(mj, model, data, eye, direction, optical_z, groups):
    distance_vector = direction / np.linalg.norm(direction)
    geom = np.asarray([-1], dtype=np.int32)
    distance = mj.mj_ray(model, data, eye, distance_vector, groups, 1, -1, geom)
    if distance < 0:
        require(geom[0] == -1, "invalid no-hit witness")
        return {"geom": None, "distance_m": None, "axial_depth_m": None}
    return {
        "geom": model.geom(int(geom[0])).name,
        "distance_m": distance,
        "axial_depth_m": float(distance * (distance_vector @ optical_z)),
    }


def ray_diagnostic(mj, plan, capture, registration, sealed):
    optical_fields = {"camera": sealed["camera"], "inputs": sealed["inputs"]}
    require(
        optical_fields == read_ray_inputs(plan, capture, registration)
        and sealed["source_seal_sha256"] == sha(capture / "seal.json")
        and sealed["plan_sha256"] == sha(PLAN_FILE)
        and sealed["run_scope"] == plan["run_scope"],
        "sealed ray input differs",
    )
    inputs = sealed["inputs"]
    model = mj.MjModel.from_xml_path(str(ROOT / plan["asset"]))
    require(model.ncam == 1, "ambiguous original camera")
    groups = mj.MjvOption().geomgroup.copy()
    camera = registration["camera"]
    fx, fy, cx, cy = camera["intrinsics"]
    count = 0
    for row in inputs:
        labels = read(capture / row["case"] / "offline-physics.json")["frame_labels"]
        (label,) = [label for label in labels if label["frame_id"] == row["frame_id"]]
        require(
            label["checksum_sha256"] == row["checksum_sha256"]
            and label["physics_step"] == row["step"],
            "offline label differs from exposure",
        )
        data, tf = restore(mj, model, row, label, camera)
        eye, optical_z = tf[:3, 3].copy(), tf[:3, 2].copy()
        if count == 0:
            table = model.geom("table")
            point = np.array([0.48, -0.3, table.pos[2] + table.size[2]])
            down = hit(mj, model, data, eye, point - eye, optical_z, groups)
            up = hit(mj, model, data, eye, eye - point, optical_z, groups)
            require(
                down["geom"] == "table"
                and abs(down["axial_depth_m"] - ((point - eye) @ optical_z)) < TOL
                and up["geom"] is None,
                "analytic hit or no-hit control failed",
            )
        before = data.qpos.copy()
        for pixel in row["pixels"]:
            u, v = pixel["uv"]
            offsets = plan["aperture_offsets_px"]
            samples = []
            for du, dv in itertools.product(offsets, repeat=2):
                direction = tf[:3, :3] @ [(u + du - cx) / fx, (v + dv - cy) / fy, 1.0]
                sample = hit(mj, model, data, eye, direction, optical_z, groups)
                z = sample["axial_depth_m"]
                samples.append(
                    sample
                    | {
                        "offset_px": [du, dv],
                        "measured_minus_axial_m": None if z is None else pixel["depth_m"] - z,
                    }
                )
            count += len(samples)
            pixel["rays"] = samples
        require(
            np.array_equal(before, data.qpos) and data.time == row["native_time_s"],
            "ray mutated pose",
        )
    require(
        count == plan["maximum_diagnostic_rays"] == 72 and len(inputs) == 6, "ray budget differs"
    )
    return {
        "frames": inputs,
        "diagnostic_rays": count,
        "control_rays": 2,
        "geom_groups": groups.tolist(),
        "ray_visible_geoms_only": True,
        "static_table_hit": True,
        "reverse_ray_empty": True,
        "depth_agreement_gate": None,
        "mujoco": mj.__version__,
    }


def prohibited(*_args, **_kwargs):
    raise RuntimeError("rendering or integration forbidden in archived-readback process")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("volume", "ray-input", "rays"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--ray-input", type=Path)
    args = parser.parse_args()
    plan = read(PLAN_FILE)
    capture, registration = preflight(plan)
    import mujoco

    with patch.multiple(
        mujoco,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
        Renderer=prohibited,
        mjr_render=prohibited,
    ):
        if args.part == "volume":
            result = volume_diagnostic(plan, capture, registration)
        elif args.part == "ray-input":
            result = read_ray_inputs(plan, capture, registration)
        else:
            require(args.ray_input is not None, "sealed optical inputs required")
            sealed = read(args.ray_input)
            result = ray_diagnostic(mujoco, plan, capture, registration, sealed)
            result["ray_input_sha256"] = sha(args.ray_input)
    result["source_seal_sha256"] = sha(capture / "seal.json")
    result["plan_sha256"] = sha(PLAN_FILE)
    result["run_scope"] = plan["run_scope"]
    write(args.output, result)


if __name__ == "__main__":
    main()
