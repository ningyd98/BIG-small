"""Reconstruct the archived trigger with the two registered box geometries."""

import argparse
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path

import mujoco
import numpy as np

ROUND = Path(__file__).resolve().parent
ROOT = next(p for p in ROUND.parents if (p / "pyproject.toml").is_file())
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
screen = importlib.import_module("scripts.graduation.g1_visibility_radial_screen")

TRIAL = (
    ROOT
    / "experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02"
)
PLAN = "6a8eb89a5609a01dbbd5560c28a5379b95b72c7061522299185c7ced94fc3d9c"
FINGER, PLATE = "right_finger_geom", "g1_dual_id8_plate"
SIGNS = np.array(list(itertools.product((-1, 1), repeat=3)))
EDGES = np.array(
    [(i, j) for i, j in itertools.combinations(range(8), 2) if np.sum(SIGNS[i] != SIGNS[j]) == 1]
)
AXES = "XYZ"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def box(model, data, name):
    g, w = model.geom(name), data.geom(name)
    assert int(g.type[0]) == int(mujoco.mjtGeom.mjGEOM_BOX)
    return dict(name=name, id=g.id, c=w.xpos.copy(), r=w.xmat.reshape(3, 3).copy(), h=g.size.copy())


def local(box, points):
    return (points - box["c"]) @ box["r"]


def world(box, points):
    return points @ box["r"].T + box["c"]


def faces(box, point):
    q = local(box, point)
    return dict(
        local_mm=q * 1000,
        half_extents_mm=box["h"] * 1000,
        incident_faces=[
            ("+" if q[i] >= 0 else "-") + AXES[i]
            for i in range(3)
            if abs(abs(q[i]) - box["h"][i]) <= 1e-7
        ],
        distance_to_nearest_face_on_each_axis_mm=(box["h"] - abs(q)) * 1000,
    )


def sat_table(a, b):
    axes = [(a["r"][:, i], "finger-" + AXES[i]) for i in range(3)]
    axes += [(b["r"][:, i], "plate-" + AXES[i]) for i in range(3)]
    axes += [
        (np.cross(a["r"][:, i], b["r"][:, j]), "finger-" + AXES[i] + " cross plate-" + AXES[j])
        for i in range(3)
        for j in range(3)
    ]
    rows = []
    for axis, label in axes:
        length = np.linalg.norm(axis)
        if length <= 1e-10:
            rows.append(dict(axis=label, degenerate=True))
            continue
        u = axis / length
        ra = float(abs(u @ a["r"]) @ a["h"])
        rb = float(abs(u @ b["r"]) @ b["h"])
        s = float(u @ (b["c"] - a["c"]))
        direction = float(u @ b["r"][:, 0])
        row = dict(
            axis=label,
            unit_world=u,
            center_difference_mm=1000 * s,
            finger_radius_mm=1000 * ra,
            plate_radius_mm=1000 * rb,
            sat_gap_mm=1000 * (abs(s) - ra - rb),
            radial_slope=direction,
        )
        if abs(direction) > 1e-12:
            row["overlap_radial_delta_interval_mm"] = sorted(
                [1000 * (-ra - rb - s) / direction, 1000 * (ra + rb - s) / direction]
            )
        rows.append(row)
    return rows


def closest_disjoint_boxes(a, b):
    """Enumerate vertex/face and interior edge/edge pairs of two disjoint boxes."""
    av, bv = (world(q, SIGNS * q["h"]) for q in (a, b))
    ca = world(a, np.clip(local(a, bv), -a["h"], a["h"]))
    cb = world(b, np.clip(local(b, av), -b["h"], b["h"]))
    first, second = [av, ca], [cb, bv]
    ea, eb = av[EDGES], bv[EDGES]
    u, v = ea[:, 1] - ea[:, 0], eb[:, 1] - eb[:, 0]
    d = ea[:, None, 0] - eb[None, :, 0]
    uu, vv = (u * u).sum(axis=1)[:, None], (v * v).sum(axis=1)[None, :]
    uv = u @ v.T
    ud, vd = (u[:, None, :] * d).sum(axis=2), (v[None, :, :] * d).sum(axis=2)
    det = uu * vv - uv**2
    nonsingular = det > 1e-12 * uu * vv
    denominator = np.where(nonsingular, det, 1)
    s = (uv * vd - vv * ud) / denominator
    t = (uu * vd - uv * ud) / denominator
    i, j = np.nonzero(nonsingular & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1))
    first.append(ea[i, 0] + s[i, j, None] * u[i])
    second.append(eb[j, 0] + t[i, j, None] * v[j])
    a_points, b_points = np.concatenate(first), np.concatenate(second)
    ds = np.linalg.norm(a_points - b_points, axis=1)
    k = np.argmin(ds)
    return dict(
        distance_mm=float(1000 * ds[k]),
        finger_world_m=a_points[k],
        plate_world_m=b_points[k],
        finger=faces(a, a_points[k]),
        plate=faces(b, b_points[k]),
    )


