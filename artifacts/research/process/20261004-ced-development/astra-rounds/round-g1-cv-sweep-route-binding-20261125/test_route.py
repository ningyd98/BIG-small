"""Regression controls for direct high targeting, exact native orientation, and force witnesses."""

from pathlib import Path

import numpy as np
import pytest
from route_forces import stability
from route_geometry import direct_envelope, mot_targets, wrist
from sweep_evaluate import Scene
from sweep_geometry import Box, contact_patch, parse_tool

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD


@pytest.mark.parametrize("mm", [0, 7, -7, 41, -41, 44, -44])
def test_native_target_including_measured_tilt(mm):
    tilt = 0.04
    R = np.array([[np.cos(tilt), 0, np.sin(tilt)], [0, 1, 0], [-np.sin(tilt), 0, np.cos(tilt)]])
    tcp = np.array([0.45, 0, 0.085])
    delta = np.array([mm / 1000, 0.0, 0.0])
    approach, high = mot_targets(tcp, R, delta)
    np.testing.assert_allclose(approach, tcp + R @ delta, atol=1e-13)
    assert high[2] == pytest.approx(max(0.16, approach[2] + 0.10))
    assert high[:2].tolist() == approach[:2].tolist()
    assert tuple(wrist(np.array([0.0, 1.0, 0.0]), True)) == _DOWNWARD


def test_native_wrist_cannot_be_borrowed_by_another_axis():
    assert not np.allclose(wrist(np.array([1.0, 0.0, 0.0]), False), _DOWNWARD)
    with pytest.raises(ValueError):
        wrist(np.array([1.0, 0.0, 0.0]), True)


def b(name, c, h):
    return Box(name, np.array(c, dtype=float), np.array(h, dtype=float), np.eye(3))


def test_direct_shift_route_has_its_own_obstacle_and_clear_positive():
    tool = parse_tool(
        Path("assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml")
    )
    # An identity wrist translates diagonally in x/y. Its thin palm side at the
    # first third of the motion intersects this witness only on the direct path.
    state = dict(
        status="MEASURED",
        tcp_m=[0.0, -0.17, 0.25],
        rotation=np.eye(3).tolist(),
        finger_interval_m=[[0.04, 0.04], [0.04, 0.04]],
    )
    highs = np.array([[0.0, 0.04, 0.25], [0.049, 0.04, 0.25]])
    target = b("object_geom", [0.6, 0.6, 0], [0.02] * 3)
    free = Scene([target], 0.0, known_static_volume=True)
    group = direct_envelope(state, tool, highs, np.eye(3), free)
    assert group["status"] == "CLEAR" and group["max_vertex_motion_mm"] <= 1
    assert group["members"] == 2
    # This obstacle intersects a translated positive-x finger corner and misses
    # both the original central diagonal and the later central-high horizontal shift.
    obstacle = b("direct_only", [0.046, -0.038, 0.276], [0.001, 0.001, 0.001])
    occupied = Scene([target, obstacle], 0.0, known_static_volume=True)
    old = direct_envelope(state, tool, highs[:1], np.eye(3), occupied)
    new = direct_envelope(state, tool, highs[1:], np.eye(3), occupied)
    assert old["status"] == "CLEAR" and new["actual_midpoint_hits"] > 0
    shifted_state = state | dict(tcp_m=highs[0].tolist())
    assert direct_envelope(shifted_state, tool, highs[1:], np.eye(3), occupied)["status"] == "CLEAR"


def test_static_constructive_witness_and_infeasible_weight():
    tool = parse_tool(
        Path("assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml")
    )
    c = np.array([0.0, 0.0, 0.035])
    tcp = np.array([0.0, 0.0, 0.045])
    patch = contact_patch(tool, tcp, c, tool["target"].h, 0, 0, 0.0)
    pos = stability(tool, c, tcp, 0.0, 0.0, patch)
    assert pos["status"] == "WITNESS" and pos["normal_each_n"] == pytest.approx([0.4905, 0.4905])
    assert max(abs(np.array(pos["force_residual_n"]))) < 1e-10
    heavy = stability(tool | {"mass": 100.0}, c, tcp, 0.0, 0.0, patch)
    assert heavy["status"] == "PROVEN_INFEASIBLE_WEIGHT"
    assert heavy["weight_n"] > heavy["vertical_coulomb_capacity_upper_n"]
