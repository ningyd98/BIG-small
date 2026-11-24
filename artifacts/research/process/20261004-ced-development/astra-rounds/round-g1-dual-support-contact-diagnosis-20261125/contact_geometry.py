"""Compare registered boxes at the saved configurations. This diagnostic never steps physics."""

import argparse
import hashlib
import importlib
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import mujoco
import numpy as np

ROUND = Path(__file__).resolve().parent
OLD = ROUND.parent / "round-g1-radial30-contact-20261125"
ROOT = next(p for p in ROUND.parents if (p / "pyproject.toml").is_file())
sys.path[:0] = [str(OLD), str(ROOT), str(ROOT / "src")]
prior = importlib.import_module("contact_witness")
screen = prior.screen
radial = screen.radial
BASE = screen.BASE
TRIALS = {
    15: BASE / "batches/train-radial15-timing-01/d02",
    30: BASE / "batches/train-radial30-contact-d02-02/d02",
}
BUILDS = {
    15: "f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892",
    30: "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212",
}
PLAN = "3df98fe7e537dce1196aef233dd0dad2fc347c41eae30e0202f06da5f5a102e2"
LEFT, BEAM = "left_finger_geom", "g1_dual_id7_crossbar"
PAIRS = {"left_beam": (LEFT, BEAM), "right_plate": (prior.FINGER, prior.PLATE)}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=prior.json_default
    ).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pins():
    assert prior.sha(ROUND / "plan.json") == PLAN
    for rel, digest in prior.read(ROUND / "plan.json")["inputs_sha256"].items():
        assert prior.sha(ROOT / rel) == digest, rel
    assert (
        prior.sha(Path(prior.__file__))
        == "7cff296e3d23d6405172ad9e2ba06b6824f9152a3a4e4790ad092bd427a9822b"
    )


def exact_asset(off):
    case = screen.checked_case(TRIALS[off])
    rel = case["geometry"]["asset_path"]
    tree = BASE / "builds" / BUILDS[off] / "runtime-source"
    assert prior.sha(tree / "runtime-build.json") == BUILDS[off]
    p = tree / rel
    assert prior.sha(p) == case["asset_sha256"] == prior.sha(ROOT / rel)
    assert radial.build_xml(radial._parent(), off) == p.read_bytes()
    return p


def axes(a, b):
    names = "XYZ"
    candidates = [(a["r"][:, i], "finger." + names[i]) for i in range(3)]
    candidates.extend((b["r"][:, i], "part." + names[i]) for i in range(3))
    candidates.extend(
        (np.cross(a["r"][:, i], b["r"][:, j]), "finger." + names[i] + " × part." + names[j])
        for i in range(3)
        for j in range(3)
    )
    out = []
    for v, label in candidates:
        size = np.linalg.norm(v)
        if size <= 1e-10:
            out.append(dict(axis=label, degenerate=True))
            continue
        u = v / size
        # Coordinates relative to the finger center avoid subtraction of two large projections.
        r1 = float(abs(u @ a["r"]) @ a["h"]) * 1000
        r2 = float(abs(u @ b["r"]) @ b["h"]) * 1000
        center = float(u @ (b["c"] - a["c"])) * 1000
        out.append(
            dict(
                axis=label,
                degenerate=False,
                unit_world=u,
                first_interval_mm=[-r1, r1],
                second_interval_mm=[center - r2, center + r2],
                signed_gap_mm=float(abs(center) - r1 - r2),
            )
        )
    return out


def line_interval(box, origin, normal):
    """Clip p+t n to the exact oriented box, retaining degenerate edge/corner intersections."""
    p = prior.local(box, origin)
    d = normal @ box["r"]
    good = abs(d) > 1e-12
    assert (abs(p[~good]) <= box["h"][~good] + 1e-9).all()
    lim1 = (-box["h"][good] - p[good]) / d[good]
    lim2 = (box["h"][good] - p[good]) / d[good]
    lo, hi = float(np.minimum(lim1, lim2).max()), float(np.maximum(lim1, lim2).min())
    assert lo <= hi + 1e-8, (lo, hi, box["name"])
    return lo, hi