def contact_row(model, data, contact):
    ids = [int(contact.geom1), int(contact.geom2)]
    names = [model.geom(i).name for i in ids]
    a, b = [box(model, data, k) for k in names]
    normal = contact.frame[:3].copy()
    pos = contact.pos.copy()
    dist = float(contact.dist)
    p1, p2 = pos - 0.5 * dist * normal, pos + 0.5 * dist * normal
    method = "directed half-distance about solver contact position; both OBB surfaces verified"
    if names == ["table", "object_geom"]:
        vertices = world(b, SIGNS * b["h"])
        p2 = vertices[np.argmin(np.linalg.norm(vertices - pos, axis=1))]
        top = a["r"][:, 2]
        t = (a["h"][2] - (p2 - a["c"]) @ top) / (normal @ top)
        p1 = p2 + t * normal
        method = "actual object corner nearest solver position; its line to plane of table top"
    first, second = faces(a, p1), faces(b, p2)
    assert first["incident_faces"] and second["incident_faces"]
    return dict(
        geom_ids=ids,
        geom_names=names,
        midpoint_world_m=pos,
        frame_world=contact.frame.copy().reshape(3, 3),
        geom1_to_geom2_normal_world=normal,
        signed_distance_mm=dist * 1000,
        surface_point_method=method,
        directed_surface_point_separation_mm=float(1000 * (p2 - p1) @ normal),
        geom1_surface_world_m=p1,
        geom2_surface_world_m=p2,
        geom1_surface=first,
        geom2_surface=second,
        normal_in_geom1=normal @ a["r"],
        normal_in_geom2=normal @ b["r"],
    )


def pair_state(model, data, state, offset, terminal_locals):
    residual = screen.restore(model, data, state)
    a, b = box(model, data, FINGER), box(model, data, PLATE)
    all_contacts = [contact_row(model, data, c) for c in data.contact]
    actual = [r for r in all_contacts if r["geom_names"] == [FINGER, PLATE]]
    expected = sorted(tuple(sorted(p)) for p in state["contact_pairs"])
    reconstructed = sorted(tuple(sorted(p["geom_names"])) for p in all_contacts)
    if offset == 15:
        assert expected == reconstructed
    sat = sat_table(a, b)
    best = max((r for r in sat if not r.get("degenerate")), key=lambda r: r["sat_gap_mm"])
    witness = np.empty(6)
    gap = mujoco.mj_geomDistance(model, data, a["id"], b["id"], 3.0, witness)
    separated = best["sat_gap_mm"] > 1e-7
    feature = closest_disjoint_boxes(a, b) if separated else None
    assert bool(actual) != separated
    if feature is not None:
        assert feature["distance_mm"] + 1e-7 >= best["sat_gap_mm"]
    points = []
    for row in terminal_locals:
        p1 = world(a, row["geom1_surface"]["local_mm"] / 1000)
        p2 = world(b, row["geom2_surface"]["local_mm"] / 1000)
        n = row["geom1_to_geom2_normal_world"]
        points.append(
            dict(
                finger_world_m=p1,
                plate_world_m=p2,
                gap_along_terminal_normal_mm=1000 * float((p2 - p1) @ n),
            )
        )
    return dict(
        step=state["physics_step"],
        sim_time_s=state["sim_time_s"],
        archived_contact_pairs=state["contact_pairs"],
        restored_contacts=all_contacts,
        restore_residual=residual,
        finger_box=a,
        plate_box=b,
        finger_open=state["gripper_open"],
        finger_q_m=state["finger_positions_m"],
        raw_distance_mm=float(gap * 1000),
        raw_nearest_points_world_m=witness.reshape(2, 3),
        raw_zero_without_contact=gap == 0 and not actual,
        max_sat_gap_mm=best["sat_gap_mm"],
        max_sat_axis=best["axis"],
        separating_axes=sat,
        disjoint_feature_distance=feature,
        final_contact_material_points=points,
    )


