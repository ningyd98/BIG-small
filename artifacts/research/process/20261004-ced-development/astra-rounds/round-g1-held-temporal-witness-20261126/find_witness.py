"""Find two fully feasible held poses with different first surfaces on one ray."""

import argparse
import gzip
import json
import sys
from itertools import combinations
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.perception_io import ROOT, read, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "plan.json"
PLAN = read(PLAN_FILE)
OUT = ROOT / PLAN["output"]
BOX = int(mujoco.mjtGeom.mjGEOM_BOX)
GROUPS = mujoco.MjvOption().geomgroup.copy()
ANCHOR_MARGIN = PLAN["minimum_anchor_constraint_margin_m"]
ROT_MARGIN = PLAN["minimum_rotation_constraint_margin"]
METHODS = {"both", "id8_opposite_edges", "id8_opposite_ink"}
STRIDE = PLAN["capture_stride"]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pinned(base, relative, digest):
    p = base / relative
    require(p.resolve(strict=True) == p and p.is_relative_to(base), f"redirected input: {p}")
    require(sha(p) == digest, f"changed input: {p}")
    return p


def seal_access():
    banned = (
        "offline-physics",
        "offline-truth",
        "original-stops-01",
        "needle-witness",
        "physically_added_tip",
        "capture-input.json",
        "cvfix-e01",
        "cvfix-e02",
    )

    def audit(event, args):
        if (
            event == "open"
            and isinstance(args[0], (str, bytes))
            and any(s in str(args[0]) for s in banned)
        ):
            raise PermissionError("physical object labels and controls are isolated")

    sys.addaudithook(audit)
    for name in ("offline-physics.json", "needle-witness.json"):
        try:
            Path(name).read_bytes()
        except PermissionError:
            continue
        raise ValueError("failed label isolation control")


def read_slot(family, case):
    root = ROOT / PLAN["captures"][family]
    seal = read(root / "seal.json")
    members = seal["sealed_sha256"]
    registration = read(pinned(root, "registration.json", seal["registration_sha256"]))

    def item(name):
        p = f"{case}/{name}"
        return read(pinned(root, p, members[p]))

    gates = item("clearance-gate.json")["checks"]
    index = item("rgbd-index.json")
    receipt = item("sensor-receipt.json")
    commands = item("native-commands.json")
    require(
        index["episode_id"] == receipt["episode_id"]
        and index["scene_id"] == receipt["scene_id"]
        and receipt["index_sha256"] == members[f"{case}/rgbd-index.json"]
        and receipt["registration_sha256"] == seal["registration_sha256"],
        "native reset and gates are not bound",
    )
    return root, registration["camera"], members, gates, index, commands


def eligible_chain(items):
    current, seen = [], set()
    for item in items:
        if item["frame_id"] in seen:
            current = []
            continue
        seen.add(item["frame_id"])
        if not item["eligible"]:
            current = []
            continue
        if current and (
            item["tick"] - current[-1]["tick"] != STRIDE
            or item["scene_episode"] != current[-1]["scene_episode"]
        ):
            current = []
        current.append(item)
    return current


