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
        assert candidate["model"]["weights"] == (0.,) * 7
        assert candidate["model"]["intercept"] == 0.
        assert candidate["model"]["source_accepted"] is False
        assert candidate["calibration"]["isotonic_blocks"] == ((.5, .5, .5),)
        assert all(row["failure_probability"] == .5 for row in candidate["selection_results"])
        assert candidate["calibration"]["geometry_scope"] == "MARKER_CENTER_TRANSLATION"
        assert candidate["calibration"]["marker_point_error_bound_m"] == pytest.approx(.018, abs=1e-15)
        assert candidate["calibration"]["motion_residual_bound_m_s"] == pytest.approx(.18, abs=1e-15)
        assert candidate["selection_results"][0]["motion_bound_m_s"] == pytest.approx(.23, abs=1e-15)
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


def test_authorized_development_train_history_is_retained_and_formal_forbidden():
    allocations, rows = numeric_fixture()
    for row in rows:
        if row["split"] == "train":
            row["used_purposes"] = ("DEVELOPMENT_FEEDBACK", "TRAIN")
    result = replay(allocations, rows)
    assert result["status"] == "VALID"
    assert result["component_usage_histories"]["train-g-0"] == ("DEVELOPMENT_FEEDBACK", "TRAIN")
    assert result["candidate_results"][0]["model"]["formal_use"] == "FORBIDDEN"
    assert result["candidate_results"][0]["model"]["fit_provenance"]["used_purposes_by_group"]["train-g-0"] == ("DEVELOPMENT_FEEDBACK", "TRAIN")


@pytest.mark.parametrize("kind", ["missing_train", "missing_calibration", "one_class_train", "unknown_history"])
def test_required_fit_populations_are_unavailable_instead_of_filtered(kind):
    allocations, rows = numeric_fixture()
    if kind == "missing_train":
        rows[0]["online_features"] = None
    elif kind == "missing_calibration":
        next(row for row in rows if row["split"] == "calibration")["offline_labels"]["failure"] = None
    elif kind == "one_class_train":
        for row in rows:
            if row["split"] == "train":
                row["offline_labels"]["failure"] = True
    else:
        rows[0]["used_purposes"] = ("UNKNOWN",)
    result = replay(allocations, rows)
    assert result["status"] == "UNAVAILABLE"
    assert result["counts"]["allocated_observations"] == 32
    assert all(c["model"] is None and len(c["selection_results"]) == 4 for c in result["candidate_results"])


def test_registered_invalid_initial_is_preserved_as_invalid_source(tmp_path):
    from tests.test_research_admission import _registration
    registration, source, artifacts, _, _ = registered_replay(tmp_path)
    initial_dir = tmp_path / "initial"
    initial_dir.mkdir()
    initial = _registration(initial_dir)
    initial.protocol_path.write_text("null\n")
    source = replace(source, initial_registration=initial)
    config=json.loads((artifacts/"config.json").read_text())
    config["supervision_registration_hash"] = api().supervision_registration_hash(source)
    json_file(artifacts/"config.json", config)
    registration=replace(registration, original_file_hashes=hashes(artifacts))
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == result.actual_source_status == "INVALID"
    assert result.counts["allocated_observations"] == 2


def original_numeric_artifacts(tmp_path):
    """Explicit SOFTWARE_ONLY original files, for byte/schema/math negative controls."""
    module=api()
    result=replay()
    registrations={}
    for candidate in result["candidate_results"]:
        digest=candidate["parameters_hash"]
        folder=tmp_path/digest
        folder.mkdir()
        json_file(folder/"model.json", dict_plain(candidate["model"]))
        cal_name=f"calibration-{candidate['calibration_hash']}.json"
        json_file(folder/cal_name, dict_plain(candidate["calibration"]))
        registrations[digest]=module.RiskReplayArtifactRegistration(f"{digest}/model.json", f"{digest}/{cal_name}")
    json_file(tmp_path/"selection.json", dict_plain(result["selection_snapshot"]))
    json_file(tmp_path/"config.json", {"fixture_scope":"SOFTWARE_ONLY"})
    registered=module.RiskReplayRegistration(tmp_path, hashes(tmp_path), "config.json", "source", registrations, "selection.json")
    return registered,result


def dict_plain(value):
    from collections.abc import Mapping
    if isinstance(value, Mapping):
        return {key:dict_plain(item) for key,item in value.items()}
    if isinstance(value, (list,tuple)):
        return [dict_plain(item) for item in value]
    return value


