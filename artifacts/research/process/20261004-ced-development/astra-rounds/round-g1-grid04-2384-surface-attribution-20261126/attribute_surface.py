"""Attribute two sealed grid-04 pixels with original gates and zero live physics."""

import argparse
import base64
import fcntl
import gzip
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree

import cv2
import mujoco
import numpy as np
from scripts.graduation import g1_complete_cv_clearance as local
from scripts.graduation.g1_complete_cv_calibrate import BAND, axial
from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface, compare_face_patch
from scripts.graduation.g1_complete_cv_handoff_optics import directional_error, rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_cv_payload import object_matrix
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = ROOT / PLAN["raw"]
OUT = ROOT / PLAN["output"]
CAL = ROOT / "experiments/results/g1-complete-cv-repair-20261125/calibration-gpu-01"
UV = np.asarray(PLAN["pixels"], dtype=int)
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def require(value, reason):
    if not value:
        raise ValueError(reason)


def deny(*args, **kwargs):
    raise RuntimeError("offline attribution attempted physics or a native exposure")


def pin(files):
    for path, expected in files.items():
        require(sha(ROOT / path) == expected, f"changed sealed source: {path}")


def load():
    pin(PLAN["blind_inputs_sha256"])
    allocation_path = RAW / "optical-registration.json"
    reg = read(allocation_path)
    geo = reg["geometry"]
    original = read(RAW / "rgbd-index.json")
    identity = bind_allocation(
        allocation_path.read_bytes(),
        allocation_sha256=sha(allocation_path),
        generation_sha256=reg["runtime_build_sha256"],
        calibration_sha256=reg["calibration_sha256"],
        asset_sha256=reg["asset_sha256"],
        reset_scene_id=original["scene_id"],
        reset_episode_id=original["episode_id"],
    )
    asset = ROOT / PLAN["runtime"] / geo["asset_path"]
    model = local.LocalClearance(
        geo,
        asset,
        CAL,
        calibration_sha256=reg["calibration_sha256"],
        isolated_scene=True,
        optical_identity=identity,
    )
    source = (
        ROOT
        / "experiments/results/g1-complete-cv-repair-20261125/builds"
        / reg["runtime_build_sha256"]
        / "runtime-source"
    )
    manifest = read(source / "runtime-build.json")
    marker_path = "scripts/graduation/g1_visibility_vision.py"
    require(
        sha(source / "runtime-build.json") == reg["runtime_build_sha256"]
        and sha(source / marker_path) == manifest["runtime_files_sha256"][marker_path],
        "marker generation differs",
    )
    spec = importlib.util.spec_from_file_location("bound_marker", source / marker_path)
    marker_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(marker_module)
    observed_gate = {
        r["step"]: r
        for r in read(RAW / "clearance-gate.json")["checks"]
        if r["phase"] == "FEEDBACK"
    }
    rows = {}
    for label, name in PLAN["frames"].items():
        (item,) = [r for r in original["rows"] if r["file"] == name]
        robot = item["robot"]
        at = int(label)
        with gzip.open(RAW / name, "rb") as stream:
            frame = RGBDObservation.model_validate_json(stream.read())
        require(
            item["skill"] == "LIFT"
            and item["phase"] == "FEEDBACK"
            and robot["research_role"] == "motion"
            and robot["physics_step"] == at
            and robot["frame_id"] == frame.frame_id
            and frame.checksum_sha256
            == robot["checksum_sha256"]
            == observed_gate[at]["checksum_sha256"]
            and frame.sim_time_s == robot["camera_encoder_sim_time_s"] == robot["sim_time_s"]
            and robot["native_last_command_seq"] == observed_gate[at]["native_last_command_seq"],
            "closed shutter binding differed",
        )
        require(
            frame.model_dump(mode="json", include=set(geo["camera"])) == geo["camera"],
            "changed camera",
        )
        marker = marker_module.measure_frame(frame, geo)
        require(identity.matches(frame, marker, geo, at), "frozen marker identity differs")
        pose = rigid_pose(frame, marker, geo, identity=identity, physics_step=at)
        require(
            pose == observed_gate[at]["current"]["payload_observation"]["pose"],
            "recovered optical pose differs",
        )
        rgb = cv2.imdecode(
            np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR
        )
        require(rgb is not None, "missing original RGB")
        rows[at] = SimpleNamespace(
            frame=frame,
            rgb=rgb[:, :, ::-1].copy(),
            depth=axial(frame),
            robot=robot,
            pose=pose,
            marker=marker,
            recorded=observed_gate[at],
        )
    return model, asset, rows