def contact(model, data, c, obj):
    names = [model.geom(i).name for i in (c.geom1, c.geom2)]
    if names == ["table", "object_geom"]:
        return prior.contact_row(model, data, c)
    a, b = [prior.box(model, data, name) for name in names]
    pos, n = c.pos.copy(), c.frame[:3].copy()
    # Directed surface points come from the box intervals along the solver normal.
    a1 = line_interval(a, pos, n)[1]
    b0 = line_interval(b, pos, n)[0]
    p1, p2 = pos + a1 * n, pos + b0 * n
    f1, f2 = prior.faces(a, p1), prior.faces(b, p2)
    assert f1["incident_faces"] and f2["incident_faces"]
    assert np.max(abs((p1 + p2) / 2 - pos)) < 1e-8
    return dict(
        geom_ids=[a["id"], b["id"]],
        geom_names=names,
        midpoint_world_m=pos,
        frame_world=c.frame.copy().reshape(3, 3),
        geom1_to_geom2_normal_world=n,
        normal_in_geom1=n @ a["r"],
        normal_in_geom2=n @ b["r"],
        signed_distance_mm=1000 * float(c.dist),
        geom1_surface_world_m=p1,
        geom2_surface_world_m=p2,
        geom1_surface=f1,
        geom2_surface=f2,
        geom1_surface_object_mm=1000 * prior.local(obj, p1),
        geom2_surface_object_mm=1000 * prior.local(obj, p2),
        directed_surface_point_separation_mm=1000 * (b0 - a1),
        surface_point_method="interval of the normal line in each exact OBB",
    )


def interior_ball(a, b, obj):
    """Enumerate vertices of the inscribed-sphere LP in object coordinates, in millimeters."""
    normals = []
    limits = []
    labels = []
    for box in (a, b):
        center = 1000 * prior.local(obj, box["c"])
        world_axes = box["r"].T @ obj["r"]
        for i, axis in enumerate(world_axes):
            for sign in (-1, 1):
                n = axis * sign
                normals.append(n)
                limits.append(1000 * box["h"][i] + center @ n)
                labels.append(box["name"] + ":" + ("+" if sign > 0 else "-") + "XYZ"[i])
    norms = np.asarray(normals)
    limits = np.asarray(limits)
    design = np.column_stack((norms, np.ones(12)))
    best = None
    for key in itertools.combinations(range(len(limits)), 4):
        idx = list(key)
        m = design[idx]
        if abs(np.linalg.det(m)) < 1e-12:
            continue
        value = np.linalg.solve(m, limits[idx])
        if ((design @ value) <= limits + 1e-9).all() and (best is None or value[3] > best[3]):
            best = value
    assert best is not None and best[3] > 0
    residuals = limits - norms @ best[:3]
    assert min(residuals) >= best[3] - 1e-9
    return dict(
        object_center_mm=best[:3],
        inscribed_radius_mm=best[3],
        twelve_wall_distances_mm=dict(zip(labels, residuals, strict=True)),
    )


def pair(model, data, obj, names, contacts):
    a, b = [prior.box(model, data, n) for n in names]
    table = axes(a, b)
    best = max((q for q in table if not q["degenerate"]), key=lambda v: v["signed_gap_mm"])
    points = np.zeros(6)
    d = 1000 * mujoco.mj_geomDistance(model, data, a["id"], b["id"], 3, points)
    hits = [v for v in contacts if set(v["geom_names"]) == set(names)]
    sep = best["signed_gap_mm"] > 1e-7
    assert (not hits) == sep
    out = dict(
        boxes=[a, b],
        axes=table,
        largest_signed_gap_mm=best["signed_gap_mm"],
        largest_axis=best["axis"],
        solver_distance_mm=d,
        solver_fromto_world_m=points.reshape(2, 3),
        zero_without_contact=d == 0 and not hits,
        contact_count=len(hits),
    )
    if sep:
        feat = prior.closest_disjoint_boxes(a, b)
        out["nearest_disjoint"] = dict(
            distance_mm=feat["distance_mm"],
            finger_world_m=feat["finger_world_m"],
            part_world_m=feat["plate_world_m"],
            finger=feat["finger"],
            part=feat["plate"],
        )
        assert feat["distance_mm"] + 1e-7 >= best["signed_gap_mm"]
    else:
        out["strict_intersection_witness"] = interior_ball(a, b, obj)
    return out


def mount_meta(model, off):
    b = model.geom(BEAM)
    assert np.allclose(b.pos - b.size, [-0.004, 0.035, 0.017], atol=1e-12, rtol=0)
    assert np.allclose(
        b.pos + b.size, [0.004, 0.071 if off == 15 else 0.086, 0.019], atol=1e-12, rtol=0
    )
    assert np.array_equal(b.quat, [1, 0, 0, 0])
    return {
        name: dict(
            id=model.geom(name).id,
            type="box",
            local_center_mm=1000 * model.geom(name).pos,
            half_extents_mm=1000 * model.geom(name).size,
            contype=int(model.geom(name).contype[0]),
            conaffinity=int(model.geom(name).conaffinity[0]),
        )
        for names in PAIRS.values()
        for name in names
    }


