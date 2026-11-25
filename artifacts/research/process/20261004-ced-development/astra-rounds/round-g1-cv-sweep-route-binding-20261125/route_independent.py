"""Independent native target, friction, and geometric envelope calculations after sealing."""

import ast
import math
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from sweep_evaluate import load_support
from sweep_geometry import SIGNS

from cloud_edge_robot_arm.contracts import Pose

RUNTIME = Path(
    "experiments/results/g1-cv-grasp-validation-20261125/binding-qualification/run-01/runtime-source"
)


def exact_function(path, name, globals_):
    tree = ast.parse(path.read_text())
    f = next(e for e in tree.body if isinstance(e, ast.FunctionDef) and e.name == name)
    source = "from __future__ import annotations\n" + ast.get_source_segment(path.read_text(), f)
    namespace = dict(globals_)
    exec(compile(source, str(path), "exec"), namespace)
    return namespace[name]


def native_check(rows):
    owner = RUNTIME / "src/cloud_edge_robot_arm/vision/owner_registration.py"
    binding = RUNTIME / "scripts/graduation/binding.py"
    native = exact_function(owner, "_resolved_parameters", {"Pose": Pose})
    selected = exact_function(binding, "selected_tcp", {"np": np})
    from binding import check_direction

    policy = SimpleNamespace(
        minimum_height_m=0.16, clearance_m=0.10, tcp_velocity=0.15, acceleration=0.5
    )
    orig = SimpleNamespace(
        contract=SimpleNamespace(task_target=SimpleNamespace(object_id="object"))
    )
    online = SimpleNamespace(robot_state=SimpleNamespace(tcp_pose=Pose(x=0, y=0, z=0.8)))
    worst = 0.0
    calls = 0
    accepted = 0
    rejected = 0
    for fr in rows:
        rot = np.array(fr["marker"]["rotation_object_to_world"]).reshape(3, 3)
        for r in fr["candidates"]:
            low = selected(fr["marker"]["grasp_world_m"], rot, r["offset_object_m"])
            args = SimpleNamespace(
                grasp_tcp=dict(zip("xyz", low, strict=True)),
                destination=dict(x=0.25, y=0.25, z=0.0),
                support_height_m=0.0,
            )
            for skill, k in (("MOVE_ABOVE", "target_high_m"), ("APPROACH", "target_low_m")):
                obj = native(
                    SimpleNamespace(skill=SimpleNamespace(value=skill)), orig, online, args, policy
                )["target_pose"]
                worst = max(worst, max(abs(np.array([obj[v] for v in "xyz"]) - r[k])))
                calls += 1
            try:
                check_direction(r["orientation_wxyz"])
                ok = True
            except ValueError:
                ok = False
            assert ok == r["original_orientation"]
            accepted += ok
            rejected += not ok
    assert worst < 1e-11
    return dict(
        original_owner_calls=calls,
        max_per_axis_residual_mm=1000 * worst,
        native_fixed_direction_acceptances=accepted,
        native_other_direction_rejections=rejected,
        confirmed_native_targets=["MOVE_ABOVE", "APPROACH"],
    )


def verify_force(force, tool):
    contacts = force["face_contacts"]
    com = np.array(tool["com"])
    normal_actual = np.zeros(2)
    weight = tool["mass"] * 9.81
    forces = []
    moments = []
    worst_cone = 0.0
    for w in contacts:
        f = np.asarray(w["force_n"])
        p = np.asarray(w["point_object_m"])
        forces.append(f)
        moments.append(np.cross(p - com, f))
        assert (
            np.all(abs(p) <= tool["target"].h + 1e-9)
            and np.min(abs(abs(p[:2]) - tool["target"].h[:2])) < 1e-9
        )
        assert w["normal_n"] >= -1e-9
        worst_cone = max(worst_cone, w["tangential_n"] - force["mu"] * w["normal_n"])
        normal_actual[w["side"]] += w["normal_n"]
    assert np.all(normal_actual <= np.array(force["nominal_static_normal_capacity_n"]) + 1e-7)
    residual = np.linalg.norm(np.sum(forces, axis=0) - [0, 0, weight])
    moment = np.linalg.norm(np.sum(moments, axis=0))
    assert residual < 1e-7 and moment < 1e-7 and worst_cone < 1e-7
    return residual, moment


