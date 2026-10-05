"""CPU-only checks for preregistered scene diagnostics and honest denominators."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


def _module():
    return importlib.import_module("scripts.evaluate_rgbd_model_scenes")


def _record(case):
    negative = case["kind"] == "negative_absent"
    return {
        "case_id": case["case_id"], "kind": case["kind"], "complete": True,
        "scene_sha256": case["scene_sha256"], "rgb_sha256": "b" * 64,
        "capture": {"source": "mujoco_camera", "synchronized": True},
        "diagnostics": {},
        "attempt": {
            "transport_two_images": True, "raw_model_output": "response",
            "observed_scene_present": not negative, "parsed": not negative,
            "grounded": not negative, "target_hit": not negative,
            "destination_hit": not negative,
            "visual_decision": {"target_pixel": None, "reported_confidence": 0.0},
            "observation_evidence": {
                "top_grasp_offset_status": "CALIBRATED_RGBD_TOP_GRASP_V1",
                "grasp_profile": "mujoco_upright_box_v1",
                "grasp_calibration_asset_sha256": (
                    "182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08"
                ),
                "resolved_top_grasp_tcp": {"x": 0.4, "y": 0.0, "z": 0.02},
            },
        },
    }


def test_assignments_are_reproducible_and_instructions_do_not_expose_scene_truth():
    evaluation = _module()
    first = evaluation.build_assignments()
    assert first == evaluation.build_assignments()
    cases = first["cases"]
    assert [case["seed"] for case in cases] == list(range(41001, 41013)) + list(
        range(42001, 42005)
    )
    assert len({case["scene_sha256"] for case in cases}) == 16
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene

    config = evaluation.nominal_dataset_config()
    assert config.depth_noise_m == (0.0,)
    assert config.invalid_depth_fractions == (0.0,)
    for case in cases:
        scene = sample_scene(config, case["seed"])
        color = scene.scene_parameters["target"]["color_name"]
        if case["kind"] == "negative_absent":
            assert case["instruction"] == (
                "Pick up the purple block and place it in the green region."
            )
            assert all(obj["color_name"] != "purple" for obj in [
                scene.scene_parameters["target"], *scene.scene_parameters["distractors"]
            ])
        else:
            assert case["instruction"] == (
                f"Pick up the {color} block and place it in the green region."
            )
        assert not any(char.isdigit() for char in case["instruction"])
        assert scene.group_id not in case["instruction"]
    assert evaluation.build_assignments(seed_start=51001)["cases"][12]["seed"] == 52001
    with pytest.raises(ValueError, match="positive integer"):
        evaluation.build_assignments(seed_start=0)


def test_preregister_refuses_nonempty_output_and_never_replaces_assignments(tmp_path):
    evaluation = _module()
    assignments = evaluation.build_assignments()
    output = tmp_path / "run"
    digest = evaluation.preregister(output, assignments)
    path = output / "assignments.json"
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        evaluation.preregister(output, evaluation.build_assignments(seed_start=51001))
    assert path.read_bytes() == original
    other = tmp_path / "occupied"
    other.mkdir()
    (other / "owned.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        evaluation.preregister(other, assignments)
    assert not (other / "assignments.json").exists()


def test_every_case_failure_is_saved_once_and_kept_in_the_denominator(tmp_path):
    evaluation = _module()
    assignments = evaluation.build_assignments()
    evaluation.preregister(tmp_path, assignments)
    visited = []

    def failed(case, directory):
        visited.append(case["case_id"])
        assert (tmp_path / "assignments.json").exists()
        raise RuntimeError("capture unavailable")

    records = evaluation.evaluate_assignments(assignments, tmp_path, failed)
    summary = evaluation.summarize_results(assignments, records)
    assert len(visited) == len(set(visited)) == 16
    assert summary["total_cases"] == 16
    assert summary["positive_cases"] == 12
    assert summary["negative_cases"] == 4
    assert summary["error_cases"] == 16
    assert summary["passed_cases"] == 0
    assert summary["all_cases_pass"] is False
    for case in assignments["cases"]:
        directory = tmp_path / "cases" / case["case_id"]
        assert json.loads((directory / "outcome.json").read_text())["error"]
        assert json.loads((directory / "attempt.json").read_text())["error"]


@pytest.mark.parametrize("missing", ["case", "attempt", "capture", "scene_sha256", "complete"])
def test_incomplete_evidence_cannot_pass(missing):
    evaluation = _module()
    assignments = evaluation.build_assignments()
    records = [_record(case) for case in assignments["cases"]]
    assert evaluation.summarize_results(assignments, records)["all_cases_pass"] is True
    if missing == "case":
        records.pop()
    else:
        records[0].pop(missing)
    summary = evaluation.summarize_results(assignments, records)
    assert summary["total_cases"] == 16
    assert summary["all_cases_pass"] is False


@pytest.mark.parametrize("gate", [
    "transport_two_images", "parsed", "grounded", "target_hit", "destination_hit",
    "observed_scene_present",
])
def test_each_positive_requires_every_existing_gate(gate):
    evaluation = _module()
    assignments = evaluation.build_assignments()
    records = [_record(case) for case in assignments["cases"]]
    records[0]["attempt"][gate] = False
    summary = evaluation.summarize_results(assignments, records)
    assert summary["positive_passed"] == 11
    assert summary["positive_gate_counts"][gate] == 11
    assert summary["positive_gate_counts"]["calibrated_offset"] == 12


def test_positive_requires_finite_calibrated_tcp_and_negative_requires_explicit_refusal():
    evaluation = _module()
    assignments = evaluation.build_assignments()
    records = [_record(case) for case in assignments["cases"]]
    records[0]["attempt"]["observation_evidence"]["resolved_top_grasp_tcp"]["z"] = float("nan")
    records[12]["attempt"]["visual_decision"] = {}
    records[13]["attempt"].pop("observed_scene_present")
    records[14]["attempt"]["observed_scene_present"] = True
    summary = evaluation.summarize_results(assignments, records)
    assert summary["positive_passed"] == 11
    assert summary["negative_passed"] == 1
    assert summary["all_cases_pass"] is False
    records[15]["attempt"]["visual_decision"] = {
        "target_pixel": [0, 0], "reported_confidence": 0.49,
    }
    assert evaluation.summarize_results(assignments, records)["negative_passed"] == 1


def test_duplicate_or_unknown_case_records_do_not_inflate_success():
    evaluation = _module()
    assignments = evaluation.build_assignments()
    records = [_record(case) for case in assignments["cases"]]
    records.append(copy.deepcopy(records[0]))
    summary = evaluation.summarize_results(assignments, records)
    assert summary["total_cases"] == 16
    assert summary["all_cases_pass"] is False


@pytest.mark.parametrize("field", ["grasp_profile", "grasp_calibration_asset_sha256"])
def test_uncorroborated_calibration_scope_cannot_pass(field):
    evaluation = _module()
    assignments = evaluation.build_assignments()
    records = [_record(case) for case in assignments["cases"]]
    records[0]["attempt"]["observation_evidence"].pop(field)
    assert evaluation.summarize_results(assignments, records)["positive_passed"] == 11


def test_unapproved_mjcf_is_rejected_before_rendering(tmp_path):
    evaluation = _module()
    config = evaluation.nominal_dataset_config()
    asset = tmp_path / "changed.xml"
    asset.write_text("unapproved fixture", encoding="utf-8")
    config = config.model_copy(update={"model_path": str(asset)})
    case = evaluation.build_assignments()["cases"][0]
    with pytest.raises(ValueError, match="calibrated asset"):
        evaluation._evaluate_case(
            case, tmp_path,
            snapshot=SimpleNamespace(grasp_profile="mujoco_upright_box_v1"),
            dataset_config=config,
        )


def test_offline_diagnostics_use_visible_mask_centroid_without_changing_attempt():
    evaluation = _module()
    observation = SimpleNamespace(
        width=3, height=2, intrinsics=(1, 1, 0, 0),
        camera_to_world=(1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1),
        depth_values=lambda: (1., 1., 1., 1., 1., 1.),
        valid_mask_bytes=lambda: bytes([1] * 6),
    )
    frame = SimpleNamespace(
        observation=observation, instance_ids=(0, 7, 7, 0, 0, 8),
        instance_labels={7: "object_geom", 8: "target_region_geom"},
    )
    attempt = {"target_offline_check": {
        "pixel": [1, 0], "world_surface_point_m": {"x": 11., "y": 20., "z": 31.},
    }}
    original = copy.deepcopy(attempt)
    target = evaluation.offline_diagnostics(frame, attempt)["target"]
    assert target["visible_pixel_center"] == [1.5, 0.0]
    assert target["visible_surface_center_m"] == [11.5, 20., 31.]
    assert target["pixel_center_error_px"] == 0.5
    assert target["visible_surface_center_error_m"] == 0.5
    assert attempt == original


def test_run_writes_matching_provenance_before_attempts_and_preserves_all_failures(
    tmp_path, monkeypatch,
):
    evaluation = _module()
    config = tmp_path / "candidate.yaml"
    config.write_text(json.dumps({
        "provider": "ollama", "model": "qwen3-vl-candidate:4b-instruct",
        "endpoint": "http://127.0.0.1:11434", "weight_digest": "a" * 64,
        "quantization": "Q4_K_M", "image_size": [320, 240],
        "generation_parameters": {"temperature": 0, "think": False},
        "timeout_s": 180, "coordinate_system": "normalized_1000",
        "probe": {"scenario_id": "S01_NORMAL_STATIC", "seed": 1,
                  "instruction": "unused probe instruction", "warm_runs": 3},
    }), encoding="utf-8")
    output = tmp_path / "run"

    def fail_case(case, directory, **kwargs):
        provenance = json.loads((output / "provenance.json").read_text())
        for name, key in (("assignments.json", "assignments_sha256"),
                          ("candidate-config.yaml", "candidate_sha256"),
                          ("dataset-config.json", "dataset_config_sha256")):
            assert provenance[key] == hashlib.sha256((output / name).read_bytes()).hexdigest()
        assert kwargs["snapshot"].coordinate_system == "normalized_1000"
        raise RuntimeError("CPU test: rendering deliberately unavailable")

    monkeypatch.setattr(evaluation, "_evaluate_case", fail_case)
    summary = evaluation.run_evaluation(config, output)
    assert summary["total_cases"] == summary["error_cases"] == 16
    assert json.loads((output / "summary.json").read_text()) == summary
    assert not list(output.glob("*frozen*"))


def test_scene_attempt_settles_before_capture_and_sends_only_observation_and_instruction(
    tmp_path, monkeypatch,
):
    from cloud_edge_robot_arm.simulation.models import SensorFrame
    from cloud_edge_robot_arm.vision import capture, model_resolver
    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

    evaluation = _module()
    case = evaluation.build_assignments()["cases"][0]
    observation = observation_from_sensor_frame(SensorFrame(
        frame_id="cpu-boundary-fixture", captured_at=datetime.now(UTC), sim_time_s=0.24,
        width=2, height=2, rgb=bytes((255, 0, 0)) * 4, depth=(1., 1., 1., 1.),
        intrinsics=(2., 2., 0., 0.),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
    ), source="mujoco_camera")
    frame = capture.CapturedFrame(
        observation=observation, instance_ids=(1, 1, 2, 2),
        instance_labels={1: "object_geom", 2: "target_region_geom"},
        physics_state_hash="x", pass_state_hashes=("x", "x", "x"),
    )
    events = []

    class CpuCapture:
        def __init__(self, config):
            self._backend = SimpleNamespace(step=lambda count: events.append(("step", count)))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def apply_scene(self, scene):
            events.append(("apply", scene.scene_hash))

        def capture_with_instances(self):
            assert events == [("apply", case["scene_sha256"]), ("step", 120)]
            return frame

    snapshot = SimpleNamespace(endpoint="http://127.0.0.1:11434", model="offline-fixture")
    planner = object()

    def resolve(actual):
        assert actual is snapshot
        return planner

    def attempt(**kwargs):
        request = kwargs["request"]
        assert kwargs["planner"] is planner
        assert request.observation is observation
        assert request.user_instruction == case["instruction"]
        assert request.scene.objects == request.scene.regions == request.scene.obstacles == []
        assert request.scene.robot_state == {}
        record = _record(case)["attempt"]
        record["phase"] = "cold"
        return record

    monkeypatch.setattr(capture, "MuJoCoCaptureSession", CpuCapture)
    monkeypatch.setattr(model_resolver, "resolve_visual_planner", resolve)
    monkeypatch.setattr(evaluation.probe, "_attempt", attempt)
    record = evaluation._evaluate_case(
        case, tmp_path, snapshot=snapshot, dataset_config=evaluation.nominal_dataset_config(),
    )
    assert record["attempt"]["phase"] == "scene_validation"
    assert (tmp_path / "scene.json").exists()
    assert (tmp_path / "capture.json").exists()
    assert (tmp_path / "attempt.json").exists()
