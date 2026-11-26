"""Check the actual saved grid-04 HOLD endpoint for a counterexample to spatial separation."""

import argparse
import gzip
import importlib.util
import itertools
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
NATIVE = ROOT / PLAN["native"]
CASE = ROOT / PLAN["case"]
TOL = PLAN["strict_numeric_tolerance_m"]
FRAME_TICKS = (PLAN["anchor"], PLAN["failure"])
POLY = SimpleNamespace(
    TRIPLES=np.array(list(itertools.combinations(range(12), 3))),
    SIGNS=np.array(list(itertools.product((-1, 1), repeat=3))),
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def deny(*args, **kwargs):
    raise AssertionError("saved stop readback cannot render, expose or integrate")


def module(rel):
    file = ROOT / rel
    spec = importlib.util.spec_from_file_location(file.stem, file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def inputs():
    for file, expected in PLAN["source_sha256"].items():
        require(sha(ROOT / file) == expected, f"changed frozen input: {file}")
    manifest = read(NATIVE / "result.json")
    normal = {row["tick"]: row for row in read(NATIVE / "normal.json")}
    blind = read(ROOT / PLAN["blind"])
    index = read(CASE / "rgbd-index.json")
    labels = {row["frame_id"]: row for row in read(CASE / "offline-physics.json")["frame_labels"]}
    gates = {
        row["step"]: row
        for row in read(CASE / "clearance-gate.json")["checks"]
        if row["phase"] == "FEEDBACK"
    }
    camera = read(CASE / "optical-registration.json")["geometry"]["camera"]
    rows = {}
    for tick in FRAME_TICKS:
        filename = PLAN["pixel_frame_sources"][str(tick)]
        (index_row,) = [row for row in index["rows"] if row["file"] == filename]
        enc = index_row["robot"]
        with gzip.open(CASE / filename, "rb") as stream:
            image = RGBDObservation.model_validate_json(stream.read())
        label = labels[image.frame_id]
        saved = normal[tick]
        verdict = gates[tick]
        require(
            image.sim_time_s == enc["camera_encoder_sim_time_s"] == saved["t"]
            and image.checksum_sha256
            == enc["checksum_sha256"]
            == label["checksum_sha256"]
            == verdict["checksum_sha256"]
            and enc["physics_step"] == label["physics_step"] == tick
            and index_row["phase"] == "FEEDBACK"
            and index_row["skill"] == "LIFT"
            and enc["joint_positions_rad"] + enc["finger_positions_m"] == saved["q"][:9]
            and label["center_m"] == saved["cube"]
            and image.model_dump(mode="json", include=set(camera)) == camera
            and verdict["current"]["status"] == ("CLEAR" if tick == PLAN["anchor"] else "BLOCKED"),
            "different signed phase, pose or original gate",
        )
        rows[tick] = SimpleNamespace(
            enc=enc, label=label, blind=blind[str(tick)], q=np.array(saved["q"])
        )
    locked = {}
    for tick in range(PLAN["anchor"], PLAN["failure"] + 1):
        expected = manifest["archives"][str(tick)]
        raw = NATIVE / f"stop-{tick}.npz"
        file = raw.with_suffix(".json")
        require(
            sha(raw) == expected["state_sha256"]
            and sha(file) == expected["contacts_sha256"]
            and normal[tick]["phase_sha256"] == expected["phase_sha256"],
            f"changed original stop branch {tick}",
        )
        locked[tick] = expected
    return camera, rows, normal, locked


def model_poses(model, data, sequence):
    centers, rotations = [], []
    for q in sequence:
        data.qpos[:] = q
        mujoco.mj_kinematics(model, data)
        centers.append(data.geom_xpos.copy())
        rotations.append(data.geom_xmat.reshape(model.ngeom, 3, 3).copy())
    return np.array(centers), np.array(rotations)


def at_exposure(model, data, row):
    pose = row.q.copy()
    robot = row.enc
    pose[:9] = robot["camera_joint_positions_rad"] + robot["camera_finger_positions_m"]
    addr = model.joint("object_free").qposadr[0]
    obj = model.geom("object_geom")
    require(
        np.all(obj.pos == 0) and np.array_equal(obj.quat, [1, 0, 0, 0]),
        "free-body and observed cube frames differ",
    )
    pose[addr : addr + 3] = row.label["center_m"]
    mujoco.mju_mat2Quat(pose[addr + 3 : addr + 7], np.asarray(row.label["rotation"]).ravel())
    c, r = model_poses(model, data, pose[None])
    return c[0], r[0]


def plane_packet(pixel_code, camera, tick, row):
    records = []
    for pixel in PLAN["pixels"]:
        p = next(x for x in row.blind["pixels"] if x["uv"] == pixel)
        require(p["near_mask"][1][1], "specified pixel is not an observed near return")
        z, table = p["depth_m"][1][1], p["empty_depth_m"][1][1]
        band = PLAN["shutter_band_m"]
        for kind, a, b in (
            ("measured_band", z - band, z + band),
            ("in_front_of_band", 0.01, z - band),
            ("behind_band", z + band, table + band),
        ):
            A, B = pixel_code.world_planes(camera, *pixel, a, b)
            records.append((tick, pixel, kind, (a, b), A, B))
    phase_order = {"measured_band": 0, "in_front_of_band": 1, "behind_band": 2}
    return sorted(records, key=lambda row: phase_order[row[2]])


def load_trajectory(tick, anchor, normal):
    with np.load(NATIVE / f"stop-{tick}.npz", allow_pickle=False) as file:
        q, dq, ctrl = (file[key] for key in ("q", "dq", "ctrl"))
    contacts = read(NATIVE / f"stop-{tick}.json")
    require(
        len(q) == len(dq) == len(ctrl) == len(contacts) == PLAN["branch_integrations_sealed"] + 1
        and np.array_equal(q[0], normal[tick]["q"])
        and np.array_equal(dq[0], normal[tick]["dq"])
        and np.array_equal(ctrl[0, 7:], normal[tick]["ctrl"][7:]),
        "saved stop does not join normal trajectory",
    )
    prefix = [normal[k] for k in range(anchor, tick)]
    return {
        "q": np.concatenate((np.asarray([x["q"] for x in prefix]).reshape(-1, q.shape[1]), q)),
        "qvel": np.concatenate(
            (np.asarray([x["dq"] for x in prefix]).reshape(-1, dq.shape[1]), dq)
        ),
    }


def analytic_margin(old, p, center, rotation, size, kind):
    v = (p - center) @ rotation
    if kind == old.BOX:
        return min(float(s) - abs(float(x)) for s, x in zip(size, v, strict=True))
    if kind == old.CAPSULE:
        z = max(abs(v[2]) - size[1], 0)
        return float(size[0] - np.hypot(np.hypot(v[0], v[1]), z))
    require(kind == old.CYLINDER, "unsupported physical solid")
    return float(min(size[0] - np.hypot(v[0], v[1]), size[1] - abs(v[2])))


def scan(old, native, volume, q, mocap, cone, origin_model):
    _, pixel, kind, span, A, B = cone
    center, rotation = mocap
    sizes = native.geom_size.copy()
    kinds = native.geom_type
    require(
        np.isin(kinds, [old.BOX, old.CAPSULE, old.CYLINDER]).all(), "new unmodelled physical solid"
    )
    outer = sizes.copy()
    solid_curved = kinds != old.BOX
    outer[solid_curved, :2] = sizes[solid_curved, :1]
    outer[solid_curved, 2] = sizes[solid_curved, 1] + np.where(
        kinds[solid_curved] == old.CAPSULE, sizes[solid_curved, 0], 0
    )
    a_norm = np.linalg.norm(A, axis=1)
    normals = A / a_norm[:, None]
    limits = B / a_norm
    outside, min_gap = 0, None
    best = None
    for geom in range(native.ngeom):
        c = center[:, geom]
        r = rotation[:, geom]
        distances = c @ normals.T - limits - np.abs(normals @ r) @ outer[geom]
        separation = distances.max(axis=1)
        outside += int((separation > TOL).sum())
        gap = float(separation.min())
        min_gap = gap if min_gap is None else min(min_gap, gap)
        for tick in np.flatnonzero(separation <= TOL):
            if tick == 0:
                continue
            pts = old.polytope(POLY, c[tick], r[tick], outer[geom], np.eye(4), (normals, limits))
            if not len(pts):
                continue
            centroid = pts.mean(axis=0, keepdims=True)
            points = np.concatenate(
                [centroid, *(centroid + f * (pts - centroid) for f in (0.5, 0.9, 0.99))]
            )
            cone_margin = (limits - points @ normals.T).min(axis=1)
            margin_in = old.interior(
                points, c[tick : tick + 1], r[tick : tick + 1], sizes[[geom]], kinds[[geom]]
            )[:, 0]
            anchor_out = -old.interior(points, center[0], rotation[0], sizes, kinds).max(axis=1)
            other_out = -old.interior(points, *origin_model, sizes, kinds).max(axis=1)
            margins = np.stack((cone_margin, anchor_out, other_out, margin_in), axis=1)
            k = int(margins.min(axis=1).argmax())
            if margins[k].min() <= TOL or (
                best is not None and margins[k].min() <= min(best["margins_m"])
            ):
                continue
            p = points[k]
            check = [
                float(
                    min(
                        (b - float(n @ p)) / float(length)
                        for n, b, length in zip(A, B, a_norm, strict=True)
                    )
                ),
                -max(
                    analytic_margin(old, p, c0, r0, size, typ)
                    for c0, r0, size, typ in zip(center[0], rotation[0], sizes, kinds, strict=True)
                ),
                -max(
                    analytic_margin(old, p, c0, r0, size, typ)
                    for c0, r0, size, typ in zip(*origin_model, sizes, kinds, strict=True)
                ),
                analytic_margin(old, p, c[tick], r[tick], sizes[geom], kinds[geom]),
            ]
            require(
                np.allclose(margins[k], check, atol=2e-12, rtol=0) and min(check) > TOL,
                "independent signed distance methods disagree",
            )
            best = {
                "geometry": native.geom(geom).name,
                "path_offset": int(tick),
                "point_world_m": p.tolist(),
                "margins_m": list(check),
            }
    result = {
        "pixel": pixel,
        "segment": kind,
        "axis_depth_m": span,
        "endpoint_entity_checks": len(q["q"]) * native.ngeom,
        "strictly_one_plane_separated_endpoints": outside,
        "minimum_outer_one_plane_gap_m": min_gap,
        "new_geometry_witness": best,
    }
    if best is None:
        clip = old.protection(POLY, volume, q, np.eye(4), (normals, limits))
        result["hermite_geometry_only"] = {
            name: {
                "strictly_separated": not row["interpolant_hull_possible_interval_starts"],
                "possible_interval_count": len(row["interpolant_hull_possible_interval_starts"]),
            }
            for name, row in clip.items()
        }
    return result


def run(reader):
    old = module(PLAN["prior_geometry"])
    pixel_code = module(PLAN["prior_pin"])
    camera, rows, normal, locked = inputs()
    main = PLAN["failure"]
    comparison_tick = PLAN["anchor"]
    asset = ROOT / PLAN["asset"]
    native = mujoco.MjModel.from_xml_path(str(asset))
    data = mujoco.MjData(native)
    volume = MotionGeometry(Model(asset))
    origins = {t: at_exposure(native, data, rows[t]) for t in FRAME_TICKS}
    cones = {t: plane_packet(pixel_code, camera, t, rows[t]) for t in FRAME_TICKS}
    outputs, opened = [], set()
    for anchor, triggers in ((main, (main,)), (comparison_tick, tuple(locked))):
        for tick in triggers:
            trajectory = load_trajectory(tick, anchor, normal)
            opened.add(tick)
            motion = model_poses(native, data, trajectory["q"])
            cone_sets = (
                ((anchor, cones[anchor]),)
                if anchor == main
                else ((anchor, cones[anchor]), (main, cones[main]))
            )
            for cone_tick, bank in cone_sets:
                for cone in bank:
                    result = scan(old, native, volume, trajectory, motion, cone, origins[anchor])
                    result.update(
                        anchor=anchor,
                        trigger=tick,
                        frustum_observation_tick=cone_tick,
                        online_permission_preexisting=anchor == comparison_tick,
                    )
                    witness = result["new_geometry_witness"]
                    if witness is not None:
                        witness["stop_offset"] = witness["path_offset"] - (tick - anchor)
                    outputs.append(result)
                    if anchor == main and result["segment"] == "measured_band" and witness:
                        break
                if anchor == main and any(
                    x["segment"] == "measured_band" and x["new_geometry_witness"] for x in outputs
                ):
                    break
            if anchor == main and any(
                x["segment"] == "measured_band" and x["new_geometry_witness"] for x in outputs
            ):
                break
        if anchor == main and any(
            x["segment"] == "measured_band" and x["new_geometry_witness"] for x in outputs
        ):
            break
    OUT.mkdir(parents=True, exist_ok=True)
    write(
        OUT / f"{reader}.json",
        {
            "checked": outputs,
            "pinned_stop_registry": locked,
            "opened_stop_state_arrays": sorted(opened),
            "plan_sha256": sha(HERE / "plan.json"),
            "reader_sha256": sha(Path(__file__)),
            "actual_continuous_or_full_exposure_entity_error_bound": "NOT_AVAILABLE",
            "conservative_reconstructed_geometry_only": True,
            "integrations": 0,
            "rendering": 0,
            "exposures": 0,
        },
    )


if __name__ == "__main__":
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("reader", choices=("reader-1", "reader-2"))
    with (
        patch.multiple(
            mujoco, mj_step=deny, mj_step1=deny, mj_step2=deny, Renderer=deny, mjr_render=deny
        ),
        patch.multiple(MuJoCoRGBDCamera, capture=deny, _capture=deny),
    ):
        run(arg.parse_args().reader)
