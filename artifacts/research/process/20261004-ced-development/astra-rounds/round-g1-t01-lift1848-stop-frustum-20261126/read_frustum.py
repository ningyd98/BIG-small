"""Read the sealed, phase-matched t01 HOLD and original near-return footprint."""

import argparse
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import object_matrix, snapshot
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
OUT = REPO / PLAN["output"]
PHYSICS_ROOTS = {"profile", "stop"}
TOL = 1e-9
BOX = mujoco.mjtGeom.mjGEOM_BOX
CAPSULE = mujoco.mjtGeom.mjGEOM_CAPSULE
CYLINDER = mujoco.mjtGeom.mjGEOM_CYLINDER


def require(ok, message):
    if not ok:
        raise ValueError(message)


def path(root, member):
    base = (REPO / PLAN["roots"][root]).resolve()
    target = (base / member).resolve()
    require(base.is_relative_to(REPO) and target.is_relative_to(base), "foreign input path")
    return target


def source(root, member):
    file = path(root, member)
    require(
        sha(file) == PLAN["sha256_by_root_and_member"][f"{root}/{member}"],
        f"input hash mismatch: {root}/{member}",
    )
    return file


def check_sources(physical):
    for key in PLAN["sha256_by_root_and_member"]:
        root, member = key.split("/", 1)
        if not physical and (root in PHYSICS_ROOTS or key == "old/geometry.json"):
            continue
        source(root, member)
        if root == "src":
            require(
                sha(ROOT / "scripts/graduation" / member) == sha(path(root, member)),
                "mixed runtime",
            )


