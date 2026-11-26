"""Cold-check necessary source-envelope expansions on original admitted frames."""

import argparse
import gzip
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import BAND
from scripts.graduation.g1_complete_cv_clearance import _covers
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import PayloadClearance
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
ROOTS = {k: REPO / v for k, v in PLAN["roots"].items()}
PANDA = "assets/robots/franka_panda/" + (
    "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
)
VIEWS = ("panel-primary", "panel-start")


def require(valid, error):
    if not valid:
        raise ValueError(error)


def deny(*args, **kwargs):
    raise AssertionError("source-envelope precheck cannot render or integrate")


def input_path(key):
    root, rel = key.split("/", 1)
    base = ROOTS[root].resolve()
    path = (base / rel).resolve()
    require(path.is_relative_to(base) and base.is_relative_to(REPO), "foreign path")
    return path


def source(key):
    path = input_path(key)
    require(sha(path) == PLAN["sha256"][key], f"wrong input: {key}")
    return path


def verify():
    require(ROOT == ROOTS["runtime"].resolve(), "wrong frozen runtime")
    for key in PLAN["sha256"]:
        source(key)
    for path, h in read(source("runtime/runtime-build.json"))["runtime_files_sha256"].items():
        require(sha(input_path(f"runtime/{path}")) == h, f"wrong running dependency: {path}")


def decode(path):
    raw = path.read_bytes()
    return RGBDObservation.model_validate_json(
        gzip.decompress(raw) if path.suffix == ".gz" else raw
    )


def bind_grid(case, tick):
    r = read(source(f"{case}/sensor-receipt.json"))
    index = pinned(source(f"{case}/rgbd-index.json"), r["index_sha256"])
    require(index["episode_id"] == r["episode_id"], "foreign grid episode")
    seal = read(source("grid/seal.json"))
    require(r["registration_sha256"] == seal["registration_sha256"], "foreign grid registration")
    (exposure,) = [
        x
        for x in index["rows"]
        if x["phase"] == "FEEDBACK" and x["skill"] == "LIFT" and x["robot"]["physics_step"] == tick
    ]
    f = decode(source(f"{case}/{exposure['file']}"))
    robot = exposure["robot"]
    require(
        sha(input_path(f"{case}/{exposure['file']}"))
        == exposure["file_sha256"]
        == seal["sealed_sha256"][f"g1-lift-grid-04/{exposure['file']}"]
        and f.episode_id == index["episode_id"]
        and f.scene_id == index["scene_id"],
        "grid original exposure does not bind",
    )
    (decision,) = [
        x
        for x in read(source(f"{case}/clearance-gate.json"))["checks"]
        if x["skill"] == "LIFT" and x["phase"] == "FEEDBACK" and x["step"] == tick
    ]
    return f, robot, decision["current"]


def bind_t01(tick):
    r = read(source("t01/receipt.json"))
    light = read(source("t01/local-clearance-seal.json"))
    capture = pinned(source("t01/acquisition-seal.json"), r["capture_sha256"])
    require(light["acquisition_seal_sha256"] == r["capture_sha256"], "t01 seal lineage")
    index = pinned(source("t01/pixel-index.json"), capture["index_sha256"])
    rows = pinned(source("t01/local-clearance.json"), light["local_clearance_sha256"])["rows"]
    (e,) = [
        x for x in index["frames"] if x["label"] == "LIFT/feedback" and x["physics_step"] == tick
    ]
    f = decode(source("t01/" + e["file"]))
    require(
        f.episode_id == index["episode"]
        and f.scene_id == index["scene"]
        and e["frame_id"] == f.frame_id
        and e["checksum_sha256"] == f.checksum_sha256
        and sha(input_path("t01/" + e["file"])) == e["file_sha256"],
        "t01 original exposure does not bind",
    )
    (decision,) = [
        x
        for x in rows
        if x["frame_id"] == f.frame_id
        and x["phase"] == "FEEDBACK"
        and x["skill"] == "LIFT"
        and x["physics_step"] == tick
    ]
    require(decision["status"] == "CLEAR", "original t01 verdict changed")
    return f, decision["robot"], decision["evidence"]