def original_lp(fr, row, tool):
    """Read the frozen simplex coefficients; verify forces independently in object coordinates."""
    yaw = math.radians(fr["object_yaw_deg"])
    rel = {"object_X": 0.0, "object_Y": np.pi / 2, "existing_tool_closure_axis": np.pi / 2 - yaw}[
        row["direction"]
    ]
    m = fr["marker"]
    center = np.array(m["object_center_world_m"])
    tcp = np.array(m["grasp_world_m"])
    orig = cv2.solveLP
    capture = []

    def seen(*a, **kw):
        r = orig(*a, **kw)
        capture.append(r)
        return r

    cv2.solveLP = seen
    try:
        proof = load_support(tool, center, tcp, yaw, rel, row["tangent_mm"] / 1000, row["patch"])
    finally:
        cv2.solveLP = orig
    assert proof["status"] == "nominal_static_equilibrium", (row["candidate_id"], proof["status"])
    x = capture[0][1].ravel()
    assert x.min() >= -1e-7
    n = np.array([np.cos(rel), np.sin(rel), 0.0])
    t = np.array([n[1], -n[0], 0.0])
    z = np.array([0.0, 0.0, 1.0])
    h = tool["target"].h
    hn = abs(n) @ h
    ht = abs(t) @ h
    mu = proof["mu"]
    forces = []
    moments = []
    normal = np.zeros(2)
    k = 0
    for s, (f, sign, _) in enumerate(tool["fingers"]):
        ft = row["tangent_mm"] / 1000 + row["patch"]["tcp_tangent_offset_m"] + f.c[2]
        pz = tcp[2] - center[2] - f.c[0]
        for xx in (max(-ht, ft - f.h[2]), min(ht, ft + f.h[2])):
            for zz in (max(-h[2], pz - f.h[0]), min(h[2], pz + f.h[0])):
                pt = n * hn * sign + t * xx + zz * z
                assert np.all(abs(pt) <= h + 1e-8)
                ff = np.zeros(3)
                for side_t in (t, -t, z, -z):
                    ff += x[k] * (-sign * n + mu * side_t)
                    k += 1
                nn = -sign * float(n @ ff)
                assert nn >= -1e-7 and np.linalg.norm(ff + sign * nn * n) <= mu * nn + 1e-7
                normal[s] += nn
                forces.append(ff)
                moments.append(np.cross(pt - tool["com"], ff))
    assert np.all(normal <= np.array(proof["stationary_position_servo_nominal_capacity_n"]) + 1e-7)
    e = float(np.linalg.norm(np.sum(forces, axis=0) - [0, 0, 9.81 * tool["mass"]]))
    m = float(np.linalg.norm(np.sum(moments, axis=0)))
    assert max(e, m) < 1e-6
    return e, m


def envelope_verification(fr, tool):
    """Project every member/part/corner at both ends and midpoint of every segment."""
    state = fr["measured_robot"]
    if state["status"] != "MEASURED":
        return None
    p = np.array(state["tcp_m"])
    R0 = np.array(state["rotation"])
    out = {}
    local_parts = []
    for b, sg, iv in [
        (tool["palm"], 0, [0.0, 0.0]),
        *(
            (b, sg, [min(r[0], rng[1]), max(r[1], rng[1])])
            for (b, sg, rng), r in zip(tool["fingers"], state["finger_interval_m"], strict=True)
        ),
    ]:
        cc = b.c.copy()
        cc[1] += sg * (iv[1] + iv[0]) / 2
        h = b.h.copy()
        h[1] += (iv[1] - iv[0]) / 2
        local_parts.append((cc, h))
    for key, g in fr["initial_routes"].items():
        H = np.array([r["target_high_m"] for r in fr["candidates"] if r["direction"] == key])
        n = g["segments"]
        R1 = np.array(g["goal_orientation_matrix"])
        rotvec = cv2.Rodrigues(R0.T @ R1)[0].ravel()

        def point(t, H=H, rotvec=rotvec):
            return p + t * (H - p), R0 @ cv2.Rodrigues(rotvec * t)[0]

        worst = -np.inf
        checked = 0
        for i in range(n):
            Tc, Rc = point((i + 0.5) / n)
            base = Tc[0]
            T = (Tc - base) @ Rc
            dlo = T.min(axis=0)
            dhi = T.max(axis=0)
            pad = g["within_segment_pad_mm"] / 1000
            for frac in (i / n, (i + 0.5) / n, (i + 1) / n):
                Ta, Ra = point(frac)
                inter = (Ta - base) @ Rc
                tl = inter.min(axis=0)
                th = inter.max(axis=0)
                for cc, h in local_parts:
                    transformed = (cc + SIGNS * h) @ Ra.T @ Rc
                    actual_lo = tl + transformed.min(axis=0)
                    actual_hi = th + transformed.max(axis=0)
                    lower = dlo + cc - h - pad
                    upper = dhi + cc + h + pad
                    worst = max(
                        worst, float(max(np.max(lower - actual_lo), np.max(actual_hi - upper)))
                    )
                    checked += len(H) * 8
        assert worst <= 1e-10 and g["max_vertex_motion_mm"] <= 1.0 + 1e-10
        out[key] = dict(
            checked_member_vertices=checked,
            max_signed_excess_mm=1000 * worst,
            members=len(H),
            segments=n,
        )
    return out
