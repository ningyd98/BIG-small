"""Identity, measurement and decision controls for the single-marker counterfactual."""

import importlib
import importlib.util

import cv2
import numpy as np
import pytest


def module(name):
    name = f"scripts.graduation.g1_refusal_{name}"
    assert importlib.util.find_spec(name), f"missing {name}"
    return importlib.import_module(name)


def test_feedback_requires_distinct_terminal_and_eight_step_gap():
    check = module("capture").feedback_window
    rows = [
        {"frame_id": "a", "physics_step": 120, "label": "MOVE_ABOVE/feedback"},
        {"frame_id": "r", "physics_step": 128, "label": "MOVE_ABOVE/feedback"},
        {"frame_id": "t", "physics_step": 128, "label": "terminal"},
    ]
    accepted = [{"observation_id": "a"}]
    assert [r["frame_id"] for r in check(rows, accepted, 128)] == ["a", "r", "t"]
    with pytest.raises(ValueError):
        check([rows[0], {**rows[1], "physics_step": 127}, rows[2]], accepted, 128)
    with pytest.raises(ValueError):
        check([rows[0], rows[1], {**rows[2], "frame_id": "r"}], accepted, 128)
    with pytest.raises(ValueError):
        check([rows[0], {**rows[0], "physics_step": 124}, *rows[1:]], accepted, 128)


def test_blind_decoder_records_all_candidates_and_avoids_shifted_pose():
    px = module("pixels")
    gray = np.full((120, 160), 255, dtype=np.uint8)
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    gray[25:85, 40:100] = cv2.aruco.generateImageMarker(d, 7, 60)
    result = px.decode(gray)
    assert result["direct_ids"] == result["observed_ids"] == [7]
    assert np.asarray(result["direct_quads_px"]).shape == (1, 4, 2)
    assert result["recovered_ids"] == []
    assert px.decode(np.full_like(gray, 255))["observed_ids"] == []
    shifts = px.shift_decodes(gray)
    assert {(s["dx_px"], s["dy_px"]) for s in shifts} == {
        (0.25, 0),
        (-0.25, 0),
        (0, 0.25),
        (0, -0.25),
    }
    assert all(s["decode"]["observed_ids"] == [7] and "grasp_world_m" not in s for s in shifts)


def test_counterfactual_pair_rejects_diagnostic_mix_and_foreign_state():
    check = module("score").check_normal_pair
    common = dict(
        condition="normal",
        case="m01-original",
        time_role="refused",
        source_episode="ep",
        step=128,
        seed=24113001,
        source_state_sha256="state",
        state_sha256="physics",
    )
    pair = {s: dict(common, mount_side=s) for s in ("X", "Y")}
    check(
        pair, common["case"], common["time_role"], common["source_episode"], 128, 24113001, "state"
    )
    for field, value in (
        ("condition", "hand_hidden"),
        ("source_episode", "other"),
        ("source_state_sha256", "other"),
        ("time_role", "previous"),
        ("mount_side", "X"),
        ("seed", 24113000),
        ("state_sha256", "another"),
    ):
        with pytest.raises(ValueError):
            check(
                {**pair, "Y": {**pair["Y"], field: value}},
                common["case"],
                "refused",
                "ep",
                128,
                24113001,
                "state",
            )


def test_complementarity_needs_verified_both_directions_and_preserves_unknown():
    decision = module("score").decision
    cases = [
        dict(
            case=f"m{i // 4 + 1:02}-{('original', 'selected')[i // 2 % 2]}",
            time_role=("previous", "refused")[i % 2],
            source_side=("Y", "X")[i // 2 % 2],
            verified=True,
            X=i != 3,
            Y=i != 0,
        )
        for i in range(16)
    ]
    d = decision(cases)
    assert d["triggered"] is True and d["outcome"] == "bidirectional_complementarity"
    assert (
        d["by_time_role"]["previous"]["X_only"] == 1 and d["by_time_role"]["refused"]["Y_only"] == 1
    )
    assert d["all"]["union_usable"] == 16
    cases[3]["verified"] = False
    assert decision(cases)["outcome"] == "unresolved" and not decision(cases)["triggered"]
    cases[3].update(verified=True, X=True, Y=True)
    assert decision(cases)["outcome"] == "bidirectional_complementarity_absent"