@pytest.mark.parametrize("kind", ["coefficient", "raw_probability", "omit_candidate", "winner", "source_flag", "unknown_schema", "bool_coefficient", "wrong_filename"])
def test_rehashed_original_numeric_files_cannot_override_full_replay(tmp_path, kind):
    registered,result=original_numeric_artifacts(tmp_path)
    digest=result["candidate_results"][0]["parameters_hash"]
    artifact=registered.candidate_artifacts[digest]
    path=tmp_path/artifact.model_path
    payload=json.loads(path.read_text())
    if kind in {"raw_probability","omit_candidate","winner"}:
        path=tmp_path/"selection.json"
        payload=json.loads(path.read_text())
        if kind == "raw_probability":
            payload["candidate_results"][0]["selection_results"][0]["failure_probability"] = .75
            payload["candidate_results"][0]["selection_brier"] = .328125
            payload["diagnostic_winner_hash"] = payload["candidate_results"][1]["parameters_hash"]
        elif kind == "omit_candidate":
            payload["candidate_results"].pop()
        else:
            payload["diagnostic_winner_hash"] = "f"*64
    elif kind == "coefficient":
        payload["weights"][0] = .1
    elif kind == "bool_coefficient":
        payload["weights"][0] = True
    elif kind == "source_flag":
        payload["source_accepted"] = True
    elif kind == "unknown_schema":
        payload["schema_version"] = "unknown.model.v9"
    else:
        bad=tmp_path/digest/"calibration-wrong.json"
        old=tmp_path/artifact.calibration_path
        old.rename(bad)
        artifacts=dict(registered.candidate_artifacts)
        artifacts[digest]=replace(artifact, calibration_path=f"{digest}/{bad.name}")
        registered=replace(registered, candidate_artifacts=artifacts, original_file_hashes=hashes(tmp_path))
    if kind != "wrong_filename":
        json_file(path, payload)
        if kind == "coefficient":
            old_cal=tmp_path/artifact.calibration_path
            calibrated=json.loads(old_cal.read_text())
            calibrated.pop("content_hash")
            calibrated["model_hash"]=content_digest(payload)
            calibrated["content_hash"]=content_digest(calibrated)
            new_cal=old_cal.with_name(f"calibration-{calibrated['content_hash']}.json")
            old_cal.unlink()
            json_file(new_cal,calibrated)
            artifacts=dict(registered.candidate_artifacts)
            artifacts[digest]=replace(artifact,calibration_path=str(new_cal.relative_to(tmp_path)))
            registered=replace(registered,candidate_artifacts=artifacts,original_file_hashes=hashes(tmp_path))
        else:
            registered=replace(registered, original_file_hashes=hashes(tmp_path))
    pattern = "full replay" if kind == "coefficient" else "probabilities" if kind == "raw_probability" else None
    with pytest.raises(ValueError, match=pattern):
        api()._compare_original_artifacts(registered, result, [])


def test_complete_original_numeric_comparison_remains_diagnostic_only(tmp_path):
    registered,result=original_numeric_artifacts(tmp_path)
    assert api()._compare_original_artifacts(registered, result, []) == "VALID"
    assert result["scope"] == "SOFTWARE_ONLY"
    assert all(c["model"]["source_accepted"] is False for c in result["candidate_results"])


def test_contradictory_component_histories_cannot_overwrite_original_history():
    allocations, rows = numeric_fixture()
    rows[8]["used_purposes"] = ("UNKNOWN",)
    assert rows[8]["group_id"] == rows[9]["group_id"]
    with pytest.raises(ValueError, match="history"):
        replay(allocations, rows)


def test_fresh_pair_with_zero_interval_cannot_be_a_valid_online_input():
    allocations, rows = numeric_fixture()
    rows[0]["online_features"]["frame_interval_s"] = 0.
    with pytest.raises(ValueError, match="interval"):
        replay(allocations, rows)


@pytest.mark.parametrize("kind", ["null", "duplicate_key", "environment", "unknown_field"])
def test_rehashed_config_shape_and_environment_are_invalid_with_full_denominator(tmp_path, kind):
    registration, source, artifacts, _, _ = registered_replay(tmp_path)
    path=artifacts/"config.json"
    config=json.loads(path.read_text())
    if kind == "null":
        path.write_text("null\n")
    elif kind == "duplicate_key":
        path.write_text('{"schema_version":"unknown","schema_version":"ced.risk-replay-config.v1"}\n')
    else:
        if kind == "environment":
            config["environment"]["python"]="unknown-runtime"
        else:
            config["accepted"]=True
        json_file(path,config)
    registration=replace(registration, original_file_hashes=hashes(artifacts))
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == result.diagnostic_status == "INVALID"
    assert result.counts["assigned_attempts"] == 1
    assert result.counts["allocated_observations"] == 2