def roi_margin(points, camera, depth, allowance):
    t = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    local = (points - t[:3, 3]) @ t[:3, :3]
    if local[:, 2].min() <= 0:
        return None
    f, c = np.split(np.asarray(camera["intrinsics"]), 2)
    pixel = local[:, :2] / local[:, 2, None] * f + c
    lo = np.floor(pixel.min(axis=0) - 0.5).astype(int)
    hi = np.ceil(pixel.max(axis=0) + 0.5).astype(int)
    if (lo < 0).any() or (hi >= depth.shape[::-1]).any():
        return None
    roi = depth[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1]
    return float(roi.min() + allowance - local[:, 2].max())


def volume_check(model, views, observed):
    def covers(box, pad):
        require(not np.any(pad), "frozen payload call already uses an inflated box")
        points = box.corners()
        allowance = 0.0
        if box.name == "object_geom":
            points[:, 2] = np.maximum(points[:, 2], model.table.c[2] + model.table.h[2])
            allowance = 2 * BAND
        result = {}
        for key, (camera, depth) in views.items():
            covered = _covers(points, camera, depth, allowance)
            margin = roi_margin(points, camera, depth, allowance)
            require(covered == (margin is not None and margin >= 0), "volume math failed control")
            result[key] = margin
        observed[box.name] = result
        return any(z is not None and z >= 0 for z in result.values())

    return covers


def evaluate(guard, robot, evidence, cfg, class_key, part, axis, new_limit):
    seq = guard.source_classes[class_key] if class_key else None
    if seq is not None and new_limit is not None:
        w, windows = seq
        box = w.copy()
        require(new_limit >= box[part, axis], "candidate reserve may only increase")
        box[part, axis] = new_limit
        guard.source_classes[class_key] = (box, windows)
    try:
        p = {}
        result = guard.check(
            "LIFT",
            np.asarray(robot["joint_positions_rad"]),
            np.asarray(robot["finger_positions_m"]),
            np.asarray(robot["joint_velocities_rad_s"]),
            np.asarray(robot["finger_velocities_m_s"]),
            robot["handoff"],
            evidence["payload_observation"],
            volume_check(guard.motion.model, cfg, p),
            allow_grasp_station_contact=True,
            native_target=np.asarray(evidence["commanded_target_xyz_m"]),
        )
        limits = {
            n: max((x for x in row.values() if x is not None), default=None) for n, row in p.items()
        }
        smallest = min(
            ((n, a) for n, a in limits.items() if a is not None), key=lambda x: x[1], default=None
        )
        return {"predicate": result, "views": p, "minimum_best_view_m": smallest}
    finally:
        if seq is not None:
            guard.source_classes[class_key] = seq


