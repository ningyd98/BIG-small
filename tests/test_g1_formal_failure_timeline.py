from copy import deepcopy

import pytest
from scripts.graduation.g1_formal_failure_timeline import (
    last_feedback_pair,
    pixel_span,
    unique_index,
)


def observations():
    previous = dict(
        frame_id="previous",
        physics_step=672,
        accepted=True,
        usable=True,
        skill="MOVE_ABOVE",
        usable_ids=[7],
        reason="derived",
        checksum_sha256="a",
    )
    refused = {
        **previous,
        "frame_id": "feedback",
        "physics_step": 680,
        "accepted": False,
        "usable": False,
        "reason": "dual_marker_grasp_conflict",
        "usable_ids": [7, 8],
        "checksum_sha256": "b",
    }
    terminal = {**refused, "frame_id": "separate-terminal", "checksum_sha256": "c"}
    return (
        [previous, refused],
        terminal,
        {"skill": "MOVE_ABOVE", "physics_step": 680},
        deepcopy(refused),
    )


def test_last_feedback_uses_distinct_terminal_at_identical_physics_step():
    feedback, terminal, stop, first_refused = observations()
    assert last_feedback_pair(feedback, terminal, stop, first_refused) == tuple(feedback)


@pytest.mark.parametrize("incorrect", ["terminal", "step", "checksum", "extra_refusal"])
def test_wrong_stop_join_is_rejected(incorrect):
    feedback, terminal, stop, frozen_refusal = observations()
    if incorrect == "terminal":
        terminal["frame_id"] = feedback[-1]["frame_id"]
    elif incorrect == "step":
        feedback[0]["physics_step"] -= 1
    elif incorrect == "checksum":
        frozen_refusal["checksum_sha256"] = "c"
    else:
        feedback.insert(0, deepcopy(feedback[-1]))
    with pytest.raises(ValueError):
        last_feedback_pair(feedback, terminal, stop, frozen_refusal)


def test_duplicate_identity_and_conflict_after_partial_measurement():
    feedback, _, _, _ = observations()
    with pytest.raises(ValueError):
        unique_index([feedback[0], feedback[0]], "frame_id")
    spans = pixel_span([{**feedback[0], "physics_step": 664}, *feedback])
    assert [s["consumed_frames"] for s in spans] == [2, 1]
    assert spans[1]["usable_ids"] == [7, 8] and not spans[1]["usable"]