def test_raw_allocation_omission_cannot_redefine_full_source_population(tmp_path):
    registration, source, artifacts, _, _ = registered_replay(tmp_path)
    source=replace(source, allocations=source.allocations[:1])
    config=json.loads((artifacts/"config.json").read_text())
    config["supervision_registration_hash"]=api().supervision_registration_hash(source)
    json_file(artifacts/"config.json",config)
    registration=replace(registration, original_file_hashes=hashes(artifacts))
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == "INVALID"
    assert result.counts["allocated_observations"] == result.counts["missing_observations"] == 2
    assert len(result.candidate_results) == 2


def test_artifact_root_lexical_symlink_before_parent_component_is_rejected(tmp_path):
    registration, source, artifacts, _, _ = registered_replay(tmp_path)
    alias=tmp_path/"alias"
    alias.symlink_to(artifacts, target_is_directory=True)
    registration=replace(registration, artifact_root=alias/".."/"replay")
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == "INVALID"
    assert result.counts["allocated_observations"] == 2


def test_changed_original_during_replay_is_invalid_without_discarding_rows(tmp_path, monkeypatch):
    registration, source, _, directory, _ = registered_replay(tmp_path)
    module=api()
    original=module.replay_diagnostic_candidates
    def mutate_after_numeric(*args):
        result=original(*args)
        with (directory/"raw-physics.jsonl").open("a") as stream:
            stream.write(" \n")
        return result
    monkeypatch.setattr(module,"replay_diagnostic_candidates",mutate_after_numeric)
    result=module.RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.status == "INVALID"
    assert result.counts["allocated_observations"] == 2
    assert len(result.candidate_results) == 2


def test_schema_rejects_actual_permission_fields_even_on_diagnostic_files(tmp_path):
    registered,result=original_numeric_artifacts(tmp_path)
    digest=result["candidate_results"][0]["parameters_hash"]
    path=tmp_path/registered.candidate_artifacts[digest].model_path
    model=json.loads(path.read_text())
    model["execution_admitted"]=True
    json_file(path,model)
    registered=replace(registered,original_file_hashes=hashes(tmp_path))
    with pytest.raises(ValueError,match="fields"):
        api()._compare_original_artifacts(registered,result,[])


def test_unavailable_original_numeric_artifacts_cannot_be_reproduction_pass(tmp_path):
    registered,result=original_numeric_artifacts(tmp_path)
    registered=replace(registered,candidate_artifacts={},selection_results_path=None)
    reasons=[]
    assert api()._compare_original_artifacts(registered,result,reasons) == "UNKNOWN"
    assert "original_candidate_artifacts_unavailable" in reasons


def test_full_point_group_bound_is_recomputed_after_coherent_calibration_rehash(tmp_path):
    registered,result=original_numeric_artifacts(tmp_path)
    digest=result["candidate_results"][0]["parameters_hash"]
    artifact=registered.candidate_artifacts[digest]
    old=tmp_path/artifact.calibration_path
    calibration=json.loads(old.read_text())
    calibration.pop("content_hash")
    calibration["marker_point_error_bound_m"]=.017
    calibration["content_hash"]=content_digest(calibration)
    new=old.with_name(f"calibration-{calibration['content_hash']}.json")
    old.unlink()
    json_file(new,calibration)
    artifacts=dict(registered.candidate_artifacts)
    artifacts[digest]=replace(artifact,calibration_path=str(new.relative_to(tmp_path)))
    registered=replace(registered,candidate_artifacts=artifacts,original_file_hashes=hashes(tmp_path))
    with pytest.raises(ValueError,match="full replay"):
        api()._compare_original_artifacts(registered,result,[])


def test_all_candidate_blockers_are_retained_when_calibration_is_also_missing(tmp_path):
    registration, source, _, _, _ = registered_replay(tmp_path)
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert all("complete_calibration_population_unavailable" in candidate["reasons"]
               and "both_class_training_unavailable" in candidate["reasons"]
               for candidate in result.candidate_results)


@pytest.mark.parametrize("identity", ["../source", "source with spaces"])
def test_only_opaque_source_registration_identity_is_allowed(tmp_path, identity):
    with pytest.raises(ValueError,match="identity"):
        api().RiskReplayRegistration(tmp_path,{"config.json":"a"*64},"config.json",identity)


def test_diagnostic_audit_constructor_cannot_mint_actual_valid_source():
    with pytest.raises(ValueError,match="actual"):
        api().RiskArtifactAudit("VALID","VALID","VALID","VALID",(),{}, {}, (), None, {}, {})


def test_registered_original_component_histories_are_preserved_without_fitted_model(tmp_path):
    registration, source, _, _, _ = registered_replay(tmp_path)
    result=api().RiskArtifactAuditor({"replay":registration},{"source":source}).audit("replay")
    assert result.component_usage_histories == {source.histories[0].group_id:("UNVIEWED",)}
