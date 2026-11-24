import pytest
from scripts.graduation.proposal_camera import STEPS
from scripts.graduation.proposal_translated import STORED_POSES, admissions, slots


def test_qualification_requires_both_real_views_all_states_and_negative_controls():
    flags = {s: True for s in STEPS}
    checks = dict(
        verified=flags,
        nominal_positive=True,
        nominal_negative=True,
        translated_detected=flags,
        probes={"nominal": True, "translated": True},
        absent_rejected={
            "120-nominal": True,
            "120-translated": True,
            "848-nominal": True,
            "848-translated": True,
        },
    )
    assert admissions(**checks) == []
    assert admissions(**{**checks, "translated_detected": {**flags, 848: False}})
    assert admissions(**{**checks, "probes": {"nominal": True, "translated": False}})
    with pytest.raises(ValueError):
        admissions(**{**checks, "verified": {120: True}})
    cases = slots()
    assert len(cases) == 8
    assert [(r["seed"], r["view"]) for r in cases[:4]] == [
        (24112501, "nominal"),
        (24112501, "translated"),
        (24112502, "translated"),
        (24112502, "nominal"),
    ]
    assert len(STORED_POSES) == 4


def test_paired_difference_and_unacquired_cases_are_counted_by_placement():
    from scripts.graduation.proposal_translated_cases import paired_summary

    rows = [{**c, "acquired": True, "joint_success": c["view"] == "translated"} for c in slots()]
    result = paired_summary(rows)
    assert result["paired_success_difference"] == 1
    assert result["fully_acquired_groups"] == 4
    rows[0]["acquired"] = False
    assert paired_summary(rows)["paired_success_difference"] is None
    with pytest.raises(ValueError):
        paired_summary(rows[:-1])


def test_exact_binomial_limits_include_extremes_and_invert_both_tails():
    import math

    from scripts.graduation.proposal_translated_cases import exact_discordance_interval

    bounds = [exact_discordance_interval(k, 4) for k in range(5)]
    assert bounds[0] == pytest.approx((0.0, 1 - 0.0125**0.25), abs=1e-10)
    assert bounds[-1] == pytest.approx((0.0125**0.25, 1.0), abs=1e-10)
    for k, (lo, hi) in enumerate(bounds):
        assert (lo, hi) == pytest.approx((1 - bounds[4 - k][1], 1 - bounds[4 - k][0]), abs=1e-10)
        if k:
            assert lo > bounds[k - 1][0] and hi > bounds[k - 1][1]
        if 0 < k < 4:
            assert sum(
                math.comb(4, j) * lo**j * (1 - lo) ** (4 - j) for j in range(k, 5)
            ) == pytest.approx(0.0125, abs=1e-10)
            assert sum(
                math.comb(4, j) * hi**j * (1 - hi) ** (4 - j) for j in range(k + 1)
            ) == pytest.approx(0.0125, abs=1e-10)


@pytest.mark.parametrize("gain,loss", [(0, 0), (4, 0), (0, 4), (1, 1), (2, 1)])
def test_discordance_signs_and_group_denominator(gain, loss):
    from scripts.graduation.proposal_translated_cases import paired_summary

    rows = []
    for s in slots():
        group = int(s["group"][1:]) - 1
        win = group < gain if s["view"] == "translated" else gain <= group < gain + loss
        rows.append({**s, "acquired": True, "joint_success": win})
    r = paired_summary(rows)
    assert (r["gains"], r["losses"], r["paired_success_difference"]) == (
        gain,
        loss,
        (gain - loss) / 4,
    )
    lo, hi = r["conservative_difference_ci95"]
    assert -1 <= lo <= r["paired_success_difference"] <= hi <= 1
