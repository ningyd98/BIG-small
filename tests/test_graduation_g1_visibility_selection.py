import hashlib

import pytest
from scripts.graduation import g1_visibility_selection as selection


def test_draw_is_blind_reproducible_and_avoids_reused_centers_and_seeds():
    secret = bytes(32)
    first = selection.draw(secret, [], set())
    assert first == selection.draw(secret, [], set())
    assert len({tuple(row["reset_fixture_center_m"]) for row in first}) == 4
    assert len({row["seed"] for row in first}) == 4
    for row, signs in zip(first, selection.QUADRANTS, strict=True):
        x, y, z = row["reset_fixture_center_m"]
        assert 0.435 <= x <= 0.465 and -0.020 <= y <= 0.020 and z == 0.035
        assert -0.120 <= row["yaw_rad"] <= 0.120
        assert (x - 0.45) * signs[0] > 0 and y * signs[1] > 0
    earlier = [{"pose": first[0]["reset_fixture_center_m"], "seed": first[1]["seed"]}]
    revised = selection.draw(secret, earlier, set())
    assert revised[0] != first[0] and revised[1] != first[1]
    assert revised[2:] == first[2:]
    assert {r["seed"] for r in revised}.isdisjoint({first[1]["seed"]})


def training():
    return {
        "evidence_status": "SCORED",
        "verified_posts": 8,
        "dispatched": 8,
        "online_success": True,
        "physical_success": True,
        "joint_success": True,
        "both_windows_qualified": True,
        "registered_windows": {
            "lift": {"qualified": True, "actual_samples": 121},
            "release": {"qualified": True, "actual_samples": 241},
        },
        "independent_physical_outcome": {
            "success": True,
            "safety_assessment": "SCOPED_NO_VIOLATION",
            "measured_lift_m": 0.05,
            "hold_s": 0.5,
            "placed_stable_s": 1.0,
        },
        "contacts": {"bilateral_cube_steps": 120},
        "hand_contacts": {"board_or_support_hand_or_finger_steps": []},
    }


def test_unqualified_training_cannot_reveal_the_holdout(tmp_path):
    secret = tmp_path / "never-sealed"
    rule_file = tmp_path / "rule.json"
    build = tmp_path / "build.json"
    score = tmp_path / "score.json"
    destination = tmp_path / "alloc.json"
    selection.register_rule(secret, rule_file)
    selection.write(build, {"id": "unit"})
    report = training()
    report["online_success"] = False
    selection.write(
        score,
        {
            "schema": selection.SCORE_SCHEMA,
            "scope": "training",
            "runtime_build_sha256": selection.sha(build),
            "cases": [report],
        },
    )
    with pytest.raises(ValueError, match="training"):
        selection.select(secret, rule_file, build, score, destination)
    assert not destination.exists()
    with pytest.raises(FileExistsError):
        selection.register_rule(secret, rule_file)
    assert (
        selection.read(rule_file)["seed_commitment_sha256"]
        == hashlib.sha256(secret.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    "mutation", ["wrong_safety", "short_window", "hand_contact", "no_grip", "low_lift"]
)
def test_claimed_success_still_requires_complete_independent_evidence(mutation):
    case = training()
    assert selection.qualified(case)
    if mutation == "wrong_safety":
        case["independent_physical_outcome"]["safety_assessment"] = "UNKNOWN"
    elif mutation == "short_window":
        case["registered_windows"]["release"]["actual_samples"] = 240
    elif mutation == "hand_contact":
        case["hand_contacts"]["board_or_support_hand_or_finger_steps"] = [543]
    elif mutation == "no_grip":
        case["contacts"]["bilateral_cube_steps"] = 0
    else:
        case["independent_physical_outcome"]["measured_lift_m"] = 0.04999
    assert not selection.qualified(case)


def test_selection_binds_seed_build_and_training_before_disclosing_four_slots(
    tmp_path, monkeypatch
):
    from copy import deepcopy

    seed = bytes(range(32))
    monkeypatch.setattr(selection.secrets, "token_bytes", lambda n: seed)
    monkeypatch.setattr(selection, "history_documents", lambda: iter([]))
    secret, rule, build, score, output = (
        tmp_path / key for key in ("secret", "rule", "build", "score", "selection")
    )
    selection.register_rule(secret, rule)
    selection.write(build, {"fixture": "unit"})
    evidence = {
        "scope": "training",
        "schema": selection.SCORE_SCHEMA,
        "runtime_build_sha256": selection.sha(build),
        "blind_seals_sha256": ["11" * 32] * 2,
        "score_passes_sha256": ["22" * 32] * 2,
        "cases": [training()],
    }
    for index, change in enumerate(
        (
            {"scope": "evaluation"},
            {"runtime_build_sha256": "33" * 32},
            {"blind_seals_sha256": ["44" * 32, "55" * 32]},
        )
    ):
        bad = tmp_path / f"bad{index}"
        selection.write(bad, {**deepcopy(evidence), **change})
        with pytest.raises(ValueError):
            selection.select(secret, rule, build, bad, output)
        assert not output.exists()
    selection.write(score, evidence)
    selection.select(secret, rule, build, score, output)
    result = selection.read(output)
    assert result["seed_opening_hex"] == seed.hex()
    assert result["placements"] == selection.draw(seed, [], set())
    assert result["training_score_sha256"] == selection.sha(score)
    with pytest.raises(FileExistsError):
        selection.select(secret, rule, build, score, output)
