"""Read t02's two archived exposures and localize the sealed pin in original camera rays."""

import argparse
import itertools
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
PROBE_STEPS = tuple(PLAN["steps"].values())
OUT = ROOT / PLAN["output"]
TIP = "diagnostic_pin"
EPS = 1e-8
BOX_SIGNS = np.array(list(itertools.product((-1.0, 1.0), repeat=3)))
TRIPLETS = np.array(list(itertools.combinations(range(12), 3)))


def require(condition, problem):
    if not condition:
        raise ValueError(problem)


def xml_identity(node):
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        (node.text or "").strip(),
        tuple(xml_identity(child) for child in node),
    )


def models():
    asset, needle = (ROOT / PLAN[key] for key in ("asset", "needle"))
    bare_xml, pin_xml = [ET.parse(path).getroot() for path in (asset, needle)]
    world, materials = pin_xml.find("worldbody"), pin_xml.find("asset")
    element = world.find(f"geom[@name='{TIP}']")
    require(element is not None and len(materials) == 1, "original fixture is incomplete")
    require(materials[0].attrib["name"] == element.attrib["material"], "pin material unbound")
    world.remove(element)
    pin_xml.remove(materials)
    require(
        xml_identity(bare_xml) == xml_identity(pin_xml), "models differ beyond the physical pin"
    )
    return {
        key: mujoco.MjModel.from_xml_path(str(p)) for key, p in (("bare", asset), ("pin", needle))
    }


def original_inputs():
    for name, expected in PLAN["sha256"].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == expected, f"source drift: {name}")
    case = ROOT / PLAN["original_case"]
    inst = case / "instance"
    allocation = read(case / "allocation.json")
    receipt = read(inst / "receipt.json")
    seal = read(inst / "acquisition-seal.json")
    index = read(inst / "pixel-index.json")
    truth = read(inst / "offline-truth.json")
    history = read(ROOT / PLAN["history"])
    camera = allocation["geometry"]["camera"]
    require(
        sha(case / "allocation.json")
        == receipt["allocation_sha256"]
        == index["allocation_sha256"]
        == truth["allocation_sha256"]
        and sha(inst / "acquisition-seal.json") == receipt["capture_sha256"]
        and sha(inst / "pixel-index.json") == seal["index_sha256"]
        and sha(inst / "offline-truth.json") == seal["truth_sha256"]
        and index["episode"] == truth["episode"]
        and index["scene"] == truth["scene"]
        and allocation["asset_sha256"]
        == history["native_asset_sha256"]
        == sha(ROOT / PLAN["asset"])
        and sha(ROOT / PLAN["needle"]) == history["physical_tip_xml_sha256"],
        "source capture and physical needle do not bind",
    )
    checks = read(inst / "local-clearance.json")["rows"]
    source = {}
    for step in PROBE_STEPS:
        (past,) = [r for r in history["actual_recorded_exposures"] if r["step"] == step]
        frame_id = past["original_source_checksum"]
        (record,) = [r for r in checks if r["frame_id"] == frame_id]
        (indexed,) = [r for r in index["frames"] if r["frame_id"] == frame_id]
        frame_path = (inst / indexed["file"]).resolve()
        require(
            frame_path.is_relative_to(inst) and sha(frame_path) == indexed["file_sha256"],
            "original frame file differs",
        )
        frame = RGBDObservation.model_validate_json(frame_path.read_bytes())
        label = truth["samples"][step]
        robot = record["robot"]
        require(
            frame.model_dump(include=set(camera), mode="json") == camera
            and frame.frame_id == frame_id
            and frame.episode_id == index["episode"] == label["episode_id"]
            and frame.scene_id == index["scene"]
            and frame.checksum_sha256 == indexed["checksum_sha256"] == robot["checksum_sha256"]
            and label["physics_step"]
            == indexed["physics_step"]
            == robot["physics_step"]
            == record["physics_step"]
            == step
            and frame.sim_time_s == robot["camera_encoder_sim_time_s"] == label["sim_time_s"]
            and abs(frame.sim_time_s - step / PLAN["physics_hz"]) < EPS,
            f"original shutter/physical clock does not bind: {step}",
        )
        source[step] = {
            "robot": robot,
            "physical": label,
            "original_frame_id": frame_id,
            "original_checksum_sha256": frame.checksum_sha256,
            "time_s": frame.sim_time_s,
            "old_match": past,
        }
    return camera, source, history


