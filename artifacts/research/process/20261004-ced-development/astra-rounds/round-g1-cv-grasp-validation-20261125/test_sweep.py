"""Fixed, independent geometric and calibrated-depth controls for the G1 grasp sweep."""

import numpy as np
import pytest
from sweep_depth import DepthView
from sweep_geometry import Box, clearance, contact_patch, hand_sweeps, parse_tool, sweep_box


@pytest.fixture
def tool():
    from pathlib import Path

    return parse_tool(
        Path(
            "assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml"
        )
    )


def box(c, h=(0.003, 0.003, 0.003), name="fixture"):
    return Box(name, np.array(c), np.array(h), np.eye(3))


def test_exact_continuous_sweep_closes_midstep_gap():
    a = box([-0.02, 0, 0.1])
    b = box([0.02, 0, 0.1])
    thin = box([0, 0, 0.1], (0.0003, 0.001, 0.001))
    assert min(clearance(a, thin), clearance(b, thin)) > 0.015
    assert clearance(sweep_box(a, b), thin) < 0


def test_full_gripper_intentional_terminal_contact_and_lateral_limits(tool):
    tf = np.array([0.0, 0.0, 0.045])
    axis = np.array([0.0, 1.0, 0.0])
    h = [0.035] * 3
    rows = hand_sweeps(tool, tf, axis, 0.0, 0.070)
    target = box([0, 0, 0.035], h, "object_geom")
    for phase, hand in rows:
        distance = clearance(hand, target)
        if phase == "close" and hand.name != "hand":
            assert abs(distance) < 1e-9
        else:
            assert distance > 0
    np.testing.assert_allclose(
        contact_patch(tool, tf, np.array([0, 0, 0.035]), h, 0.0, 0.0, 0.0)["overlap_mm"],
        [56.0, 55.0],
    )
    assert contact_patch(tool, tf, np.array([0, 0, 0.035]), h, 0.0, 0.0, 0.049)["face_supported"]
    assert not contact_patch(tool, tf, np.array([0, 0, 0.035]), h, 0.0, 0.0, 0.050)[
        "face_supported"
    ]
    assert not contact_patch(tool, tf, np.array([0, 0, 0.035]), h, 0.0, np.pi / 4, 0.0)[
        "aperture_ok"
    ]
    assert not contact_patch(tool, tf, np.array([0, 0, 0.035]), h, 0.0, 0.005, 0.0)[
        "face_supported"
    ]


def test_full_entities_block_centerline_free_scenes(tool):
    rows = hand_sweeps(tool, np.array([0.0, 0.0, 0.045]), np.array([0.0, 1.0, 0.0]), 0.0, 0.070)
    for obstacle, name in [
        (box([0, 0.0565, 0.061]), "left_finger_geom"),
        (box([0, 0, 0.100]), "hand"),
        (box([0.025, -0.051, 0.06], (0.001, 0.001, 0.0002)), "right_finger_geom"),
    ]:
        hits = {(phase, b.name) for phase, b in rows if clearance(b, obstacle) <= 0}
        assert any(k == name for _, k in hits)
    assert min(clearance(b, box([0.14, 0.14, 0.08])) for _, b in rows) > 0.06


@pytest.fixture
def view():
    # Downward optical z, an unobstructed horizontal floor at world z=0.
    R = np.diag([1.0, -1.0, -1.0, 1.0])
    R[:3, 3] = [0.0, 0.0, 1.0]
    return lambda d, v: DepthView(d, v, (100.0, 100.0, 15.5, 15.5), R, 0.004)


def test_ray_front_surface_behind_hole_edge_and_outside(view):
    depth = np.ones((32, 32))
    valid = np.ones_like(depth, bool)
    for z, expected in [(0.20, "FREE"), (0.0, "OCCUPIED"), (-0.10, "UNKNOWN")]:
        out = view(depth, valid).assess(box([0.0, 0.0, z], (0.015, 0.015, 0.002)))
        assert out["state"] == expected
    holes = valid.copy()
    holes[15:17, 15:17] = False
    assert (
        view(depth, holes).assess(box([0.0, 0.0, 0.20], (0.015, 0.015, 0.002)))["state"]
        == "UNKNOWN"
    )
    edge = depth.copy()
    edge[:, 16:] = 0.8
    assert (
        view(edge, valid).assess(box([0.0, 0.0, 0.16], (0.002, 0.002, 0.002)))["state"] == "UNKNOWN"
    )
    assert view(depth, valid).assess(box([1.0, 0.0, 0.1]))["state"] == "UNKNOWN"


def test_pixel_corner_not_certified_from_center_ray(view):
    d = np.ones((32, 32))
    mask = np.ones_like(d, bool)
    mask[15, 15] = False
    # The small box reaches a masked pixel footprint even where no pixel centre hits it.
    out = view(d, mask).assess(box([-0.0005, 0.0005, 0.2], (0.00025, 0.00025, 0.001)))
    assert out["state"] == "UNKNOWN" and out["unknown_volume_upper_mm3"] > 0


def test_whole_two_finger_and_palm_sweep_with_independently_bounded_clear_room(tool):
    from sweep_evaluate import Scene, evaluate, qualify

    center = np.array([0.0, 0.0, 0.035])
    tcp = np.array([0.0, 0.0, 0.045])
    target = box(center, [0.035] * 3, "object_geom")
    clear = Scene([target, box([0.14, 0.14, 0.12])], 0.0, known_static_volume=True)
    row = evaluate(tool, center, tcp, 0.0, 0.0, 0.0, clear)
    assert row["clearance"] == "CLEAR"
    assert (
        qualify(
            row,
            {"tracking_mm": 0.3, "stopping_mm": 0.2, "object_pose_mm": 0.1, "depth_mm": 0.05},
            "NOMINALLY_CLEAR",
        )[0]
        == "CLEAR"
    )
    assert qualify(row, {"tracking_mm": None}, "UNKNOWN")[0] == "UNKNOWN"
    assert (
        qualify(
            row,
            {"tracking_mm": 7.0, "stopping_mm": 0.2, "object_pose_mm": 0.1, "depth_mm": 0.05},
            "NOMINALLY_CLEAR",
        )[0]
        == "UNKNOWN"
    )
    thin = Scene(
        [target, box([0.056, 0, 0.06], (0.0003, 0.012, 0.0002), "outboard_beam")],
        0.0,
        known_static_volume=True,
    )
    e = evaluate(tool, center, tcp, 0.0, 0.0, 0.0, thin)
    assert e["clearance"] == "BLOCKED" and any(h[2] == "outboard_beam" for h in e["hits"])


def test_offset_tcp_meets_each_independent_jaw_at_its_own_face(tool):
    from sweep_evaluate import Scene, evaluate

    center = np.array([0.0, 0.0, 0.035])
    tcp = np.array([0.0004, 0.0, 0.045])
    target = box(center, [0.035] * 3, "object_geom")
    row = evaluate(
        tool, center, tcp, 0.0, 0.0, 0.040, Scene([target], 0.0, known_static_volume=True)
    )
    assert row["geometric_status"] == "CLEAR"
    assert row["patch"]["contact_joint_positions_m"] == pytest.approx([0.0336, 0.0344])