def frame_records(case, off):
    raw = TRIALS[off] / "instance"
    audit = prior.read(raw / "online-audit.json")
    run = prior.read(raw / "run.json")
    vision = prior.read(raw / "online-vision.json")["frames"]
    idx = case["index"]["frames"]
    times = {
        x["physics_step"]: x["sample_and_ik_s"]
        for q in audit
        if q.get("skill") == "APPROACH" and q.get("phase") == "servo"
        for x in q["control_samples"]
    }
    output = []
    for r in idx[-9:]:
        f = screen.frame_from_row(
            raw, r, case["index"]["episode"], case["index"]["scene"], case["geometry"]
        )
        v = vision.get(f.frame_id)
        if v:
            assert v["callers"] == {"servo_measure": 1}
        output.append(
            dict(
                step=r["physics_step"],
                file=r["file"],
                file_sha256=r["file_sha256"],
                role=r["label"],
                frame_id=f.frame_id,
                checksum=f.checksum_sha256,
                sim_time_s=f.sim_time_s,
                usable_ids=v["measurement"]["usable_ids"] if v else None,
                selected_id=v["measurement"]["selected_id"] if v else None,
                decision=v["measurement"]["reason"] if v else None,
                calls=v["callers"] if v else {},
                sample_and_ik_ms=1000 * times[r["physics_step"]] if v else None,
            )
        )
    commands = prior.read(raw / "backend-commands.json")
    stop = run["stop"]["physics_step"]
    return dict(
        trajectory=kind(off),
        frames=output,
        native_stop=run["stop"],
        last_motion=next(q for q in reversed(commands) if q["type"] == "joint_target"),
        commands_at_or_after_stop=[q for q in commands if q["physics_step"] >= stop],
        safe_stop=run["safe_stop"]["success"],
    )


def kind(off):
    return "trajectory-" + str(off)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pins()
    out = {}
    cases = {}
    for src in TRIALS:
        case = screen.checked_case(TRIALS[src])
        cases[src] = case
        entry = frame_records(case, src)
        out[kind(src)] = entry
        entry["poses"] = {}
        critical = {1220, 1221} | ({1227, 1228} if src == 30 else set())
        for off in TRIALS:
            asset = exact_asset(off)
            model = mujoco.MjModel.from_xml_path(str(asset))
            data = mujoco.MjData(model)
            mount = dict(xml_sha256=prior.sha(asset), geoms=mount_meta(model, off), states=[])
            entry["poses"][str(off)] = mount
            for step in sorted(critical | {r["step"] for r in entry["frames"]}):
                s = case["states"][step]
                res = screen.restore(model, data, s)
                obj = prior.box(model, data, "object_geom")
                contacts = [contact(model, data, c, obj) for c in data.contact]
                if src == off:
                    assert Counter(tuple(sorted(r["geom_names"])) for r in contacts) == Counter(
                        tuple(sorted(r)) for r in s["contact_pairs"]
                    )
                pairs = {
                    key: pair(model, data, obj, names, contacts) for key, names in PAIRS.items()
                }
                mount["states"].append(
                    dict(
                        step=step,
                        ground_truth_sha256=sha(canonical(s)),
                        archived_pairs=s["contact_pairs"],
                        fk_residuals=res,
                        joints_rad=s["joint_positions_rad"],
                        fingers_m=s["finger_positions_m"],
                        tcp_archive_m=s["tcp_position_m"],
                        object_pose=obj,
                        pairs=pairs,
                        contacts=contacts,
                    )
                )
    diffs = {}
    for step in (1220, 1221):
        a, b = [cases[s]["states"][step] for s in (15, 30)]
        diffs[str(step)] = {
            k: np.subtract(b[k], a[k])
            for k in (
                "joint_positions_rad",
                "finger_positions_m",
                "tcp_position_m",
                "object_position_m",
                "object_geom_rotation_row_major",
            )
        }
    # The same positive-radius ball from the smaller beam lies strictly within the larger beam.
    archived = out[kind(30)]["poses"]
    small = archived["15"]["states"][-1]
    large = archived["30"]["states"][-1]
    ball = small["pairs"]["left_beam"]["strict_intersection_witness"]
    q = ball["object_center_mm"]
    radius = ball["inscribed_radius_mm"]
    assert q[1] - radius > 35 and q[1] + radius < 71 and radius > 0
    object_box = large["object_pose"]
    center = prior.world(object_box, q / 1000)
    large_d = [
        1000 * (b["h"] - abs(prior.local(b, center))) for b in large["pairs"]["left_beam"]["boxes"]
    ]
    assert min(v.min() for v in large_d) >= radius - 1e-8
    doc = dict(
        schema="g1.dual-support.local-contact.v1",
        plan_sha256=PLAN,
        source_sha256=prior.sha(Path(__file__)),
        source_generations=BUILDS,
        mujoco=mujoco.__version__,
        generator_sha256=prior.sha(Path(radial.__file__)),
        face_tolerance_m=1e-7,
        axis_degenerate_norm=1e-10,
        trajectory_same_step_differences_30_minus_15=diffs,
        strict_common_intersection=dict(
            center_object_mm=q,
            radius_mm=radius,
            half_face_distances_in_larger_finger_and_beam_mm=large_d,
        ),
        trajectories=out,
    )
    with args.output.open("xb") as f:
        f.write(canonical(doc) + b"\n")


if __name__ == "__main__":
    main()