def json_default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.generic):
        return x.item()
    raise TypeError(type(x).__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plan = ROUND / "plan.json"
    assert sha(plan) == PLAN
    spec = read(plan)
    pins = spec["inputs_sha256"]
    for rel, digest in pins.items():
        if sha(ROOT / rel) != digest:
            # The two development entry points can advance in a parallel authorized build.
            assert (
                rel.startswith("scripts/graduation/")
                and rel != Path(screen.__file__).relative_to(ROOT).as_posix()
            )
            parent = TRIAL.parents[2] / "builds" / spec["parent_generation"] / "runtime-source"
            assert sha(parent / "runtime-build.json") == spec["parent_generation"]
            assert sha(parent / rel) == digest, rel
    case = screen.checked_case(TRIAL)
    inst = TRIAL / "instance"
    frames = case["index"]["frames"][-9:]
    assert [r["physics_step"] for r in frames] == [*range(1160, 1217, 8), 1221]
    for r in frames:
        assert sha(inst / r["file"]) == r["file_sha256"]
    run, commands, vision = (
        read(inst / f) for f in ("run.json", "backend-commands.json", "online-vision.json")
    )
    audit = read(inst / "online-audit.json")
    controls = {
        r["physics_step"]: r
        for q in audit
        if q.get("phase") == "servo" and q["skill"] == "APPROACH"
        for r in q["control_samples"]
    }
    roles = []
    for r in frames:
        hit = vision["frames"].get(r["frame_id"])
        roles.append(
            dict(
                file=r["file"],
                file_sha256=r["file_sha256"],
                frame_id=r["frame_id"],
                checksum_sha256=r["checksum_sha256"],
                step=r["physics_step"],
                role=r["label"],
                measure_calls=hit["callers"] if hit else {},
                usable_ids=hit["measurement"]["usable_ids"] if hit else [],
                sample_and_ik_ms=1000 * controls[r["physics_step"]]["sample_and_ik_s"]
                if r["physics_step"] in controls
                else None,
            )
        )
    doc = dict(
        schema="g1.radial30.right-finger-contact.v1",
        source_sha256=sha(Path(__file__)),
        plan_sha256=PLAN,
        mujoco=mujoco.__version__,
        truth_sha256=case["truth_sha256"],
        index_sha256=case["index_sha256"],
        real_frames=roles,
        native_stop=run["stop"],
        native_safe_stop_success=run["safe_stop"]["success"],
        native_commands=[r for r in commands if r["physics_step"] >= 1212],
        scope="Positions, normals, faces and nearest points come from a frozen-pose mj_forward. "
        "The archive supplies the actual state and contact pair names. No integration.",
        face_tolerance_m=1e-7,
        sat_axis_degeneracy_norm=1e-10,
        mounts={},
    )
    for offset in (15, 30):
        asset = screen.physical_root(offset)
        model = mujoco.MjModel.from_xml_path(str(asset))
        data = mujoco.MjData(model)
        if offset == 15:
            assert sha(asset) == case["asset_sha256"]
            screen.restore(model, data, case["states"][1221])
            terminal_locals = [
                contact_row(model, data, c)
                for c in data.contact
                if model.geom(c.geom1).name == FINGER and model.geom(c.geom2).name == PLATE
            ]
            assert len(terminal_locals) == 2
        else:
            assert sha(asset) == "14a1a9fc2d2993fa28fbb873e25d1e9672c07b7433b3cb9ad27f07434c75efbe"
        states = [
            pair_state(model, data, case["states"][n], offset, terminal_locals)
            for n in [*range(1160, 1217, 8), *range(1217, 1222)]
        ]
        doc["mounts"][str(offset)] = dict(
            xml=asset.relative_to(ROOT).as_posix(), xml_sha256=sha(asset), states=states
        )
    original = doc["mounts"]["15"]["states"]
    last = original[-1]
    movements = {}
    for start in (1160, 1216, 1220):
        first = next(r for r in original if r["step"] == start)
        deltas = []
        for c, f, t in zip(
            terminal_locals,
            first["final_contact_material_points"],
            last["final_contact_material_points"],
            strict=True,
        ):
            a = t["finger_world_m"] - f["finger_world_m"]
            b = t["plate_world_m"] - f["plate_world_m"]
            n = c["geom1_to_geom2_normal_world"]
            deltas.append(
                dict(
                    finger_displacement_world_mm=a * 1000,
                    plate_displacement_world_mm=b * 1000,
                    finger_inward_normal_mm=float(1000 * a @ n),
                    plate_normal_mm=float(1000 * b @ n),
                    normal_gap_change_mm=float(1000 * (b - a) @ n),
                )
            )
        movements[f"{start}_to_1221"] = deltas
    doc["terminal_material_point_motion"] = movements
    comp = doc["mounts"]["30"]["states"][-1]
    assert comp["max_sat_gap_mm"] > 0 and comp["disjoint_feature_distance"]["distance_mm"] > 0
    assert abs(comp["disjoint_feature_distance"]["distance_mm"] - comp["raw_distance_mm"]) < 1e-5
    doc["terminal_conclusion"] = dict(
        registered_plus30_pair_separated=True,
        additional_outward_motion_required_mm=0,
        scope="Right finger and ID8 plate at the fixed trigger pose only.",
    )
    with args.output.open("x") as f:
        json.dump(doc, f, sort_keys=True, indent=2, allow_nan=False, default=json_default)
        f.write("\n")


if __name__ == "__main__":
    main()
