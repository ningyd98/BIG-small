"""A carried/released body must retain a positive signed separation through its native stop."""

import importlib.util

import numpy as np


def test_downward_support_does_not_turn_an_upward_halt_into_a_table_intersection():
    name = "scripts.graduation.g1_complete_cv_payload"
    assert importlib.util.find_spec(name), "loaded per-direction horizon evidence missing"
    gate = __import__(name, fromlist=["positive_support"])
    states = np.array([[[[0.0, 0.0, 0.014]]], [[[0.002, 0.0, 0.025]]], [[[0.004, 0.0, 0.029]]]])
    speed = np.zeros_like(states)
    dirs = np.array([[0.0, 0.0, -1.0], [0.0, 0.0, 1.0]])
    pad = gate.positive_support(states, speed, states[0], dirs)
    assert pad[0, 0] == 0 and pad[0, 1] >= 0.015 - 1e-10
    states[1, 0, 0, 2] = -0.001
    pad = gate.positive_support(states, speed, states[0], dirs)
    assert 0.014 - pad[0, 0] < 0


def test_failed_optical_release_relation_rejects_retreat():
    from scripts.graduation.g1_complete_cv_payload import permits_relation

    assert permits_relation("LIFT", "held")
    assert permits_relation("RETREAT", "supported_and_separated")
    assert not permits_relation("RETREAT", "held")
    assert not permits_relation("RETREAT", "unknown")


def test_world_box_remains_separated_when_other_box_moves_away_but_not_toward_it():
    from scripts.graduation.g1_complete_cv_payload import world_interval_separation

    arm = np.array([[0.0, 0.0, 0.0], [0.01, 0.01, 0.01]])
    load = np.array([[0.012, 0.002, 0.002], [0.020, 0.004, 0.004]])
    moving_negative_x = np.array([0.0, 0.010, 0.0, 0.0, 0.0, 0.0])
    still = np.zeros(6)
    assert world_interval_separation(arm, moving_negative_x, load, still) > 0.0019
    assert world_interval_separation(arm, still, load, moving_negative_x) < 0


def test_loaded_domain_refuses_opposite_and_lateral_driver_directions():
    from scripts.graduation.g1_complete_cv_payload import direction_compatible

    source = np.array([[0.001, 0.0, 0.04], [0.0, 0.0, 0.0]])
    assert direction_compatible([0.0, 0.0, 0.042], source, 0.0025).tolist() == [True, False]
    assert not direction_compatible([0.0, 0.0, -0.042], source, 0.0025).any()
    assert not direction_compatible([0.0, 0.04, 0.0], source, 0.0025).any()


def test_source_support_requires_the_same_visible_table_and_known_grasp_footprint():
    from types import SimpleNamespace

    from scripts.graduation.g1_complete_cv_geometry import Box
    from scripts.graduation.g1_complete_cv_payload import source_support_evidence

    box = Box("object_geom", np.zeros(3), np.full(3, 0.035), np.eye(3))
    table = Box("table", np.array([0.4, 0.0, -0.02]), np.array([0.3, 0.4, 0.02]), np.eye(3))
    model = SimpleNamespace(object=[box], table=table)
    registered = dict(
        max_current_gap_m=0.022, source_xy_local_max_m=0.01, max_tilt_rad=0.046, xy_reserve_m=0.015
    )
    pose = dict(
        center_m=[0.45, 0.0, 0.043],
        rotation=np.eye(3),
        basis_error_object=np.zeros((3, 3)),
        center_error_m=0.001,
    )
    surface = dict(
        support_surface_visible=True,
        support_plane_m=0.0,
        support_plane_residual_m=0.0,
        real_table_quadrant_samples=[7] * 4,
        support_table_bounds_xy_m=[[0.1, -0.4], [0.7, 0.4]],
        cube_bottom_interval_m=[0.007, 0.009],
    )
    vision = dict(relation="held", pose=pose, evidence=surface)
    assert source_support_evidence(vision, np.array([0.45, 0.0]), model, registered)["qualified"]
    assert not source_support_evidence(vision, np.array([0.47, 0.0]), model, registered)[
        "qualified"
    ]
    for change in (
        dict(support_surface_visible=False),
        dict(real_table_quadrant_samples=[7, 0, 8, 9]),
        dict(cube_bottom_interval_m=[0.028, 0.030]),
        dict(support_plane_m=0.01),
    ):
        assert not source_support_evidence(
            vision | dict(evidence=surface | change), np.array([0.45, 0.0]), model, registered
        )["qualified"]
