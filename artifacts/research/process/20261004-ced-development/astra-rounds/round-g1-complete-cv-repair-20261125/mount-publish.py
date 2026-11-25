"""Read independent assembly, camera, gripper and stop evidence into a compact report."""

import collections
import gzip
import hashlib
import json
from pathlib import Path

import cv2
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").is_file())
RAW = ROOT / "experiments/results/g1-complete-cv-repair-20261125"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    b = path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix == ".gz" else b)


def bind(path):
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "sha256": sha(path),
        "bytes": path.stat().st_size,
    }


def peaks(rows):
    result = {}
    for tick in ("1", "8", "32", "240"):
        result[tick] = {}
        for what in ("tcp_m", "wrist_deg", "joint_rad", "arm_links", "palm", "fingers", "payload"):
            candidates = []
            for r in rows:
                x = r["milestones"][tick]
                v = x[what] if what in x else x["max_vertex_m"][what]
                candidates.append((v, r["step"]))
            value, step = max(candidates)
            result[tick][what] = {"maximum": value, "initial_step": step}
    return result


def pad_face_projection(model, data, row):
    """Face-area overlap projected onto the cube XZ faces, independent of measured normal force."""
    data.qpos[:7] = row["joints_rad"]
    data.qpos[7:9] = row["finger_joints_m"]
    free = model.joint("object_free").qposadr[0]
    data.qpos[free : free + 3] = row["cube_xyz_m"]
    mujoco.mju_mat2Quat(data.qpos[free + 3 : free + 7], np.array(row["cube_rotation"]))
    mujoco.mj_forward(model, data)
    cube = data.geom("object_geom")
    square = np.float32([[-35, -35], [35, -35], [35, 35], [-35, 35]])
    values = []
    for name, face in (("left_finger_geom", -1), ("right_finger_geom", 1)):
        pad, shape = data.geom(name), model.geom(name)
        signs = np.array([[-1, face, -1], [1, face, -1], [1, face, 1], [-1, face, 1]])
        world = pad.xpos + (signs * shape.size) @ pad.xmat.reshape(3, 3).T
        xyz = (world - cube.xpos) @ cube.xmat.reshape(3, 3)
        polygon = np.float32(xyz[:, [0, 2]] * 1000)
        values.append(float(cv2.intersectConvexConvex(square, cv2.convexHull(polygon))[0]))
    return values


