"""Preregistered nominal development validation, never a held-out test or freeze gate.

Every assigned scene gets exactly one attempt. Simulator truth stays offline; only
the natural-language instruction and RGBDObservation reach the visual planner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Permit both `python -m scripts...` and the documented direct CLI form.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import probe_rgbd_model as probe

EVALUATION_NAME = "nominal development validation"
POSITIVE_COUNT = 12
NEGATIVE_COUNT = 4


def _write_json(path: Path, value: Any) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                      allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def nominal_dataset_config() -> Any:
    from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig

    return DatasetConfig(
        dataset_id="rgbd-nominal-development-validation-v1", groups=16, seed=0,
        width=320, height=240,
        target_x=(0.18, 0.55), target_y=(-0.20, 0.28), half_size=(0.025, 0.045),
        camera_height=(1.2, 1.6), camera_x=(0.30, 0.40), camera_y=(-0.04, 0.04),
        camera_fovy=(45, 55), light_intensity=(0.65, 1.0), distractor_count=(0, 3),
        depth_noise_m=(0.0,), invalid_depth_fractions=(0.0,), settle_steps=120,
    )


def build_assignments(
    *, seed_start: int = 41001, grasp_profile: str = "mujoco_upright_box_v2",
) -> dict[str, Any]:
    """Choose all scenes and readable tasks before any rendering or model call."""
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

    if type(seed_start) is not int or seed_start <= 0:
        raise ValueError("seed_start must be a positive integer")
    config = nominal_dataset_config()
    asset_hash = calibration_asset_sha256(grasp_profile)
    cases = []
    for kind, count, start in (
        ("positive", POSITIVE_COUNT, seed_start),
        ("negative_absent", NEGATIVE_COUNT, seed_start + 1000),
    ):
        for index in range(count):
            seed = start + index
            case: dict[str, Any] = {
                "case_id": f"{kind}-{index + 1:02d}", "kind": kind, "seed": seed,
                "scene_sha256": None, "instruction": None,
                "grasp_profile": grasp_profile, "grasp_calibration_asset_sha256": asset_hash,
            }
            try:
                scene = sample_scene(config, seed)
                color = scene.scene_parameters["target"]["color_name"]
                if color not in {"red", "blue", "yellow"}:
                    raise ValueError("sampled target is outside the registered palette")
                color = "purple" if kind == "negative_absent" else color
                case.update({
                    "scene_sha256": scene.scene_hash,
                    "instruction": f"Pick up the {color} block and place it in the green region.",
                })
            except Exception as exc:
                case["assignment_error"] = f"{type(exc).__name__}: {exc}"
            cases.append(case)
    return {
        "schema_version": "rgbd.model-scene-eval.v1", "evaluation": EVALUATION_NAME,
        "held_out_test": False, "seed_start": seed_start,
        "dataset_config": config.model_dump(mode="json"),
        "dataset_config_hash": config.config_hash,
        "policy": "one attempt per case; no retries, exclusions, selection or model freeze",
        "cases": cases,
    }


def preregister(output: Path, assignments: Mapping[str, Any]) -> str:
    """An exclusive assignment file is the run's commit point before model access."""
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("scene evaluation requires an empty output directory")
    return _write_json(output / "assignments.json", assignments)


