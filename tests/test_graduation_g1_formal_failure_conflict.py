"""Check the signed geometry, patch sampling and missing-frame convention independently."""

import numpy as np
from scripts.graduation import g1_formal_failure_conflict as diagnostic


def top_camera():
    world_from_camera = np.diag([1.0, -1.0, -1.0, 1.0])
    world_from_camera[2, 3] = 1.0
    return diagnostic.Camera(
        {"intrinsics": [600.0, 580.0, 159.5, 119.5], "camera_to_world": world_from_camera}
    )


def test_exact_registration_composes_nonidentity_marker_rotation_into_the_correct_tcp():
    camera = top_camera()
    world_from_object = np.eye(4)
    world_from_object[:3, 3] = [0.01, -0.02, 0.25]
    object_from_marker = np.eye(4)
    object_from_marker[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    object_from_marker[:3, 3] = [0.08, 0.05, 0.0]
    object_tcp = np.eye(4)
    object_tcp[:3, 3] = [0.009, 0.002, 0.012]
    half = 0.0375
    local = np.array([[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]])
    true_marker = world_from_object @ object_from_marker
    uv = camera.project(local @ true_marker[:3, :3].T + true_marker[:3, 3])
    reg = dict(
        object_T_marker=object_from_marker,
        ordered_corners_marker_m=local,
        marker_id=8,
        marker_size_m=2 * half,
    )
    side = diagnostic.side_row(
        dict(corners=uv, origins=["direct"]),
        reg,
        world_from_object,
        object_tcp,
        camera,
        np.full((240, 320), 0.75),
    )
    assert side["usable"]
    np.testing.assert_allclose(side["rotation_marker_to_world"], true_marker[:3, :3], atol=1e-12)
    np.testing.assert_allclose(
        side["target_world_m"], (world_from_object @ object_tcp)[:3, 3], atol=1e-12
    )
    for name in diagnostic.VARIANTS:
        assert side["variant_metric_checks"][name]["gates_pass"]
        assert np.linalg.norm(side["variant_target_errors_mm"][name]) < 1e-8


def test_delta_uses_signed_effects_with_a_nonzero_two_factor_interaction():
    targets = dict(
        observed=np.array([2.0, 3.0, 4.0]),
        true_depth=np.array([1.0, 3.0, 3.0]),
        true_corners=np.array([-1.0, 0.0, 5.0]),
        both_true=np.zeros(3),
    )
    result = diagnostic.two_orders(targets)
    for name in ("corners_first_reductions", "depth_first_reductions"):
        np.testing.assert_allclose(sum(result[name]), targets["observed"])
    np.testing.assert_equal(result["interaction"], np.array([2.0, 0.0, -4.0]))
    assert not np.isclose(
        np.linalg.norm(targets["observed"]),
        sum(np.linalg.norm(v) for v in result["corners_first_reductions"]),
    )


def test_median_nearest_majority_and_signed_true_plane_depth_at_each_sample():
    camera = top_camera()
    uv = np.array([[110, 90], [150, 90], [150, 125], [110, 125]], dtype=float)
    depth = np.full((240, 320), 0.75)
    depth[124:126, 109:112] = 0.54
    _, medians, plane, patches = diagnostic.depths_at(
        uv, depth, camera, np.array([0.0, 0.0, 0.25]), np.eye(3), 0.0375
    )
    np.testing.assert_allclose(plane, np.full(5, 0.75))
    np.testing.assert_allclose(medians, [0.75, 0.75, 0.75, 0.54, 0.75])
    assert patches[3]["nearer_than_plane_by_gt20mm"] == 6
    np.testing.assert_allclose(patches[3]["median_minus_true_at_site_mm"], -210)
    assert patches[2]["nearer_than_plane_by_gt5mm"] == 0


def test_missing_pairs_do_not_join_at_a_stage_change_or_across_a_measured_frame():
    rows = [
        dict(
            ordinal=i,
            physics_step=step,
            stage=stage,
            usable_ids=ids,
            pair={"distance_mm": 2.0} if len(ids) == 2 else None,
        )
        for i, (step, stage, ids) in enumerate(
            [
                (872, "MOVE_ABOVE", [8]),
                (880, "MOVE_ABOVE", [8]),
                (880, "APPROACH", [8]),
                (888, "APPROACH", [7, 8]),
                (896, "APPROACH", [8]),
                (904, "APPROACH", []),
            ]
        )
    ]
    intervals = diagnostic.missing_intervals(rows)
    assert [(g["first_ordinal"], g["last_ordinal"], g["feedbacks"]) for g in intervals] == [
        (0, 1, 2),
        (2, 2, 1),
        (4, 4, 1),
        (5, 5, 1),
    ]
