"""功效设计只估配对不一致率；不根据正式显著性追加样本。"""

from importlib import import_module, util

import pytest


def api():
    name = "cloud_edge_robot_arm.research.power"
    assert util.find_spec(name) is not None, "missing production research power"
    return import_module(name)


def test_power_selects_smallest_allowed_n():
    result = api().choose_formal_n(
        [(True, False)] * 3 + [(True, True)] * 117, [(True, False)] + [(False, False)] * 119
    )
    assert result.selected_n == 1200
    assert result.power_by_n[600]["safety"] < 0.8
    assert result.power_by_n[1200]["success"] >= 0.8
    assert result.power_by_n[1200]["safety"] >= 0.8
    # .01 * sqrt(600/(1/120)) - z_.99 = .356934 -> Phi = .639429.
    assert result.power_by_n[600]["safety"] == pytest.approx(0.63942928, abs=0.000001)


def test_zero_disagreement_uses_exact_boundary_not_invented_variance():
    result = api().choose_formal_n([(True, True)] * 120, [(False, False)] * 120)
    assert result.selected_n == 600
    assert result.power_by_n[600]["safety"] == 1.0
    assert result.discordance_upper_bound["safety"] > 0


def test_power_above_2400_is_insufficient():
    discordant = [(True, False)] * 24 + [(False, False)] * 96
    result = api().choose_formal_n(discordant, discordant)
    assert result.selected_n is None
    assert "2400" in result.reason


def test_power_uses_only_disagreement_not_favorable_pilot_effect():
    first = [(True, False)] * 6 + [(False, False)] * 114
    flipped = [(False, True)] * 6 + [(True, True)] * 114
    assert api().choose_formal_n(first, first) == api().choose_formal_n(flipped, flipped)


@pytest.mark.parametrize(
    "pairs", [[], [(False, False)] * 119, [(False, False)] * 121, [(0, 1)] * 120, [(False,)] * 120]
)
def test_power_requires_complete_boolean_120_pair_pilot(pairs):
    with pytest.raises(ValueError, match="120|boolean|pair"):
        api().choose_formal_n(pairs, [(False, False)] * 120)


@pytest.mark.parametrize("kwargs", [{"alpha": 0.1}, {"target_power": 0.7}, {"alpha": float("nan")}])
def test_power_design_cannot_change_alpha_or_target_after_pilot(kwargs):
    with pytest.raises(ValueError, match="fixed"):
        api().choose_formal_n([(False, False)] * 120, [(False, False)] * 120, **kwargs)


def test_power_provenance_wrapper_rejects_reused_or_formal_groups():
    rows = [
        {
            "group_id": f"power-{i}",
            "split_role": "power",
            "success": [True, True],
            "safety": [False, False],
            "method_hashes": {"B0": "a" * 64, "JOINT": "b" * 64},
            "source_hashes": ["c" * 64],
        }
        for i in range(120)
    ]
    module = api()
    decision = module.choose_formal_n_from_pilot(
        rows, excluded_groups={"old-group"}, method_hashes={"B0": "a" * 64, "JOINT": "b" * 64}
    )
    assert decision.selected_n == 600
    with pytest.raises(ValueError, match="isolation"):
        module.choose_formal_n_from_pilot(
            rows, excluded_groups={"power-1"}, method_hashes={"B0": "a" * 64, "JOINT": "b" * 64}
        )
    rows[0]["split_role"] = "formal"
    with pytest.raises(ValueError, match="power"):
        module.choose_formal_n_from_pilot(
            rows, excluded_groups=set(), method_hashes={"B0": "a" * 64, "JOINT": "b" * 64}
        )