def crop(values, u, v):
    return values[v - 1 : v + 2, u - 1 : u + 2]


def initial(model, rows):
    result = {}
    for at, r in rows.items():
        near, lost = local.depth_changes(r.depth, model.reference, BAND)
        require(
            int(near.sum()) == r.recorded["current"]["depth"]["nearer_returns"],
            "original near count differs",
        )
        require(
            int(lost.sum()) == r.recorded["current"]["depth"]["lost_or_farther_static"],
            "original far count differs",
        )
        result[at] = {
            "recorded_optical_method": r.pose["method"],
            "synchronized_frame_checksum": r.frame.checksum_sha256,
            "stationary_near_count": int(near.sum()),
            "stationary_far_count": int(lost.sum()),
            "original_robot_command_seq": r.robot["native_last_command_seq"],
            "pixels": [
                {
                    "uv": [int(u), int(v)],
                    "near_mask": crop(near, u, v).tolist(),
                    "depth_m": crop(r.depth, u, v).tolist(),
                    "valid": (crop(r.depth, u, v) > 0).tolist(),
                    "empty_depth_m": crop(model.reference, u, v).tolist(),
                    "rgb": crop(r.rgb, u, v).tolist(),
                }
                for u, v in UV
            ],
        }
    early, late = rows.values()
    require(
        early.robot["camera_encoder_sim_time_s"] != late.frame.sim_time_s
        and early.frame.checksum_sha256 != late.robot["checksum_sha256"],
        "cross-exposure negative failed",
    )
    mask = np.ones((3, 3), bool)
    reference = np.ones((3, 3))
    color = np.broadcast_to([0, 20, 100], (3, 3, 3))
    require(compare_face_patch(reference, reference, color, color, mask), "positive carried patch")
    require(
        not compare_face_patch(reference, reference, color[..., ::-1], color, mask),
        "RGB swap negative",
    )
    wrong = reference.copy()
    wrong[0] += 0.005
    require(
        not compare_face_patch(wrong, reference, color, color, mask), "wrong-row depth negative"
    )
    return result


def project(model, asset, rows):
    exact = [OUT / f"blind-reader-{i}.json" for i in (1, 2)]
    require(sha(exact[0]) == sha(exact[1]), "blind CPU readers disagree")
    require(
        all(
            x.recorded["current"]["depth"]["robot_raster_surface_pixels"] > 0 for x in rows.values()
        ),
        "no reference evidence gap",
    )
    from OpenGL import GL

    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        dest = OUT / "reference-projections"
        dest.mkdir(exist_ok=False)
        robot = local.RobotDepthReference(asset, 320, 240)
        carried = CarriedSurface(asset)
        files = {}
        try:
            gl = {
                k: GL.glGetString(v).decode()
                for k, v in (
                    ("version", GL.GL_VERSION),
                    ("vendor", GL.GL_VENDOR),
                    ("renderer", GL.GL_RENDERER),
                )
            }
            require(gl == read(CAL / "manifest.json")["renderer"], "reference EGL renderer differs")
            for at, r in rows.items():
                q, fingers = (
                    r.robot["camera_joint_positions_rad"],
                    r.robot["camera_finger_positions_m"],
                )
                arm = robot.project(q, fingers).copy()
                rgb, depth = carried.project(r.pose["center_m"], r.pose["rotation"], q, fingers)
                file = dest / f"{at}.npz"
                with file.open("xb") as output:
                    np.savez_compressed(output, robot=arm, carried_rgb=rgb, carried_depth=depth)
                files[file.name] = sha(file)
            write(
                dest / "seal.json",
                {
                    "members_sha256": files,
                    "graphics": gl,
                    "blind_reader_sha256": sha(exact[0]),
                    "robot_reference_projections": 2,
                    "carried_reference_projections": 2,
                    "native_exposures": 0,
                    "integrations": 0,
                },
            )
        finally:
            carried.close()
            robot.close()


class RasterBuffer:
    def __init__(self, array):
        self.array = array

    def project(self, joints, fingers):
        return self.array


class Unresolved:
    def __init__(self):
        self.uv = set()

    def explain(self, frame, pose, joints, fingers, pixels):
        self.uv = set(map(tuple, pixels))
        return np.zeros(len(pixels), dtype=bool), {"unexplained": len(pixels)}


