"""Software fixtures exercise guards; they are never research calibration evidence."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import struct
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from PIL import Image

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.datasets.rgbd.models import SampleRecord, SceneSpec, content_digest
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def module(name: str) -> Any:
    try:
        return importlib.import_module(f"cloud_edge_robot_arm.vision.risk.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"risk {name} behavior is not implemented")


def observation(
    name: str = "frame", *, seconds: float = 1, depth: float = 1, version: str = "v1"
) -> RGBDObservation:
    image = io.BytesIO()
    Image.new("RGB", (2, 2), (30, 50, 70)).save(image, format="PNG")
    return RGBDObservation(
        frame_id=name,
        captured_at=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds),
        sim_time_s=seconds,
        width=2,
        height=2,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<4f", *([depth] * 4))).decode(),
        intrinsics=(2, 2, 1, 1),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        source="mujoco_camera",
        scene_id="scene",
        episode_id="episode",
        calibration_version=version,
    )


def record(index: int, split: str, **supervision: Any) -> SampleRecord:
    scene = SceneSpec.from_parameters({"layout": index}, "fixture-asset", index)
    frame = observation(f"f-{index}", depth=1 + index / 100)
    state = f"state-{index}"
    return SampleRecord(
        sample_id=f"s-{index}",
        group_id=scene.group_id,
        episode_id=f"e-{index}",
        frame_id=frame.frame_id,
        scene=scene,
        observation_metadata=frame.model_dump(
            mode="json", exclude={"rgb_png_base64", "depth_float32_base64", "valid_mask_base64"}
        ),
        labels={
            "risk_supervision": {
                "split": split,
                "failure": bool(index % 2),
                "calibration_residuals_m": [0.001],
                **supervision,
            }
        },
        physics_state_hash=state,
        status="POSITIVE",
        captured_frame=CapturedFrame(frame, (-1,) * 4, {}, state, (state,) * 3),
    )


def fitted() -> Any:
    return module("fit").fit_risk_model([record(i, "train") for i in range(10)], seed=7)


def calibrated() -> Any:
    return module("calibration").calibrate_risk(
        fitted(),
        [record(i, "calibration", geometric_error_m=(i - 9) / 100) for i in range(10, 19)],
    )


@pytest.mark.parametrize(
    "key",
    [
        "target_xyz",
        "true_localization_error",
        "fault_label",
        "future_fault",
        "oracle_success",
        "candidate_probability",
        "reported_confidence",
    ],
)
def test_true_error_and_fault_label_are_not_online_features(key: str) -> None:
    models = module("models")
    with pytest.raises(ValueError):
        models.RiskFeatures({key: models.FeatureValue(0.9, "ESTIMATOR")}, "frame")


def test_oracle_features_never_enter_edge_judgment() -> None:
    extract = module("features").extract_risk_features
    base = observation()
    with pytest.raises(ValueError):
        extract(base.model_copy(update={"target_xyz": [1, 2, 3]}), None, [0.001])
    # Offline decoy truth stays entirely outside the online extractor signature.
    other = record(100, "train", true_localization_error=900)
    first = module("fit").sample_features(other, [other], "train")
    other.labels["risk_supervision"]["true_localization_error"] = -900
    assert module("fit").sample_features(other, [other], "train") == first


def test_feature_sources_cannot_be_relabeled_truth() -> None:
    models = module("models")
    with pytest.raises(ValueError):
        models.FeatureValue(1, "ORACLE")
    with pytest.raises(ValueError):
        models.FeatureValue(float("nan"), "DEPTH")


def test_motion_bound_uses_timestamped_new_frames() -> None:
    extract = module("features").extract_risk_features
    before = observation("before", seconds=0, depth=1)
    after = observation("after", seconds=2, depth=1.2)
    features = extract(after, before, [0.001])
    assert features.values["frame_interval_s"].value == 2
    assert features.values["motion_pair_valid"].value == 1
    assert features.values["observed_motion_m_s"].value == pytest.approx(0.1224745)
    assert extract(after.crop((0, 0, 1, 1)), after, [0.001]).values["motion_pair_valid"].value == 0


def test_reported_confidence_is_not_probability() -> None:
    estimate = module("calibration").estimate_risk(
        fitted(), module("features").extract_risk_features(observation(), None, [0.001])
    )
    assert estimate.status == "UNKNOWN"
    assert estimate.failure_probability is None


def test_candidate_probability_is_not_failure_probability() -> None:
    sample = record(0, "train")
    sample.labels = {"positive": True, "candidate_probability": 0.9}
    with pytest.raises(ValueError, match="risk supervision"):
        module("fit").fit_risk_model([sample], seed=0)


def test_fit_accepts_only_train_and_both_failure_classes() -> None:
    with pytest.raises(ValueError, match="train"):
        module("fit").fit_risk_model([record(0, "selection"), record(1, "test")], seed=0)
    with pytest.raises(ValueError, match="both"):
        module("fit").fit_risk_model([record(0, "train"), record(2, "train")], seed=0)


def test_calibration_groups_are_disjoint() -> None:
    model = fitted()
    with pytest.raises(ValueError, match="overlap"):
        module("calibration").calibrate_risk(model, [record(0, "calibration")])
    forged = record(0, "calibration")
    forged = forged.model_copy(
        update={
            "group_id": "forged",
            "scene": forged.scene.model_copy(update={"group_id": "forged"}),
        }
    )
    with pytest.raises(ValueError, match="overlap"):
        module("calibration").calibrate_risk(model, [forged])


@pytest.mark.parametrize("kind", ["invalid", "drift", "old_crop"])
def test_invalid_depth_or_drift_returns_unknown(kind: str) -> None:
    before = observation("before", seconds=0)
    current = observation(
        "after", depth=0 if kind == "invalid" else 1, version="v2" if kind == "drift" else "v1"
    )
    if kind == "old_crop":
        before = current
        current = current.crop((0, 0, 1, 1))
    features = module("features").extract_risk_features(current, before, [0.001])
    result = module("calibration").estimate_risk(runtime_fixture(), features)
    assert result.status == "UNKNOWN"
    assert result.failure_probability is None


def test_calibrated_bound_tracks_held_out_residuals() -> None:
    model = calibrated()
    payload = json.loads(Path(model.calibration_path).read_text())
    # ceil((9 + 1) * .9) = 9: maximum of .01, ..., .09, not training spread.
    assert payload["geometric_error_bound_m"] == pytest.approx(0.09)
    assert payload["motion_residual_bound_m_s"] is None
    assert len(model.calibration_group_ids) == 9


def test_missing_action_outcomes_remain_uncalibrated() -> None:
    result = module("calibration").estimate_risk(
        calibrated(),
        module("features").extract_risk_features(
            observation("after"), observation("before", seconds=0), [0.001]
        ),
    )
    assert result.failure_probability_by_action["LOCAL_RECOVER"] is None
    assert result.failure_probability_by_action["CONTINUE"] is None
    assert result.status == "UNKNOWN"  # Missing motion residual supervision.


def test_artifact_tamper_cannot_be_used_online() -> None:
    model = fitted()
    path = Path(model.model_path)
    payload = json.loads(path.read_text())
    payload["intercept"] = 123
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash"):
        module("calibration").estimate_risk(
            model, module("features").extract_risk_features(observation(), None, [0.001])
        )


def test_cli_missing_dataset_is_incomplete_and_never_enables(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/calibrate_rgbd_risk.py",
            "--dataset",
            str(tmp_path / "missing"),
            "--config",
            "configs/research/risk.yaml",
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2, completed.stderr
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "INCOMPLETE"
    assert report["research_status"] == "NOT_RUN"
    assert report["enabled"] is False


def test_self_reported_action_feedback_is_rejected(tmp_path: Path) -> None:
    # Removing trajectory/result verification would incorrectly accept this forged outcome.
    sample = record(0, "train", action_outcomes={"LOCAL_RECOVER": {"evidence_key": "feedback"}})
    feedback = {
        "executed": True,
        "failure": False,
        "action": "LOCAL_RECOVER",
        "sample_id": sample.sample_id,
        "observation_id": sample.frame_id,
        "split": "train",
        "trajectory_hash": "pretend-trajectory",
        "independent_result_ref": "missing-result.json",
    }
    payload = json.dumps(feedback).encode()
    (tmp_path / "feedback.json").write_bytes(payload)
    sample = sample.model_copy(
        update={
            "root": tmp_path,
            "paths": {"feedback": "feedback.json"},
            "file_hashes": {"feedback": hashlib.sha256(payload).hexdigest()},
        }
    )
    with pytest.raises(ValueError, match="trajectory|result|feedback"):
        module("fit").action_outcomes(sample, "train")


def test_calibration_content_hash_is_pinned_by_artifact_path() -> None:
    model = calibrated()
    path = Path(model.calibration_path)
    payload = json.loads(path.read_text())
    payload.pop("content_hash")
    payload["geometric_error_bound_m"] = 0
    payload["content_hash"] = content_digest(payload)
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash"):
        module("calibration").load_calibration(model)


def runtime_fixture() -> Any:
    # Nine separate source groups, each with an initial and genuinely later frame.
    records = []
    for index in range(10, 19):
        previous = record(index, "calibration", geometric_error_m=(index - 9) / 100)
        frame = observation(f"later-{index}", seconds=2, depth=1 + index / 100)
        later = previous.model_copy(
            update={
                "sample_id": f"later-s-{index}",
                "frame_id": frame.frame_id,
                "labels": {
                    "risk_supervision": {
                        **previous.labels["risk_supervision"],
                        "previous_sample_id": previous.sample_id,
                        "motion_error_m_s": (index - 9) / 200,
                    }
                },
                "captured_frame": CapturedFrame(
                    frame, (-1,) * 4, {}, f"later-state-{index}", (f"later-state-{index}",) * 3
                ),
            }
        )
        records.extend((previous, later))
    model = module("calibration").calibrate_risk(fitted(), records)
    # Test-only acceptance exercises runtime numeric behavior; no source is accepted in production.
    data = module("fit").load_model(model)
    data["source_accepted"] = True
    Path(model.model_path).write_text(json.dumps(data))
    model = replace(
        model, model_hash=content_digest(data), calibration_path="", calibration_group_ids=()
    )
    model = module("calibration").calibrate_risk(model, records)
    return model


def test_motion_and_geometry_bounds_use_distinct_actual_residuals() -> None:
    model = runtime_fixture()
    payload = module("calibration").load_calibration(model)
    assert payload["geometric_error_bound_m"] == pytest.approx(0.09)
    assert payload["motion_residual_bound_m_s"] == pytest.approx(0.045)
    result = module("calibration").estimate_risk(
        model,
        module("features").extract_risk_features(
            observation("new", depth=1.05), observation("old", seconds=0, depth=1), [0.001]
        ),
    )
    assert result.status == "VALID"
    assert result.geometric_error_bound_m == pytest.approx(0.09)
    assert result.motion_bound_m_s == pytest.approx(0.1062372)
    assert result.failure_probability_by_action["LOCAL_RECOVER"] is None


def test_unknown_actions_use_shared_runtime_vocabulary() -> None:
    result = module("calibration").estimate_risk(
        fitted(), module("features").extract_risk_features(observation(), None, [0.001])
    )
    assert set(result.failure_probability_by_action) == {action.value for action in DecisionAction}


def test_observable_depth_outside_supported_domain_is_unknown() -> None:
    result = module("calibration").estimate_risk(
        runtime_fixture(),
        module("features").extract_risk_features(
            observation("new", depth=100), observation("old", seconds=0, depth=100), [0.001]
        ),
    )
    assert result.status == "UNKNOWN"
    assert result.failure_probability is None


def test_too_few_independent_groups_cannot_make_a_finite_coverage_bound() -> None:
    model = module("calibration").calibrate_risk(
        fitted(),
        [
            record(10, "calibration", geometric_error_m=0.001),
            record(11, "calibration", geometric_error_m=0.002),
        ],
    )
    assert module("calibration").load_calibration(model)["geometric_error_bound_m"] is None


def calibration_script() -> Any:
    return importlib.import_module("scripts.calibrate_rgbd_risk")


def test_configured_split_cannot_reassign_official_test_sources(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.datasets.rgbd.models import SplitManifest

    official = SplitManifest(
        seed=0,
        group_assignments={"heldout": "test"},
        sample_assignments={"s-heldout": "test"},
        counts={"test": 1},
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/split_audit.json").write_text(official.model_dump_json())
    altered = official.model_copy(
        update={
            "group_assignments": {"heldout": "train"},
            "sample_assignments": {"s-heldout": "train"},
        }
    )
    (tmp_path / "alternative.json").write_text(altered.model_dump_json())
    with pytest.raises(ValueError, match="official"):
        calibration_script().official_split(tmp_path, "alternative.json")
    assert calibration_script().official_split(tmp_path, "reports/split_audit.json") == official


def test_frozen_yaml_without_selection_artifact_remains_incomplete(tmp_path: Path) -> None:
    import yaml

    config = yaml.safe_load(Path("configs/research/risk.yaml").read_text())
    config["selection_status"] = "FROZEN"
    config["selection_artifact"] = "reports/missing-selection.json"
    path = tmp_path / "frozen.yaml"
    path.write_text(yaml.safe_dump(config))
    assert (
        calibration_script().main(
            ["--dataset", str(tmp_path), "--config", str(path), "--output", str(tmp_path / "out")]
        )
        == 2
    )
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert "selection" in " ".join(report["reasons"]).lower()
    assert report["research_status"] == "NOT_RUN"
    assert report["enabled"] is False
    assert not (tmp_path / "out/artifact.json").exists()


def test_coverage_curve_uses_metres_and_counts_equal_residuals_together() -> None:
    # A rank-only curve would lose the threshold scale and miscount duplicate .01 errors.
    result = calibration_script().coverage_curve(
        [0.01, 0.01, 0.03], bound=0.01, requested_coverage=0.9
    )
    assert result["points"] == [(0.0, 0.0), (0.01, 2 / 3), (0.03, 1.0)]
    assert result["bound_empirical_coverage"] == 2 / 3
    assert result["bound_m"] == 0.01
    assert result["requested_coverage"] == 0.9
    assert result["independent_test_coverage"] is None


def test_coverage_svg_keeps_threshold_scale_and_honest_axes() -> None:
    script = calibration_script()
    small = script.coverage_svg([0.001, 0.002], bound=0.002, requested_coverage=0.9)
    large = script.coverage_svg([1.0, 2.0], bound=2.0, requested_coverage=0.9)
    assert small != large
    root = ElementTree.fromstring(large)
    labels = [node.text for node in root.findall("{http://www.w3.org/2000/svg}text")]
    assert "Error threshold (m)" in labels
    assert "Calibration-set empirical coverage" in labels
    assert "2" in labels
    assert any("independent test: NOT_RUN" in str(label) for label in labels)


@pytest.mark.parametrize(
    "field",
    [
        "initial_protocol_hash",
        "parameters_hash",
        "selection_group_ids",
        "source_hashes",
        "split_manifest_sha256",
    ],
)
def test_selection_snapshot_rejects_unbound_identity_parameters_or_sources(
    tmp_path: Path, field: str
) -> None:
    import yaml

    script = calibration_script()
    config = yaml.safe_load(Path("configs/research/risk.yaml").read_text())
    selection = [record(20, "selection"), record(21, "selection")]
    parameters = {
        "method": config["method"],
        "seed": config["seed"],
        "settings": {key: config[key] for key in module("fit").SETTINGS},
    }
    partitions = {"selection": selection}
    bindings = {
        "initial_protocol_hash": "unit-initial",
        "initial_protocol_stage": "INITIAL",
        "dataset_manifest_sha256": "unit-manifest",
        "split_manifest_sha256": "unit-split",
    }
    results = {
        "schema_version": "risk.selection.results.v1",
        "initial_protocol_hash": "unit-initial",
        "selection_group_ids": sorted(r.group_id for r in selection),
        "selection_sample_ids": sorted(r.sample_id for r in selection),
        "chosen_parameters_hash": content_digest(parameters),
        "selection_rule": "minimum_brier_then_parameters_hash",
        "candidate_results": [
            {
                "parameters_hash": content_digest(parameters),
                "sample_results": [
                    {"sample_id": r.sample_id, "failure": bool(i % 2), "failure_probability": 0.5}
                    for i, r in enumerate(selection)
                ],
            }
        ],
    }
    raw = json.dumps(results).encode()
    (tmp_path / "selection-results.json").write_bytes(raw)
    snapshot = {
        "schema_version": "risk.selection.v1",
        "status": "FROZEN",
        **bindings,
        "parameters": parameters,
        "parameters_hash": content_digest(parameters),
        "selection_group_ids": sorted(r.group_id for r in selection),
        "selection_sample_ids": sorted(r.sample_id for r in selection),
        "selection_provenance": module("fit").provenance(selection),
        "source_hashes": script.risk_source_hashes(),
        "results_ref": "selection-results.json",
        "results_sha256": hashlib.sha256(raw).hexdigest(),
    }
    checked = script.verify_selection_snapshot(tmp_path, snapshot, config, partitions, bindings)
    assert checked["selection_parameters_hash"] == content_digest(parameters)
    assert checked["selection_group_ids"] == sorted(r.group_id for r in selection)
    altered = {**snapshot, field: ["test-group"] if field == "selection_group_ids" else "changed"}
    with pytest.raises(ValueError, match="selection"):
        script.verify_selection_snapshot(tmp_path, altered, config, partitions, bindings)