def main():
    op = RAW / "mount-optics-02/capture-gpu"
    phys = RAW / "mount-qualification-01/angles-centers-grid"
    hist = RAW / "mount-historical-01"
    brake = RAW / "mount-brake-02/braking"
    final = RAW / "mount-brake-03/braking"
    archived = RAW / "mount-historic-brake-01/braking"
    optics = read(op / "summary.json")
    compiled = read(op / "compiled.json.gz")
    grips = read(phys / "summary.json")
    cases = grips["cases"]
    model = mujoco.MjModel.from_xml_path(str(ROOT / compiled["geometry"]["asset_path"]))
    data = mujoco.MjData(model)
    all_overlaps = []
    for r in cases:
        if sha(phys / (r["case"] + ".json.gz")) != r["raw_sha256"]:
            raise ValueError("changed grasp trajectory")
        raw = read(phys / (r["case"] + ".json.gz"))
        close = next(s for s in reversed(raw) if s["phase"] == "GRASP")
        hold = raw[-120:]
        overlaps = [pad_face_projection(model, data, s) for s in (close, *hold)]
        r["per_pad_minimum_projected_inner_face_overlap_mm2"] = np.min(overlaps, axis=0).tolist()
        all_overlaps.extend(overlaps)
    brakes = {}
    sources = [
        op / "summary.json",
        op / "compiled.json.gz",
        phys / "summary.json",
        hist / "summary.json",
        brake / "summary.json",
        final / "summary.json",
        archived / "summary.json",
    ]
    for name, directory, mode in (
        ("empty", brake, "empty"),
        ("loaded", brake, "loaded"),
        ("through_retreat", final, "loaded"),
        *[
            (p.name.removesuffix("-stop.json.gz"), archived, p.name.removesuffix("-stop.json.gz"))
            for p in sorted(archived.glob("*-stop.json.gz"))
        ],
    ):
        end = "-stop.json.gz" if directory == archived else "-branches.json.gz"
        groups = collections.defaultdict(list)
        bystep = read(directory / (mode + end))
        for record in bystep:
            groups[record["stage"]].append(record)
        dense = directory / (mode + "-continuous.npz")
        with np.load(dense, allow_pickle=False) as capture:
            shape = list(capture["qpos"].shape)
            if len(capture["step"]) != len(bystep) or shape[1] != 241:
                raise ValueError("incomplete stop trajectories")
        sources.extend((directory / (mode + end), dense))
        brakes[name] = dict(
            branches=len(bystep),
            samples=shape,
            stages={
                s: dict(
                    branches=len(v),
                    peaks=peaks(v),
                    forbidden_branches=sum(bool(x["forbidden_contacts"]) for x in v),
                    lost_bilateral_branches=sum(bool(x["loaded_bilateral_loss_steps"]) for x in v),
                    maximum_initial_joint_speed_rad_s=max(
                        x["initial_max_joint_speed_rad_s"] for x in v
                    ),
                )
                for s, v in groups.items()
            },
        )
    trajectory = read(final / "loaded-native.json.gz")
    tail = trajectory["frames"][-240:]
    settled = all(
        r["phase"] == "RETREAT"
        and abs(r["cube_bottom_z_m"]) < 0.001
        and np.linalg.norm(r["cube_linear_velocity_m_s"]) < 0.02
        and np.linalg.norm(r["cube_angular_velocity_rad_s"]) < 0.5
        and np.max(np.abs(np.array(r["cube_xyz_m"][:2]) - [0.2, 0.25])) < 0.045
        for r in tail
    )
    compiled_public = {k: v for k, v in compiled.items() if k not in ("geometry", "reset_fk")}
    compiled_public["reset_poses"] = [
        {
            "pose": row["xyz_yaw"],
            "markers": row["markers"],
            "minimum_structural_clearance_m": min(
                row["structure_to_arm_and_table_clearance_m"].values()
            ),
            "minimum_by_counterpart_m": {
                other: min(
                    v
                    for k, v in row["structure_to_arm_and_table_clearance_m"].items()
                    if k.rsplit("/", 1)[-1] == other
                )
                for other in ("table", "hand", "left_finger_geom", "right_finger_geom")
            },
        }
        for row in compiled["reset_fk"]
    ]
    grid = {
        "total": len(cases),
        "passed": sum(r["eligible"] for r in cases),
        "max_slip_m": max(r["max_lift_slip_m"] for r in cases),
        "min_object_lift_last_half_second_m": min(r["last_half_second_min_lift_m"] for r in cases),
        "forbidden_steps": sum(r["forbidden_contact_steps"] for r in cases),
        "physics_steps": sum(r["physical_steps"] for r in cases),
        "open_jaw_width_min_m": min(r["inside_open_width_m"] for r in cases),
        "projected_cube_width_max_m": max(r["projected_cube_width_m"] for r in cases),
        "minimum_hold_normal_force_N_each": np.min(
            [r["min_hold_normal_force_N"] for r in cases], axis=0
        ).tolist(),
        "open_measured_center_ranges_object_m": np.column_stack(
            (
                np.min([r["measured_open_xyz_error_object_m"] for r in cases], axis=0),
                np.max([r["measured_open_xyz_error_object_m"] for r in cases], axis=0),
            )
        ).tolist(),
        "max_first_side_delay_steps": max(
            abs(r["first_contact_step"][0] - r["first_contact_step"][1]) for r in cases
        ),
        "max_abs_measured_yaw_deg": max(abs(r["measured_face_yaw_deg"]) for r in cases),
        "rows": cases,
        "pad_projection_samples": len(all_overlaps),
        "minimum_inner_pad_projected_face_overlap_mm2": np.min(all_overlaps, axis=0).tolist(),
    }
    files = sorted((ROOT / "scripts/graduation").glob("g1_clearance_mount*.py"))
    files += [
        ROOT / "tests/test_graduation_g1_clearance_mount.py",
        ROOT / compiled["geometry"]["asset_path"],
        Path(__file__),
    ]
    result = dict(
        schema="g1.end-wings.development-qualification.v1",
        plan_sha256=sha(HERE / "plan.json"),
        sources=[bind(f) for f in files],
        diagnostic_raw=[bind(f) for f in sources],
        assembly=compiled_public,
        geometry=compiled["geometry"],
        optics=optics,
        historical_contact=read(hist / "summary.json"),
        historical_braking=read(archived / "summary.json"),
        empirical_grasp=grid,
        brake=brakes,
        final_diagnostic_actions=trajectory["actions"],
        final_rest=dict(
            duration_s=len(tail) / 240,
            within_region_and_velocity_limits=bool(settled),
            maximum_linear_velocity_m_s=max(
                float(np.linalg.norm(r["cube_linear_velocity_m_s"])) for r in tail
            ),
            maximum_angular_velocity_rad_s=max(
                float(np.linalg.norm(r["cube_angular_velocity_rad_s"])) for r in tail
            ),
            final_center_m=tail[-1]["cube_xyz_m"],
        ),
        complete_development_evaluation_episodes=0,
        new_formal_or_hardware_cases=0,
    )
    (HERE / "mount-evidence.public.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