def history(rig, family, case, last_tick):
    root, camera, members, gates, index, commands = read_slot(family, case)
    by_frame = {x["robot"]["frame_id"]: x for x in index["rows"]}
    require(len(by_frame) == len(index["rows"]), "repeated exposure on original index")
    result = []
    for g in gates:
        if (g["skill"], g["phase"]) != ("LIFT", "FEEDBACK") or g["step"] > last_tick:
            continue
        row = by_frame[g["frame_id"]]
        robot = row["robot"]
        path = f"{case}/{row['file']}"
        require(members[path] == row["file_sha256"], "frame not in capture seal")
        raw = pinned(root, path, members[path])
        frame = RGBDObservation.model_validate_json(gzip.decompress(raw.read_bytes()))
        require(
            frame.frame_id == robot["frame_id"] == g["frame_id"]
            and frame.checksum_sha256 == robot["checksum_sha256"] == g["checksum_sha256"]
            and frame.episode_id == index["episode_id"]
            and frame.scene_id == index["scene_id"]
            and frame.sim_time_s == robot["camera_encoder_sim_time_s"] == robot["sim_time_s"]
            and abs(frame.sim_time_s - g["step"] / PLAN["native_physics_hz"]) < 1e-9
            and robot["physics_step"] == g["step"]
            and frame.model_dump(include=set(camera), mode="json") == camera,
            "exposure/encoder/camera binding failed",
        )
        observed = g["current"]["payload_observation"]
        pose = observed["pose"]
        command_seq = robot["native_last_command_seq"]
        commands_so_far = [
            c
            for c in commands
            if c["command_seq"] <= command_seq and c["accepted"] and c["type"] == "gripper"
        ]
        cmd = commands_so_far[-1]
        eligible = (
            pose is not None
            and pose["method"] in METHODS
            and observed["relation"] == "held"
            and cmd["target_open"] is False
            and robot["last_accepted_gripper_open"] is False
            and cmd["physics_step"] == robot["last_accepted_gripper_command_step"]
            and cmd["episode_id"] == frame.episode_id
        )
        measure = {
            "frame_id": g["frame_id"],
            "checksum_sha256": g["checksum_sha256"],
            "scene_episode": [frame.scene_id, frame.episode_id],
            "tick": g["step"],
            "eligible": eligible,
        }
        if eligible:
            measured_r = np.asarray(pose["rotation"])
            center, anchor, world_anchor = (
                np.asarray(pose[k]) for k in ("center_m", "anchor_object_m", "anchor_world_m")
            )
            tcp, wrist, _ = rig.forward(np.asarray(robot["camera_joint_positions_rad"]))
            require(
                pose["frame_id"] == frame.frame_id
                and pose["checksum_sha256"] == frame.checksum_sha256
                and np.max(np.abs(center + measured_r @ anchor - world_anchor)) <= 1e-9
                and np.allclose(measured_r.T @ measured_r, np.eye(3), atol=1e-10, rtol=0)
                and np.linalg.det(measured_r) > 0.999999999,
                "pose basis, anchor or current exposure lost",
            )
            measure.update(
                tcp=tcp,
                wrist=wrist,
                anchor=anchor,
                anchor_world=world_anchor,
                estimated_rotation=measured_r,
                base=measured_r.T @ wrist,
                relative=wrist.T @ measured_r,
                err=np.asarray(pose["anchor_error_object_m"]),
                basis_err=np.asarray(pose["basis_error_object"]),
                joints=robot["camera_joint_positions_rad"],
                fingers=robot["camera_finger_positions_m"],
            )
        result.append(measure)
    chain = eligible_chain(result)
    require(chain and chain[-1]["tick"] == last_tick, "endpoint has no original held evidence")
    return camera, chain


def translation_system(frames, relative_r):
    normals, bounds = [], []
    for item in frames:
        base = item["base"]
        offset = item["tcp"] + item["wrist"] @ relative_r @ item["anchor"] - item["anchor_world"]
        origin = item["estimated_rotation"].T @ offset
        normals.extend((base, -base))
        bounds.extend((item["err"] - origin, item["err"] + origin))
    return np.concatenate(normals), np.concatenate(bounds)


def verify_pose(frames, rel_rot, translation):
    anchor_margins, rot_margins = [], []
    for item in frames:
        rotation = item["wrist"] @ rel_rot
        center = item["wrist"] @ translation + item["tcp"]
        anchor_residual = item["estimated_rotation"].T @ (
            center + rotation @ item["anchor"] - item["anchor_world"]
        )
        matrix_residual = item["estimated_rotation"].T @ rotation - np.eye(3)
        anchor_margins.append(float((item["err"] - np.abs(anchor_residual)).min()))
        rot_margins.append(float((item["basis_err"] - np.abs(matrix_residual)).min()))
    return min(anchor_margins), min(rot_margins)


def feasible_points(frames, rotation):
    if any(
        np.min(x["basis_err"] - abs(x["base"] @ rotation - np.eye(3))) <= ROT_MARGIN for x in frames
    ):
        return []
    normals, b = translation_system(frames, rotation)
    triples = np.array(list(combinations(range(len(b)), 3)))
    blocks = normals[triples]
    good = abs(np.linalg.det(blocks)) > 1e-9
    verts = np.linalg.solve(blocks[good], b[triples[good]][..., None])[..., 0]
    verts = verts[np.all(verts @ normals.T <= b + 1e-10, axis=1)]
    if not len(verts):
        return []
    inner = verts.mean(0)
    # Keep extremal candidates strictly inside all original half spaces.
    points = np.vstack((inner, verts * 0.999 + 0.001 * inner))
    return np.unique(points.round(12), axis=0)


def lifetime(frames, rotation, translation):
    count = 0
    for frame in reversed(frames):
        a, r = verify_pose([frame], rotation, translation)
        if a <= ANCHOR_MARGIN or r <= ROT_MARGIN:
            break
        count += 1
    return count


