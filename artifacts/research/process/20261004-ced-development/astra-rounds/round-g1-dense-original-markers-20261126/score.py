"""Score sealed marker estimates without using labels to choose a pose or an interval."""

import importlib.util
import math
from itertools import product
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from predict import (
    ASSET,
    DENSE,
    NEEDLE,
    OPTICAL,
    OUT,
    PLAN,
    PLAN_PATH,
    ROOT,
    require,
    snapshot_sources,
)
from scripts.graduation.perception_io import read, sha, write

COLD = OUT / "prediction.cold.json"
MAIN = OUT / "prediction.json"
COPIED_PREDICTOR = OUT / "predict.executed.py"
FOLLOWUP_PREDICTION = OUT / "masked-support.json"


def validate_inputs():
    for relative, frozen in PLAN["sha256"].items():
        item = (ROOT / relative).resolve()
        require(item.is_relative_to(ROOT) and sha(item) == frozen, f"changed input {relative}")
    require(MAIN.read_bytes() == COLD.read_bytes(), "cold marker predictions differ")
    source = Path(__file__).with_name("predict.py")
    require(
        COPIED_PREDICTOR.read_text().replace(
            "for job, meta, dense, _ in specs:", "for job, _meta, dense, _ in specs:", 1
        )
        == source.read_text(),
        "delivered predictor exceeds the unused-name-only change since capture",
    )
    candidate = read(MAIN)
    require(
        candidate["plan_sha256"] == sha(PLAN_PATH)
        and candidate["prediction_source_sha256"] == sha(COPIED_PREDICTOR)
        and candidate["optical_input_sha256"] == sha(OPTICAL)
        and candidate["blocked_file_accesses"] == 2
        and candidate["scope"] == PLAN["scope"],
        "blind prediction/source/registration does not bind",
    )
    for root in (NEEDLE, DENSE / "native"):
        members = read(root / "seal.json")["members"]
        require(
            set(members) | {"seal.json"} == {p.name for p in root.iterdir() if p.is_file()},
            "old sealed image inventory differs",
        )
        require(
            all(sha(root / name) == fingerprint for name, fingerprint in members.items()),
            "a sealed native image changed",
        )
    return candidate


def angle_deg(rotation):
    return math.degrees(math.acos(float(np.clip((np.trace(rotation) - 1.0) / 2.0, -1, 1))))


def dimensions(name):
    obj = ET.parse(ASSET).find("./worldbody/body[@name='object']")
    g = obj.find(f"geom[@name='{name}']")
    require(
        g is not None and g.get("type") == "box" and g.get("quat") is None,
        "physical comparison geometry unbound",
    )
    return np.fromstring(g.get("pos", "0 0 0"), sep=" "), np.fromstring(g.attrib["size"], sep=" ")


def pose_metrics(pose, physical_center, physical_r, crossbar):
    center = np.array(pose.get("center_m", pose["center_world_m"]))
    rotation = np.array(pose.get("rotation", pose["rotation_object_to_world"]))
    delta = center - physical_center
    local, half = crossbar
    absolute_relative = physical_r.T @ rotation
    signed_edge = {}
    for side in (-1, 1):
        endpoints = np.array([local + half * [i, side, k] for i, k in product((-1, 1), repeat=2)])
        p = center + endpoints @ rotation.T
        t = physical_center + endpoints @ physical_r.T
        displacement = (p - t) @ (side * physical_r[:, 1])
        signed_edge[str(side)] = [float(displacement.min()), float(displacement.max())]
    return {
        "center_error_m": float(np.linalg.norm(delta)),
        "center_error_world_m": delta.tolist(),
        "center_error_along_true_object_axes_m": (delta @ physical_r).tolist(),
        "rotation_error_deg": angle_deg(absolute_relative),
        "axis_orientation_error_deg": np.degrees(
            np.arccos(
                np.clip(np.diag(absolute_relative), -1, 1),
            )
        ).tolist(),
        "id8_crossbar_lateral_face_projection_error_m": signed_edge,
        "id8_crossbar_worst_lateral_face_error_m": max(
            abs(x) for points in signed_edge.values() for x in points
        ),
    }


def supported_pose(job, result):
    new = result["pose"]
    return {
        "joints_rad": job["joints_rad"],
        "fingers_m": job["fingers_m"],
        "time_s": job["time_s"],
        "frame_id": result["dense_frame_id"],
        "checksum_sha256": result["dense_raw_sha256"],
        "optical": new
        | {
            "center_m": new["center_world_m"],
            "rotation": new["rotation_object_to_world"],
            # Retain the *old* directional error shape only for hypothetical scale probes.
            "anchor_error_object_m": job["optical"]["anchor_error_object_m"],
            "basis_error_object": job["optical"]["basis_error_object"],
        },
    }