def restore(model, source, camera):
    data = mujoco.MjData(model)
    robot, truth = source["robot"], source["physical"]
    names = [f"joint{i}" for i in range(1, 8)] + ["finger_left_joint", "finger_right_joint"]
    slots = [model.joint(n).qposadr[0] for n in names]
    addr = model.joint("object_free").qposadr[0]
    free = model.geom("object_geom")
    require(
        model.nq == 16
        and len(set(slots) | set(range(addr, addr + 7))) == model.nq
        and np.array_equal(free.pos, [0, 0, 0])
        and np.array_equal(free.quat, [1, 0, 0, 0])
        and free.bodyid[0] == model.joint("object_free").bodyid[0],
        "native free-body and encoders do not fully reconstruct",
    )
    data.qpos[slots] = robot["camera_joint_positions_rad"] + robot["camera_finger_positions_m"]
    data.qpos[addr : addr + 3] = truth["object_geom_position_m"]
    rotation = np.array(truth["object_geom_rotation_row_major"])
    mujoco.mju_mat2Quat(data.qpos[addr + 3 : addr + 7], rotation)
    data.time = source["time_s"]
    before = data.qpos.copy()
    mujoco.mj_forward(model, data)
    optical = np.eye(4)
    optical[:3, 3] = data.camera("rgbd").xpos
    optical[:3, :3] = data.camera("rgbd").xmat.reshape(3, 3) * [1, -1, -1]
    fx = (camera["height"] / 2) / np.tan(np.deg2rad(model.camera("rgbd").fovy[0]) / 2)
    intrinsics = [fx, fx, (camera["width"] - 1) / 2, (camera["height"] - 1) / 2]
    require(
        np.allclose(optical.ravel(), camera["camera_to_world"], rtol=0, atol=1e-12)
        and np.allclose(intrinsics, camera["intrinsics"], rtol=0, atol=1e-12)
        and np.linalg.norm(data.geom("object_geom").xpos - truth["object_geom_position_m"]) < 1e-9
        and np.linalg.norm(data.geom("object_geom").xmat - rotation) < 1e-9
        and np.array_equal(before, data.qpos)
        and data.time == source["time_s"],
        "optical transform, archived physical pose or time did not close",
    )
    return data, optical


def project(world, optical, camera):
    local = (world - optical[:3, 3]) @ optical[:3, :3]
    fx, fy, cx, cy = camera["intrinsics"]
    uv = local[:, :2] / local[:, 2, None] * [fx, fy] + [cx, cy]
    return np.column_stack((uv, local[:, 2]))


def ray_interval(eye, ray, center, half, axes):
    start, travel = (eye - center) @ axes, ray @ axes
    directed = abs(travel) > 1e-12
    if np.any(abs(start[~directed]) > half[~directed]):
        return None
    bounds = (np.stack((-half[directed], half[directed])) - start[directed]) / travel[directed]
    near, far = max(0.0, float(bounds.min(axis=0).max())), float(bounds.max(axis=0).min())
    return (near, far) if near <= far else None


def first_return(model, data, eye, ray, groups):
    direction = ray / np.linalg.norm(ray)
    hit = np.array([-1], dtype=np.int32)
    distance = mujoco.mj_ray(model, data, eye, direction, groups, 1, -1, hit)
    if distance < 0:
        require(hit[0] == -1, "invalid native ray miss")
        return {"geom": None, "axial_m": None}
    return {"geom": model.geom(int(hit[0])).name, "axial_m": float(distance / np.linalg.norm(ray))}


