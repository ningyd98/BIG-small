"""Differentiate paper occlusion from neighboring-hand and sampling interventions."""

import importlib.util

import numpy as np


def module():
    assert importlib.util.find_spec("scripts.graduation.g1_refusal_diagnostics"), (
        "missing region-aware counterfactual attribution"
    )
    from scripts.graduation import g1_refusal_diagnostics

    return g1_refusal_diagnostics


def test_recovery_contributes_to_correct_print_or_quiet_region():
    assess = module().attribute
    before = {"usable": False, "ids": []}
    clear = {"usable": True, "ids": [7]}
    shifted = [{"decode": {"observed_ids": [7]}}, {"decode": {"observed_ids": []}}]
    dark = {"black_cells": 2, "white_cells": 0, "quiet_white_margin": 3}
    results = assess(before, clear, dark, [1, 2], shifted)
    assert results["supported_paper_regions"] == ["black_cells", "quiet_white_margin"]
    assert results["sampling_interpolation_id_sensitive"]
    edge = assess(before, clear, {**dark, "black_cells": 0}, [1, 2], [])
    assert edge["supported_paper_regions"] == ["quiet_white_margin"]
    exterior = assess(before, clear, dict.fromkeys(dark, 0), [1, 2], [])
    assert (
        exterior["supported_paper_regions"] == []
        and exterior["hand_intervention"] == "hand_appearance_only"
    )
    unchanged = assess(before, before, dark, [1, 2], [])
    assert (
        unchanged["supported_paper_regions"] == []
        and unchanged["hand_intervention"] == "unresolved"
    )


def test_quad_overlap_is_invariant_to_rotation_order_and_zero_for_distant_candidates():
    nearest = module().quad_overlap
    board = np.array([[2, 2], [10, 2], [10, 10], [2, 10]])
    assert nearest(board, np.roll(board, 1, axis=0))["intersection_over_union"] == 1
    assert nearest(board, board + [20, 0])["intersection_over_union"] == 0
    assert nearest(board, np.flip(board, axis=0))["best_corner_rms_px"] == 0
