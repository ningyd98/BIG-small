"""Strict outer-depth and paired physical connector attribution controls."""

from importlib.util import find_spec

import numpy as np


def tool():
    assert find_spec("scripts.graduation.g1_dual_bootstrap_diagnostic"), (
        "missing matched physical connector diagnosis"
    )
    from scripts.graduation import g1_dual_bootstrap_diagnostic

    return g1_dual_bootstrap_diagnostic


def test_outer_depth_requires_strictly_deeper_and_valid_in_selected_ring():
    depth = np.array([[1.04, 1.039, 1.05], [9.0, 1.05, 1.05]])
    ring = np.array([[1, 1, 1], [0, 1, 0]], dtype=bool)
    valid = np.array([[1, 1, 1], [0, 0, 1]], dtype=bool)
    # The exactly-equal depth fails the strict inequality.
    got = tool().ring_summary(ring, depth, valid, 1.0, 0.02)
    assert got["ring_pixels"] == 4
    assert [r["rc"] for r in got["failures"]] == [[0, 0], [0, 1], [1, 1]]


def test_only_matching_original_and_rescued_actual_gate_support_attribution():
    fn = tool().assess
    assert (
        fn(True, True, True, ["direct", "direct"]) == "direct_support_instances_and_hidden_recovery"
    )
    assert (
        fn(True, True, True, ["mixed_boundary", "direct"]) == "support_boundary_and_hidden_recovery"
    )
    for args in [
        (False, True, True, ["direct"]),
        (True, False, True, ["direct"]),
        (True, True, False, ["direct"]),
        (True, True, True, ["other"]),
        (True, True, True, []),
    ]:
        assert fn(*args) == "unresolved"
