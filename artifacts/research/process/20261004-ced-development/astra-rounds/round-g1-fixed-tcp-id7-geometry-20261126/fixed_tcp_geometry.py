"""Static registered-pose visibility with a fixed tool and unchanged camera."""
import argparse
from collections import Counter
from itertools import combinations, product
from pathlib import Path
import sys
from unittest.mock import patch

import cv2
import mujoco as mj
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "round-g1-release-camera-ab-20261126"))
from release_camera_ab_capture import ASSET, JOINTS, restore, verify_camera_model
from release_camera_ab_inputs import read, require, sha, verify_inputs

from cloud_edge_robot_arm.simulation.mujoco.motion_controller import _rotation_error
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    _SELF_COLLISION_ARM_GEOMS as ARM,
    _SELF_COLLISION_FINGER_GEOMS as FINGERS,
)

HERE = Path(__file__).resolve().parent
OBJECT = "object_geom"
CAB = ("plate", "crossbar", "upright")
LOAD = (OBJECT, *(f"g1_dual_id{i}_{name}" for i in (7, 8) for name in CAB))
ROBOT = (*ARM, *FINGERS)
SELF_PAIRS = [*(pair for pair in combinations(ARM, 2)
                if ARM.index(pair[1]) - ARM.index(pair[0]) >= 2),
              *product(ARM[:6], FINGERS)]
WORLD_PAIRS = [*product(ROBOT, (*LOAD, "table", "target_region_geom")), tuple(FINGERS)]
PAIRS = [*SELF_PAIRS, *WORLD_PAIRS]
POSITION = 1e-7
ANGLE = 1e-6
STATIC_GAP = 0.001
POSITION_MARGIN = 1e-9
VISIBILITY_TOL = 0.0002
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
CODES = np.asarray([cv2.aruco.generateImageMarker(DICT, i, 6) > 127 for i in range(50)])