def _calibrated_offset(attempt: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

    evidence = attempt.get("observation_evidence")
    if not isinstance(evidence, dict):
        return False
    tcp = evidence.get("resolved_top_grasp_tcp")
    profile = case.get("grasp_profile")
    asset_hash = calibration_asset_sha256(profile)
    return (
        evidence.get("top_grasp_offset_status") == "CALIBRATED_RGBD_TOP_GRASP_V1"
        and asset_hash is not None
        and case.get("grasp_calibration_asset_sha256") == asset_hash
        and evidence.get("grasp_profile") == profile
        and evidence.get("grasp_calibration_asset_sha256") == asset_hash
        and isinstance(tcp, dict) and set(tcp) == {"x", "y", "z"}
        and all(type(value) in {int, float} and math.isfinite(value) for value in tcp.values())
    )


def _explicit_refusal(attempt: Mapping[str, Any]) -> bool:
    decision = attempt.get("visual_decision")
    if not isinstance(decision, dict):
        return False
    confidence = decision.get("reported_confidence")
    return (
        attempt.get("observed_scene_present") is False
        and attempt.get("grounded") is False
        and bool(attempt.get("raw_model_output"))
        and (("target_pixel" in decision and decision["target_pixel"] is None)
             or (isinstance(confidence, (int, float)) and type(confidence) in {int, float}
                 and math.isfinite(confidence)
                 and 0 <= confidence < 0.5))
    )


def case_passes(case: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    attempt, capture = record.get("attempt"), record.get("capture")
    if not (
        record.get("complete") is True and not record.get("error")
        and record.get("case_id") == case["case_id"]
        and record.get("kind") == case["kind"]
        and isinstance(case.get("scene_sha256"), str)
        and record.get("scene_sha256") == case["scene_sha256"]
        and isinstance(record.get("rgb_sha256"), str) and len(record["rgb_sha256"]) == 64
        and isinstance(record.get("diagnostics"), dict)
        and isinstance(capture, dict) and capture.get("source") == "mujoco_camera"
        and capture.get("synchronized") is True
        and isinstance(attempt, dict) and not attempt.get("error")
        and attempt.get("transport_two_images") is True
    ):
        return False
    if case["kind"] == "negative_absent":
        return _explicit_refusal(attempt)
    return all(attempt.get(key) is True for key in (
        "observed_scene_present", "parsed", "grounded", "target_hit", "destination_hit",
    )) and _calibrated_offset(attempt, case)


def summarize_results(
    assignments: Mapping[str, Any], records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Count against assignments, including missing, failed and incomplete cases."""
    cases = assignments["cases"]
    counts = Counter(record.get("case_id") for record in records)
    by_id = {record.get("case_id"): record for record in records}
    unique_records = [by_id[case["case_id"]] for case in cases
                      if counts[case["case_id"]] == 1]
    passed = [case for case in cases if counts[case["case_id"]] == 1
              and case_passes(case, by_id[case["case_id"]])]
    complete = [record for record in unique_records if record.get("complete") is True]
    positive_attempts = [(case, by_id[case["case_id"]]["attempt"]) for case in cases
                         if case["kind"] == "positive" and counts[case["case_id"]] == 1
                         and isinstance(by_id[case["case_id"]].get("attempt"), dict)]
    positive_gates = {key: sum(attempt.get(key) is True for _, attempt in positive_attempts)
                      for key in ("transport_two_images", "observed_scene_present", "parsed",
                                  "grounded", "target_hit", "destination_hit")}
    positive_gates["calibrated_offset"] = sum(
        _calibrated_offset(attempt, case) for case, attempt in positive_attempts
    )
    return {
        "total_cases": len(cases),
        "positive_cases": sum(case["kind"] == "positive" for case in cases),
        "negative_cases": sum(case["kind"] == "negative_absent" for case in cases),
        "recorded_cases": len(unique_records), "complete_cases": len(complete),
        "error_cases": sum(bool(record.get("error")) for record in unique_records),
        "missing_cases": sum(counts[case["case_id"]] == 0 for case in cases),
        "duplicate_cases": sum(counts[case["case_id"]] > 1 for case in cases),
        "unknown_records": sum(record.get("case_id") not in {case["case_id"] for case in cases}
                               for record in records),
        "unique_scene_count": len({record["scene_sha256"] for record in unique_records
                                   if record.get("scene_sha256")}),
        "unique_rgb_count": len({record["rgb_sha256"] for record in unique_records
                                 if record.get("rgb_sha256")}),
        "passed_cases": len(passed),
        "positive_passed": sum(case["kind"] == "positive" for case in passed),
        "negative_passed": sum(case["kind"] == "negative_absent" for case in passed),
        "positive_gate_counts": positive_gates,
        "all_cases_pass": bool(cases) and len(passed) == len(cases) == len(records),
    }


def offline_diagnostics(frame: Any, attempt: Mapping[str, Any]) -> dict[str, Any]:
    """Distance to visible geom-mask centroids, computed only after the response.

    The metric center is a mean of visible surface world points, not the object's
    physical center or a grasp target. These numbers never alter requests or gates.
    """
    observation = frame.observation
    width = observation.width
    depth, valid = observation.depth_values(), observation.valid_mask_bytes()
    fx, fy, cx, cy = observation.intrinsics
    matrix = observation.camera_to_world
    result: dict[str, Any] = {}
    for kind, label in (("target", "object_geom"), ("destination", "target_region_geom")):
        ids = {key for key, value in frame.instance_labels.items() if value == label}
        indexes = [index for index, value in enumerate(frame.instance_ids) if value in ids]
        diagnostic: dict[str, Any] = {
            "expected_geom_label": label, "visible_pixel_count": len(indexes),
            "visible_pixel_center": None, "visible_surface_center_m": None,
            "pixel_center_error_px": None, "visible_surface_center_error_m": None,
            "metric_center_semantics": "MEAN_VISIBLE_SURFACE_NOT_OBJECT_CENTER",
        }
        if indexes:
            center = [sum(index % width for index in indexes) / len(indexes),
                      sum(index // width for index in indexes) / len(indexes)]
            diagnostic["visible_pixel_center"] = center
            points = []
            for index in indexes:
                if not valid[index] or depth[index] <= 0:
                    continue
                camera = ((index % width - cx) * depth[index] / fx,
                          (index // width - cy) * depth[index] / fy, depth[index])
                points.append([sum(matrix[row + axis] * camera[axis] for axis in range(3))
                               + matrix[row + 3] for row in (0, 4, 8)])
            metric_center = ([sum(point[axis] for point in points) / len(points)
                              for axis in range(3)] if points else None)
            diagnostic["visible_surface_center_m"] = metric_center
            check = attempt.get(f"{kind}_offline_check", {})
            pixel, world = check.get("pixel"), check.get("world_surface_point_m")
            if isinstance(pixel, (list, tuple)) and len(pixel) == 2:
                diagnostic["pixel_center_error_px"] = math.dist(pixel, center)
            if metric_center is not None and isinstance(world, dict):
                diagnostic["visible_surface_center_error_m"] = math.dist(
                    [world[axis] for axis in ("x", "y", "z")], metric_center,
                )
        result[kind] = diagnostic
    return result


def evaluate_assignments(
    assignments: Mapping[str, Any], output: Path,
    evaluate_case: Callable[[dict[str, Any], Path], dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for case in assignments["cases"]:
        directory = output / "cases" / case["case_id"]
        directory.mkdir(parents=True, exist_ok=False)
        record: dict[str, Any] = {
            "case_id": case["case_id"], "kind": case["kind"], "seed": case["seed"],
            "complete": False, "scene_sha256": case.get("scene_sha256"),
        }
        try:
            record.update(evaluate_case(case, directory))
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {str(exc)[:1000]}"
            record["complete"] = False
        # Failures have explicit stage artifacts too; no fabricated image or response.
        for name in ("scene", "capture", "attempt"):
            path = directory / f"{name}.json"
            if not path.exists():
                _write_json(path, record.get(name, {
                    "available": False, "error": record.get("error", "stage not completed"),
                }))
        record["passed"] = case_passes(case, record)
        _write_json(directory / "outcome.json", record)
        records.append(record)
        print(f"{case['case_id']}: complete={record['complete']} passed={record['passed']}",
              flush=True)
    return records


def _evaluate_case(
    case: Mapping[str, Any], directory: Path, *, snapshot: Any, dataset_config: Any,
) -> dict[str, Any]:
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
    from cloud_edge_robot_arm.vision.model_resolver import resolve_visual_planner
    from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

    if case.get("assignment_error"):
        raise ValueError(case["assignment_error"])
    asset_hash = calibration_asset_sha256(snapshot.grasp_profile)
    if asset_hash is None or (
        hashlib.sha256(Path(dataset_config.model_path).read_bytes()).hexdigest() != asset_hash
    ):
        raise ValueError("nominal scene requires the approved calibrated asset")
    scene = sample_scene(dataset_config, case["seed"])
    if scene.scene_hash != case["scene_sha256"]:
        raise ValueError("sampled scene differs from preregistered assignment")
    _write_json(directory / "scene.json", scene.model_dump(mode="json"))
    config = SimulatorConfig(
        camera_width=dataset_config.width, camera_height=dataset_config.height,
        model_path=dataset_config.model_path, render_rgb=True, render_depth=True,
        domain_randomization=False, seed=case["seed"],
    )
    with MuJoCoCaptureSession(config) as session:
        session.apply_scene(scene)
        session._backend.step(dataset_config.settle_steps)
        frame = session.capture_with_instances()
        capture = {
            **frame.observation.evidence(), "settle_steps": dataset_config.settle_steps,
            "physics_state_hash": frame.physics_state_hash,
            "pass_state_hashes": list(frame.pass_state_hashes),
            "synchronized": len(frame.pass_state_hashes) == 3
            and len(set(frame.pass_state_hashes)) == 1
            and frame.pass_state_hashes[0] == frame.physics_state_hash,
        }
        _write_json(directory / "capture.json", capture)
        # The scene summary intentionally has no objects, regions or simulator truth.
        request = InitialPlanningRequest(
            request_id="nominal-development-validation",
            user_instruction=case["instruction"], observation=frame.observation,
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        )
        planner = resolve_visual_planner(snapshot)
        attempt = probe._attempt(
            planner=planner, request=request, frame=frame, index=1, output=directory,
            endpoint=snapshot.endpoint, model_name=snapshot.model,
        )
        # The model is not unloaded between cases; this is not cold-start timing.
        attempt["phase"] = "scene_validation"
        _write_json(directory / "attempt.json", attempt)
        diagnostics = offline_diagnostics(frame, attempt)
    return {
        "complete": True, "capture": capture, "attempt": attempt, "diagnostics": diagnostics,
        "scene_sha256": scene.scene_hash, "rgb_sha256": capture["rgb_sha256"],
    }


def run_evaluation(config_path: Path, output: Path, *, seed_start: int = 41001) -> dict[str, Any]:
    os.environ.setdefault("MUJOCO_GL", "egl")
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot

    snapshot_data, _probe_settings = probe._read_candidate(config_path)
    assignments = build_assignments(
        seed_start=seed_start, grasp_profile=snapshot_data.get("grasp_profile", "unconfigured"),
    )
    assignment_sha = preregister(output, assignments)
    raw_config = config_path.read_bytes()
    with (output / "candidate-config.yaml").open("xb") as stream:
        stream.write(raw_config)
    dataset_config = nominal_dataset_config()
    dataset_sha = _write_json(
        output / "dataset-config.json", dataset_config.model_dump(mode="json"),
    )
    source = probe._source_fingerprints()
    root = Path(__file__).resolve().parents[1]
    for name in (
        "scripts/evaluate_rgbd_model_scenes.py", "tests/test_rgbd_model_scene_eval.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/scene_sampler.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/capture.py",
        "src/cloud_edge_robot_arm/vision/top_grasp.py",
        "src/cloud_edge_robot_arm/simulation/config.py",
        "src/cloud_edge_robot_arm/simulation/models.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py", dataset_config.model_path,
    ):
        source[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    provenance = {
        "evaluation": EVALUATION_NAME, "held_out_test": False,
        "started_at": datetime.now(UTC).isoformat(), "candidate_path": str(config_path),
        "candidate_sha256": hashlib.sha256(raw_config).hexdigest(), "snapshot": snapshot_data,
        "dataset_config_sha256": dataset_sha, "assignments_sha256": assignment_sha,
        "source_fingerprints": source,
        "model_freeze": False,
    }
    _write_json(output / "provenance.json", provenance)

    def evaluate(case: dict[str, Any], directory: Path) -> dict[str, Any]:
        snapshot = ModelConfigSnapshot(**{**snapshot_data,
                                          "image_size": tuple(snapshot_data["image_size"])})
        return _evaluate_case(case, directory, snapshot=snapshot, dataset_config=dataset_config)

    records = evaluate_assignments(assignments, output, evaluate)
    summary = summarize_results(assignments, records)
    _write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-start", type=int, default=41001)
    args = parser.parse_args()
    if args.seed_start <= 0:
        parser.error("--seed-start must be a positive integer")
    try:
        summary = run_evaluation(args.config, args.output, seed_start=args.seed_start)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"scene evaluation not started: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_cases_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