class StaticRays:
    def __init__(self, model, camera, frame, coordinates):
        self.model = model
        self.data = mujoco.MjData(model)
        names = [f"joint{i}" for i in range(1, 8)] + ["finger_left_joint", "finger_right_joint"]
        idx = [int(model.joint(n).qposadr[0]) for n in names]
        self.addr = int(model.joint("object_free").qposadr[0])
        self.data.qpos[idx] = frame["joints"] + frame["fingers"]
        tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
        self.eye = tf[:3, 3].copy()
        fx, fy = np.asarray(camera["intrinsics"][:2]) * 4
        coords = np.asarray(coordinates)
        image = (coords - [(camera["width"] * 4 - 1) / 2, (camera["height"] * 4 - 1) / 2]) / [
            fx,
            fy,
        ]
        directions = np.column_stack((image, np.ones(len(coords)))) @ tf[:3, :3].T
        self.unit = directions / np.linalg.norm(directions, axis=1, keepdims=True)
        self.frame = frame
        self.geom = [
            i for i in range(model.ngeom) if GROUPS[min(5, max(0, int(model.geom_group[i])))]
        ]
        self.load = int(model.body("object").id)

    def place(self, rotation, position):
        d, m, j = self.data, self.model, self.addr
        r = self.frame["wrist"] @ rotation
        c = self.frame["tcp"] + self.frame["wrist"] @ position
        d.qpos[j : j + 3] = c
        mujoco.mju_mat2Quat(d.qpos[j + 3 : j + 7], r.ravel())
        mujoco.mj_kinematics(m, d)
        require(
            np.max(np.abs(d.xmat[self.load].reshape(3, 3) - r)) <= 1e-10
            and np.max(np.abs(d.xpos[self.load] - c)) <= 1e-10,
            "restored orientation or position differs",
        )
        require(
            np.max(np.abs(d.site("tcp").xpos - self.frame["tcp"])) <= 1e-9, "FK position differs"
        )

    def measure(self, i, exclude=None):
        ray = self.unit[i]
        m, d = self.model, self.data
        idx = np.array([-1], dtype=np.int32)
        distance = float(mujoco.mj_ray(m, d, self.eye, ray, GROUPS, 1, -1, idx))
        g = int(idx[0])
        if distance <= 0 or g < 0 or m.geom_type[g] != BOX:
            return None
        name = m.geom(g).name
        # The witness only compares materially different registered surfaces.
        if name == exclude:
            return None
        hit = self.eye + ray * distance
        orientation = d.geom_xmat[g].reshape(3, 3)
        point = (hit - d.geom_xpos[g]) @ orientation
        margins = m.geom_size[g] - abs(point)
        axis = int(abs(margins).argmin())
        transverse = float(np.delete(margins, axis).min())
        if transverse <= PLAN["minimum_face_edge_margin_m"] or abs(margins[axis]) > 1e-8:
            return None
        sign = int(np.sign(point[axis]))
        if -sign * (ray @ orientation)[axis] <= 1e-3:
            return None
        others = [
            mujoco.mju_rayGeom(
                d.geom_xpos[k], d.geom_xmat[k], m.geom_size[k], self.eye, ray, int(m.geom_type[k])
            )
            for k in self.geom
            if k != g
        ]
        for k in range(m.nsite):
            if GROUPS[min(5, max(0, int(m.site_group[k])))]:
                others.append(
                    mujoco.mju_rayGeom(
                        d.site_xpos[k],
                        d.site_xmat[k],
                        m.site_size[k],
                        self.eye,
                        ray,
                        int(m.site_type[k]),
                    )
                )
        next_distance = min((x for x in others if x >= 0), default=float("inf"))
        lead = next_distance - distance
        if lead <= PLAN["minimum_first_hit_lead_m"]:
            return None
        return {
            "geom": name,
            "face_axis": axis,
            "face_sign": sign,
            "ray_length_m": distance,
            "side_margin_m": transverse,
            "competing_surface_lead_m": lead if np.isfinite(lead) else None,
        }