def write(path, data):
    import json
    with path.open("x") as out:
        json.dump(data, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def preflight(plan):
    for name, expected in plan["sha256"].items():
        path = Path(name.format(**plan["roots"]))
        require(path.resolve().is_relative_to(Path.cwd()), f"unsafe input {path}")
        require(sha(path) == expected, f"digest mismatch {path}")
    manifest, slots, cal = verify_inputs()
    raw_b = Path(plan["roots"]["B"])
    require(manifest == read(raw_b / "input-manifest.json"), "A/B input manifest differs")
    sources = read(raw_b / "source-slots.json")
    for key, row in slots.items():
        require(row["source"] == sources[key], "A/B anchor provenance differs")
    return slots, cal, len(manifest)


def live_pairs(model, data):
    return {frozenset((model.geom(c.geom1).name, model.geom(c.geom2).name))
            for c in data.contact}


def t02_setup(plan, model, data, calibration):
    root = Path(plan["roots"]["t02"])
    indexed = read(root / "pixel-index.json")
    event, = [row for row in read(root / "local-clearance.json")["rows"]
              if row["physics_step"] == 1512 and row["phase"] == "FEEDBACK"]
    source, = [row for row in indexed["frames"] if row["frame_id"] == event["frame_id"]]
    sample, = [row for row in read(root / "offline-truth.json")["samples"]
               if row["physics_step"] == 1512]
    raw = root / source["file"]
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    require(sha(raw) == source["file_sha256"], "t02-frame bytes changed")
    frame = RGBDObservation.model_validate_json(raw.read_bytes())
    robot = event["robot"]
    require(frame.frame_id == source["frame_id"] == robot["frame_id"]
            and frame.episode_id == sample["episode_id"] == indexed["episode"]
            and frame.checksum_sha256 == source["checksum_sha256"] == robot["checksum_sha256"]
            and frame.sim_time_s == robot["camera_encoder_sim_time_s"] == sample["sim_time_s"]
            and source["physics_step"] == sample["physics_step"] == robot["physics_step"],
            "inconsistent t02 synchronized exposure")
    require(tuple(frame.intrinsics) == tuple(calibration["primary_camera"]["intrinsics"])
            and tuple(frame.camera_to_world) == tuple(calibration["primary_camera"]["camera_to_world"]),
            "t02 calibration differs")
    q = np.r_[robot["camera_joint_positions_rad"], robot["camera_finger_positions_m"]]
    dq = np.r_[sample["joint_velocities_rad_s"], sample["finger_velocities_m_s"]]
    for name, value, speed in zip(JOINTS, q, dq, strict=True):
        joint = model.joint(name)
        data.qpos[int(joint.qposadr[0])] = value
        data.qvel[int(joint.dofadr[0])] = speed
    joint = model.joint("object_free")
    adr = int(joint.qposadr[0])
    data.qpos[adr:adr+3] = sample["object_geom_position_m"]
    mujoco_orientation = np.asarray(sample["object_geom_rotation_row_major"], dtype=float)
    mj.mju_mat2Quat(data.qpos[adr+3:adr+7], mujoco_orientation)
    data.time = frame.sim_time_s
    mj.mj_forward(model, data)
    verify_camera_model(model, data, calibration)
    residual = float(np.linalg.norm(data.site("tcp").xpos - robot["tcp_position_m"]))
    require(residual <= POSITION_MARGIN, f"t02 camera TCP mismatch {residual}")
    require(np.linalg.norm(data.geom(OBJECT).xmat - mujoco_orientation) <= POSITION_MARGIN,
            "t02 object transform mismatch")
    ref = {(a,b): value for a,b,value in sample["self_collision_distances_m"]}
    current = {(a,b): mj.mj_geomDistance(model, data, model.geom(a).id, model.geom(b).id, np.inf, None)
               for a,b in SELF_PAIRS}
    require(ref.keys() == current.keys(), "t02 self-collision pairs differ")
    distance_error = max(abs(ref[p] - current[p]) for p in ref)
    require(distance_error <= 1e-7, f"t02 self-distance readback residual {distance_error}")
    expected = {frozenset(p) for p in sample["contact_pairs"]}
    require(expected == live_pairs(model, data), "t02 sampled contact categories differ")
    return {"camera_tcp_residual_m": residual, "self_distance_residual_m": distance_error,
            "frame_id": frame.frame_id, "frame_sha256": sha(raw), "source_time_s": data.time}


def projection_support(shape, axes, model, data, name):
    rotation = data.geom(name).xmat.reshape(3, 3)
    sizes = model.geom(name).size
    if shape == mj.mjtGeom.mjGEOM_BOX:
        return abs(axes @ rotation) @ sizes
    alignment = np.clip(abs(axes @ rotation[:,2]), 0, 1)
    if shape == mj.mjtGeom.mjGEOM_CAPSULE:
        return sizes[0] + sizes[1] * alignment
    if shape == mj.mjtGeom.mjGEOM_CYLINDER:
        return sizes[0] * np.sqrt(1 - alignment**2) + sizes[1] * alignment
    return np.full(len(axes), np.inf)


def distance(model, data, a, b):
    i, j = model.geom(a).id, model.geom(b).id
    estimated = float(mj.mj_geomDistance(model, data, i, j, np.inf, None))
    if np.isfinite(estimated) and estimated != 0:
        return estimated
    ra, rb = (data.geom(name).xmat.reshape(3, 3).T for name in (a,b))
    axes = np.vstack((np.eye(3), ra, rb, np.cross(ra[:,None], rb[None,:]).reshape(-1,3)))
    norm = np.linalg.norm(axes, axis=1)
    axes = axes[norm > 1e-10] / norm[norm > 1e-10,None]
    gap = (abs(axes @ (data.geom(a).xpos - data.geom(b).xpos))
           - projection_support(model.geom_type[i], axes, model, data, a)
           - projection_support(model.geom_type[j], axes, model, data, b))
    return float(max(0, gap.max()))


def screen(model, data, expected_contacts, fixed_gap):
    table = min((distance(model, data, a, b), a, b) for a,b in PAIRS if frozenset((a,b)) not in expected_contacts)
    gained_contact = live_pairs(model, data) - expected_contacts
    kept = expected_contacts <= live_pairs(model, data)
    lost_margin = any(distance(model, data, *pair) < value - POSITION
                      for pair,value in fixed_gap.items())
    return {"minimum_gap_m": table[0], "limiting_pair": list(table[1:]), "new_contact": bool(gained_contact),
            "allowed_contacts_preserved": bool(kept and not lost_margin),
            "pass": table[0] > STATIC_GAP and not gained_contact and kept and not lost_margin}


def pose(data):
    tcp = data.site("tcp")
    return tcp.xpos.copy(), tcp.xmat.reshape(3,3).copy()


def residuals(data, target):
    p, r = pose(data)
    quaternion = np.empty(4)
    mj.mju_mat2Quat(quaternion, target[1].ravel())
    return target[0] - p, _rotation_error(quaternion, r)


def jacobian(model, data, indices):
    p, r = (np.zeros((3, model.nv)) for _ in range(2))
    mj.mj_jacSite(model, data, p, r, model.site("tcp").id)
    return np.vstack((p[:,indices], 0.12 * r[:,indices]))


def solve(model, data, q, start, paddr, vaddr, axis, degrees, limits, target):
    data.qpos[paddr] = start
    data.qpos[paddr[axis]] = q[axis] + np.deg2rad(degrees)
    movable = [i for i in range(7) if i != axis]
    iteration_limit = limits["corrections_per_row"]
    for count in range(iteration_limit + 1):
        current = data.qpos[paddr]
        if (np.any(current <= model.jnt_range[:7,0]) or np.any(current >= model.jnt_range[:7,1])
                or np.max(abs(current - q)) > np.deg2rad(limits["excursion_deg"])):
            return None, count, "joint_limit_or_excursion"
        mj.mj_forward(model, data)
        xyz, rot = residuals(data, target)
        if np.linalg.norm(xyz) <= POSITION and np.linalg.norm(rot) <= ANGLE:
            return current.copy(), count, None
        if count == iteration_limit:
            break
        system = jacobian(model, data, vaddr)[:,movable]
        try:
            correction = np.linalg.solve(system, np.r_[xyz, 0.12*rot])
        except np.linalg.LinAlgError:
            return None, count, "singular_fixed_axis"
        limit = np.deg2rad(limits["maximum_correction_deg"])
        data.qpos[paddr[movable]] += correction * min(1., limit / max(np.max(abs(correction)), 1e-15))
    return None, iteration_limit, "fixed_tcp_solution_not_reached"


class Rays:
    def __init__(self, model, data, camera):
        self.model, self.data = model, data
        transform = np.asarray(camera["camera_to_world"]).reshape(4,4)
        self.eye, self.r = transform[:3,3], transform[:3,:3]
        self.focal = np.array(camera["intrinsics"][:2])
        self.center = np.array(camera["intrinsics"][2:])
        self.hit = np.empty(1, dtype=np.int32)
        self.cache = {}

    def cast(self, vector):
        distance = mj.mj_ray(self.model, self.data, self.eye, vector / np.linalg.norm(vector),
                            None, True, -1, self.hit)
        return float(distance), self.model.geom(int(self.hit[0])).name if distance >= 0 else None

    def pixel(self, x, y):
        if (x,y) not in self.cache:
            ray = self.r @ np.r_[(np.array([x,y]) - self.center) / self.focal, 1.]
            distance, name = self.cast(ray)
            self.cache[x,y] = distance / np.linalg.norm(ray), name
        return self.cache[x,y]

    def project(self, world):
        v = (world - self.eye) @ self.r
        return self.center + self.focal * v[:,:2] / v[:,2,None]

    def seen(self, world, marker):
        v = world - self.eye
        dist, name = self.cast(v)
        ok = bool(name and name.startswith(marker) and abs(dist-np.linalg.norm(v)) <= VISIBILITY_TOL)
        return ok, name

    def edges(self, marker, p, r):
        surface, across = r[:,2], r[:,1]
        counts = []
        for side in (-1,1):
            ends = np.array([p + 0.05*side*across + along*r[:,0] for along in (-.037,.037)])
            uv = self.project(ends)
            if abs(uv[1,0] - uv[0,0]) < 8:
                return [0,0]
            lo, hi = sorted(uv[:,0])
            sx = range(int(np.ceil(lo)), int(np.floor(hi)) + 1)
            slope = (uv[1,1]-uv[0,1]) / (uv[1,0]-uv[0,0])
            sign = int(np.sign(uv[:,1].mean() - self.project(p[None])[0,1]))
            if not sign:
                return [0,0]
            radius = max(4, int(np.ceil(0.016*self.focal[1]/abs((p-self.eye)@self.r[:,2]))))
            cols = []
            for x in sx:
                mid = int(np.rint(uv[0,1] + (x-uv[0,0])*slope))
                witnesses = 0
                for y in range(mid-radius, mid+radius+1):
                    coords = (y-sign,y-2*sign,y,y+sign)
                    if not (1 <= x < 319 and all(0 <= k < 240 for k in coords)):
                        continue
                    for i, k in enumerate(coords):
                        direction = self.r @ np.r_[(np.array([x,k])-self.center)/self.focal,1.]
                        plane = ((p - self.eye) @ surface) / (direction @ surface)
                        z, name = self.pixel(x,k)
                        if i < 2:
                            if not(name and name.startswith(marker) and abs(z-plane)<0.004):
                                break
                        elif not z > plane + 0.006:
                            break
                    else:
                        witnesses += 1
                if witnesses == 1:
                    cols.append(x)
            counts.append(len(cols) if cols and max(cols)-min(cols) >= 4 else 0)
        return counts

    def measure(self, code):
        marker = f"g1_dual_id{code}_"
        white = self.data.geom(marker+"quiet")
        r = white.xmat.reshape(3,3)
        p = white.xpos + self.model.geom(marker+"quiet").size[2] * r[:,2]
        require((self.eye-p) @ r[:,2] > 0, "reverse camera-facing code")
        grid = ((np.arange(32)+.5)/32-.5)*0.075
        counts = Counter()
        for x,y in product(grid,repeat=2):
            point = p + r @ [x,y,0]
            u,v = self.project(point[None])[0]
            if 0 <= u < 319 and 0 <= v < 239:
                ok, blocking = self.seen(point, marker)
                counts["visible" if ok else blocking or "unreturned"] += 1
            else:
                counts["out_of_view"] += 1
        seen = np.zeros((6,6),dtype=bool)
        printed = np.zeros((6,6),dtype=bool)
        for y,x in product(range(6),repeat=2):
            name = f"{marker}r{y}c{x}"
            cell = self.data.geom(name)
            printed[y,x] = self.model.geom(name).rgba[0] > 0.5
            seen[y,x] = self.seen(cell.xpos + self.model.geom(name).size[2]*r[:,2], marker)[0]
        require(np.array_equal(printed,CODES[code]), "native code grid order differs")
        seen_inner = seen[1:5,1:5]
        ideal_ids = [[idx,k*90] for idx, grid in enumerate(CODES)
                     for k in range(4) if np.array_equal(np.rot90(grid,k)[1:5,1:5][seen_inner],
                                                         printed[1:5,1:5][seen_inner])]
        return {"first_hits": dict(counts), "visible": counts["visible"], "visible_cells": np.argwhere(seen).tolist(),
                "compatible_dictionary_orientations": ideal_ids, "depth_only_edge_columns": self.edges(marker,p,r)}


def scan_case(model, data, name, state, cal, limits):
    all_joints = [model.joint(f"joint{i}") for i in range(1,8)]
    pos = np.array([int(j.qposadr[0]) for j in all_joints])
    vel = np.array([int(j.dofadr[0]) for j in all_joints])
    base = data.qpos[pos].copy()
    target = pose(data)
    contacts = live_pairs(model,data)
    permitted = {frozenset((OBJECT,"table"))}
    if name.startswith("train"):
        permitted.update(frozenset((OBJECT,finger)) for finger in FINGERS)
    require(contacts <= permitted, "unregistered original contact")
    fixed_gaps = {pair:distance(model,data,*pair) for pair in contacts}
    _, sigma, vectors = np.linalg.svd(jacobian(model,data,vel), full_matrices=True)
    axis = int(np.argmax(abs(vectors[-1])))
    checks = {0: identity_row(model, data, contacts, fixed_gaps, cal, target)}
    clock = float(data.time)
    for seq in ((-2,-4,-6),(2,4,6)):
        start = base
        retry = sigma[-1] > sigma[0]*1e-9
        for degrees in seq:
            if retry:
                solution,count,reason = solve(model,data,base,start,pos,vel,axis,degrees,limits,target)
                retry = solution is not None
            else:
                count, reason = 0, "rank_or_preceding_fit_unavailable"
            if retry:
                checks[degrees] = identity_row(model, data, contacts, fixed_gaps, cal, target)
                checks[degrees]["scientific_use"] = "static_only"
                start = solution
            else:
                checks[degrees] = {"unavailable":reason}
            checks[degrees]["corrections"] = count
    require(data.time == clock, "static scan advanced source clock")
    return {"source":state, "axis":JOINTS[axis], "jacobian_singular":sigma.tolist(),
            "per_offset_deg":{str(k): checks[k] for k in sorted(checks)}}


def identity_row(model, data, contacts, fixed_gaps, cal, target):
    collision = screen(model,data,contacts,fixed_gaps)
    p,r = residuals(data,target)
    row = {"tcp_position_error_m":float(np.linalg.norm(p)), "tcp_rotation_error_rad":float(np.linalg.norm(r)),
           "static_collision":collision}
    if collision["pass"]:
        rays = Rays(model,data,cal["primary_camera"])
        row["markers"]={str(k):rays.measure(k) for k in (7,8)}
    return row


def run(plan):
    slots, cal, count = preflight(plan)
    require(mj.__version__ == "3.3.7", "wrong geometry engine")
    model = mj.MjModel.from_xml_path(str(ASSET))
    model.opt.timestep = 1/240
    rows = {}
    for label,ticks in plan["states"].items():
        for tick in ticks:
            name = f"{label}/{tick}"
            data = mj.MjData(model)
            if label.startswith("B/"):
                source = restore(model,data,slots[name],cal)
            else:
                require(tick == 1512 and label.endswith("cvfix-t02"), "unexpected LIFT case")
                source = t02_setup(plan,model,data,cal)
            rows[name] = scan_case(model,data,name,source,cal,plan["limits"])
    require(sum(len(row["per_offset_deg"]) for row in rows.values()) == plan["limits"]["rows"], "unaccounted grid")
    return {"A_B_manifest_files":count,"plan_sha256":sha(HERE/"plan.json"),
            "driver_sha256":sha(Path(__file__)),"states":rows,"integration_steps":0,"renders":0}


def forbidden(*args, **kwargs):
    raise RuntimeError("static calculation cannot integrate")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with patch.object(mj,"mj_step",forbidden), patch.object(mj,"mj_step1",forbidden), patch.object(mj,"mj_step2",forbidden):
        write(args.output,run(read(HERE/"plan.json")))
