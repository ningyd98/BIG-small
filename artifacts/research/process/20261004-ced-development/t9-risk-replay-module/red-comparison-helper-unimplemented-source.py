"""Complete finite CPU risk replay, with no actual source or execution authority.

The pure kernel accepts SOFTWARE_ONLY numerical inputs. The registered reader
reconstructs them with the concrete reviewed supervision auditor. Neither path
creates committed SampleRecord labels, source acceptance or a METHOD permit.
"""
from __future__ import annotations

import json
import math
import platform
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

import cv2
import numpy
import PIL
import pydantic

from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
from cloud_edge_robot_arm.research.risk_sources import (
    Status, _copied, _hashes, _inventory, _number, _plain, _relative, _safe,
)
from cloud_edge_robot_arm.research.risk_supervision import (
    RiskObservationAllocation, RiskSupervisionAuditor, RiskSupervisionRegistration,
)
from cloud_edge_robot_arm.vision.risk.calibration import isotonic_fit, isotonic_predict
from cloud_edge_robot_arm.vision.risk.fit import REGRESSORS, SETTINGS, logistic_fit, predict
from cloud_edge_robot_arm.vision.risk.models import ACTIONS, FEATURE_SOURCES, FeatureValue, RiskFeatures

_SUPERVISION_SHA = "b5d0118b733f3da25747d50ac704b9e036a07bdf17aa958868b9d2c411ee268b"
_RAW_SHA = "0bf79e3ef94ee33fec9e3642b7c77f956efa6e1a1f015de17d567d0f585c983a"
_METHOD = "logistic_isotonic_group_conformal"
_RULE = "minimum_brier_then_parameters_hash"
_POPULATION = "all_allocated_observations_v1"
_SPLITS = ("train", "calibration", "selection", "test")
_FIXED = {"coverage": 0.9, "iterations": 400, "learning_rate": 0.1, "l2": 0.01,
          "max_invalid_depth_fraction": 0.3, "max_frame_interval_s": 2.0}
_ROW_KEYS = {"sample_id", "case_id", "observation_id", "split", "source_kind", "group_id",
             "scene_hash", "used_purposes", "geometry_scope", "online_features",
             "offline_labels", "failure_horizon"}


def required_replay_source_paths() -> tuple[str, ...]:
    return ("src/cloud_edge_robot_arm/research/risk_replay.py",
            "src/cloud_edge_robot_arm/research/risk_supervision.py",
            "src/cloud_edge_robot_arm/research/risk_sources.py",
            "src/cloud_edge_robot_arm/vision/risk/fit.py",
            "src/cloud_edge_robot_arm/vision/risk/calibration.py",
            "src/cloud_edge_robot_arm/vision/risk/features.py",
            "src/cloud_edge_robot_arm/vision/risk/models.py",
            "src/cloud_edge_robot_arm/datasets/rgbd/models.py")


def risk_replay_environment() -> Mapping[str, str]:
    return _copied({"python": platform.python_version(), "pydantic": pydantic.__version__,
                    "Pillow": PIL.__version__, "numpy": numpy.__version__, "opencv": cv2.__version__})


def _object(value: Any, keys: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"exact {what} fields required")
    return dict(value)


def _identity(value: Any) -> str:
    if type(value) is not str or not value or len(value) > 160:
        raise ValueError("explicit registered identity required")
    return value


def _candidate(value: Any) -> dict[str, Any]:
    data = _object(value, {"method", "seed", "settings"}, "candidate parameter object")
    seed = data["seed"]
    if data["method"] != _METHOD or type(seed) is not int or not 0 <= seed <= 2**31-1:
        raise ValueError("fixed method and explicit nonnegative bounded seed required")
    settings = _object(data["settings"], set(_FIXED), "frozen settings")
    if any(type(settings[k]) is not type(v) or settings[k] != v for k,v in _FIXED.items()):
        raise ValueError("only the existing fixed recipe SETTINGS are supported")
    if dict(SETTINGS) != _FIXED:
        raise ValueError("runtime fixed fit SETTINGS changed")
    return {"method": _METHOD, "seed": seed, "settings": settings}


