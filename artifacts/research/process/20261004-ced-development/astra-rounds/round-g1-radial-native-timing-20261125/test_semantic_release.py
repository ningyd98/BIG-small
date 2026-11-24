"""Boundary tests for the independent native radial software release."""
from pathlib import Path
import runpy

import pytest


def code():
    return runpy.run_path(str(Path(__file__).with_name("semantic_release.py")))


def test_exact_comparison_separates_candidate_and_independent_scorer_roundoff():
    judge = code()["independent_difference"]
    assert judge({"path": ["per_id", "7", "tcp_m", 1], "old": 0.123, "new": 0.123000000000001})
    assert not judge({"path": ["top_m", 1], "old": 0.123, "new": 0.124})
    assert not judge({"path": ["selected_id"], "old": 7, "new": 8})
    assert not judge({"path": ["reason"], "old": "old", "new": "new"})


def test_same_frame_target_uses_reference_and_immutable_initial():
    endpoint = code()["control_endpoint"]
    initial = {"x": .45, "y": 0.0, "z": .16}
    assert endpoint(initial, [1, 2, 3], [1, 2, 3]) == initial
    assert endpoint(initial, [1, 2, 3], [1.001, 2, 2.998])["z"] == pytest.approx(.158)


def test_source_id_conflict_cannot_be_accepted_with_an_empty_target():
    approve = code()["negative_conflict"]
    record = {"usable": False, "selected_id": None, "usable_ids": [7, 8], "tcp_m": None,
              "top_m": None, "reason": "dual_marker_grasp_conflict", "target_disagreement_m": .0100001}
    assert approve(record)
    assert not approve({**record, "target_disagreement_m": .010})
    assert not approve({**record, "usable_ids": [7]})
    assert not approve({**record, "usable": True})

