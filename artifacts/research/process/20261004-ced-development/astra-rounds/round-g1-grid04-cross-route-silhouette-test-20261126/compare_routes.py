"""Compare two already recorded grid-04 rejections under the same frozen predicates."""

import argparse
import base64
import fcntl
import gzip
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_carried_surface import compare_face_patch
from scripts.graduation.perception_io import read, sha, write

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
sys.path.insert(0, str(ROOT / PLAN["previous"]))
import attribute_surface as prior  # noqa: E402

LOCK = prior.LOCK
require = prior.require


def load():
    prior.pin(PLAN["source_sha256"])
    data = {}
    for name, entry in PLAN["slots"].items():
        raw = ROOT / entry["path"] / "g1-lift-grid-04"
        registration = raw / entry["allocation"]
        alloc = read(registration)
        geo = alloc["geometry"]
        asset = ROOT / prior.PLAN["runtime"] / geo["asset_path"]
        index = read(raw / "rgbd-index.json")
        events = {
            x["step"]: x
            for x in read(raw / "clearance-gate.json")["checks"]
            if x["phase"] == "FEEDBACK"
        }
        key = prior.bind_allocation(
            registration.read_bytes(),
            allocation_sha256=sha(registration),
            generation_sha256=alloc["runtime_build_sha256"],
            calibration_sha256=alloc["calibration_sha256"],
            asset_sha256=alloc["asset_sha256"],
            reset_scene_id=index["scene_id"],
            reset_episode_id=index["episode_id"],
        )
        model = prior.local.LocalClearance(
            geo,
            asset,
            prior.CAL,
            calibration_sha256=alloc["calibration_sha256"],
            optical_identity=key,
            isolated_scene=True,
        )
        detector_root = (
            prior.ROOT
            / "experiments/results/g1-complete-cv-repair-20261125/builds"
            / alloc["runtime_build_sha256"]
            / "runtime-source"
        )
        manifest = read(detector_root / "runtime-build.json")
        rel = "scripts/graduation/g1_visibility_vision.py"
        require(
            sha(detector_root / "runtime-build.json") == alloc["runtime_build_sha256"]
            and sha(detector_root / rel) == manifest["runtime_files_sha256"][rel],
            "wrong optical detector",
        )
        spec = prior.importlib.util.spec_from_file_location("marker", detector_root / rel)
        detector = prior.importlib.util.module_from_spec(spec)
        spec.loader.exec_module(detector)
        rows = {}
        for tick, filename in entry["frames"].items():
            at = int(tick)
            (item,) = [x for x in index["rows"] if x["file"] == filename]
            gate = events[at]
            robot = item["robot"]
            with gzip.open(raw / filename, "rb") as file:
                image = prior.RGBDObservation.model_validate_json(file.read())
            require(
                robot["physics_step"] == gate["step"] == at
                and robot["frame_id"] == gate["frame_id"] == image.frame_id
                and robot["checksum_sha256"] == gate["checksum_sha256"] == image.checksum_sha256
                and robot["sim_time_s"] == robot["camera_encoder_sim_time_s"] == image.sim_time_s
                and robot["native_last_command_seq"] == gate["native_last_command_seq"]
                and item["phase"] == "FEEDBACK"
                and item["skill"] == "LIFT"
                and image.model_dump(mode="json", include=set(geo["camera"])) == geo["camera"],
                "different stage or exposure",
            )
            marker = detector.measure_frame(image, geo)
            require(key.matches(image, marker, geo, at), "old RGB-D failed identity")
            pose = prior.rigid_pose(image, marker, geo, identity=key, physics_step=at)
            require(
                pose == gate["current"]["payload_observation"]["pose"],
                "registered optical pose differs",
            )
            rgb = cv2.imdecode(
                np.frombuffer(base64.b64decode(image.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR
            )
            require(rgb is not None, "source RGB was absent")
            rows[at] = SimpleNamespace(
                frame=image,
                pose=pose,
                marker=marker,
                depth=prior.axial(image),
                rgb=rgb[:, :, ::-1],
                robot=robot,
                recorded=gate,
            )
        data[name] = model, asset, rows
    return data


def blind(data):
    result = {}
    for route, (model, _, rows) in data.items():
        for at, row in rows.items():
            near, lost = prior.local.depth_changes(row.depth, model.reference, prior.BAND)
            require(
                int(near.sum()) == row.recorded["current"]["depth"]["nearer_returns"],
                "near count differs",
            )
            missing = prior.Unresolved()
            prior.changed(model, row, prior.RasterBuffer(np.zeros_like(row.depth)), missing)
            result[at] = {
                "route": route,
                "frame_checksum": row.frame.checksum_sha256,
                "original_status": row.recorded["current"]["status"],
                "original_unknown": row.recorded["current"]["depth"]["unmatched_pixels_uv"],
                "near_count": int(near.sum()),
                "far_count": int(lost.sum()),
                "original_carried": row.recorded["current"]["depth"]["carried_surface_evidence"],
                "geometry": [
                    {
                        "uv": [u, v],
                        "observed_axial_m": prior.crop(row.depth, u, v).tolist(),
                        "observed_rgb": prior.crop(row.rgb, u, v).tolist(),
                        "unresolved": (u, v) in missing.uv,
                        "near": bool(near[v, u]),
                    }
                    for u, v in PLAN["pixels"]
                ],
                "capture_to_gate_ms": (
                    row.recorded["gate_finish_ns"] - row.recorded["capture_begin_ns"]
                )
                / 1e6,
            }
    return result


def project(data):
    model, asset, rows = data["original"]
    first = OUT / "blind-reader-1.json"
    require(sha(first) == sha(OUT / "blind-reader-2.json"), "blind readers disagree")
    row = rows[2112]
    require(
        row.recorded["current"]["depth"]["carried_surface_evidence"]["checked"] == 2,
        "wrong new reference",
    )
    from OpenGL import GL

    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        dest = OUT / "old-reference"
        dest.mkdir(exist_ok=False)
        robot = prior.local.RobotDepthReference(asset, 320, 240)
        carried = prior.CarriedSurface(asset)
        try:
            env = {
                k: GL.glGetString(v).decode()
                for k, v in (
                    ("version", GL.GL_VERSION),
                    ("vendor", GL.GL_VENDOR),
                    ("renderer", GL.GL_RENDERER),
                )
            }
            require(env == read(prior.CAL / "manifest.json")["renderer"], "changed registered GPU")
            q = row.robot["camera_joint_positions_rad"]
            f = row.robot["camera_finger_positions_m"]
            r = robot.project(q, f).copy()
            rgb, depth = carried.project(row.pose["center_m"], row.pose["rotation"], q, f)
            with (dest / "2112.npz").open("xb") as file:
                np.savez_compressed(file, robot=r, carried_rgb=rgb, carried_depth=depth)
            write(
                dest / "seal.json",
                {
                    "ref_sha256": sha(dest / "2112.npz"),
                    "blind_sha256": sha(first),
                    "robot_reference_projections": 1,
                    "carried_reference_projections": 1,
                    "native_exposures": 0,
                    "integrations": 0,
                    "graphics": env,
                },
            )
        finally:
            carried.close()
            robot.close()


def replay(data):
    old = OUT / "old-reference/2112.npz"
    proof = read(old.with_name("seal.json"))
    require(
        proof["blind_sha256"] == sha(OUT / "blind-reader-1.json")
        and proof["ref_sha256"] == sha(old),
        "new reference seal differs",
    )
    roots = {
        "original": (2112, old),
        "midcourse": (2384, ROOT / PLAN["previous_private"] / "reference-projections/2384.npz"),
    }
    result = {}
    for route, (at, path) in roots.items():
        model, _, rows = data[route]
        row = rows[at]
        with np.load(path, allow_pickle=False) as file:
            arm, rgb, depth = (file[key] for key in ("robot", "carried_rgb", "carried_depth"))
        carried = prior.CarriedSurface.__new__(prior.CarriedSurface)
        carried.width, carried.height, carried.boxes = 320, 240, model.model.object
        carried.project = lambda *args, color=rgb, z=depth: (color, z)
        summary = prior.changed(model, row, prior.RasterBuffer(arm), carried)
        require(
            summary == row.recorded["current"]["depth"], f"original surface branch diverged at {at}"
        )
        samples = []
        for u, v in summary["unmatched_pixels_uv"]:
            opt = prior.crop(row.depth, u, v)
            ref = prior.crop(depth, u, v)
            color = prior.crop(row.rgb, u, v)
            expected = prior.crop(rgb, u, v)
            interior = carried._first_interior_face((u, v), row.frame, row.pose, ref)
            faces = prior.first_faces(model, row, u, v)
            samples.append(
                {
                    "uv": [u, v],
                    "center": faces[4],
                    "face_ids": [x["body"] if x else None for x in faces],
                    "all_on_interior": bool(interior.all()),
                    "reference_depth_range_m": float(np.ptp(ref)),
                    "center_axial_residual_m": float(abs(opt - ref)[1, 1]),
                    "max_axial_residual_m": float(abs(opt - ref).max()),
                    "max_rgb_residual": int(abs(color.astype(int) - expected.astype(int)).max()),
                    "passes": compare_face_patch(opt, ref, color, expected, interior),
                }
            )
        result[route] = {"tick": at, "reproduced": summary, "pixels": samples}
    return result


def truth(data):
    a, b = (OUT / f"surface-reader-{i}.json" for i in (1, 2))
    require(sha(a) == sha(b), "truth opened before blind agreement")
    prior.pin(PLAN["truth_sha256"])
    result = {}
    for route, (_, _, rows) in data.items():
        p = ROOT / PLAN["slots"][route]["path"] / "g1-lift-grid-04/offline-physics.json"
        labels = {x["frame_id"]: x for x in read(p)["frame_labels"]}
        for at, row in rows.items():
            source = labels[row.frame.frame_id]
            require(
                source["physics_step"] == at
                and source["checksum_sha256"] == row.frame.checksum_sha256,
                "source labels misbound",
            )
            result[at] = {
                "route": route,
                "workpiece_center_m": source["center_m"],
                "workpiece_rotation": source["rotation"],
                "tcp_z_m": row.robot["tcp_position_m"][2],
                "contacts": source["touching"],
            }
    return {"pixels_sha256": sha(a), "states": result}


if __name__ == "__main__":
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("mode", choices=("blind", "project", "surface", "truth"))
    arg.add_argument("reader", nargs="?", choices=("reader-1", "reader-2"))
    args = arg.parse_args()
    OUT.mkdir(exist_ok=True)
    cv2.setNumThreads(1)
    with (
        patch.multiple(mujoco, mj_step=prior.deny, mj_step1=prior.deny, mj_step2=prior.deny),
        patch.multiple(prior.MuJoCoRGBDCamera, capture=prior.deny, _capture=prior.deny),
        patch.object(prior.MuJoCoPhysicsBackend, "capture_sensor_frame", prior.deny),
    ):
        data = load()
        if args.mode == "project":
            project(data)
        else:
            with patch.multiple(mujoco, Renderer=prior.deny, mjr_render=prior.deny):
                result = {"blind": blind, "surface": replay, "truth": truth}[args.mode](data)
            write(OUT / f"{args.mode}-{args.reader}.json", result)