def binary_limit(predicate):
    if not predicate(0.0):
        return None
    if predicate(1.0):
        return {"feasible_lower": 1.0, "infeasible_upper": None}
    lower, upper = 0.0, 1.0
    for _ in range(PLAN["binary_steps"]):
        mid = (lower + upper) / 2
        if predicate(mid):
            lower = mid
        else:
            upper = mid
    return {"feasible_lower": lower, "infeasible_upper": upper}


def margin_results(geom, model, camera, job, result, recorded, actual_depth, representative):
    eye, ray_direction = geom.ray_directions(camera)
    coords = [tuple(row["uv"]) for row in recorded["rays"]]
    require(
        len(coords) == 36 and tuple(representative) in coords and len(set(coords)) == 36,
        "not the original 36-ray target",
    )
    state, pose = geom.camera_state(model, supported_pose(job, result))
    scene = geom.SurfaceBounds(model, state, pose)
    observed = {uv: float(actual_depth[uv[1], uv[0]]) for uv in coords}
    directions = {uv: ray_direction(*uv) for uv in coords}

    def ray_at(uv, factor):
        g = scene.first_face(eye, directions[uv], factor)
        interval = g.get("axis_depth_interval_m")
        z = observed[uv]
        compatible = (
            interval is not None
            and np.isfinite(z)
            and z > 0
            and max(abs(z - x) for x in interval) < PLAN["band_m"]
        )
        return g | {"uv": uv, "observed_axial_m": z, "within_4mm": compatible}

    def snapshot(factor):
        rays = [ray_at(uv, factor) for uv in coords]
        return {
            "hypothetical_old_scale": factor,
            "proved_first_faces": sum(r["reason"] is None for r in rays),
            "proved_and_depth_compatible": sum(
                r["reason"] is None and r["within_4mm"] for r in rays
            ),
            "rays": rays,
        }

    def feasible(uv, factor):
        r = ray_at(uv, factor)
        return r["reason"] is None and r["within_4mm"]

    return {
        "candidate": "marker_only_uncertified",
        "geometry_and_depth_scale_bracket": binary_limit(
            lambda f: all(feasible(uv, f) for uv in coords)
        ),
        "representative_face_scale_bracket": binary_limit(
            lambda f: feasible(tuple(representative), f)
        ),
        "representative_old_full_bound_ray": next(
            row for row in recorded["rays"] if row["uv"] == representative
        ),
        "snapshots": [snapshot(f) for f in PLAN["sensitivity_scales"]],
    }


