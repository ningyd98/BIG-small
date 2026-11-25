"""Numeric controls for the first frozen estimator and independent statics cross-check."""

from pathlib import Path

import numpy as np
from sweep_depth import DepthView
from sweep_evaluate import Scene, evaluate, load_support, qualify
from sweep_geometry import Box, clearance, contact_patch, hand_sweeps, parse_tool, sweep_box
from sweep_history import ROUND, digest, encoded


def cube(name, c, h):
    return Box(name, np.asarray(c, dtype=float), np.asarray(h, dtype=float), np.eye(3))


def controls():
    tool = parse_tool(
        Path(
            "assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml"
        )
    )
    center = np.array([0.0, 0.0, 0.035])
    tcp = np.array([0.0, 0.0, 0.045])
    target = cube("object_geom", center, [0.035] * 3)
    witnesses = []
    tf = np.diag([1.0, -1.0, -1.0, 1.0])
    tf[:3, 3] = [0, 0, 1.0]
    depth = np.ones((32, 32))
    valid = np.ones_like(depth, bool)
    for name, z, expected in (
        ("front", 0.2, "FREE"),
        ("first_return", 0.0, "OCCUPIED"),
        ("behind", -0.1, "UNKNOWN"),
    ):
        view = DepthView(depth, valid, [100, 100, 15.5, 15.5], tf, 0.004)
        evidence = view.assess(cube("query", [0, 0, z], [0.015, 0.015, 0.002]))
        assert evidence["state"] == expected
        witnesses.append(dict(case=name, expected=expected, actual=evidence))
    holes = valid.copy()
    holes[15:17, 15:17] = False
    view = DepthView(depth, holes, [100, 100, 15.5, 15.5], tf, 0.004)
    hole = view.assess(cube("tiny", [-0.0005, 0.0005, 0.2], [0.00025, 0.00025, 0.001]))
    assert hole["state"] == "UNKNOWN"
    witnesses.append(
        dict(case="invalid_pixel_cone_without_center_hit", expected="UNKNOWN", actual=hole)
    )
    complete = Scene(
        [target, cube("distant", [0.14, 0.14, 0.12], [0.003] * 3)], 0, known_static_volume=True
    )
    entry = evaluate(tool, center, tcp, 0.0, 0.0, 0.0, complete)
    bounded = dict(tracking_mm=0.3, stopping_mm=0.2, object_pose_mm=0.1, depth_mm=0.05)
    safe, rs = qualify(entry, bounded, "NOMINALLY_CLEAR")
    assert safe == "CLEAR"
    witnesses.append(
        dict(
            case="fully_known_positive_scene",
            complete_sweep=safe,
            registered_sat_lower_mm=entry["registered_min_sep_bound_mm"],
            independent_fixture_bounds=bounded,
            swept_entities=[e[:2] for e in entry["phase_evidence"]],
        )
    )
    for name, origin, half, part in (
        ("left_finger", [0, 0.0565, 0.061], [0.003] * 3, "left_finger_geom"),
        ("only_palm", [0, 0, 0.1], [0.003] * 3, "hand"),
        ("thin_opposite_beam", [0.025, -0.051, 0.06], [0.001, 0.001, 0.0002], "right_finger_geom"),
    ):
        solid = cube(name, origin, half)
        parts = hand_sweeps(tool, tcp, np.array([0, 1, 0.0]), 0.0, 0.07)
        collided = [
            (phase, b.name, clearance(b, solid) * 1000)
            for phase, b in parts
            if clearance(b, solid) <= 0
        ]
        assert any(n == part for _, n, _ in collided)
        if name == "only_palm":
            assert {n for _, n, _ in collided} == {"hand"}
        witnesses.append(dict(case=name, expected="BLOCKED", contacts=collided))
    a = cube("pad", [-0.02, 0, 0.1], [0.003] * 3)
    b = cube("pad", [0.02, 0, 0.1], [0.003] * 3)
    thin = cube("line", [0, 0, 0.1], [0.0003, 0.001, 0.001])
    witnesses.append(
        dict(
            case="thin_obstacle_between_endpoints",
            end_clearance_mm=[clearance(o, thin) * 1000 for o in (a, b)],
            continuous_bound_mm=clearance(sweep_box(a, b), thin) * 1000,
        )
    )
    original = parse_tool(
        Path("assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml")
    )
    patch = contact_patch(original, tcp, center, original["target"].h, 0.0, 0.0, 0.0)
    native = load_support(original, center, tcp, 0.0, 0.0, 0.0, patch)
    each_up = original["mass"] * 9.81 / 2
    each_normal = each_up / 0.8
    locations = [np.array([sign * 0.035, 0.0, 0.0]) for sign in (1.0, -1.0)]
    forces = [np.array([-sign * each_normal, 0.0, each_up]) for sign in (1.0, -1.0)]
    grav = [0.0, 0.0, -original["mass"] * 9.81]
    balance = np.sum(forces, axis=0) + grav
    moment = np.cross(locations, forces).sum(axis=0)
    assert np.allclose(balance, 0, atol=1e-12) and np.allclose(moment, 0, atol=1e-12)
    assert each_normal < min(native["stationary_position_servo_nominal_capacity_n"])
    return dict(
        witnesses=witnesses,
        first_generation_static_solver_audit=dict(
            centered_unobstructed_patch=patch,
            solver=native,
            analytic_support=dict(
                locations_relative_to_COM_m=[p.tolist() for p in locations],
                forces_n=[v.tolist() for v in forces],
                gravity_n=grav,
                residual_force_n=balance.tolist(),
                residual_moment_nm=moment.tolist(),
                normal_each_n=each_normal,
                upward_each_n=each_up,
            ),
            interpretation="An unverified LP result leaves load support unresolved.",
        ),
    )


if __name__ == "__main__":
    out = controls() | dict(
        source_sha256=digest(Path(__file__).read_bytes()),
        frozen_predictor_seal_sha256=digest((ROUND / "sweep-seal.public.json").read_bytes()),
        first_expected_reds=[
            "ModuleNotFoundError: No module named 'sweep_depth'",
            "ImportError: cannot import name 'qualify'",
            "test_offset_tcp_meets_each_independent_jaw_at_its_own_face: BLOCKED instead of CLEAR",
        ],
        terminal_regression_cases=7,
    )
    with (ROUND / "sweep-controls.public.json").open("xb") as f:
        f.write(encoded(out))