def witness_search(scanner, frames, windows, coordinates):
    observations = []
    for length in windows:
        if len(frames) < length:
            observations.append({"window": length, "status": "insufficient_history"})
            continue
        window = frames[-length:]
        hits = [{} for _ in coordinates]
        total = 0
        for center_row in window:
            rotation = center_row["relative"]
            for pos in feasible_points(window, rotation):
                margin, rot_margin = verify_pose(window, rotation, pos)
                if margin <= ANCHOR_MARGIN or rot_margin <= ROT_MARGIN:
                    continue
                total += 1
                suffix = lifetime(frames, rotation, pos)
                scanner.place(rotation, pos)
                for i, known in enumerate(hits):
                    if (
                        known
                        and min(w["validated_history_frames"] for w in known.values()) >= suffix
                    ):
                        if len(known) >= 2:
                            continue
                        exclude = next(iter(known))
                    else:
                        exclude = None
                    face = scanner.measure(i, exclude)
                    if face is None or (
                        face["geom"] in known
                        and known[face["geom"]]["validated_history_frames"] >= suffix
                    ):
                        continue
                    known[face["geom"]] = face | {
                        "rotation": rotation.tolist(),
                        "translation_m": pos.tolist(),
                        "strict_anchor_margin_m": margin,
                        "strict_basis_margin": rot_margin,
                        "validated_history_frames": suffix,
                    }
        disagreements = []
        for uv, row in zip(coordinates, hits, strict=True):
            if len(row) >= 2:
                two = sorted(row.values(), key=lambda r: -r["validated_history_frames"])[:2]
                disagreements.append((uv, two, min(v["validated_history_frames"] for v in two)))
        strongest = max(disagreements, key=lambda r: r[2]) if disagreements else None
        observations.append(
            {
                "window": length,
                "status": "opposite_first_faces" if disagreements else "unknown",
                "tested_feasible_transforms": total,
                "tracked_rays": len(coordinates),
                "witnessed_ray_count": len(disagreements),
                "witnessed_coordinates_uv": [row[0] for row in disagreements],
                "max_sealed_anchor_history_frames_validated": strongest[2] if strongest else None,
                "example": {"uv": strongest[0], "witnesses": strongest[1]} if strongest else None,
            }
        )
    return observations


def controls():
    def row(tick, eligible=True, identity="A"):
        return dict(tick=tick, frame_id=f"id-{tick}", eligible=eligible, scene_episode=identity)

    result = {
        "continuous_three": len(eligible_chain([row(0), row(8), row(16)])) == 3,
        "missing_frame_resets": len(eligible_chain([row(0), row(16)])) == 1,
        "reorder_resets": len(eligible_chain([row(8), row(0)])) == 1,
        "foreign_episode_resets": len(eligible_chain([row(0), row(8, identity="B")])) == 1,
        "repeat_never_narrows": len(eligible_chain([row(0), row(8), row(8), row(16)])) == 1,
        "open_or_unqualified_resets": len(eligible_chain([row(0), row(8, False), row(16)])) == 1,
    }

    def pose(anchor_world):
        return dict(
            base=np.eye(3),
            wrist=np.eye(3),
            estimated_rotation=np.eye(3),
            tcp=np.zeros(3),
            anchor=np.zeros(3),
            anchor_world=np.asarray(anchor_world),
            err=np.full(3, 0.001),
            basis_err=np.full((3, 3), 0.01),
        )

    a, b = pose([0, 0, 0]), pose([0.005, 0, 0])
    result["nonzero_slip_disagrees_with_zero"] = (
        len(feasible_points([a], np.eye(3))) > 0 and len(feasible_points([a, b], np.eye(3))) == 0
    )
    require(all(result.values()), "failed witness controls")
    return result


def save(name, result):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", choices=("prediction.json", "prediction.cold.json"))
    name = p.parse_args().name
    seal_access()
    for path, digest in PLAN["sha256"].items():
        pinned(ROOT, path, digest)
    local_controls = controls()
    asset = ROOT / PLAN["asset"]
    rig = Model(asset)
    model = mujoco.MjModel.from_xml_path(str(asset))
    optical = {r["frame_id"]: r for r in read(ROOT / PLAN["optical"])["jobs"]}
    rays = {r["key"]: r for r in read(ROOT / PLAN["registered_rays"])["rows"]}
    rows = []
    for family, slot, first, last, _pixels in PLAN["cases"]:
        case = f"g1-lift-grid-{slot}"
        for tick in (first, last):
            camera, chain = history(rig, family, case, tick)
            endpoint = chain[-1]
            job = optical[endpoint["frame_id"]]
            expected = rays[job["key"]]
            require(
                job["checksum_sha256"]
                == endpoint["checksum_sha256"]
                == expected["source_checksum_sha256"]
                and endpoint["frame_id"] == expected["source_frame_id"]
                and job["joints_rad"] == endpoint["joints"]
                and job["fingers_m"] == endpoint["fingers"],
                "registered ray/endpoint mismatch",
            )
            coordinates = [r["uv"] for r in expected["rays"]]
            scanner = StaticRays(model, camera, endpoint, coordinates)
            rows.append(
                dict(
                    family=family,
                    case=case,
                    tick=tick,
                    rays=len(coordinates),
                    history_frames=len(chain),
                    first_history_tick=chain[0]["tick"],
                    frame_id=endpoint["frame_id"],
                    checksum_sha256=endpoint["checksum_sha256"],
                    windows=witness_search(
                        scanner,
                        chain,
                        PLAN["witness_windows"],
                        coordinates,
                    ),
                )
            )
    save(
        name,
        {
            "plan_sha256": sha(PLAN_FILE),
            "script_sha256": sha(Path(__file__).resolve()),
            "controls": local_controls,
            "rows": rows,
        },
    )


if __name__ == "__main__":
    main()