def shared_geometry_matches(pair, poses):
    bare, pin = pair["bare"], pair["pin"]
    for i in range(bare.ngeom):
        left = bare.geom(i).name
        require(left and pin.geom(left).id >= 0, "geometry identity differs")
        defs = [pair[k].geom(left) for k in ("bare", "pin")]
        geom = [poses[k].geom(left) for k in ("bare", "pin")]
        require(
            np.array_equal(defs[0].type, defs[1].type)
            and np.array_equal(defs[0].size, defs[1].size)
            and np.array_equal(defs[0].group, defs[1].group)
            and np.array_equal(geom[0].xpos, geom[1].xpos)
            and np.array_equal(geom[0].xmat, geom[1].xmat),
            f"native non-pin geometry differs: {left}",
        )


def box_intersection_vertices(cube_c, cube_r, cube_half, pin_c, pin_half, pin_r):
    normals = np.vstack((cube_r.T, -cube_r.T, pin_r.T, -pin_r.T))
    limits = np.r_[
        cube_half + cube_r.T @ cube_c,
        cube_half - cube_r.T @ cube_c,
        pin_half + pin_r.T @ pin_c,
        pin_half - pin_r.T @ pin_c,
    ]
    candidates = normals[TRIPLETS]
    keep = abs(np.linalg.det(candidates)) > 1e-10
    points = np.linalg.solve(candidates[keep], limits[TRIPLETS[keep]][..., None])[..., 0]
    return points[np.all(points @ normals.T <= limits + 1e-10, axis=1)]


def stop_intersections(model, needle, optical, camera):
    cube_size = model.geom("object_geom").size.copy()
    with np.load(ROOT / PLAN["stop_trace"], allow_pickle=False) as archive:
        cube_centers = archive["centers"][:, 10].copy()
        cube_rotations = archive["rotation"][:, 10].copy()
    require(
        cube_centers.shape == (241, 3) and cube_rotations.shape == (241, 3, 3),
        "terminal stop trace shape differs",
    )
    cells, overlaps = [], {}
    for tick, (center, rotation) in enumerate(zip(cube_centers, cube_rotations, strict=True)):
        vertices = box_intersection_vertices(center, rotation, cube_size, *needle)
        if len(vertices):
            cells.append(project(vertices, optical, camera))
            overlaps[tick] = (center, cube_size, rotation)
    bounds = np.concatenate(cells, axis=0)
    uv = np.array(PLAN["source_pixel_uv"])
    require(
        len(overlaps) == 65
        and min(overlaps) == 176
        and np.all((bounds[:, :2] >= uv - 0.5) & (bounds[:, :2] <= uv + 0.5))
        and abs(bounds[:, 2].min() - 1.333073) < 1e-6
        and abs(bounds[:, 2].max() - 1.334057) < 1e-6,
        "archived collision footprint differs",
    )
    return overlaps, [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()]


def original_ray(uv, optical, camera):
    fx, fy, cx, cy = camera["intrinsics"]
    u, v = uv
    return optical[:3, :3] @ [(u - cx) / fx, (v - cy) / fy, 1.0]


def probe_rays(pair, poses, optical, camera, needle, roi, stops):
    eye = optical[:3, 3].copy()
    groups = mujoco.MjvOption().geomgroup.copy()
    pin_c, pin_half, pin_r = needle
    (u0, v0), (u1, v1) = roi
    results = []
    for scale in PLAN["grids"]:
        for v, u in itertools.product(
            range(v0 * scale, (v1 + 1) * scale), range(u0 * scale, (u1 + 1) * scale)
        ):
            uv = ((u + 0.5) / scale - 0.5, (v + 0.5) / scale - 0.5)
            ray = original_ray(uv, optical, camera)
            pin_interval = ray_interval(eye, ray, pin_c, pin_half, pin_r)
            hits = {key: first_return(pair[key], poses[key], eye, ray, groups) for key in pair}
            classification, related = "outside_pin", []
            if pin_interval is not None:
                for tick, cube in stops.items():
                    other = ray_interval(eye, ray, *cube)
                    if other is not None and max(pin_interval[0], other[0]) <= min(
                        pin_interval[1], other[1]
                    ):
                        related.append(tick)
                z = hits["pin"]["axial_m"]
                bare_z = hits["bare"]["axial_m"]
                if pin_interval[1] - pin_interval[0] <= EPS or z is None:
                    classification = "boundary_or_unresolved"
                elif hits["pin"]["geom"] == TIP and abs(z - pin_interval[0]) <= EPS:
                    classification = "visible" if bare_z is None or bare_z > z + EPS else "near_tie"
                elif z < pin_interval[0] - EPS:
                    classification = "occluded"
                else:
                    classification = "boundary_or_unresolved"
            results.append(
                {
                    "scale": scale,
                    "pixel_uv": [u, v],
                    "original_coordinate_uv": list(uv),
                    "pin_axial_interval_m": None if pin_interval is None else list(pin_interval),
                    "first": hits,
                    "classification": classification,
                    "intersecting_stop_ticks": related,
                }
            )
    return results