def load_bounds():
    p = ROOT / PLAN["geometry_module"]
    spec = importlib.util.spec_from_file_location("frozen_first_face", p)
    require(spec is not None and spec.loader is not None, "original geometry routine missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fail_if_step(*_args, **_kwargs):
    raise RuntimeError("archived marker pose readback does not integrate or render")


def score():
    prediction = validate_inputs()
    followup = read(FOLLOWUP_PREDICTION)
    require(
        FOLLOWUP_PREDICTION.read_bytes() == (OUT / "masked-support.cold.json").read_bytes()
        and followup["followup_plan_sha256"]
        == sha(Path(__file__).with_name("plan-mask-support.json"))
        and followup["source_sha256"] == sha(Path(__file__).with_name("masked_support.py"))
        and followup["inherited_predictor_sha256"] == sha(Path(__file__).with_name("predict.py"))
        and followup["optical_input_sha256"] == sha(OPTICAL)
        and followup["blocked_file_accesses"] == 2
        and followup["scope"] == PLAN["scope"],
        "two supplemental cold runs, methodology or input binding differ",
    )
    camera, subjects = snapshot_sources()
    jobs = {j["key"]: j for j in read(OPTICAL)["jobs"]}
    physical = {j["key"]: j for j in read(DENSE / "capture-input.json")["jobs"]}
    dense_by_frame = {p["dense_frame_id"]: p for p in prediction["dense"]}
    followup_by_frame = {p["dense_frame_id"]: p for p in followup["dense"]}
    require(
        set(followup_by_frame) == set(dense_by_frame) and len(dense_by_frame) == 12,
        "supplemental prediction did not preserve the denominator",
    )
    before = {p["key"]: p for p in read(ROOT / PLAN["first_geometry"])["rows"]}
    stop_source = read(ROOT / PLAN["original_truth_t02"])["samples"][2112]
    crossbar = dimensions("g1_dual_id8_crossbar")
    bounds = load_bounds()
    rows = []
    targets = {
        (t["archive"], step): t["representative"]
        for t in PLAN["targets"]
        for step in (t["clear"], t["stop"])
    }
    indices = {x["key"]: x for x in read(DENSE / "native/index.json")["frames"]}
    require(len(indices) == len(physical) == 10, "ordinary physical labels differ")
    with patch.multiple(
        mujoco,
        mj_step=fail_if_step,
        mj_step1=fail_if_step,
        mj_step2=fail_if_step,
        Renderer=fail_if_step,
        mjr_render=fail_if_step,
    ):
        model = mujoco.MjModel.from_xml_path(str(ASSET))
        for job, native, array_path, frame_id in subjects:
            result = dense_by_frame[frame_id]
            second = followup_by_frame[frame_id]
            key = job["key"]
            require(
                result["key"] == key
                and result["dense_raw_sha256"] == sha(array_path)
                and result["original_frame_id"] == job["frame_id"]
                and result["original_checksum_sha256"] == job["checksum_sha256"]
                and result["detected"] == [8],
                "marker prediction not associated with its archived exposure",
            )
            require(
                all(
                    second[k] == result[k]
                    for k in (
                        "key",
                        "dense_raw_sha256",
                        "original_frame_id",
                        "original_checksum_sha256",
                        "exclusions",
                    )
                ),
                "supplement changed the frozen source or exclusion mask",
            )
            if result["reason"] is None and second["reason"] is None:
                require(
                    second["pose"] == result["pose"] and second["samples"] == result["samples"],
                    "previously eligible frame differs without a mask-dependent sample",
                )
            if key in physical:
                actual = physical[key]
                c = np.asarray(actual["world_object_center_m"])
                r = np.asarray(actual["world_object_rotation"])
                require(
                    job["time_s"] == actual["time_s"]
                    and job["frame_id"] == actual["frame_id"]
                    and job["checksum_sha256"] == actual["checksum_sha256"],
                    "archived ordinary physical label detached",
                )
                identity = {
                    "archive": actual["archive"],
                    "step": actual["step"],
                    "slot": actual["slot"],
                    "status": actual["original_status"],
                }
            else:
                require(stop_source["sim_time_s"] == job["time_s"], "old physical clock differs")
                c = np.asarray(stop_source["object_geom_position_m"])
                r = np.asarray(stop_source["object_geom_rotation_row_major"]).reshape(3, 3)
                identity = {
                    "archive": "t02",
                    "step": 2112,
                    "fixture": native["model"],
                    "physical_pose_shared_in_pair": True,
                }
            self_result = identity | {
                "forecast_reason": result["reason"],
                "supplemental_forecast_reason": second["reason"],
                "original_optical_metrics": pose_metrics(job["optical"], c, r, crossbar),
            }
            for prefix, estimate in (("", result), ("supplemental_", second)):
                self_result[prefix + "candidate_metrics"] = None
                self_result[prefix + "geometry_sensitivity"] = None
                if estimate["reason"] is not None:
                    continue
                require(
                    all(m["excluded_pixel_overlap"] == 0 for m in estimate["samples"]),
                    "candidate used excluded marker or depth observations",
                )
                self_result[prefix + "candidate_metrics"] = pose_metrics(
                    estimate["pose"], c, r, crossbar
                )
                selector = (identity["archive"], identity["step"])
                if selector in targets:
                    with np.load(array_path, allow_pickle=False) as saved:
                        z = saved["depth_m"]
                    self_result[prefix + "geometry_sensitivity"] = margin_results(
                        bounds,
                        model,
                        camera,
                        jobs[key],
                        estimate,
                        before[key],
                        z,
                        targets[selector],
                    )
            rows.append(self_result)

    common = prediction["standard_path_controls"]
    require(
        len(common) == 10
        and all(r.get("shared_native_measured_pose_identical") for r in common.values()),
        "original 320 shared-path comparisons are incomplete",
    )
    needle = [p for p in prediction["dense"] if p["key"] not in physical]
    require(len(needle) == 2, "needle pair did not share a state")
    for mode in (120, 2112):
        pair = []
        for name in ("bare", "pin"):
            with np.load(NEEDLE / f"step-{mode}-4x-{name}.npz", allow_pickle=False) as saved:
                pair.append(saved["depth_m"])
        require(
            int(np.count_nonzero(pair[0] - pair[1] > 0.008)) == 4, "needle return control drifted"
        )
    equality = all(p.get("pose") is not None for p in needle)
    if equality:
        eq_fields = ("center_world_m", "rotation_object_to_world", "ids", "method")
        equality = all(needle[0]["pose"][k] == needle[1]["pose"][k] for k in eq_fields)
    write(
        OUT / "physical-readback.json",
        {
            "schema": "g1.development.dense-marker-physical-readback.v1",
            "prediction_sha256": sha(MAIN),
            "prediction_source_executed_sha256": sha(COPIED_PREDICTOR),
            "prediction_source_delivered_sha256": sha(Path(__file__).with_name("predict.py")),
            "supplemental_prediction_sha256": sha(FOLLOWUP_PREDICTION),
            "rows": rows,
            "shared_320_controls": len(common),
            "needle_pose_identical": equality,
            "unique_physical_states": 11,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    score()