def compare():
    cal = read(source("calibration/manifest.json"))
    views = {
        key: (
            cal["maps"][key]["camera"],
            np.load(
                input_path("calibration/" + cal["maps"][key]["depth_file"]), allow_pickle=False
            ),
        )
        for key in VIEWS
    }
    for key in VIEWS:
        row = cal["maps"][key]
        require(
            sha(input_path("calibration/" + row["depth_file"])) == row["depth_sha256"],
            "volume map differs",
        )
    source_profile = read(
        source("runtime/scripts/graduation/g1_complete_cv_source_motion_profile.json")
    )
    guard = PayloadClearance(
        MotionGeometry(Model(source("runtime/" + PANDA))),
        read(source("runtime/scripts/graduation/g1_complete_cv_payload_profile.json")),
        source_profile,
    )
    stop_grid = read(source("midRaw/interchange.json"))["stops"][-1]
    stop_t01 = next(x for x in read(source("fixed/reader-1.json"))["result"] if x["tick"] == 1840)
    deficits = {
        "grid04": -stop_grid["worst_world_margin_m"],
        "t01": -stop_t01["source_world_reserve_m"],
    }
    result = {}
    for case in PLAN["known"]:
        tick, key = case["tick"], case["class"]
        name, body, axis = case["case"], case["body"], case["axis"]
        frame, robot, e = bind_grid(name, tick) if name == "grid04" else bind_t01(tick)
        camera = cal["primary_camera"]
        require(
            frame.model_dump(mode="json", include=set(camera)) == camera
            and frame.checksum_sha256 == e["checksum_sha256"] == robot["checksum_sha256"]
            and frame.frame_id
            == e["frame_id"]
            == robot["frame_id"]
            == e["payload_observation"]["pose"]["frame_id"]
            and frame.sim_time_s == robot["camera_encoder_sim_time_s"] == robot["sim_time_s"]
            and robot["physics_step"] == tick
            and robot["handoff"]["current_step"] == tick
            and e["status"] == "CLEAR"
            and e["depth"]["unknown_pixels"] == 0
            and e["source_table_support"]["qualified"]
            and e["short_motion"]["registered_source_speed_class"] == key,
            "physics, certificate input and optical identity are not co-exposure",
        )
        part = guard.motion.names.index(body)
        original = evaluate(guard, robot, e, views, key, part, axis, None)
        expected = e["short_motion"]
        matched = original["predicate"]
        require(
            matched["reason"] == expected["reason"]
            and matched["reference"] == expected["reference"]
            and matched["limiting_pair"] == expected["limiting_pair"]
            and abs(matched["minimum_gap_m"] - expected["minimum_gap_m"]) <= 1e-12
            and len(original["views"]) == len(guard.motion.names),
            "original registered source predicate failed to close",
        )
        base = guard.source_classes[key][0][part, axis]
        required = base + deficits[name]
        final_fit_lower = 1.25 * (np.ceil(1e8 * required) / 1e8) + 0.0005
        result[name] = {
            "tick": tick,
            "reference": matched["reference"],
            "body": body,
            "axis_index": axis,
            "old_world_allowance_m": float(base),
            "minimum_expansion_m": float(deficits[name]),
            "undercoverage_only_final_fit_lower_m": float(final_fit_lower),
            "original": original,
            "minimum_required": evaluate(guard, robot, e, views, key, part, axis, required),
            "known_failures_implied_fit_lower": evaluate(
                guard, robot, e, views, key, part, axis, final_fit_lower
            ),
        }
    return result


def inventory():
    result = {}
    sources = {
        "grid04": read(source("grid04/clearance-gate.json"))["checks"],
        "t01": read(source("t01/local-clearance.json"))["rows"],
        "grid02": read(source("grid02/clearance-gate.json"))["checks"],
    }
    for name, checks in sources.items():
        selected = []
        for row in checks:
            if row["skill"] != "LIFT" or row["phase"] != "FEEDBACK" or row["status"] != "CLEAR":
                continue
            e = row["evidence"] if name == "t01" else row["current"]
            if not e.get("source_table_support", {}).get("qualified"):
                continue
            key = e["short_motion"].get("registered_source_speed_class")
            if key is not None:
                selected.append([row.get("step", row.get("physics_step")), key])
        result[name] = selected
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("reader", choices=("reader-1", "reader-2"))
    args = cli.parse_args()
    folder = ROOTS["output"]
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with patch.multiple(
            mujoco, Renderer=deny, mjr_render=deny, mj_step=deny, mj_step1=deny, mj_step2=deny
        ):
            verify()
            cases = compare()
            write(
                folder / f"{args.reader}.json",
                {
                    "cases": cases,
                    "candidate_source_frames_by_original_permission": inventory(),
                    "case_splitting_note": (
                        "Grid02 inventory uses original acceptance metadata only. "
                        "New challenge stop results are absent."
                    ),
                    "new_cpu_steps": 0,
                    "new_exposures": 0,
                    "full_gate_rerun": False,
                    "candidate_profile_fitted": False,
                    "plan_sha256": sha(HERE / "plan.json"),
                    "source_sha256": sha(Path(__file__)),
                },
            )
    except BaseException as e:
        write(folder / f"{args.reader}-failure.json", {"type": type(e).__name__, "reason": str(e)})
        raise
