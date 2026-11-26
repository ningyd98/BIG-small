"""Screen in-region release offsets in the frozen native geometry."""

import argparse
import inspect
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco as mj
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha

from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "plan.json"
PLAN = read(PLAN_FILE)
OUT = ROOT / PLAN["output"]
SIGNS = np.array(list(product((-1, 1), repeat=3)))
TABLE = frozenset(("object_geom", "table"))
NATIVE_SEP = PLAN["separation_strict_gt_m"]
Q_STEP = np.deg2rad(PLAN["max_segment_joint_deg"])
CHORD = np.deg2rad(PLAN["max_chord_joint_deg"])
POS = PLAN["tcp_position_atol_m"]
ROT = PLAN["tcp_rotation_atol_rad"]
ANCHOR = PLAN["physical_anchor_tolerance_m"]


class Rejected(ValueError):
    """Single geometric station does not merit follow-up."""


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def old_code():
    path = ROOT / PLAN["original_module"]
    sys.path.insert(0, str(path.parent))
    spec = spec_from_file_location("registered_release_geometry", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def no_run(*_args, **_kwargs):
    raise RuntimeError("static screen cannot integrate, render or issue commands")


def native_boundary():
    return patch.multiple(
        mj,
        mj_step=no_run,
        mj_step1=no_run,
        mj_step2=no_run,
        Renderer=no_run,
        mjr_render=no_run,
    )


def norm(x):
    return float(np.linalg.norm(x))


def strict_red_side(points):
    if not len(points):
        return False
    unique = np.unique(points, axis=0)
    return bool(len(unique) >= 3 and min(unique[:, 2]) < 0.010)


def projected_samples(original, model, data, camera):
    rays = original.Rays(model, data, camera)
    cube = data.geom("object_geom")
    table = data.geom("table")
    destination = data.geom("target_region_geom")
    half_width = model.geom("target_region_geom").size[:2]
    half_table = model.geom("table").size[:2]
    support_height = table.xpos[2] + model.geom("table").size[2]
    target_height = destination.xpos[2] + model.geom("target_region_geom").size[2]
    origin = cube.xpos
    w, h = camera["width"], camera["height"]
    center_uv = np.rint(rays.project(origin[None])[0]).astype(int)
    lo = np.maximum(center_uv - 42, 0)
    hi = np.minimum(center_uv + 42, [w - 1, h - 1])
    x, y = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
    uv = np.column_stack((x.ravel(), y.ravel()))
    optical = np.column_stack(((uv - rays.center) / rays.focal, np.ones(len(uv)))) @ rays.r.T
    unit = optical / np.linalg.norm(optical, axis=1, keepdims=True)
    index = np.full(len(unit), -1, dtype=np.int32)
    distance = np.full(len(unit), -1.0)
    mj.mj_multiRay(
        model, data, rays.eye, unit.ravel(), None, 1, -1, index, distance, len(unit), 10.0
    )
    hit = rays.eye + unit * distance[:, None]
    delta = hit[:, :2] - origin[:2]
    radial = np.linalg.norm(delta, axis=1)
    ring = (radial >= 0.045) & (radial <= 0.204)
    in_destination = (abs(hit[:, :2] - destination.xpos[:2]) < half_width - 0.009).all(1)
    out_destination = (abs(hit[:, :2] - destination.xpos[:2]) > half_width + 0.009).any(1)
    in_table = (abs(hit[:, :2] - table.xpos[:2]) < half_table - 0.007).all(1)
    on_table = (index == model.geom("table").id) & (abs(hit[:, 2] - support_height) < 0.001)
    on_region = (index == model.geom("target_region_geom").id) & (
        abs(hit[:, 2] - target_height) < 0.004
    )

    def quadrant(mask):
        return [
            int(np.count_nonzero(mask & ((delta[:, 0] >= 0) == a) & ((delta[:, 1] >= 0) == b)))
            for a, b in product((False, True), repeat=2)
        ]

    ground = quadrant(ring & out_destination & in_table & on_table)
    green = quadrant(ring & in_destination & on_region)
    r = cube.xmat.reshape(3, 3)
    top = origin + r[:, 2] * 0.035
    top_uv = np.rint(rays.project(top[None])[0]).astype(int)
    in_red_roi = (abs(uv - top_uv) <= 16).all(1)
    local = (hit - origin) @ r
    red_xy = abs(local[:, :2]).max(axis=1)
    cube_samples = in_red_roi & (index == model.geom("object_geom").id)
    side = local[cube_samples & (red_xy > 0.027) & (local[:, 2] < 0.028) & (local[:, 2] > -0.042)]
    upper = local[cube_samples & (abs(local[:, 2] - 0.035) < 0.004)]
    span = np.ptp(upper[:, :2], axis=0) if len(upper) else np.zeros(2)
    return {
        "red_top_first_hit_pixels": len(upper),
        "red_top_span_xy_m": span.tolist(),
        "red_top_ideal_gate": bool(len(upper) >= 12 and max(span) >= 0.053 and min(span) >= 0.003),
        "red_side_first_hit_pixels": len(side),
        "red_side_low_m": float(side[:, 2].min()) if len(side) else None,
        "red_side_ideal_gate": strict_red_side(side),
        "table_quadrant_first_hits": ground,
        "green_quadrant_first_hits": green,
        "table_ideal_gate": min(ground) >= 6,
        "target_ideal_gate": min(green) >= 3,
    }


class Slot:
    def __init__(self, original, model, record, camera):
        self.original, self.model, self.camera = original, model, camera
        self.data = mj.MjData(model)
        original.restore(model, self.data, record, camera)
        self.raw = record["row"]
        self.data_lock = (
            self.data.qvel.copy(),
            self.data.ctrl.copy(),
            float(self.data.time),
            self.data.cam_xpos.copy(),
            self.data.cam_xmat.copy(),
        )
        joints = [model.joint(n) for n in original.JOINTS[:7]]
        self.arm = np.array([int(row.qposadr[0]) for row in joints])
        self.dof = np.array([int(row.dofadr[0]) for row in joints])
        limits = np.array([row.range for row in joints])
        self.lower = np.maximum(limits[:, 0] + PLAN["minimum_joint_pad_rad"], -2.8)
        self.upper = np.minimum(limits[:, 1] - PLAN["minimum_joint_pad_rad"], 2.8)
        self.q0 = self.data.qpos[self.arm].copy()
        self.addr = int(model.joint("object_free").qposadr[0])
        self.object0 = self.data.qpos[self.addr : self.addr + 3].copy()
        self.object_quat = self.data.qpos[self.addr + 3 : self.addr + 7].copy()
        self.fingers = self.data.qpos[:9].copy()[7:]
        self.tcp_orig, self.wrist = original.pose(self.data)
        self.quat = np.empty(4)
        mj.mju_mat2Quat(self.quat, self.wrist.ravel())
        self.end_site = model.site("tcp").id
        self.kinematics = MuJoCoMotionController(
            SimpleNamespace(_model=model, _data=self.data, _mujoco=mj)
        )
        self.baseline_gaps = self.physical_gaps()[0]
        self.cube_z0 = self.physical_gaps()[1]
        self.baseline_table_distance = original.distance(model, self.data, "table", "object_geom")
        require(
            self.original.live_pairs(model, self.data) == {TABLE},
            "source table-only support differs",
        )
        self.collision_checks = 0
        self.inverse_calls = 0

    def assign(self, q, delta):
        self.data.qpos[self.arm] = q
        self.data.qpos[self.addr : self.addr + 3] = self.object0 + delta
        mj.mj_forward(self.model, self.data)

    def physical_gaps(self):
        data, model = self.data, self.model
        p, r = self.original.pose(data)
        cube = data.geom("object_geom")
        world = cube.xpos + (SIGNS * model.geom("object_geom").size) @ cube.xmat.reshape(3, 3).T
        pad = []
        for name, axis in zip(self.original.FINGERS, (r[:, 1], -r[:, 1]), strict=True):
            body = data.geom(name)
            require((body.xpos - p) @ axis > 0, "wrist side assignment differs")
            inner = body.xpos @ axis - abs(axis @ body.xmat.reshape(3, 3)) @ model.geom(name).size
            pad.append(float(inner - max(world @ axis)))
        return np.array(pad), float(world[:, 2].min()), world

    def check_safety(self, q, delta):
        d, m = self.data, self.model
        qvel, ctrl, time, eye, view = self.data_lock
        require(
            d.time == time
            and np.array_equal(qvel, d.qvel)
            and np.array_equal(ctrl, d.ctrl)
            and np.array_equal(eye, d.cam_xpos)
            and np.array_equal(view, d.cam_xmat)
            and np.array_equal(self.fingers, d.qpos[7:9])
            and np.array_equal(self.object_quat, d.qpos[self.addr + 3 : self.addr + 7]),
            "unregistered state mutation",
        )
        if not np.isfinite(q).all() or np.any(q <= self.lower) or np.any(q >= self.upper):
            raise Rejected("joint_limit_or_nonfinite")
        x, angle = self.original.residuals(d, (self.tcp_orig + delta, self.wrist))
        if norm(x) > POS or norm(angle) > ROT:
            raise Rejected("tcp_pose_not_reproduced")
        clearance = self.original.screen(
            m, d, {TABLE}, {tuple(sorted(TABLE)): self.baseline_table_distance}
        )
        self.collision_checks += 1
        if not clearance["pass"]:
            raise Rejected("static_clearance_or_contact/" + "/".join(clearance["limiting_pair"]))
        gaps, z, world = self.physical_gaps()
        if np.max(abs(gaps - self.baseline_gaps)) > ANCHOR or gaps.min() <= NATIVE_SEP:
            raise Rejected("both_pad_clearances_not_preserved")
        if abs(z - self.cube_z0) > ANCHOR or d.geom("object_geom").xmat[8] <= 0.9994:
            raise Rejected("upright_or_bottom_height_changed")
        reg = d.geom("target_region_geom")
        region_corners = (world - reg.xpos) @ reg.xmat.reshape(3, 3)
        region_margin = float(
            np.min(m.geom("target_region_geom").size[:2] - abs(region_corners[:, :2]).max(0))
        )
        if region_margin <= PLAN["containment_margin_m"]:
            raise Rejected("original_region_full_footprint")
        return clearance["minimum_gap_m"], region_margin, gaps

    def exact(self, seed, delta):
        q = np.array(seed)
        for _ in range(PLAN["max_refinement_iterations"] + 1):
            if not np.isfinite(q).all() or np.any(q <= self.lower) or np.any(q >= self.upper):
                raise Rejected("refinement_joint_limit")
            self.assign(q, delta)
            p, r = self.original.residuals(self.data, (self.tcp_orig + delta, self.wrist))
            if norm(p) <= POS and norm(r) <= ROT:
                return q
            j = self.original.jacobian(self.model, self.data, self.dof)
            step, _, rank, _ = np.linalg.lstsq(j, np.r_[p, 0.12 * r], rcond=1e-10)
            if rank != 6:
                raise Rejected("source_jacobian_rank")
            q += step * min(1.0, Q_STEP / max(abs(step).max(), 1e-15))
        raise Rejected("refinement_iterations_exhausted")

    def segment(self, q, prior, delta):
        try:
            self.assign(q, prior)
            self.inverse_calls += 1
            proposed = self.kinematics._inverse_kinematics(
                self.tcp_orig + delta, self.quat, self.end_site
            )
            if proposed is None or max(abs(proposed - q)) > Q_STEP:
                raise Rejected("native_ik_branch_or_result")
            self.assign(proposed, delta)
            native_p, native_r = self.original.residuals(
                self.data, (self.tcp_orig + delta, self.wrist)
            )
            if (
                norm(native_p) > PLAN["native_inverse_position_tolerance_m"]
                or np.degrees(norm(native_r)) > PLAN["native_inverse_rotation_tolerance_deg"]
            ):
                raise Rejected("native_ik_approximate_threshold")
            solved = self.exact(proposed, delta)
            if max(abs(solved - q)) > Q_STEP:
                raise Rejected("geometric_branch_step_limit")
            subdivisions = max(1, int(np.ceil(max(abs(solved - q)) / CHORD)))
            smallest = np.inf
            previous = q
            for i in range(1, subdivisions + 1):
                f = i / subdivisions
                position = prior + f * (delta - prior)
                step_q = self.exact(q + f * (solved - q), position)
                if max(abs(step_q - previous)) > CHORD + 1e-6:
                    raise Rejected("reprojected_chord_gap")
                minimum, _, _ = self.check_safety(step_q, position)
                smallest = min(smallest, minimum)
                previous = step_q
            return previous, smallest, norm(native_p), float(np.degrees(norm(native_r)))
        except Rejected:
            if norm(delta - prior) / 2 < PLAN["min_translation_substep_m"] - 1e-12:
                raise
            middle = (prior + delta) / 2
            state, clear1, p1, r1 = self.segment(q, prior, middle)
            end, clear2, p2, r2 = self.segment(state, middle, delta)
            return end, min(clear1, clear2), max(p1, p2), max(r1, r2)

    def path(self, destination):
        zero = np.zeros(3)
        q = self.q0.copy()
        smallest, max_native_p, max_native_r = np.inf, 0.0, 0.0
        old = zero
        pieces = int(np.ceil(norm(destination) / PLAN["max_translation_step_m"]))
        for i in range(1, pieces + 1):
            new = destination * (i / pieces)
            q, paired, p, r = self.segment(q, old, new)
            smallest = min(smallest, paired)
            max_native_p, max_native_r = max(max_native_p, p), max(max_native_r, r)
            old = new
        self.assign(q, destination)
        gap, inside, pads = self.check_safety(q, destination)
        return {
            "minimum_path_forbidden_gap_m": min(smallest, gap),
            "cube_region_margin_m": inside,
            "pad_gaps_m": pads.tolist(),
            "native_max_position_error_m": max_native_p,
            "native_max_orientation_error_deg": max_native_r,
            "final_joint_positions_rad": q.tolist(),
            "tcp_pose_m": self.data.site("tcp").xpos.tolist(),
        }


def endpoint_optical(slot):
    original, model, data, cal = slot.original, slot.model, slot.data, slot.camera
    rays = original.Rays(model, data, cal["primary_camera"])
    a, b = rays.measure(7), rays.measure(8)
    both = min(a["depth_only_edge_columns"]) >= 5
    full = (
        a["visible"] == 1024
        and len(a["visible_cells"]) == 36
        and a["compatible_dictionary_orientations"] == [[7, 0]]
    )
    ideal_pose = b["visible"] == 1024 and (full or both)
    out = projected_samples(original, model, data, cal["primary_camera"])
    return {
        "ID7_geometry": a,
        "ID8_geometry": b,
        "ID7_complete_ideal_tag": full,
        "ID7_both_ideal_edges": both,
        "ideal_pose_prerequisite": ideal_pose,
        "optical_geometric_sample_limits": out,
        "joint_optical_prerequisites": ideal_pose
        and all(
            out[k]
            for k in (
                "red_top_ideal_gate",
                "red_side_ideal_gate",
                "table_ideal_gate",
                "target_ideal_gate",
            )
        ),
    }


def controls(slot):
    require(
        strict_red_side(np.array([[0, 0, 0.007], [1, 0, 0.011], [2, 0, 0.014]]))
        and not strict_red_side(np.array([[0, 0, 0.010], [1, 0, 0.011], [2, 0, 0.014]]))
        and not strict_red_side(np.array([[0, 0, 0.007], [1, 0, 0.011], [0, 0, 0.007]])),
        "native red-side uniqueness or strict height control failed",
    )
    zero = np.zeros(3)
    zero_record = slot.path(zero)
    require(
        abs(min(zero_record["pad_gaps_m"]) - min(slot.baseline_gaps)) <= ANCHOR,
        "zero pad gap not reproduced",
    )
    return {"red_side_strict_height_and_distinct_count": True, "static_zero_clearance": True}


def evaluate():
    for path, expected in PLAN["verified_sha256"].items():
        file = ROOT / path
        require(file.resolve() == file and sha(file) == expected, f"frozen source differs: {path}")
    require(
        Path(inspect.getfile(MuJoCoMotionController)).resolve()
        == ROOT / PLAN["motion_controller_path"],
        "native controller import did not use the registered build",
    )
    old = old_code()
    metadata = old.read(old.HERE / "plan.json")
    slots, cal, count = old.preflight(metadata)
    native_anchors = read(ROOT / PLAN["original_geometry_anchor"])["states"]
    placements = {}
    for fit in PLAN["cases"]:
        file = ROOT / PLAN["fit_root"] / fit / "sensor-receipt.json"
        (place,) = [x for x in read(file)["actions"] if x["skill"] == "PLACE"]
        target = place["details"]["target_pose"]
        placements[fit] = [target[k] for k in ("x", "y", "z")]
    all_rows, visits = {}, {}
    with native_boundary():
        model = mj.MjModel.from_xml_path(str(old.ASSET))
        model.opt.timestep = 1 / 240
        station_controls = None
        for fit, clocks in PLAN["cases"].items():
            for tick in clocks:
                key = f"B/{fit}/{tick}"
                slot = Slot(old, model, slots[key], cal)
                destination = slot.data.geom("target_region_geom")
                axes, center = destination.xmat.reshape(3, 3).copy(), destination.xpos.copy()
                require(
                    np.all(
                        abs((np.array(placements[fit]) - center) @ axes)[:2]
                        < model.geom("target_region_geom").size[:2]
                    ),
                    "original PLACE endpoint not in its target region",
                )
                zero = endpoint_optical(slot)
                old_zero = native_anchors[key]["per_offset_deg"]["0"]
                require(
                    old_zero["markers"]["7"] == zero["ID7_geometry"]
                    and old_zero["markers"]["8"] == zero["ID8_geometry"]
                    and not zero["ideal_pose_prerequisite"],
                    "original marker failure was not reproduced",
                )
                if station_controls is None:
                    station_controls = controls(slot)
                rows = {}
                for x, y in product(PLAN["grid_mm"], repeat=2):
                    offset = axes @ (np.array([x, y, 0]) / 1000)
                    require(abs(offset[2]) < 1e-12, "placement offset changes z")
                    slot.assign(slot.q0, np.zeros(3))
                    try:
                        target = np.array(placements[fit]) + offset
                        if np.any(
                            abs((target - center) @ axes)[:2]
                            >= model.geom("target_region_geom").size[:2]
                        ):
                            raise Rejected("requested_target_outside_region")
                        geometry = slot.path(offset)
                        optical = endpoint_optical(slot)
                        rows[f"{x},{y}"] = {
                            "reject": None,
                            "physical": geometry,
                            "optical": optical,
                        }
                    except Rejected as err:
                        rows[f"{x},{y}"] = {"reject": str(err)}
                require(
                    len(rows) == 81 and rows["0,0"]["reject"] is None,
                    "zero or grid coverage mismatch",
                )
                all_rows[key] = rows
                visits[key] = {
                    "collision_checks": slot.collision_checks,
                    "native_inverse_calls": slot.inverse_calls,
                }
    require(len(all_rows) == 9, "wrong native branch count")
    return {
        "plan_sha256": sha(PLAN_FILE),
        "source_sha256": sha(Path(__file__).resolve()),
        "input_manifest_count": count,
        "zero_reference_controls": station_controls,
        "geometry_only": {"integrations": 0, "renders": 0, "native_commands": 0},
        "original_PLACE_targets_m": placements,
        "states": all_rows,
        "kinematic_visits": visits,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", choices=("geometry.json", "geometry.cold.json"))
    args = p.parse_args()
    data = evaluate()
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / args.name).open("x", encoding="utf-8") as f:
        f.write(
            json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
