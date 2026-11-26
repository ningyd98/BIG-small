"""Bound the registered first face on each sealed dense ray using optical state only."""

import os
import sys
from itertools import product
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha, write

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
OUT = ROOT / PLAN["out"]
DENSE = ROOT / PLAN["original_dense"]
ASSET = ROOT / PLAN["asset"]
OPTICAL = DENSE / "optical-input.json"
REFERENCE = DENSE / "prediction.json"
RESULT = OUT / "geometry.json"
EPS = 1e-9
BOX = int(mujoco.mjtGeom.mjGEOM_BOX)
CAPSULE = int(mujoco.mjtGeom.mjGEOM_CAPSULE)
CYLINDER = int(mujoco.mjtGeom.mjGEOM_CYLINDER)
SPHERE = int(mujoco.mjtGeom.mjGEOM_SPHERE)
GROUPS = mujoco.MjvOption().geomgroup.copy()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def bound_pred_inputs():
    raw_root = ROOT / "experiments/results"
    allowed = {OPTICAL, REFERENCE, ASSET, RESULT}

    def guard(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(raw_root) and path not in allowed:
                raise PermissionError(f"data outside blind optical input: {path.name}")

    sys.addaudithook(guard)
    denied = 0
    for denied_path in (DENSE / PLAN["physical_source"], DENSE / "readback.json"):
        try:
            denied_path.read_bytes()
        except PermissionError:
            denied += 1
        else:
            raise ValueError("prediction accessed an outcome or physical label")
    for p in (OPTICAL, REFERENCE, ASSET):
        require(sha(p) == PLAN["sha256"][p.relative_to(ROOT).as_posix()], "unbound optical input")
    return denied


def camera_state(model, job):
    pose = job["optical"]
    center = np.asarray(pose["center_m"])
    rotation = np.asarray(pose["rotation"])
    anchor = np.asarray(pose["anchor_object_m"])
    error = np.asarray(pose["anchor_error_object_m"])
    basis = np.asarray(pose["basis_error_object"])
    require(
        (pose["frame_id"], pose["checksum_sha256"]) == (job["frame_id"], job["checksum_sha256"])
        and rotation.shape == basis.shape == (3, 3)
        and center.shape == anchor.shape == error.shape == (3,)
        and np.isfinite(np.r_[center, anchor, error, basis.ravel(), rotation.ravel()]).all()
        and np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-9)
        and abs(np.linalg.det(rotation) - 1.0) < EPS
        and np.allclose(center + rotation @ anchor, pose["anchor_world_m"], rtol=0, atol=EPS)
        and (error >= 0).all()
        and (basis >= 0).all(),
        "pose anchor, rotation or complete direction error not bound",
    )
    data = mujoco.MjData(model)
    names = [f"joint{i}" for i in range(1, 8)] + ["finger_left_joint", "finger_right_joint"]
    indices = [model.joint(name).qposadr[0] for name in names]
    free = model.joint("object_free").qposadr[0]
    require(
        set(indices) | set(range(free, free + 7)) == set(range(model.nq)) and model.nq == 16,
        "unknown active geometry state",
    )
    encoders = np.asarray(job["joints_rad"] + job["fingers_m"])
    require(encoders.shape == (9,) and np.isfinite(encoders).all(), "unbounded robot encoders")
    data.qpos[indices] = encoders
    data.qpos[free : free + 3] = center
    mujoco.mju_mat2Quat(data.qpos[free + 3 : free + 7], rotation.ravel())
    data.time = job["time_s"]
    saved = data.qpos.copy()
    mujoco.mj_kinematics(model, data)
    require(
        np.array_equal(saved, data.qpos)
        and data.time == job["time_s"]
        and np.allclose(data.body("object").xpos, center, rtol=0, atol=EPS)
        and np.allclose(data.body("object").xmat.reshape(3, 3), rotation, rtol=0, atol=EPS),
        "nominal kinematic state differs from input",
    )
    return data, (center, rotation, anchor, error, basis)


def box_half(shape, size):
    if shape == BOX:
        return size
    if shape == CAPSULE:
        return np.array([size[0], size[0], size[1] + size[0]])
    if shape == CYLINDER:
        return np.array([size[0], size[0], size[1]])
    if shape == SPHERE:
        return np.repeat(size[0], 3)
    raise ValueError(f"unsupported first-surface competitor shape {shape}")