def cpu_diagnostic():
    camera, archived, _ = original_inputs()
    pair = models()
    steps = {}
    for step, source in archived.items():
        restored = {k: restore(m, source, camera) for k, m in pair.items()}
        poses = {k: value[0] for k, value in restored.items()}
        optical = restored["bare"][1]
        require(np.array_equal(optical, restored["pin"][1]), "paired optical centers differ")
        shared_geometry_matches(pair, poses)
        pin = poses["pin"].geom(TIP)
        needle = (pin.xpos.copy(), pair["pin"].geom(TIP).size.copy(), pin.xmat.reshape(3, 3).copy())
        pin_c, pin_half, pin_r = needle
        uv = project(pin_c + (BOX_SIGNS * pin_half) @ pin_r.T, optical, camera)
        padding = PLAN["roi_padding_original_px"]
        low = np.floor(uv[:, :2].min(0)).astype(int) - padding
        high = np.ceil(uv[:, :2].max(0)).astype(int) + padding
        require(
            (low >= 0).all() and (high < [camera["width"], camera["height"]]).all(),
            "pin ROI off image",
        )
        near_far = [
            [m.stat.extent * m.vis.map.znear, m.stat.extent * m.vis.map.zfar] for m in pair.values()
        ]
        require(
            near_far[0] == near_far[1]
            and uv[:, 2].min() > near_far[0][0]
            and uv[:, 2].max() < near_far[0][1],
            "paired frustum clipping differs",
        )
        if step == PLAN["steps"]["refusal"]:
            overlap, bound = stop_intersections(pair["bare"], needle, optical, camera)
        else:
            overlap, bound = {}, None
        rays = probe_rays(pair, poses, optical, camera, needle, [low, high], overlap)
        (center,) = [
            r for r in rays if r["scale"] == 1 and r["pixel_uv"] == PLAN["source_pixel_uv"]
        ]
        if overlap:
            require(min(center["intersecting_stop_ticks"]) == 180, "central collision ray differs")
        else:
            require(center["classification"] == "visible", "known visible positive control failed")
        steps[str(step)] = {
            "original_frame_id": source["original_frame_id"],
            "original_checksum_sha256": source["original_checksum_sha256"],
            "roi_original_uv_inclusive": [low.tolist(), high.tolist()],
            "pin_uv_and_depth_bounds": [uv.min(axis=0).tolist(), uv.max(axis=0).tolist()],
            "clip_near_far_m": near_far[0],
            "collision_states": list(overlap),
            "collision_uv_and_depth_bounds": bound,
            "rays": rays,
        }
    return {
        "source_plan_sha256": sha(PLAN_PATH),
        "mujoco": mujoco.__version__,
        "physics_steps": 0,
        "camera_calls": 0,
        "steps": steps,
    }


def prohibited(*_args, **_kwargs):
    raise RuntimeError("frozen static diagnostic attempted integration or rendering")


def read_cpu():
    with patch.multiple(
        mujoco,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
        Renderer=prohibited,
        mjr_render=prohibited,
    ):
        return cpu_diagnostic()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, read_cpu())