def changed(model, row, robot, carried):
    r = row.robot
    q, f = np.array(r["joint_positions_rad"]), r["finger_positions_m"]
    tcp, rot, links = model.model.forward(q)
    center = local._xyz(row.marker["object_center_world_m"])
    rotation = np.asarray(row.marker["rotation_object_to_world"], dtype=float).reshape(3, 3)
    boxes = [b.placed(center, rotation) for b in model.model.object]
    model.robot_raster, model.carried_surface = robot, carried
    return model.changed_surfaces(
        row.frame,
        boxes,
        model.model.hand_at(tcp, rot, f),
        tcp,
        links,
        r["camera_joint_positions_rad"],
        r["camera_finger_positions_m"],
        payload_pose=row.pose,
    )


def first_faces(model, row, u, v):
    frame, pose = row.frame, row.pose
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = frame.intrinsics
    offsets = np.array([(x, y) for y in (-1, 0, 1) for x in (-1, 0, 1)])
    pixels = np.array([u, v]) + offsets
    ray = (
        np.column_stack(((pixels[:, 0] - cx) / fx, (pixels[:, 1] - cy) / fy, np.ones(9)))
        @ tf[:3, :3].T
    )
    rot = np.asarray(pose["rotation"])
    ray = ray @ rot
    eye = (tf[:3, 3] - pose["center_m"]) @ rot
    first = np.full(9, np.inf)
    face_names = [None] * 9
    for box in model.model.object:
        with np.errstate(divide="ignore", invalid="ignore"):
            a = (box.c - box.h - eye) / ray
            b = (box.c + box.h - eye) / ray
        start = np.minimum(a, b)
        axes = start.argmax(axis=1)
        at = start.max(axis=1)
        hit = (np.maximum(a, b).min(axis=1) >= at) & (at > 0) & (at < first)
        first[hit] = at[hit]
        for j in np.flatnonzero(hit):
            local_pt = eye + at[j] * ray[j]
            axis = int(axes[j])
            normal_margin = abs(ray[j, axis])
            lateral_spare = [
                box.h[k]
                - abs(local_pt[k] - box.c[k])
                - directional_error(pose, local_pt[None], rot[:, k])[0]
                for k in range(3)
                if k != axis
            ]
            face_names[j] = {
                "body": box.name,
                "face_axis": axis,
                "first_axial_m": float(at[j]),
                "ray_abs_normal": float(normal_margin),
                "min_interior_spare_m": float(min(lateral_spare)),
            }
    return face_names


def adjudicate(model, rows):
    home = OUT / "reference-projections"
    seal = read(home / "seal.json")
    require(
        sha(OUT / "blind-reader-1.json") == seal["blind_reader_sha256"],
        "projections context changed",
    )
    output = {}
    for at, r in rows.items():
        p = home / f"{at}.npz"
        require(sha(p) == seal["members_sha256"][p.name], "reference framebuffer drift")
        with np.load(p, allow_pickle=False) as arr:
            robot, rgb, dep = (arr[k] for k in ("robot", "carried_rgb", "carried_depth"))
        geometric = Unresolved()
        changed(model, r, RasterBuffer(np.zeros_like(robot)), geometric)
        after_robot = Unresolved()
        changed(model, r, RasterBuffer(robot), after_robot)
        carried = CarriedSurface.__new__(CarriedSurface)
        carried.width, carried.height, carried.boxes = 320, 240, model.model.object
        carried.project = lambda *args, color=rgb, depths=dep: (color, depths)
        current = changed(model, r, RasterBuffer(robot), carried)
        require(
            current == r.recorded["current"]["depth"], f"frozen original outcome changed at {at}"
        )
        cooked = []
        near, _ = local.depth_changes(r.depth, model.reference, BAND)
        for u, v in UV:
            raw, rd = crop(r.depth, u, v), crop(dep, u, v)
            actual_rgb, ref_rgb = crop(r.rgb, u, v), crop(rgb, u, v)
            interior = carried._first_interior_face((u, v), r.frame, r.pose, rd)
            depth_error = abs(raw - rd)
            rgb_error = abs(actual_rgb.astype(int) - ref_rgb.astype(int))
            result = compare_face_patch(raw, rd, actual_rgb, ref_rgb, interior)
            cooked.append(
                {
                    "uv": [int(u), int(v)],
                    "foreground": bool(near[v, u]),
                    "still_unattributed_after_geometry": (u, v) in geometric.uv,
                    "still_unattributed_after_robot_reference": (u, v) in after_robot.uv,
                    "robot_predicted_axial_m": float(robot[v, u]),
                    "observed_axial_m": float(r.depth[v, u]),
                    "per_ray_first_optical_box_face": first_faces(model, r, u, v),
                    "first_face_inside_mask": interior.tolist(),
                    "carried_depth_range_m": float(np.ptp(rd)),
                    "carried_depth_residual_m": depth_error.tolist(),
                    "carried_rgb_residual_levels": rgb_error.tolist(),
                    "all_depth_residuals_less_than_4mm": bool((depth_error < BAND).all()),
                    "reference_depth_range_less_than_4mm": bool(np.ptp(rd) < BAND),
                    "all_colour_residuals_at_most_6_levels": bool(rgb_error.max() <= 6),
                    "would_explain_by_carried_predicate": result,
                    "actually_sent_to_carried_comparison": (u, v) in after_robot.uv,
                }
            )
        output[at] = {
            "original_status": r.recorded["current"]["status"],
            "replayed_original_surface_counts": current,
            "pixels": cooked,
        }
    return {"cases": output, "reference_seal_sha256": sha(home / "seal.json")}