def slab(start, slope, half):
    """Intersection of nominal ray with conservative outer boxes."""
    parallel = slope == 0
    denominator = np.where(parallel, 1.0, slope)
    lo, hi = (-half - start) / denominator, (half - start) / denominator
    first = np.where(parallel, -np.inf, np.minimum(lo, hi))
    last = np.where(parallel, np.inf, np.maximum(lo, hi))
    hit = (~np.any(parallel & (abs(start) > half), axis=1)) & (
        last.min(1) >= np.maximum(first.max(1), 0.0)
    )
    return np.where(hit, np.maximum(first.max(1), 0.0), np.inf), first


class SurfaceBounds:
    def __init__(self, model, data, pose):
        self.model, self.data = model, data
        self.center, self.rotation, self.anchor, self.anchor_err, self.basis = pose
        self.centers = np.vstack((data.geom_xpos, data.site_xpos))
        self.rotations = np.concatenate((data.geom_xmat, data.site_xmat)).reshape(-1, 3, 3)
        kinds = np.r_[model.geom_type, model.site_type]
        self.half = np.stack(
            [
                box_half(int(k), sz)
                for k, sz in zip(kinds, np.vstack((model.geom_size, model.site_size)), strict=True)
            ]
        )
        self.names = [model.geom(i).name for i in range(model.ngeom)] + [
            "site/" + model.site(i).name for i in range(model.nsite)
        ]
        self.load = np.flatnonzero(model.geom_bodyid == model.body("object").id)
        self.variable = set(map(int, self.load))
        require(
            np.all(model.geom_type[self.load] == BOX)
            and np.array_equal(
                model.geom_quat[self.load], np.tile([1, 0, 0, 0], (len(self.load), 1))
            ),
            "unexpected carried surface orientation or geometry",
        )
        p = np.abs(model.geom_pos[self.load] - self.anchor) + self.half[self.load]
        distances = np.zeros_like(self.half)
        distances[self.load] = self.anchor_err + p @ self.basis.T
        self.uncertainty = distances

    def bounds_on_box_face(self, eye, ray, z_nom, geom, axis, sign, factor):
        contact_nom = eye + z_nom * ray
        if geom in self.variable:
            # Rebase at the nominal hit to avoid loss of the origin/velocity dependence.
            # In nominal load axes actual inverse rotation is (I + E).T.
            local = (contact_nom - self.center) @ self.rotation
            base = local - self.model.geom_pos[geom]
            velocity = ray @ self.rotation
            anchor_error = self.anchor_err * factor
            rotation_error = self.basis * factor
            err = anchor_error + (abs(local - self.anchor) + anchor_error) @ rotation_error
            slope_err = abs(velocity) @ rotation_error
        else:
            base = (contact_nom - self.centers[geom]) @ self.rotations[geom]
            velocity = ray @ self.rotations[geom]
            err, slope_err = np.zeros(3), np.zeros(3)

        lo, hi = base - err - EPS, base + err + EPS
        d_lo, d_hi = velocity - slope_err - EPS, velocity + slope_err + EPS
        incoming = -d_hi[axis] if sign == 1 else d_lo[axis]
        if incoming / np.linalg.norm(ray) <= PLAN["min_incidence"]:
            return {"reason": "incidence_or_direction", "minimum_incidence": float(incoming)}
        face = self.half[geom, axis] * sign
        roots = [(face - p) / v for p, v in product((lo[axis], hi[axis]), (d_lo[axis], d_hi[axis]))]
        t0, t1 = min(roots) - EPS, max(roots) + EPS
        combinations = np.stack([a * x for a, x in product((d_lo, d_hi), (t0, t1))])
        lower = lo + combinations.min(0)
        upper = hi + combinations.max(0)
        local_margin = self.half[geom] - np.maximum(abs(lower), abs(upper))
        margin = float(np.delete(local_margin, axis).min())
        return {
            "signed_face": [self.names[geom], int(axis), sign],
            "axis_depth_interval_m": [float(z_nom + t0), float(z_nom + t1)],
            "face_boundary_margin_m": margin,
            "minimum_incidence": float(incoming),
            "reason": "face_boundary" if margin <= EPS else None,
        }

    def first_face(self, eye, ray, factor):
        normalized = ray / np.linalg.norm(ray)
        target = np.array([-1], dtype=np.int32)
        distance = mujoco.mj_ray(self.model, self.data, eye, normalized, GROUPS, 1, -1, target)
        geom = int(target[0])
        if distance <= 0 or geom < 0:
            return {"reason": "no_nominal_return"}
        z_nom = float(distance / np.linalg.norm(ray))
        name = self.names[geom]
        if int(self.model.geom_type[geom]) != BOX:
            return {
                "reason": "non_planar_registered_geometry",
                "nominal_geom": name,
                "nominal_m": z_nom,
            }

        rel = np.einsum("ni,nij->nj", eye - self.centers, self.rotations)
        directions = np.einsum("i,nij->nj", ray, self.rotations)
        _, nominal = slab(
            rel[geom : geom + 1], directions[geom : geom + 1], self.half[geom : geom + 1]
        )
        axis = int(nominal[0].argmax())
        require(abs(nominal[0, axis] - z_nom) < 1e-7, "native nominal box slab differs")
        sign = -1 if directions[geom, axis] > 0 else 1
        face = self.bounds_on_box_face(eye, ray, z_nom, geom, axis, sign, factor)
        lower, _ = slab(rel, directions, self.half + factor * self.uncertainty + EPS)
        lower[geom] = np.inf
        competing = int(lower.argmin())
        possible = float(lower[competing])
        outcome = face["reason"]
        if outcome is None and possible <= face["axis_depth_interval_m"][1] + EPS:
            outcome = "competitor_overlap"
        return face | {
            "reason": outcome,
            "nominal_geom": name,
            "nominal_m": z_nom,
            "closest_competitor": self.names[competing] if np.isfinite(possible) else None,
            "closest_competitor_outer_entry_m": possible if np.isfinite(possible) else None,
        }


