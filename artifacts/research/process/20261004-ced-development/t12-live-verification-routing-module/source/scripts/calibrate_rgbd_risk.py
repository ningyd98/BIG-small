"""Calibrate only source-accepted committed RGB-D records after a verified INITIAL freeze."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from cloud_edge_robot_arm.datasets.rgbd.models import (
    SampleRecord,
    SplitManifest,
    canonical_json,
    content_digest,
)
from cloud_edge_robot_arm.datasets.rgbd.quality import validate_dataset
from cloud_edge_robot_arm.datasets.rgbd.writer import load_manifest, load_records
from cloud_edge_robot_arm.research.protocol import load_protocol
from cloud_edge_robot_arm.vision.offline_reader import resolve_payload
from cloud_edge_robot_arm.vision.risk.calibration import calibrate_risk, load_calibration
from cloud_edge_robot_arm.vision.risk.fit import (
    SETTINGS,
    assert_disjoint,
    fit_risk_model,
    load_model,
    provenance,
    supervision,
)

SELECTION_RULE = "minimum_brier_then_parameters_hash"


def risk_source_hashes() -> dict[str, str]:
    """Bind selection to the actual estimator, calibration and acceptance implementation."""
    from cloud_edge_robot_arm.vision.risk import calibration, features, fit, models

    paths = []
    for module in (models, features, fit, calibration):
        if module.__file__ is None:
            raise ValueError("selection requires inspectable risk implementation source files")
        paths.append(Path(module.__file__))
    paths.append(Path(__file__))
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def load_selection_snapshot(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    if config.get("selection_status") != "FROZEN":
        raise ValueError("selection is NOT_RUN; a verified frozen snapshot is required")
    reference = config.get("selection_artifact")
    digest = config.get("selection_artifact_sha256")
    if not isinstance(reference, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("selection artifact path and independently recorded SHA256 are required")
    return verified_json(root, reference, digest)


def verify_selection_snapshot(
    root: Path,
    snapshot: dict[str, Any],
    config: dict[str, Any],
    partitions: dict[str, list[SampleRecord]],
    bindings: dict[str, Any],
) -> dict[str, Any]:
    """Check actual isolated selection results before marking a model source accepted."""
    parameters = {
        "method": config["method"],
        "seed": config["seed"],
        "settings": {key: config[key] for key in SETTINGS},
    }
    parameter_hash = content_digest(parameters)
    selection = partitions["selection"]
    groups = sorted({record.group_id for record in selection})
    samples = sorted({record.sample_id for record in selection})
    expected = {
        "schema_version": "risk.selection.v1",
        "status": "FROZEN",
        "parameters": parameters,
        "parameters_hash": parameter_hash,
        "source_hashes": risk_source_hashes(),
        "selection_group_ids": groups,
        "selection_sample_ids": samples,
        "selection_provenance": provenance(selection),
        **{
            key: bindings[key]
            for key in (
                "initial_protocol_hash",
                "initial_protocol_stage",
                "dataset_manifest_sha256",
                "split_manifest_sha256",
            )
        },
    }
    if (
        bindings.get("initial_protocol_stage") != "INITIAL"
        or not bindings.get("initial_protocol_hash")
        or any(snapshot.get(key) != value for key, value in expected.items())
    ):
        raise ValueError(
            "selection snapshot identity, parameters or isolated source binding mismatch"
        )
    results = verified_json(root, snapshot["results_ref"], snapshot["results_sha256"])
    if any(
        results.get(key) != value
        for key, value in {
            "schema_version": "risk.selection.results.v1",
            "selection_rule": SELECTION_RULE,
            "initial_protocol_hash": bindings["initial_protocol_hash"],
            "selection_group_ids": groups,
            "selection_sample_ids": samples,
            "chosen_parameters_hash": parameter_hash,
        }.items()
    ):
        raise ValueError("selection result does not bind INITIAL, parameters and isolated groups")
    candidates = results.get("candidate_results")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("selection must retain actual candidate results")
    actual_labels = {
        record.sample_id: supervision(record, "selection")["failure"] for record in selection
    }
    scores: dict[str, float] = {}
    for candidate in candidates:
        candidate_hash = candidate.get("parameters_hash")
        rows = candidate.get("sample_results")
        if (
            not isinstance(candidate_hash, str)
            or candidate_hash in scores
            or not isinstance(rows, list)
            or len(rows) != len(samples)
            or {row.get("sample_id") for row in rows} != set(samples)
        ):
            raise ValueError("selection candidate must cover the exact isolated sample sources")
        errors = []
        for row in rows:
            probability = row.get("failure_probability")
            failure = actual_labels[row["sample_id"]]
            if (
                type(probability) not in {int, float}
                or not math.isfinite(probability)
                or not 0 <= probability <= 1
                or type(row.get("failure")) is not bool
                or row["failure"] != failure
            ):
                raise ValueError(
                    "selection result requires actual risk labels and finite predictions"
                )
            errors.append((probability - failure) ** 2)
        scores[candidate_hash] = sum(errors) / len(errors)
    if (
        min(scores, key=lambda candidate_hash: (scores[candidate_hash], candidate_hash))
        != parameter_hash
    ):
        raise ValueError("selection chosen parameters do not follow the recorded Brier-score rule")
    return {
        "selection_snapshot_hash": content_digest(snapshot),
        "selection_results_sha256": snapshot["results_sha256"],
        "selection_parameters_hash": parameter_hash,
        "selection_group_ids": groups,
        "selection_source_hashes": expected["source_hashes"],
        "selection_brier_scores": scores,
    }


def verified_json(root: Path, relative: str, expected_hash: str) -> dict[str, Any]:
    payload = resolve_payload(root, relative).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError(f"source evidence hash mismatch: {relative}")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"source evidence must be a JSON object: {relative}")
    return data


def official_split(root: Path, relative: str) -> SplitManifest:
    """Use the one audit independently checked against committed split payloads."""
    if relative != "reports/split_audit.json":
        raise ValueError("risk fitting requires the official reports/split_audit.json")
    return SplitManifest.model_validate_json(resolve_payload(root, relative).read_bytes())


def accepted_records(
    root: Path, config: dict[str, Any], initial_directory: Path | None
) -> tuple[dict[str, list[SampleRecord]], dict[str, Any]]:
    manifest = load_manifest(root)
    if manifest is None or manifest.status != "COMPLETE":
        raise ValueError("a COMPLETE committed genuine dataset is required")
    records = load_records(root)
    if not records:
        raise ValueError("committed dataset records are missing")
    split = official_split(root, config["split_manifest"])
    partitions: dict[str, list[SampleRecord]] = {
        role: [] for role in ("train", "calibration", "selection", "test")
    }
    for record in records:
        role = split.sample_assignments.get(record.sample_id)
        if role is None or split.group_assignments.get(record.group_id) != role:
            raise ValueError("split audit must bind each sample to its isolated source group")
        supervision(record, role)
        partitions[role].append(record)
    for index, (partition_role, partition) in enumerate(partitions.items()):
        if not partition:
            raise ValueError(f"isolated {partition_role} source records are required")
        for other in list(partitions.values())[index + 1 :]:
            assert_disjoint(provenance(partition), provenance(other))
    # A stored valid=true flag never substitutes for payload-backed validation.
    quality = validate_dataset(root)
    if not quality.valid:
        raise ValueError(f"dataset quality rejected: {quality.errors}")
    acceptance = json.loads(resolve_payload(root, config["source_acceptance"]).read_bytes())
    if acceptance.get("schema_version") != "risk.acceptance.v1":
        raise ValueError("risk acceptance requires the independent-label source schema")
    for name, relative in {
        "dataset_manifest": "manifest.json",
        "split_manifest": config["split_manifest"],
        "quality_report": config["quality_report"],
    }.items():
        verified_json(root, relative, acceptance.get(f"{name}_sha256", ""))
    if initial_directory is None:
        raise ValueError("a separately loaded --initial-protocol directory is required")
    initial = load_protocol(initial_directory)
    if (
        initial.stage != "INITIAL"
        or acceptance.get("initial_protocol_hash") != initial.content_hash
    ):
        raise ValueError("source acceptance must bind the independently verified INITIAL protocol")
    if acceptance.get("source_status") != "ACCEPTED":
        raise ValueError("independent source evidence has not been accepted")
    refs = acceptance.get("independent_label_refs")
    if not isinstance(refs, list) or not refs:
        raise ValueError("raw independent label references and hashes are required")
    evidence: dict[str, Any] = {}
    for ref in refs:
        raw = verified_json(root, ref["path"], ref["sha256"])
        if raw.get("schema_version") != "risk.supervision.v1" or not raw.get("evaluator_hash"):
            raise ValueError("raw supervision needs independent evaluator provenance")
        for sample_id, label in raw.get("records", {}).items():
            if sample_id in evidence:
                raise ValueError("duplicate independent supervision sample")
            evidence[sample_id] = label
    if set(evidence) != {record.sample_id for record in records}:
        raise ValueError("raw supervision must cover exactly the accepted sample sources")
    for record in records:
        expected = record.labels["risk_supervision"]
        label = evidence[record.sample_id]
        if (
            label.get("risk_supervision") != expected
            or label.get("observation_id") != record.frame_id
        ):
            raise ValueError("risk labels differ from bound independent raw supervision")
        # Read and check the separately recorded actual evaluator evidence.
        raw = verified_json(root, label["raw_evaluation_ref"], label["raw_evaluation_sha256"])
        if (
            raw.get("source") != "INDEPENDENT_EVALUATOR"
            or raw.get("observation_checksum") != record.observation_metadata.get("checksum_sha256")
            or raw.get("failure") != expected["failure"]
            or type(raw.get("failure")) is not bool
            or raw.get("geometric_error_m") != expected.get("geometric_error_m")
            or raw.get("motion_error_m_s") != expected.get("motion_error_m_s")
            or raw.get("calibration_residuals_m") != expected["calibration_residuals_m"]
        ):
            raise ValueError("independent evaluator output does not bind the actual risk labels")
    return partitions, {
        "initial_protocol_hash": initial.content_hash,
        "initial_protocol_stage": initial.stage,
        "acceptance_hash": content_digest(acceptance),
        "dataset_manifest_sha256": acceptance["dataset_manifest_sha256"],
        "split_manifest_sha256": acceptance["split_manifest_sha256"],
    }


def curve_svg(points: list[tuple[float, float]], title: str) -> str:
    coordinates = " ".join(f"{50 + 400 * x:.2f},{450 - 400 * y:.2f}" for x, y in points)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="520">'
        '<rect width="520" height="520" fill="white"/>'
        f'<text x="50" y="25" font-size="14">{title}</text>'
        '<path d="M50 50V450H450" fill="none" stroke="black"/>'
        '<path d="M50 450L450 50" stroke="#aaa" stroke-dasharray="4 4"/>'
        f'<polyline points="{coordinates}" fill="none" stroke="#2563eb" stroke-width="2"/>'
        '<text x="50" y="480">0</text><text x="445" y="480">1</text>'
        '<text x="25" y="55">1</text></svg>\n'
    )


def coverage_curve(
    residuals: list[float], *, bound: float, requested_coverage: float
) -> dict[str, Any]:
    """Actual group-error threshold versus calibration-set empirical CDF."""
    if (
        not residuals
        or not math.isfinite(bound)
        or bound < 0
        or not 0 < requested_coverage < 1
        or any(not math.isfinite(value) or value < 0 for value in residuals)
    ):
        raise ValueError("coverage curve requires finite nonnegative residuals and bound")
    thresholds = sorted({0.0, *residuals})
    return {
        "points": [
            (value, sum(r <= value for r in residuals) / len(residuals)) for value in thresholds
        ],
        "bound_m": bound,
        "requested_coverage": requested_coverage,
        "bound_empirical_coverage": sum(r <= bound for r in residuals) / len(residuals),
        "sample_unit": "independent group maximum",
        "dataset_role": "calibration",
        "independent_test_coverage": None,
    }


def coverage_svg(residuals: list[float], *, bound: float, requested_coverage: float) -> str:
    curve = coverage_curve(residuals, bound=bound, requested_coverage=requested_coverage)
    maximum = max(max(residuals), bound, 1e-12)
    points = curve["points"]
    # Horizontal/vertical steps show <= threshold membership, including duplicate residuals.
    steps = [points[0]]
    for (_previous_x, previous_y), (x, y) in zip(points[:-1], points[1:], strict=True):
        steps.extend(((x, previous_y), (x, y)))
    coordinates = " ".join(f"{60 + 420 * x / maximum:.2f},{440 - 350 * y:.2f}" for x, y in steps)
    bound_x = 60 + 420 * bound / maximum
    label = html.escape(
        f"Bound={bound:g} m; requested={requested_coverage:g}; "
        f"empirical={curve['bound_empirical_coverage']:.3f}; independent test: NOT_RUN"
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="650" height="540">'
        '<rect width="650" height="540" fill="white"/>'
        '<text x="60" y="25" font-size="14">Calibration-set empirical coverage</text>'
        '<text x="60" y="48" font-size="11">'
        "Independent group maxima; fitted calibration bound</text>"
        '<path d="M60 90V440H480" fill="none" stroke="black"/>'
        f'<polyline points="{coordinates}" fill="none" stroke="#2563eb" stroke-width="2"/>'
        f'<path d="M{bound_x:.2f} 90V440" stroke="#d97706" stroke-dasharray="4 4"/>'
        '<text x="60" y="465">0</text>'
        f'<text x="460" y="465">{maximum:g}</text>'
        '<text x="30" y="95">1</text>'
        '<text x="180" y="490">Error threshold (m)</text>'
        f'<text x="60" y="520" font-size="11">{label}</text></svg>\n'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial-protocol", type=Path)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "status": "INCOMPLETE",
        "research_status": "NOT_RUN",
        "enabled": False,
        "dataset": str(args.dataset),
        "reasons": [],
    }
    try:
        config = yaml.safe_load(args.config.read_text())
        if not isinstance(config, dict) or config.get("schema_version") != "risk.config.v1":
            raise ValueError("risk configuration schema is required")
        if config.get("enabled") is not False:
            raise ValueError("this software preparation command cannot enable an online method")
        if config.get("method") != "logistic_isotonic_group_conformal":
            raise ValueError("unsupported risk method")
        for key, value in SETTINGS.items():
            if config.get(key) != value:
                raise ValueError(
                    f"unselected risk hyperparameter: {key}; select/freeze independently"
                )
        snapshot = (
            load_selection_snapshot(args.dataset, config)
            if config.get("selection_status") == "FROZEN"
            else None
        )
        partitions, bindings = accepted_records(args.dataset, config, args.initial_protocol)
        if snapshot is None:
            raise ValueError(
                "selection parameter choice is NOT_RUN; source-backed freezing required"
            )
        bindings.update(
            verify_selection_snapshot(args.dataset, snapshot, config, partitions, bindings)
        )
        bindings["selection_artifact_sha256"] = config["selection_artifact_sha256"]
        model = fit_risk_model(partitions["train"], config["seed"])
        data = load_model(model)
        data.update(source_accepted=True, source_bindings=bindings)
        Path(model.model_path).write_text(canonical_json(data) + "\n")
        model = replace(model, model_hash=content_digest(data))
        model = calibrate_risk(model, partitions["calibration"])
        calibration = load_calibration(model)
        assert calibration is not None
        if (
            not calibration["isotonic_blocks"]
            or calibration["geometric_error_bound_m"] is None
            or calibration["motion_residual_bound_m_s"] is None
        ):
            raise ValueError(
                "insufficient independent calibration labels or fresh-frame motion residuals"
            )
        if not calibration["action_coverage"]["CONTINUE"]["calibrated"]:
            raise ValueError("executed CONTINUE outcomes lack independent fit/calibration coverage")
        shutil.copyfile(model.model_path, args.output / "model.json")
        calibration_name = Path(model.calibration_path).name
        shutil.copyfile(model.calibration_path, args.output / calibration_name)
        model = replace(
            model,
            model_path=str((args.output / "model.json").resolve()),
            calibration_path=str((args.output / calibration_name).resolve()),
        )
        payload = {
            "model_hash": model.model_hash,
            "model_path": model.model_path,
            "calibration_path": model.calibration_path,
            "fit_group_ids": model.fit_group_ids,
            "calibration_group_ids": model.calibration_group_ids,
            "feature_schema": dict(model.feature_schema),
        }
        (args.output / "artifact.json").write_text(canonical_json(payload) + "\n")
        reliability = []
        for _, _, probability in calibration["isotonic_blocks"]:
            rows = [row for row in calibration["reliability"] if row["calibrated"] == probability]
            reliability.append((probability, sum(row["failure"] for row in rows) / len(rows)))
        (args.output / "reliability.svg").write_text(
            curve_svg(reliability, "Calibration-set reliability (not independent evaluation)")
        )
        residuals = calibration["geometry_group_residuals_m"]
        (args.output / "coverage.svg").write_text(
            coverage_svg(
                residuals,
                bound=calibration["geometric_error_bound_m"],
                requested_coverage=calibration["coverage"],
            )
        )
        coverage = coverage_curve(
            residuals,
            bound=calibration["geometric_error_bound_m"],
            requested_coverage=calibration["coverage"],
        )
        (args.output / "coverage.json").write_text(canonical_json(coverage) + "\n")
        report.update(
            status="CALIBRATED_SOFTWARE_ARTIFACT",
            research_status="CALIBRATED",
            source_bindings=bindings,
            model_hash=model.model_hash,
            groups={role: sorted({r.group_id for r in rows}) for role, rows in partitions.items()},
            action_coverage=calibration["action_coverage"],
            test_evaluation_status="NOT_RUN",
            online_method_status="NOT_RUN",
        )
        exit_code = 0
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        report["reasons"].append(str(exc))
        exit_code = 2
    (args.output / "report.json").write_text(canonical_json(report) + "\n")
    print(canonical_json(report))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