def _candidates(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise ValueError("nonempty finite complete candidate inventory required")
    result = [_candidate(value) for value in values]
    if len({content_digest(value) for value in result}) != len(result):
        raise ValueError("duplicate finite candidate parameter object")
    return sorted(result, key=content_digest)


def supervision_registration_hash(registration: RiskSupervisionRegistration) -> str:
    if type(registration) is not RiskSupervisionRegistration:
        raise TypeError("concrete supervision registration required")
    registration = replace(registration)
    raw = registration.raw_registration
    measured = registration.diagnostic_measurements
    initial = registration.initial_registration
    return content_digest({
        "cases": [{"case_id": c.case_id, "directory": c.relative_directory, "layout": c.layout,
                   "original_file_hashes": dict(c.original_file_hashes),
                   "assignment": _plain(c.assignment), "context": _plain(c.context),
                   "expected_counts": dict(c.expected_counts), "source_kind": c.source_kind,
                   "marker_registration": asdict(c.marker_registration) if c.marker_registration else None}
                  for c in raw.cases],
        "criteria": asdict(raw.criteria), "current_source_hashes": dict(raw.current_source_hashes),
        "current_role": raw.current_role_binding.evidence() if raw.current_role_binding else None,
        "allocations": [asdict(item) for item in registration.allocations],
        "histories": [{"group_id": h.group_id, "used_purposes": list(h.used_purposes)}
                      for h in registration.histories],
        "measurements": {"original_file_hashes": dict(measured.original_file_hashes),
                         "clock_path": measured.clock_path, "calibration_path": measured.calibration_path}
                        if measured else None,
        "initial": {"protocol_path": str(initial.protocol_path),
                    "current_source_hashes": dict(initial.current_source_hashes),
                    "current_role": initial.current_role_binding.evidence()} if initial else None,
    })


def _features(values: Any, observation_id: str) -> RiskFeatures | None:
    if values is None:
        return None
    values = _object(values, set(FEATURE_SOURCES), "online feature schema")
    numbers = {key: _number(value) for key,value in values.items()}
    for key in ("calibration_valid", "motion_pair_valid"):
        if numbers[key] not in (0.0, 1.0):
            raise ValueError("binary observable validity feature required")
    if not 0 <= numbers["calibration_fingerprint"] < 2**48:
        raise ValueError("calibration fingerprint outside existing feature domain")
    if not all(0 <= numbers[key] <= 1 for key in ("invalid_depth_fraction", "pixel_consistency")):
        raise ValueError("observable fraction outside unit interval")
    if any(numbers[key] < 0 for key in REGRESSORS):
        raise ValueError("nonnegative observable feature required")
    return RiskFeatures({key: FeatureValue(value, FEATURE_SOURCES[key])
                         for key,value in numbers.items()}, observation_id)


def _rows(allocations: Sequence[RiskObservationAllocation], values: Sequence[Mapping[str, Any]]):
    if any(type(item) is not RiskObservationAllocation for item in allocations):
        raise TypeError("concrete original allocations required")
    alloc = {item.sample_id: replace(item) for item in allocations}
    if len(alloc) != len(allocations):
        raise ValueError("duplicate original allocation")
    observed = {}
    components = {}
    case_failures = {}
    for raw in values:
        row = _object(raw, _ROW_KEYS, "reconstructed supervision row")
        sample = _identity(row["sample_id"])
        item = alloc.get(sample)
        if item is None or sample in observed:
            raise ValueError("extra or duplicate row outside original allocations")
        if (row["case_id"], row["observation_id"], row["split"]) != (
            item.case_id, item.observation_id, item.split
        ):
            raise ValueError("original allocation identity/split mismatch")
        for kind in ("case_id", "group_id", "scene_hash"):
            component = (kind, _identity(row[kind]))
            if component in components and components[component] != item.split:
                raise ValueError("connected source component spans purpose splits")
            components[component] = item.split
        history = row["used_purposes"]
        if not isinstance(history, (list, tuple)) or any(type(p) is not str for p in history):
            raise ValueError("original component usage history required")
        if item.split != "train" and set(history) - {"UNVIEWED", "UNKNOWN"}:
            raise ValueError("seen or tuned component cannot become an independent holdout")
        if row["source_kind"] not in {"SOFTWARE_ONLY", "RECORDED_SIMULATION"}:
            raise ValueError("unsupported reconstructed diagnostic source kind")
        if row["geometry_scope"] != "MARKER_CENTER_TRANSLATION":
            raise ValueError("only marker-center point residual scope is supported")
        labels = _object(row["offline_labels"], {"failure", "geometric_error_m", "motion_residual_m_s"}, "offline labels")
        failure = labels["failure"]
        if failure is not None and type(failure) is not bool:
            raise ValueError("terminal failure must be an offline boolean or unavailable")
        if failure is not None:
            if row["case_id"] in case_failures and case_failures[row["case_id"]] != failure:
                raise ValueError("one original episode cannot have contradictory terminal failure labels")
            case_failures[row["case_id"]] = failure
        for key in ("geometric_error_m", "motion_residual_m_s"):
            if labels[key] is not None:
                labels[key] = _number(labels[key])
                if labels[key] < 0:
                    raise ValueError("nonnegative offline point residual required")
        horizon = _object(row["failure_horizon"], {"kind", "evaluation_start_step", "terminal_step", "terminal_sim_time_s"}, "terminal horizon")
        if (horizon["kind"] != "ORIGINAL_EPISODE_TERMINAL"
            or type(horizon["evaluation_start_step"]) is not int or horizon["evaluation_start_step"] != 120
            or type(horizon["terminal_step"]) is not int or horizon["terminal_step"] < 120
            or _number(horizon["terminal_sim_time_s"]) < 0):
            raise ValueError("original terminal horizon required")
        row["offline_labels"] = labels
        row["features"] = _features(row["online_features"], item.observation_id)
        row["history_available"] = bool(history) and "UNKNOWN" not in history
        observed[sample] = row
    output = []
    for sample,item in sorted(alloc.items()):
        output.append(observed.get(sample, {"sample_id": sample, "case_id": item.case_id,
            "observation_id": item.observation_id, "split": item.split, "group_id": None,
            "scene_hash": None, "features": None, "history_available": False,
            "offline_labels": {"failure": None, "geometric_error_m": None, "motion_residual_m_s": None}}))
    return output, len(observed)


def _provenance(rows):
    return {**{key: sorted({row[key] for row in rows}) for key in (
        "sample_id", "case_id", "observation_id", "group_id", "scene_hash")},
        "used_purposes_by_group": {row["group_id"]: list(row["used_purposes"]) for row in rows}}


def _fit(rows, parameters):
    vectors = [[row["features"].values[key].value for key in REGRESSORS] for row in rows]
    # Check the fixed legacy arithmetic before its squared-deviation operation.
    for index in range(len(REGRESSORS)):
        mean = sum(row[index] for row in vectors) / len(vectors)
        if not math.isfinite(mean) or any(not math.isfinite((row[index]-mean)*(row[index]-mean)) for row in vectors):
            raise ValueError("fixed fit recipe arithmetic exceeds finite range")
    data = logistic_fit(vectors, [row["offline_labels"]["failure"] for row in rows], parameters["seed"])
    data.update({"schema_version": "ced.risk-replay-model.v1", "scope": "SOFTWARE_ONLY",
        "target": "ORIGINAL_EPISODE_TERMINAL_FAILURE", "seed": parameters["seed"],
        "settings": dict(parameters["settings"]), "feature_schema": dict(FEATURE_SOURCES),
        "regressors": list(REGRESSORS), "fit_group_ids": sorted({row["group_id"] for row in rows}),
        "fit_provenance": _provenance(rows),
        "calibration_fingerprints": sorted({row["features"].values["calibration_fingerprint"].value for row in rows}),
        "feature_ranges": {key: [min(row["features"].values[key].value for row in rows),
                                  max(row["features"].values[key].value for row in rows)] for key in REGRESSORS},
        "action_models": {action: None for action in ACTIONS}, "source_accepted": False, "formal_use": "FORBIDDEN"})
    return data


def _bound(rows, key, motion=False):
    groups = {}
    eligible = [row for row in rows if not motion or row["features"].values["motion_pair_valid"].value == 1]
    for row in eligible:
        value = row["offline_labels"][key]
        if value is not None:
            groups[row["group_id"]] = max(groups.get(row["group_id"], 0.), value)
    residuals = sorted(groups.values())
    rank = math.ceil((len(residuals)+1)*_FIXED["coverage"])
    return (residuals[rank-1] if residuals and rank <= len(residuals) else None,
            residuals, len(eligible), sum(row["offline_labels"][key] is not None for row in eligible))


def _calibrate(model, rows):
    scores = [predict(model, row["features"]) for row in rows]
    labels = [row["offline_labels"]["failure"] for row in rows]
    blocks = isotonic_fit(scores, labels)
    geometry, geo_groups, geo_eligible, geo_labels = _bound(rows, "geometric_error_m")
    motion, motion_groups, motion_eligible, motion_labels = _bound(rows, "motion_residual_m_s", True)
    coverage = {"geometry_group_count": len(geo_groups), "motion_group_count": len(motion_groups),
                "geometry_eligible_rows": geo_eligible, "geometry_label_rows": geo_labels,
                "motion_eligible_rows": motion_eligible, "motion_label_rows": motion_labels,
                "geometry_missing_label_rows": geo_eligible-geo_labels,
                "motion_missing_label_rows": motion_eligible-motion_labels}
    calibrated = {"schema_version": "ced.risk-replay-calibration.v1", "scope": "SOFTWARE_ONLY",
        "model_hash": content_digest(model), "calibration_group_ids": sorted({row["group_id"] for row in rows}),
        "calibration_provenance": _provenance(rows), "isotonic_blocks": blocks,
        "observable_support": {key: [min(model["feature_ranges"][key][0], min(row["features"].values[key].value for row in rows)),
                                     max(model["feature_ranges"][key][1], max(row["features"].values[key].value for row in rows))]
                               for key in ("depth_median_m", "depth_dispersion_m", "calibration_residual_m")},
        "action_isotonic_blocks": {action: None for action in ACTIONS}, "coverage": _FIXED["coverage"],
        "geometry_scope": "MARKER_CENTER_TRANSLATION", "bound_scope": "AVAILABLE_LABEL_GROUP_DIAGNOSTICS",
        "marker_point_error_bound_m": geometry, "motion_residual_bound_m_s": motion,
        "geometry_group_residuals_m": geo_groups, "motion_group_residuals_m_s": motion_groups,
        "reliability": [{"score": score, "failure": label, "calibrated": isotonic_predict(blocks, score)}
                        for score,label in zip(scores,labels,strict=True)], "label_coverage": coverage}
    calibrated["content_hash"] = content_digest(calibrated)
    return calibrated, coverage


def _prediction(row, model, calibrated):
    reasons = []
    feature = row["features"]
    raw_probability = None
    probability = None
    point = None
    motion = None
    if model is None or calibrated is None:
        reasons.append("fitted_calibrated_candidate_unavailable")
    elif feature is None:
        reasons.append("online_features_unavailable")
    else:
        values = {key:value.value for key,value in feature.values.items()}
        raw_probability = predict(model, feature)
        for condition,reason in (
            (values["invalid_depth_fraction"] > _FIXED["max_invalid_depth_fraction"], "invalid_depth_outside_guard"),
            (values["calibration_valid"] != 1, "calibration_guard_unavailable"),
            (values["motion_pair_valid"] != 1, "fresh_motion_pair_unavailable"),
            (values["calibration_fingerprint"] not in model["calibration_fingerprints"], "calibration_fingerprint_outside_fit"),
            (values["frame_interval_s"] > _FIXED["max_frame_interval_s"], "frame_interval_outside_guard"),
            (any(not low <= values[key] <= high for key,(low,high) in calibrated["observable_support"].items()), "observable_support_outside_fit_calibration"),
            (calibrated["marker_point_error_bound_m"] is None, "marker_point_group_bound_unavailable"),
            (calibrated["motion_residual_bound_m_s"] is None, "fresh_motion_group_bound_unavailable"),
            (not calibrated["isotonic_blocks"], "both_class_isotonic_unavailable"),
        ):
            if condition:
                reasons.append(reason)
        if not reasons:
            probability = isotonic_predict(calibrated["isotonic_blocks"], raw_probability)
            point = calibrated["marker_point_error_bound_m"]
            motion = _number(values["observed_motion_m_s"]+calibrated["motion_residual_bound_m_s"])
    if row["offline_labels"]["failure"] is None:
        reasons.append("terminal_failure_label_unavailable")
    return {"sample_id": row["sample_id"], "failure": row["offline_labels"]["failure"],
        "raw_failure_probability": raw_probability, "failure_probability": probability,
        "failure_probability_by_action": {action: None for action in ACTIONS},
        "marker_point_error_bound_m": point, "motion_bound_m_s": motion,
        "status": "UNKNOWN" if reasons else "VALID", "reasons": reasons}


def _brier(rows):
    if not rows or any(row["failure_probability"] is None or row["failure"] is None for row in rows):
        return None
    return sum((row["failure_probability"]-row["failure"])**2 for row in rows)/len(rows)


def replay_diagnostic_candidates(allocations, reconstructed_rows, candidates) -> Mapping[str, Any]:
    """Replay the full fixed numerical recipe; every output is SOFTWARE_ONLY.

    This function does not attest the caller's vector/label/acquisition history.
    Registered source consumers must use RiskArtifactAuditor's concrete reread.
    """
    parameters = _candidates(candidates)
    rows, observed_count = _rows(allocations, reconstructed_rows)
    splits = {name: [row for row in rows if row["split"] == name] for name in _SPLITS}
    counts = {"allocated_observations": len(allocations), "assigned_attempts": len({a.case_id for a in allocations}),
              "missing_observations": len(allocations)-observed_count,
              "task_labels": sum(row["offline_labels"]["failure"] is not None for row in rows),
              "feature_rows": sum(row["features"] is not None for row in rows),
              "failed_task_observations": sum(row["offline_labels"]["failure"] is True for row in rows)}
    split_counts = {name: {"allocated": len(items), "feature_rows": sum(row["features"] is not None for row in items),
                          "failure_labels": sum(row["offline_labels"]["failure"] is not None for row in items),
                          "missing_features": sum(row["features"] is None for row in items),
                          "missing_labels": sum(row["offline_labels"]["failure"] is None for row in items)}
                    for name,items in splits.items()}
    results = []
    for candidate in parameters:
        reasons = ["action_execution_feedback_reconstruction_unavailable"]
        model = None
        calibrated = None
        coverage = None
        for name in ("train", "calibration"):
            items = splits[name]
            if not items or any(row["features"] is None or row["offline_labels"]["failure"] is None
                                or not row["history_available"] for row in items):
                reasons.append(f"complete_{name}_population_unavailable")
        if len(reasons) == 1 and {row["offline_labels"]["failure"] for row in splits["train"]} != {False,True}:
            reasons.append("both_class_training_unavailable")
        if len(reasons) == 1:
            model = _fit(splits["train"], candidate)
            calibrated, coverage = _calibrate(model, splits["calibration"])
        selection = [_prediction(row, model, calibrated) for row in splits["selection"]]
        test = [_prediction(row, model, calibrated) for row in splits["test"]]
        score = _brier(selection)
        if any(not row["history_available"] for row in splits["selection"]):
            score = None
            reasons.append("original_selection_usage_history_unavailable")
        status = "UNAVAILABLE" if model is None else "NO_FEASIBLE" if score is None else "FEASIBLE"
        if score is None:
            reasons.append("complete_selection_predictions_unavailable")
        results.append({"parameters": candidate, "parameters_hash": content_digest(candidate), "status": status,
            "reasons": reasons, "model": model, "model_hash": content_digest(model) if model else None,
            "calibration": calibrated, "calibration_hash": calibrated["content_hash"] if calibrated else None,
            "coverage": coverage, "selection_results": selection, "test_results": test,
            "selection_brier": score, "test_brier": _brier(test),
            "action_coverage": {action: {"train_outcomes": None, "calibration_outcomes": None,
                "selection_outcomes": None, "missing_train_rows": len(splits["train"]),
                "missing_calibration_rows": len(splits["calibration"]),
                "missing_selection_rows": len(splits["selection"])} for action in ACTIONS}})
    feasible = [candidate for candidate in results if candidate["selection_brier"] is not None]
    winner = min(feasible, key=lambda c:(c["selection_brier"], c["parameters_hash"]))["parameters_hash"] if feasible else None
    status = "VALID" if winner else "UNAVAILABLE" if all(c["status"] == "UNAVAILABLE" for c in results) else "NO_FEASIBLE"
    selection_snapshot = {"schema_version": "ced.risk-replay-selection.v1", "scope": "SOFTWARE_ONLY",
        "selection_rule": _RULE, "population_rule": _POPULATION, "diagnostic_winner_hash": winner,
        "selection_sample_ids": [row["sample_id"] for row in splits["selection"]],
        "candidate_results": [{key:candidate[key] for key in ("parameters", "parameters_hash", "model_hash",
            "calibration_hash", "selection_results", "selection_brier", "status")} for candidate in results]}
    return _copied({"scope": "SOFTWARE_ONLY", "status": status, "counts": counts,
        "split_counts": split_counts, "candidate_results": results, "diagnostic_winner_hash": winner,
        "selection_snapshot": selection_snapshot,
        "component_usage_histories": {row["group_id"]: list(row["used_purposes"]) for row in rows if row["group_id"] is not None}})


@dataclass(frozen=True)
class RiskReplayArtifactRegistration:
    model_path: str
    calibration_path: str

    def __post_init__(self):
        _relative(self.model_path)
        _relative(self.calibration_path)


@dataclass(frozen=True)
class RiskReplayRegistration:
    artifact_root: Path
    original_file_hashes: Mapping[str, str]
    config_path: str
    supervision_evidence_id: str
    candidate_artifacts: Mapping[str, RiskReplayArtifactRegistration] = field(default_factory=dict)
    selection_results_path: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "artifact_root", Path(self.artifact_root).absolute())
        object.__setattr__(self, "original_file_hashes", _hashes(self.original_file_hashes))
        _identity(self.supervision_evidence_id)
        required = [self.config_path]
        _relative(self.config_path)
        artifacts = {}
        for digest,artifact in self.candidate_artifacts.items():
            _hashes({"candidate":digest})
            if type(artifact) is not RiskReplayArtifactRegistration:
                raise TypeError("concrete original candidate artifact registrations required")
            artifacts[digest] = replace(artifact)
            required.extend((artifact.model_path, artifact.calibration_path))
        if self.selection_results_path is not None:
            _relative(self.selection_results_path)
            required.append(self.selection_results_path)
        if not set(required) <= self.original_file_hashes.keys():
            raise ValueError("original config/artifact paths absent from complete inventory")
        object.__setattr__(self, "candidate_artifacts", MappingProxyType(artifacts))