def old_reader():
    file = source("opt", "first_stop_readback.py")
    spec = importlib.util.spec_from_file_location("sealed_first_stop", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pixel_stage(old, out):
    def deny_truth(event, args):
        old.blind_audit(event, args)
        if event == "open" and isinstance(args[0], (bytes, str)):
            name = str(args[0])
            if "g1-t01-lift-fixed-height-stop-profile-20261126" in name or name.endswith(
                "geometry.json"
            ):
                raise PermissionError("physical sidecar unavailable to RGB-D stage")

    sys.addaudithook(deny_truth)
    check_sources(False)
    old.verify_inputs(False)
    allocation, _, table, samples = old.bound_sources()
    pixels = old.pixel_readback(allocation["geometry"]["camera"], table, samples)
    require(
        pixels == read(source("old", "pixels.json"))["result"],
        "original optical comparison differs",
    )
    write(out / "pixels.json", {"pixels": pixels, "plan_sha256": sha(HERE / "plan.json")})


def input_stop(old, model, seal, samples, tick):
    manifest = read(source("stop", "seal.json"))
    row = manifest["branches"][str(tick)]
    state_path = source("stop", row["state_file"])
    require(
        row["state_sha256"] == sha(state_path)
        and manifest["plan_sha256"] == sha(source("profile", "plan.json"))
        and manifest["source_sha256"] == sha(source("profile", "fixed_height_stop_profile.py"))
        and manifest["geom_names"] == [model.geom(i).name for i in range(model.ngeom)],
        "stop seal or named geometry differs",
    )
    if tick == 1848:
        contacts = pinned(source("stop", row["contact_file"]), row["contact_sha256"])
        require(
            len(contacts) == 241 and ["object_geom", "table"] in contacts[27],
            "missing original contact witness",
        )
    with np.load(state_path, allow_pickle=False) as f:
        state = {k: f[k] for k in f.files}
    require(
        state["q"].shape == (241, model.nq)
        and state["qvel"].shape == (241, model.nv)
        and state["ctrl"].shape == (241, model.nu)
        and state["geom_positions_m"].shape == (241, model.ngeom, 3)
        and state["geom_rotations"].shape == (241, model.ngeom, 9)
        and all(np.isfinite(a).all() for a in state.values())
        and np.allclose(state["time_s"], (tick + np.arange(241)) / 240, atol=TOL, rtol=0),
        "missing pose, nonfinite state or shifted stop clock",
    )
    row, frame, _ = samples[tick]
    labels = pinned(old.RAW / "offline-truth.json", seal["truth_sha256"])["samples"]
    label = labels[tick]
    require(
        frame.sim_time_s == state["time_s"][0] == label["sim_time_s"],
        "exposure and stop clock differ",
    )
    require(
        frame.episode_id == label["episode_id"] and label["physics_step"] == tick,
        "wrong physical phase",
    )
    return state, row["robot"], label, frame


def restore_initial(old, native, state, robot, label, frame, camera, tick):
    data, calibration = old.original_rays().restore(
        native, dict(robot=robot, physical=label, time_s=frame.sim_time_s), camera
    )
    pos = np.linalg.norm(state["geom_positions_m"][0] - data.geom_xpos, axis=1)
    rot = np.linalg.norm(state["geom_rotations"][0] - data.geom_xmat, axis=1)
    require(
        np.array_equal(state["q"][0, :7], robot["joint_positions_rad"])
        and np.array_equal(state["q"][0, 7:9], robot["finger_positions_m"])
        and float(pos.max()) <= TOL
        and float(rot.max()) <= TOL,
        f"exposure buffer does not match initial geometry at {tick}",
    )
    trace = read(old.RAW.parent / "lift-qualification-trace.json")
    (original,) = [
        item["state"]
        for item in trace["frames"]
        if item["frame_id"] == frame.frame_id and item["checksum_sha256"] == frame.checksum_sha256
    ]
    check = mujoco.MjData(native)
    mujoco.mj_setState(
        native,
        check,
        np.asarray(original["integration"]),
        mujoco.mjtState.mjSTATE_INTEGRATION,
    )
    require(
        check.time == frame.sim_time_s == original["sim_time_s"]
        and np.array_equal(check.qpos, state["q"][0])
        and np.array_equal(check.qvel, state["qvel"][0])
        and np.array_equal(check.ctrl, original["ctrl"]),
        f"the HOLD boundary changed original q/dq, or the old ctrl source differs at {tick}",
    )
    gains = native.actuator_gainprm[:7, 0]
    applied = np.clip(
        check.qpos[:7] + np.asarray(original["qfrc_bias_arm"]) / gains,
        native.actuator_ctrlrange[:7, 0],
        native.actuator_ctrlrange[:7, 1],
    )
    require(
        np.array_equal(applied, state["ctrl"][0, :7])
        and np.array_equal(check.ctrl[7:], state["ctrl"][0, 7:]),
        f"original immediate HOLD drive did not close at {tick}",
    )
    return calibration, {
        "max_geom_position_delta_m": float(pos.max()),
        "max_geom_rotation_delta": float(rot.max()),
        "arm_ctrl_change_at_hold_rad": float(abs(applied - check.ctrl[:7]).max()),
    }


def polytope(old, center, R, half, camera, planes):
    a, b = planes
    T = camera[:3, :3]
    eye = camera[:3, 3]
    r = T.T @ R
    c = T.T @ (center - eye)
    A = np.vstack((a, r.T, -r.T))
    B = np.r_[b, half + r.T @ c, half - r.T @ c]
    rows = A[old.TRIPLES]
    ok = abs(np.linalg.det(rows)) > 1e-11
    x = np.linalg.solve(rows[ok], B[old.TRIPLES[ok], None])[..., 0]
    x = x[np.all(x @ A.T <= B + 1e-10, axis=1)]
    return x


def interior(points, centers, rotations, sizes, kinds):
    local = np.einsum("pgi,gij->pgj", points[:, None] - centers, rotations)
    margins = (sizes - abs(local)).min(axis=-1)
    caps = kinds == CAPSULE
    if caps.any():
        sphere = local[:, caps].copy()
        sphere[..., 2] -= np.clip(sphere[..., 2], -sizes[caps, 1], sizes[caps, 1])
        margins[:, caps] = sizes[caps, 0] - np.linalg.norm(sphere, axis=-1)
    cyl = kinds == CYLINDER
    if cyl.any():
        x = local[:, cyl]
        margins[:, cyl] = np.minimum(
            sizes[cyl, 0] - np.linalg.norm(x[..., :2], axis=-1),
            sizes[cyl, 1] - abs(x[..., 2]),
        )
    return margins


def controls(old):
    eye = np.eye(4)
    require(
        interior(
            np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            np.zeros((1, 3)),
            np.eye(3)[None],
            np.ones((1, 3)),
            np.array([BOX]),
        )
        .ravel()
        .tolist()
        == [1.0, -1.0, 0.0],
        "initial, free and touching synthetic points were conflated",
    )
    planes = (np.vstack((np.eye(3), -np.eye(3))), np.ones(6))
    require(
        len(polytope(old, np.zeros(3), np.eye(3), np.full(3, 0.5), eye, planes)) > 0
        and not len(
            polytope(old, np.array([2.0, 0.0, 0.0]), np.eye(3), np.full(3, 0.5), eye, planes)
        ),
        "ordered intersection/separation control failed",
    )


def projection(old, camera, planes, centers, rotations, half):
    vertices = centers[:, None] + (old.SIGNS * half) @ rotations.swapaxes(1, 2)
    local = (vertices - camera[:3, 3]) @ camera[:3, :3]
    a, b = planes
    violation = ((local @ a.T).min(axis=1) - b) / np.linalg.norm(a, axis=1)
    return violation.max(axis=1)


def native_witnesses(old, native, state, camera, planes):
    kinds = native.geom_type
    require(np.isin(kinds, [BOX, CAPSULE, CYLINDER]).all(), "unmodelled native solid")
    sizes = native.geom_size.copy()
    outer = sizes.copy()
    nonbox = kinds != BOX
    outer[nonbox, :2] = sizes[nonbox, :1]
    outer[nonbox, 2] = sizes[nonbox, 1] + np.where(kinds[nonbox] == CAPSULE, sizes[nonbox, 0], 0)
    centers = state["geom_positions_m"]
    rotations = state["geom_rotations"].reshape(*centers.shape[:-1], 3, 3)
    a, b = planes
    a_norm = np.linalg.norm(a, axis=1)
    summaries = {}
    for g in range(native.ngeom):
        name = native.geom(g).name
        gap = projection(old, camera, planes, centers[:, g], rotations[:, g], outer[g])
        events, best, example = [], None, None
        for t in np.flatnonzero(gap <= TOL):
            vertices = polytope(old, centers[t, g], rotations[t, g], outer[g], camera, planes)
            if len(vertices) == 0:
                continue
            if example is None:
                example = {
                    "offset": int(t),
                    "point_world_m": (camera[:3, 3] + camera[:3, :3] @ vertices[0]).tolist(),
                }
            middle = vertices.mean(axis=0, keepdims=True)
            samples = np.concatenate(
                [middle, *(middle + f * (vertices - middle) for f in (0.5, 0.9, 0.99, 0.999))]
            )
            pts = samples @ camera[:3, :3].T + camera[:3, 3]
            inner = interior(pts, centers[t, [g]], rotations[t, [g]], sizes[[g]], kinds[[g]])[:, 0]
            frustum = ((b - samples @ a.T) / a_norm).min(axis=1)
            if kinds[g] == BOX or ((inner > TOL) & (frustum > TOL)).any():
                events.append(int(t))
            if t == 0:
                continue
            free = -interior(pts, centers[0], rotations[0], sizes, kinds).max(axis=1)
            margins = np.stack((frustum, free, inner), axis=1)
            score = margins.min(axis=1)
            i = int(score.argmax())
            if score[i] > TOL and (best is None or score[i] > min(best["margins_m"])):
                best = {
                    "offset": int(t),
                    "point_world_m": pts[i].tolist(),
                    "margins_m": margins[i].tolist(),
                    "margin_order": [
                        "inside_frustum",
                        "outside_all_initial_solids",
                        "inside_later_solid",
                    ],
                }
        summaries[name] = {
            "solid_intersection_offsets": events,
            "sufficient_new_occupancy_witness": best,
            "first_outer_bound_intersection": example,
            "nearest_one_plane_separation_m": float(gap.min()),
            "outer_box_for_capsule_or_cylinder": bool(nonbox[g]),
        }
    return summaries


def protection(old, model, state, camera, planes):
    q, dq = state["q"], state["qvel"]
    R = object_matrix(q)
    centers, rots, _, _ = model.solids(q[:, :7], q[:, 7:9], q[:, 9:12], R)
    points, speeds, _, _ = snapshot(model, q, dq, q[:, 9:12], R)
    shift = speeds / (3 * 240)
    nodes = np.concatenate(
        (points[:-1], points[:-1] + shift[:-1], points[1:] - shift[1:], points[1:]), axis=2
    )
    nodes = (nodes - camera[:3, 3]) @ camera[:3, :3]
    a, b = planes
    gap = (((nodes @ a.T).min(axis=2) - b) / np.linalg.norm(a, axis=1)).max(axis=-1)
    result = {}
    for i, name in enumerate(model.names):
        separates = projection(old, camera, planes, centers[:, i], rots[:, i], model.sizes[i])
        hit, first_point, newly = [], None, None
        for t in np.flatnonzero(separates <= TOL):
            vertices = polytope(old, centers[t, i], rots[t, i], model.sizes[i], camera, planes)
            if len(vertices):
                hit.append(int(t))
                if first_point is None:
                    first_point = (vertices[0] @ camera[:3, :3].T + camera[:3, 3]).tolist()
                if t == 0:
                    continue
                middle = vertices.mean(axis=0, keepdims=True)
                tests = np.concatenate(
                    [middle, *(middle + f * (vertices - middle) for f in (0.5, 0.9, 0.99, 0.999))]
                )
                pts = tests @ camera[:3, :3].T + camera[:3, 3]
                prim = np.full(len(model.names), BOX)
                free = -interior(pts, centers[0], rots[0], model.sizes, prim).max(axis=1)
                inner = interior(pts, centers[t, [i]], rots[t, [i]], model.sizes[[i]], prim[[i]])[
                    :, 0
                ]
                in_cone = ((b - tests @ a.T) / np.linalg.norm(a, axis=1)).min(axis=1)
                merits = np.stack([in_cone, free, inner], axis=1)
                k = int(merits.min(axis=1).argmax())
                if merits[k].min() > TOL and (
                    newly is None or merits[k].min() > min(newly["margins_m"])
                ):
                    newly = {
                        "offset": int(t),
                        "point_world_m": pts[k].tolist(),
                        "margins_m": merits[k].tolist(),
                    }
        result[name] = {
            "first_point_world_m": first_point,
            "endpoint_intersection_offsets": hit,
            "sufficient_new_occupancy_witness": newly,
            "interpolant_hull_possible_interval_starts": np.flatnonzero(gap[:, i] <= TOL).tolist(),
            "minimum_interpolant_one_plane_gap_m": float(gap[:, i].min()),
            "minimum_endpoint_one_plane_gap_m": float(separates.min()),
        }
    return result


def geometry_stage(old, out):
    check_sources(True)
    old.verify_inputs(True)
    allocation, seal, reference, samples = old.bound_sources()
    camera = allocation["geometry"]["camera"]
    pixel_seal = read(out / "pixels.json")
    pixels = old.pixel_readback(camera, reference, samples)
    require(
        pixels == pixel_seal["pixels"] and sha(HERE / "plan.json") == pixel_seal["plan_sha256"],
        "physical stage cannot change sealed pixel classification",
    )
    asset = ROOT / allocation["case"]["asset_path"]
    native = mujoco.MjModel.from_xml_path(str(asset))
    volume = MotionGeometry(Model(asset))
    controls(old)
    initial = {}
    for tick in (1840, 1848):
        state, robot, label, frame = input_stop(old, native, seal, samples, tick)
        optical, initial[str(tick)] = restore_initial(
            old, native, state, robot, label, frame, camera, tick
        )
    baseline = old.stop_overlap(asset, optical, camera, pixels["1848"])
    require(
        baseline == read(source("old", "geometry.json"))["result"]["stop_pixel_cone"],
        "old 1840 stop versus 1848 view was not reproduced",
    )
    require("g1_dual_id8_plate" in volume.names, "registered marker plate absent")
    for name in volume.names:
        require(native.geom(name).id >= 0, f"unmapped protection box: {name}")
    result = {}
    for name, (z0, z1) in baseline["depth_bands_m"].items():
        planes = old.cone_planes(camera, z0, z1)
        result[name] = {
            "range_m": [z0, z1],
            "protection": protection(old, volume, state, optical, planes),
            "native": native_witnesses(old, native, state, optical, planes),
        }
    # The contiguous core is open at shared depth limits for a new witness.
    for region in result.values():
        for key in ("native", "protection"):
            for row in region[key].values():
                new = row["sufficient_new_occupancy_witness"]
                if new:
                    z = float((np.asarray(new["point_world_m"]) - optical[:3, 3]) @ optical[:3, 2])
                    require(
                        region["range_m"][0] + TOL < z < region["range_m"][1] - TOL,
                        "shared face is not an interior witness",
                    )
    write(
        out / "geometry.json",
        {
            "original_1840_regression": True,
            "inputs_pose_checks": initial,
            "pixels_sha256": sha(out / "pixels.json"),
            "source_sha256": sha(Path(__file__)),
            "actual_optical_reject_preserved": True,
            "regions": result,
            "actual_native_continuous_sweep": "UNKNOWN_NO_SUBSTEP_OR_INTERPOLATION_RESIDUAL_BOUND",
            "fixed_pin": "NO_REGISTERED_SUPPORTED_T01_POSE_OR_1840_POSITIVE_NATIVE_PREDICTION",
            "new_integrations": 0,
            "new_exposures": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pixels", "geometry"))
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    old = old_reader()
    folder = OUT / PLAN["readback_subdirectory"] / args.reader
    folder.mkdir(parents=True, exist_ok=True)
    with patch.multiple(
        mujoco,
        Renderer=old.prohibited,
        mjr_render=old.prohibited,
        mj_step=old.prohibited,
        mj_step1=old.prohibited,
        mj_step2=old.prohibited,
    ):
        try:
            if args.mode == "pixels":
                pixel_stage(old, folder)
            else:
                geometry_stage(old, folder)
        except BaseException as error:
            write(
                folder / f"{args.mode}-failure.json",
                {"type": type(error).__name__, "message": str(error)},
            )
            raise