def compare_truth(asset, rows):
    blind = [OUT / f"surface-reader-{i}.json" for i in (1, 2)]
    require(sha(blind[0]) == sha(blind[1]), "unblinded before final surface result")
    sources = PLAN["truth_after_optical_seal_sha256"]
    pin(sources)
    data = {r["frame_id"]: r for r in read(RAW / "offline-physics.json")["frame_labels"]}
    mech_path = next(s for s in sources if s.endswith("native/normal.json"))
    mechanical = {r["tick"]: r for r in read(ROOT / mech_path)}
    evidence = {}
    for at, item in rows.items():
        p = data[item.frame.frame_id]
        m = mechanical[at]
        require(
            p["physics_step"] == at and p["checksum_sha256"] == item.frame.checksum_sha256,
            "truth identity differs",
        )
        robot = item.robot
        enc = np.array(robot["camera_joint_positions_rad"] + robot["camera_finger_positions_m"])
        current = np.array(robot["joint_positions_rad"] + robot["finger_positions_m"])
        q = np.array(m["q"])
        require(
            np.array_equal(current, q[:9]) and m["cube"] == p["center_m"],
            "mechanical state linkage failed",
        )
        evidence[at] = {
            "original_phase_sha256": m["phase_sha256"],
            "exact_final_robot_position_match": True,
            "maximum_exposure_minus_final_joint_rad": float(abs(enc[:7] - current[:7]).max()),
            "maximum_exposure_minus_final_finger_m": float(abs(enc[7:] - current[7:]).max()),
            "workpiece_exposure_minus_final_center_m": (
                np.asarray(p["center_m"]) - q[9:12]
            ).tolist(),
            "workpiece_exposure_minus_final_rotation_norm": float(
                np.linalg.norm(np.asarray(p["rotation"]) - object_matrix(q[None])[0])
            ),
            "optical_minus_label_workpiece_center_m": (
                np.asarray(item.pose["center_m"]) - p["center_m"]
            ).tolist(),
            "contact_pairs": p["touching"],
            "native_all_entity_exposure_transforms_present": False,
        }
    names = [e.get("name") for e in ElementTree.parse(asset).iter("geom") if e.get("name")]
    return {
        "pixel_report_sha256": sha(blind[0]),
        "state_links": evidence,
        "geometries": names,
        "registry_lists_all_named_roles": True,
        "native_physics_or_exposure": 0,
        "pixel_attribution_is_not_an_online_clearance": True,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("blind", "project", "surface", "truth"))
    cli.add_argument("reader", nargs="?", choices=("reader-1", "reader-2"))
    args = cli.parse_args()
    cv2.setNumThreads(1)
    OUT.mkdir(exist_ok=True)
    with (
        patch.multiple(mujoco, mj_step=deny, mj_step1=deny, mj_step2=deny),
        patch.multiple(MuJoCoRGBDCamera, capture=deny, _capture=deny),
        patch.object(MuJoCoPhysicsBackend, "capture_sensor_frame", deny),
    ):
        model, asset, rows = load()
        if args.mode == "project":
            project(model, asset, rows)
        else:
            with patch.multiple(mujoco, Renderer=deny, mjr_render=deny):
                value = {
                    "blind": lambda: initial(model, rows),
                    "surface": lambda: adjudicate(model, rows),
                    "truth": lambda: compare_truth(asset, rows),
                }[args.mode]()
            write(OUT / f"{args.mode}-{args.reader}.json", value)