@dataclass(frozen=True)
class RiskArtifactAudit:
    status: Status
    actual_source_status: Status
    diagnostic_status: str
    comparison_status: Status
    reasons: tuple[str, ...]
    counts: Mapping[str, int]
    split_counts: Mapping[str, Any]
    candidate_results: tuple[Mapping[str, Any], ...]
    diagnostic_winner_hash: str | None
    original_file_hashes: Mapping[str, str]
    current_source_hashes: Mapping[str, str]
    source_scope: str = "SOFTWARE_ONLY"
    schema_version: str = "ced.risk-replay-audit.v1"

    def __post_init__(self):
        for name in ("counts", "split_counts", "candidate_results", "original_file_hashes", "current_source_hashes"):
            object.__setattr__(self, name, _copied(getattr(self,name)))


def _json_object(path):
    def pairs(values):
        result = {}
        for key,value in values:
            if key in result:
                raise ValueError("duplicate original artifact JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f"nonfinite original artifact JSON: {value}")
    data = json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(data, dict):
        raise ValueError("original artifact must be a JSON object")
    return data


def _same(left, right):
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


class RiskArtifactAuditor:
    """Concrete copied registrations only; actual risk/selection remain UNKNOWN."""
    def __init__(self, registrations, supervision_registrations):
        if not isinstance(supervision_registrations, Mapping) or not isinstance(registrations, Mapping):
            raise TypeError("concrete registration mappings required, not passed auditors")
        self._registered = {}
        self._supervision = {}
        for evidence,source in supervision_registrations.items():
            _identity(evidence)
            if type(source) is not RiskSupervisionRegistration:
                raise TypeError("concrete supervision registration required")
            source = replace(source)
            sources = source.raw_registration.current_source_hashes
            if sources.get("src/cloud_edge_robot_arm/research/risk_supervision.py") != _SUPERVISION_SHA:
                raise ValueError("corrected independently reviewed supervision fix1 required")
            if sources.get("src/cloud_edge_robot_arm/research/risk_sources.py") != _RAW_SHA:
                raise ValueError("corrected independently reviewed RAW fix2 required")
            if not set(required_replay_source_paths()) <= sources.keys():
                raise ValueError("complete replay validating production sources required")
            self._supervision[evidence] = source
        for evidence,registration in registrations.items():
            _identity(evidence)
            if type(registration) is not RiskReplayRegistration:
                raise TypeError("concrete replay registration required")
            self._registered[evidence] = replace(registration)

    def audit(self, evidence_id):
        registration = self._registered.get(evidence_id)
        counts = {"assigned_attempts":0, "allocated_observations":0, "missing_observations":0}
        reasons = []
        originals = {}
        sources = {}
        candidate_results = ()
        split_counts = {}
        winner = None
        status: Status = "UNKNOWN"
        diagnostic = "UNAVAILABLE"
        comparison: Status = "UNKNOWN"
        scope = "SOFTWARE_ONLY"
        source = self._supervision.get(registration.supervision_evidence_id) if registration else None
        if registration is None or source is None:
            reasons.append("evidence_id_not_registered" if registration is None else "supervision_evidence_id_not_registered")
        else:
            counts["assigned_attempts"] = len(source.raw_registration.cases)
            counts["allocated_observations"] = sum(case.expected_counts["frames"] for case in source.raw_registration.cases)
            counts["missing_observations"] = counts["allocated_observations"]
            try:
                concrete = RiskSupervisionAuditor({"source":source})
                supervised = concrete.audit("source")
                counts.update(supervised.counts)
                originals.update({f"supervision/{name}":digest for name,digest in supervised.original_file_hashes.items()})
                sources.update(supervised.current_source_hashes)
                scope = supervised.source_scope
                reasons.extend(supervised.reasons)
                before = _inventory(registration.artifact_root, registration.original_file_hashes, complete=True)
                originals.update({f"replay/{name}":digest for name,digest in before.items()})
                raw = source.raw_registration
                source_before = _inventory(raw.source_root, raw.current_source_hashes, complete=False)
                config = _object(_json_object(_safe(registration.artifact_root,registration.config_path)),
                    {"schema_version", "inventory_version", "selection_rule", "population_rule", "candidates",
                     "environment", "recipe_source_hashes", "supervision_registration_hash"}, "replay config")
                if (config["schema_version"] != "ced.risk-replay-config.v1" or not _identity(config["inventory_version"])
                    or config["selection_rule"] != _RULE or config["population_rule"] != _POPULATION
                    or not _same(config["environment"], risk_replay_environment())
                    or not _same(config["recipe_source_hashes"], {name:raw.current_source_hashes[name] for name in required_replay_source_paths()})
                    or config["supervision_registration_hash"] != supervision_registration_hash(source)):
                    raise ValueError("frozen config/environment/recipe/source binding mismatch")
                candidates = _candidates(config["candidates"])
                replay = replay_diagnostic_candidates(source.allocations, supervised.rows, candidates)
                candidate_results = replay["candidate_results"]
                split_counts = replay["split_counts"]
                winner = replay["diagnostic_winner_hash"]
                diagnostic = replay["status"]
                counts.update({key:value for key,value in replay["counts"].items() if key not in {"assigned_attempts","allocated_observations","missing_observations","task_labels","feature_rows"}})
                if supervised.diagnostic_status == "INVALID" or supervised.actual_source_status == "INVALID":
                    status = "INVALID"
                    diagnostic = "INVALID"
                    winner = None
                missing = not registration.candidate_artifacts or registration.selection_results_path is None
                if not registration.candidate_artifacts:
                    reasons.append("original_candidate_artifacts_unavailable")
                if registration.selection_results_path is None:
                    reasons.append("original_selection_results_unavailable")
                if registration.candidate_artifacts and set(registration.candidate_artifacts) != {c["parameters_hash"] for c in candidate_results}:
                    raise ValueError("original artifact inventory must retain every frozen candidate")
                comparable = True
                for candidate in candidate_results:
                    artifact = registration.candidate_artifacts.get(candidate["parameters_hash"])
                    if artifact is None:
                        continue
                    model = _json_object(_safe(registration.artifact_root, artifact.model_path))
                    calibration = _json_object(_safe(registration.artifact_root, artifact.calibration_path))
                    if (model.get("schema_version") != "ced.risk-replay-model.v1" or model.get("scope") != "SOFTWARE_ONLY"
                        or model.get("source_accepted") is not False or calibration.get("schema_version") != "ced.risk-replay-calibration.v1"
                        or calibration.get("scope") != "SOFTWARE_ONLY" or calibration.get("geometry_scope") != "MARKER_CENTER_TRANSLATION"):
                        raise ValueError("diagnostic model/calibration schema cannot confer source acceptance")
                    body = dict(calibration)
                    digest = body.pop("content_hash", None)
                    if (digest != content_digest(body) or calibration.get("model_hash") != content_digest(model)
                        or Path(artifact.calibration_path).name != f"calibration-{digest}.json"):
                        raise ValueError("original calibration content/file/model hash mismatch")
                    if candidate["model"] is None or candidate["calibration"] is None:
                        comparable = False
                        reasons.append("complete_candidate_reconstruction_unavailable")
                    elif not _same(model, candidate["model"]) or not _same(calibration, candidate["calibration"]):
                        raise ValueError("original candidate numeric artifact differs from full replay")
                if registration.selection_results_path is not None:
                    snapshot = _json_object(_safe(registration.artifact_root, registration.selection_results_path))
                    if not _same(snapshot, replay["selection_snapshot"]):
                        raise ValueError("original selection probabilities/population/winner differ from replay")
                comparison = "VALID" if not missing and comparable else "UNKNOWN"
                after = concrete.audit("source")
                if (after.rows != supervised.rows or after.counts != supervised.counts or after.original_file_hashes != supervised.original_file_hashes
                    or after.current_source_hashes != supervised.current_source_hashes or after.diagnostic_status != supervised.diagnostic_status
                    or after.actual_source_status != supervised.actual_source_status
                    or _inventory(registration.artifact_root, registration.original_file_hashes, complete=True) != before
                    or _inventory(raw.source_root, raw.current_source_hashes, complete=False) != source_before):
                    raise ValueError("original or current validating source changed during replay")
                reasons.extend(("actual_risk_selection_unavailable", "derived_sample_record_materializer_unavailable",
                                "actual_action_feedback_replay_unavailable"))
            except (ValueError, TypeError, KeyError, IndexError) as error:
                status = "INVALID"
                diagnostic = "INVALID"
                comparison = "INVALID"
                winner = None
                reasons.append(f"risk_replay_invalid:{error}")
            except OSError as error:
                reasons.append(f"risk_replay_unavailable:{error}")
        return RiskArtifactAudit(status, status, diagnostic, comparison, tuple(dict.fromkeys(reasons)),
            counts, split_counts, tuple(candidate_results), winner, originals, sources, scope)