def ray_directions(camera):
    rot = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    fx, fy = np.asarray(camera["intrinsics"][:2]) * PLAN["scale"]
    width, height = PLAN["dense_size"]
    cx, cy = (width - 1) / 2, (height - 1) / 2
    return rot[:3, 3].copy(), lambda u, v: rot[:3, :3] @ [(u - cx) / fx, (v - cy) / fy, 1.0]


def registered_coordinates(row):
    coordinates = {
        (point["uv"][0] + i, point["uv"][1] + j)
        for pixel in row["pixels"]
        for point in pixel["subpixels"]
        for i, j in product((-1, 0, 1), repeat=2)
    }
    return sorted(coordinates, key=lambda coord: (coord[1], coord[0]))


def forbid(*_args, **_kwargs):
    raise RuntimeError("the frozen geometry diagnostic cannot integrate or render")


def run():
    blocked = bound_pred_inputs()
    source, predictions = read(OPTICAL), read(REFERENCE)
    require(
        predictions["optical_input_sha256"] == sha(OPTICAL)
        and source["assembly_sha256"] == sha(ASSET)
        and [job["key"] for job in source["jobs"]]
        == [row["key"] for row in predictions["predictions"]],
        "optical prediction detached from archive",
    )
    OUT.mkdir(exist_ok=False)
    rows, increased_bound_losses = [], 0
    with patch.multiple(
        mujoco,
        mj_step=forbid,
        mj_step1=forbid,
        mj_step2=forbid,
        Renderer=forbid,
        mjr_render=forbid,
    ):
        model = mujoco.MjModel.from_xml_path(str(ASSET))
        eye, direction = ray_directions(source["camera"])
        for job, predicted in zip(source["jobs"], predictions["predictions"], strict=True):
            require(
                job["checksum_sha256"] == predicted["shutter_checksum_sha256"]
                and job["pixels_original_uv"] == [x["original_uv"] for x in predicted["pixels"]],
                "wrong frame or unchecked dense patch",
            )
            state, pose = camera_state(model, job)
            frame = SurfaceBounds(model, state, pose)
            samples = []
            for u, v in registered_coordinates(predicted):
                ray = direction(u, v)
                bound = frame.first_face(eye, ray, factor=1.0)
                expanded = frame.first_face(eye, ray, factor=PLAN["control_expansion"])
                require(
                    bound["reason"] is None or expanded["reason"] is not None,
                    "expanded uncertainty promoted a first-face proof",
                )
                increased_bound_losses += int(
                    bound["reason"] is None and expanded["reason"] is not None
                )
                samples.append(
                    bound | {"uv": [u, v], "expanded_control_reason": expanded["reason"]}
                )
            rows.append(
                {
                    "key": job["key"],
                    "source_frame_id": job["frame_id"],
                    "source_checksum_sha256": job["checksum_sha256"],
                    "rays": samples,
                }
            )
    write(
        RESULT,
        {
            "plan_sha256": sha(PLAN_PATH),
            "optical_input_sha256": sha(OPTICAL),
            "sealed_prediction_sha256": sha(REFERENCE),
            "source_sha256": sha(Path(__file__)),
            "rows": rows,
            "denied_file_controls": blocked,
            "proofs_lost_after_bound_expansion": increased_bound_losses,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    run()
