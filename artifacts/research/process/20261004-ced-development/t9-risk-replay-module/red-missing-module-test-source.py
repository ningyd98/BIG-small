"""Finite numerical SOFTWARE_ONLY controls, never actual risk/selection authority."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.risk_supervision import RiskObservationAllocation
from tests.test_research_risk_supervision import registered_fixture
from tests.test_research_risk_sources import ROOT, hashes, json_file


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.risk_replay")


def parameters(seed=7):
    return {
        "method": "logistic_isotonic_group_conformal",
        "seed": seed,
        "settings": {
            "coverage": .9,
            "iterations": 400,
            "learning_rate": .1,
            "l2": .01,
            "max_invalid_depth_fraction": .3,
            "max_frame_interval_s": 2.,
        },
    }


def numeric_fixture():
    """Hand-specified vectors/labels verify math only, no simulated acquisitions."""
    allocations, rows = [], []
    for split, count in (("train", 8), ("calibration", 18), ("selection", 4), ("test", 2)):
        for index in range(count):
            sample = f"{split}-{index}"
            group = f"{split}-g-{index//2 if split == 'calibration' else index}"
            allocations.append(RiskObservationAllocation(sample, f"case-{sample}", sample, split))
            rows.append({
                "sample_id": sample,
                "case_id": f"case-{sample}",
                "observation_id": sample,
                "split": split,
                "source_kind": "SOFTWARE_ONLY",
                "group_id": group,
                "scene_hash": hashlib.sha256(group.encode()).hexdigest(),
                "used_purposes": ("UNVIEWED",),
                "geometry_scope": "MARKER_CENTER_TRANSLATION",
                "online_features": {
                    "invalid_depth_fraction": 0., "depth_median_m": .4,
                    "depth_dispersion_m": 0., "pixel_consistency": 1.,
                    "calibration_residual_m": .004, "calibration_valid": 1.,
                    "calibration_fingerprint": 123., "motion_pair_valid": 1.,
                    "observed_motion_m_s": .05, "frame_interval_s": .25,
                },
                "offline_labels": {
                    "failure": bool(index % 2),
                    "geometric_error_m": .001*(index+1),
                    "motion_residual_m_s": .01*(index+1),
                },
                "failure_horizon": {"kind": "ORIGINAL_EPISODE_TERMINAL",
                    "evaluation_start_step": 120, "terminal_step": 121,
                    "terminal_sim_time_s": .5041666707},
            })
    return allocations, rows


def replay(allocations=None, rows=None, candidates=None):
    if allocations is None:
        allocations, rows = numeric_fixture()
    return api().replay_diagnostic_candidates(
        allocations, rows, candidates or [parameters(7), parameters(11)]
    )


def test_unregistered_audit_is_unknown_without_actual_accessors():
    result = api().RiskArtifactAuditor({}, {}).audit("absent")
    assert result.status == result.actual_source_status == "UNKNOWN"
    assert result.diagnostic_winner_hash is None
    assert result.counts["allocated_observations"] == 0
    assert not any(hasattr(result, name) for name in ("accepted", "execution_admitted", "method_accepted"))


def test_complete_finite_replay_is_deterministic_and_calibrated_with_hash_tie_break():
    result = replay()
    assert result["scope"] == "SOFTWARE_ONLY"
    assert result["status"] == "VALID"
    assert len(result["candidate_results"]) == 2
    expected = min(content_digest(parameters(7)), content_digest(parameters(11)))
    assert result["diagnostic_winner_hash"] == expected
    assert result["counts"]["allocated_observations"] == 32
    assert result == replay()
    for candidate in result["candidate_results"]:
        assert candidate["selection_brier"] == .25
        assert candidate["test_brier"] == .25
        assert candidate["model"]["weights"] == [0.] * 7
        assert candidate["model"]["intercept"] == 0.
        assert candidate["model"]["source_accepted"] is False
        assert candidate["calibration"]["isotonic_blocks"] == [[.5, .5, .5]]
        assert all(row["failure_probability"] == .5 for row in candidate["selection_results"])
        assert candidate["calibration"]["geometry_scope"] == "MARKER_CENTER_TRANSLATION"
        assert candidate["calibration"]["marker_point_error_bound_m"] == .018
        assert candidate["calibration"]["motion_residual_bound_m_s"] == .18
        assert candidate["selection_results"][0]["motion_bound_m_s"] == .23
        assert candidate["coverage"]["geometry_group_count"] == 9
        assert candidate["coverage"]["motion_group_count"] == 9
        assert all(value is None for value in candidate["model"]["action_models"].values())


def test_raw_sigmoid_cannot_replace_calibrated_probability():
    allocations, rows = numeric_fixture()
    for row in rows:
        if row["split"] == "train":
            row["offline_labels"]["failure"] = int(row["sample_id"].split("-")[-1]) >= 2
    result = replay(allocations, rows)
    candidate = result["candidate_results"][0]
    assert all(row["failure_probability"] == .5 for row in candidate["selection_results"])
    assert all(row["raw_failure_probability"] > .7 for row in candidate["selection_results"])
    assert candidate["selection_brier"] == .25


def test_group_maxima_and_nine_group_rank_not_frame_quantile():
    allocations, rows = numeric_fixture()
    for row in rows:
        if row["split"] == "calibration":
            i = int(row["sample_id"].split("-")[-1])
            row["offline_labels"]["geometric_error_m"] = .1 if i == 0 else 0.
    result = replay(allocations, rows)
    assert all(c["calibration"]["marker_point_error_bound_m"] == .1 for c in result["candidate_results"])


@pytest.mark.parametrize("kind", ["eight_groups", "no_geometry", "no_motion", "no_classes"])
def test_incomplete_calibration_retains_population_and_has_no_feasible_winner(kind):
    allocations, rows = numeric_fixture()
    for row in rows:
        if row["split"] == "calibration":
            if kind == "eight_groups" and row["group_id"] == "calibration-g-8":
                row["group_id"] = "calibration-g-7"
                row["scene_hash"] = hashlib.sha256(row["group_id"].encode()).hexdigest()
            elif kind == "no_geometry":
                row["offline_labels"]["geometric_error_m"] = None
            elif kind == "no_motion":
                row["offline_labels"]["motion_residual_m_s"] = None
            elif kind == "no_classes":
                row["offline_labels"]["failure"] = False
    result = replay(allocations, rows)
    assert result["status"] == "NO_FEASIBLE"
    assert result["diagnostic_winner_hash"] is None
    assert result["split_counts"]["calibration"]["allocated"] == 18
    assert all(c["selection_brier"] is None for c in result["candidate_results"])
    assert all(len(c["selection_results"]) == 4 for c in result["candidate_results"])


@pytest.mark.parametrize("kind", ["missing_row", "missing_features", "missing_failure", "outside_support", "no_pair"])
def test_missing_selection_cannot_choose_favorable_surviving_subset(kind):
    allocations, rows = numeric_fixture()
    index = next(i for i,r in enumerate(rows) if r["sample_id"] == "selection-0")
    if kind == "missing_row":
        rows.pop(index)
    elif kind == "missing_features":
        rows[index]["online_features"] = None
    elif kind == "missing_failure":
        rows[index]["offline_labels"]["failure"] = None
    elif kind == "outside_support":
        rows[index]["online_features"]["depth_median_m"] = 99.
    else:
        rows[index]["online_features"]["motion_pair_valid"] = 0.
    result = replay(allocations, rows)
    assert result["status"] == "NO_FEASIBLE"
    assert result["counts"]["allocated_observations"] == 32
    assert result["split_counts"]["selection"]["allocated"] == 4
    assert all(len(c["selection_results"]) == 4 for c in result["candidate_results"])
    assert all(c["selection_brier"] is None for c in result["candidate_results"])


def test_test_labels_and_features_do_not_fit_select_or_change_winner():
    allocations, rows = numeric_fixture()
    before = replay(allocations, rows)
    for row in rows:
        if row["split"] == "test":
            row["offline_labels"]["failure"] = True
            row["online_features"]["depth_median_m"] = 99.
    after = replay(allocations, rows)
    assert before["diagnostic_winner_hash"] == after["diagnostic_winner_hash"]
    for a,b in zip(before["candidate_results"], after["candidate_results"], strict=True):
        assert a["model"] == b["model"]
        assert a["calibration"] == b["calibration"]
        assert a["selection_results"] == b["selection_results"]
        assert b["test_brier"] is None


@pytest.mark.parametrize("kind", ["component", "history", "feature_truth", "bool_feature", "huge_feature", "label_bool", "extra_row"])
def test_invalid_source_or_online_boundary_cannot_feed_numeric_fit(kind):
    allocations, rows = numeric_fixture()
    if kind == "component":
        rows[-1]["group_id"] = rows[0]["group_id"]
    elif kind == "history":
        rows[-1]["used_purposes"] = ("TUNED",)
    elif kind == "feature_truth":
        rows[0]["online_features"]["true_error_m"] = 0.
    elif kind == "bool_feature":
        rows[0]["online_features"]["depth_median_m"] = True
    elif kind == "huge_feature":
        rows[0]["online_features"]["depth_median_m"] = 10**500
    elif kind == "label_bool":
        rows[0]["offline_labels"]["failure"] = 0
    else:
        rows.append({**rows[0], "sample_id":"unallocated"})
    with pytest.raises(ValueError):
        replay(allocations, rows)


@pytest.mark.parametrize("kind", ["duplicate", "incomplete", "authority_flag", "mutable_settings", "boolean_seed"])
def test_candidates_require_complete_exact_frozen_recipe_objects(kind):
    candidates = [parameters()]
    if kind == "duplicate":
        candidates.append(parameters())
    elif kind == "incomplete":
        candidates[0].pop("settings")
    elif kind == "authority_flag":
        candidates[0]["eligible"] = True
    elif kind == "mutable_settings":
        candidates[0]["settings"]["l2"] = .2
    else:
        candidates[0]["seed"] = True
    with pytest.raises(ValueError):
        replay(candidates=candidates)


def registered_replay(tmp_path: Path):
    module = api()
    source, directory, measurements, frames = registered_fixture(tmp_path)
    inventory = dict(source.raw_registration.current_source_hashes)
    for name in module.required_replay_source_paths():
        inventory[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    source = replace(source, raw_registration=replace(source.raw_registration, current_source_hashes=inventory))
    artifacts = tmp_path / "replay"
    artifacts.mkdir()
    config = {
        "schema_version": "ced.risk-replay-config.v1", "inventory_version": "software-grid-v1",
        "selection_rule": "minimum_brier_then_parameters_hash",
        "population_rule": "all_allocated_observations_v1",
        "candidates": [parameters(7), parameters(11)],
        "environment": dict(module.risk_replay_environment()),
        "recipe_source_hashes": {name: inventory[name] for name in module.required_replay_source_paths()},
        "supervision_registration_hash": module.supervision_registration_hash(source),
    }
    json_file(artifacts / "config.json", config)
    registration = module.RiskReplayRegistration(artifacts, hashes(artifacts), "config.json", "source")
    return registration, source, artifacts, directory, measurements


def test_registered_raw_only_source_is_reread_and_keeps_failure_denominators(tmp_path):
    registration, source, _, _, _ = registered_replay(tmp_path)
    result = api().RiskArtifactAuditor({"replay":registration}, {"source":source}).audit("replay")
    assert result.status == result.actual_source_status == "UNKNOWN"
    assert result.comparison_status == "UNKNOWN"
    assert result.diagnostic_winner_hash is None
    assert result.counts["assigned_attempts"] == 1
    assert result.counts["allocated_observations"] == 2
    assert result.counts["task_labels"] == 2
    assert len(result.candidate_results) == 2
    assert "initial_source_registration_unavailable" in result.reasons
    assert "point_motion_label_reconstruction_unavailable" in result.reasons
    assert "original_candidate_artifacts_unavailable" in result.reasons


def test_registry_rejects_fake_supervision_auditor_receipt_and_subclass(tmp_path):
    module=api()
    registration, source, _, _, _ = registered_replay(tmp_path)
    with pytest.raises(TypeError):
        module.RiskArtifactAuditor({"replay":registration}, {"source":{"status":"VALID"}})
    from cloud_edge_robot_arm.research.risk_supervision import RiskSupervisionAuditor, RiskSupervisionRegistration
    with pytest.raises(TypeError):
        module.RiskArtifactAuditor({"replay":registration}, RiskSupervisionAuditor({"source":source}))
    class Forged(RiskSupervisionRegistration):
        pass
    copied=Forged(**source.__dict__)
    with pytest.raises(TypeError):
        module.RiskArtifactAuditor({"replay":registration}, {"source":copied})


def test_rehashed_candidate_config_cannot_omit_frozen_full_object(tmp_path):
    registration, source, artifacts, _, _ = registered_replay(tmp_path)
    config=json.loads((artifacts/"config.json").read_text())
    config["candidates"][0] = {"parameters_hash": content_digest(parameters())}
    json_file(artifacts/"config.json", config)
    registration=replace(registration, original_file_hashes=hashes(artifacts))
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == 2


def test_original_current_source_drift_does_not_drop_failed_assignments(tmp_path):
    registration, source, _, directory, _ = registered_replay(tmp_path)
    (directory/"raw-physics.jsonl").write_text("null\n")
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == "INVALID"
    assert result.counts["assigned_attempts"] == 1
    assert result.counts["allocated_observations"] == 2
    assert result.counts["missing_observations"] == 2
