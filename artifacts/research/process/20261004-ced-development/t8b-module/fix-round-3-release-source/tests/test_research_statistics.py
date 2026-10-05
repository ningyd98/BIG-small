"""配对得分区间、Holm 与场景簇 bootstrap 的独立数值反例。"""

from importlib import import_module, util

import pytest


def api():
    name = "cloud_edge_robot_arm.research.statistics"
    assert util.find_spec(name) is not None, "missing production research statistics"
    return import_module(name)


def test_matched_binary_uses_fixed_four_cell_score_counts():
    # ++40,+-20,-+10,--30 -> JOINT-B0=.1, McNemar score z=10/sqrt(30).
    pairs = (
        [(True, True)] * 40 + [(True, False)] * 20 + [(False, True)] * 10 + [(False, False)] * 30
    )
    result = api().paired_binary_effect(pairs)
    assert result.point == pytest.approx(0.1)
    assert result.denominator == 100
    assert result.p_value == pytest.approx(0.0678891549, abs=1e-8)
    assert result.lower95 < result.point < result.upper95
    # Same marginal .6/.5, different paired concordance => larger uncertainty.
    less_concordant = (
        [(True, True)] * 30 + [(True, False)] * 30 + [(False, True)] * 20 + [(False, False)] * 20
    )
    wider = api().paired_binary_effect(less_concordant)
    assert wider.point == pytest.approx(0.1)
    assert wider.p_value == pytest.approx(0.1572992071, abs=1e-8)
    assert wider.upper95 - wider.lower95 > result.upper95 - result.lower95


def test_all_concordant_difference_has_nonzero_score_interval():
    result = api().paired_binary_effect([(False, False)] * 100)
    # Analytic boundary score inversion z^2/(n+z^2), not zero-width Wald.
    assert result.point == 0
    assert result.p_value == 1
    assert result.upper95 == pytest.approx(0.0369934982, abs=1e-8)
    assert result.lower95 == pytest.approx(-0.0369934982, abs=1e-8)
    assert result.one_sided_upper95 == pytest.approx(0.0263427208, abs=1e-8)


def test_zero_events_have_nonzero_upper_bound():
    assert api().zero_event_upper_bound(100) == pytest.approx(0.0295130496, abs=1e-8)
    assert api().zero_event_upper_bound(1) == pytest.approx(0.95)
    with pytest.raises(ValueError):
        api().zero_event_upper_bound(0)


@pytest.mark.parametrize("values", [[], [(1, 0)], [(True,)], [None]])
def test_binary_estimate_rejects_missing_or_nonboolean_pairs(values):
    with pytest.raises(ValueError):
        api().paired_binary_effect(values)


def test_holm_adjustment_is_applied():
    adjusted = api().holm_adjust(
        {"requests": 0.001, "success": 0.01, "safety": 0.02, "gate": 0.2, "recovery": 0.5}
    )
    assert adjusted == {
        "requests": 0.005,
        "success": 0.04,
        "safety": 0.06,
        "gate": 0.4,
        "recovery": 0.5,
    }
    with pytest.raises(ValueError):
        api().holm_adjust({"bad": float("nan")})


def records(group_count=8, *, baseline=10, joint=5):
    from cloud_edge_robot_arm.research.assignments import EpisodeAssignment, EpisodeRecord
    from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot
    from cloud_edge_robot_arm.research.models import EvidenceKind, RunProvenance
    from cloud_edge_robot_arm.research.protocol import STRATA
    from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome

    result = []
    for index in range(group_count):
        for method, calls in (("B0", baseline), ("JOINT", joint)):
            row = EpisodeAssignment(
                f"g{index}::{method}",
                f"g{index}",
                STRATA[index % 12],
                method,
                index,
                f"network-{index}",
                len(result),
            )
            provenance = RunProvenance(
                run_id=row.assignment_id,
                source_tree_hash="",
                scene_group_id=row.group_id,
                split_role="formal",
                physics_steps=0,
                evidence_kind=EvidenceKind.MOCK,
            )
            outcome = VisualEpisodeOutcome(False, "FAILED", False, "SOFTWARE_FIXTURE", 0, 0, 0, 1.0)
            result.append(
                EpisodeRecord(
                    row,
                    outcome,
                    provenance,
                    CostSnapshot(model_requests=calls, cloud_model_requests=calls),
                    120.0,
                    None,
                    (),
                    (),
                    (),
                    {},
                    run_status="FAILED",
                )
            )
    return result


def test_bootstrap_resamples_groups_not_frames():
    from dataclasses import replace

    rows = records()
    result = api().stratified_paired_bootstrap(rows, "cloud_requests_relative_reduction")
    duplicated_frames = [
        replace(row, verification_records=tuple({"status": "UNKNOWN"} for _ in range(100)))
        for row in rows
    ]
    repeated = api().stratified_paired_bootstrap(
        duplicated_frames, "cloud_requests_relative_reduction"
    )
    assert repeated == result
    assert result.denominator == 8
    assert result.point == result.lower95 == result.upper95 == 0.5


def test_baseline_zero_returns_na_relative_gain():
    result = api().stratified_paired_bootstrap(
        records(baseline=0, joint=0), "cloud_requests_relative_reduction"
    )
    assert result.point is result.lower95 is result.upper95 is None
    assert result.p_value is None


def test_bootstrap_rejects_less_than_ten_thousand_or_unpaired_groups():
    with pytest.raises(ValueError, match="10000"):
        api().stratified_paired_bootstrap(
            records(), "cloud_requests_relative_reduction", iterations=9999
        )
    with pytest.raises(ValueError, match="paired"):
        api().stratified_paired_bootstrap(records()[:-1], "cloud_requests_relative_reduction")


def test_score_noninferiority_p_value_is_not_zero_difference_p_value():
    module = api()
    concordant = [(True, True)] * 600
    success = module.paired_binary_effect(concordant, null_difference=-0.03, alternative="greater")
    safety = module.paired_binary_effect(concordant, null_difference=0.01, alternative="less")
    assert success.p_value < 0.01
    assert safety.p_value < 0.01
    assert module.paired_binary_effect(concordant).p_value == 1


def test_fixed_opportunity_reduction_clusters_multiple_opportunities_per_group():
    effect = api().clustered_rate_reduction([(10, 5), (20, 10)], ("STATIC_RTT0", "STATIC_RTT100"))
    assert effect.denominator == 2
    assert effect.point == effect.lower95 == effect.upper95 == 0.5
    assert effect.p_value == 0.25


def test_bootstrap_rejects_mismatched_repeated_seed_multiplicity():
    from dataclasses import replace

    from cloud_edge_robot_arm.research.assignments import EpisodeAssignment

    originals = records(1)
    rows = []
    for method, seeds in (("B0", (1, 1, 2)), ("JOINT", (1, 2, 2))):
        base = next(row for row in originals if row.assignment.method_id == method)
        for index, seed in enumerate(seeds):
            assignment = EpisodeAssignment(
                f"g0::{method}::{index}", "g0", "STATIC_RTT0", method, seed, "network", index
            )
            rows.append(
                replace(
                    base,
                    assignment=assignment,
                    provenance=base.provenance.model_copy(
                        update={"run_id": assignment.assignment_id}
                    ),
                )
            )
    with pytest.raises(ValueError, match="paired"):
        api().stratified_paired_bootstrap(rows, "cloud_requests_relative_reduction")
