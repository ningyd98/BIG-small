"""Bounded risk-source diagnostics; pure math fixtures never actual acceptance."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.risk_sources import RiskSourceRegistration
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from tests.test_pose_marker_evidence import observation
from tests.test_research_risk_sources import (
    ROOT,
    fixture_case,
    hashes,
    json_file,
    sources,
)


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.risk_supervision")


def test_unregistered_source_has_no_observation_or_actual_authority() -> None:
    result = api().RiskSupervisionAuditor({}).audit("not-registered")
    assert result.status == "UNKNOWN"
    assert result.actual_source_status == "UNKNOWN"
    assert result.counts["assigned_attempts"] == result.counts["allocated_observations"] == 0
    assert "evidence_id_not_registered" in result.reasons


def registered_fixture(tmp_path: Path, *, history=("UNVIEWED",), split="train"):
    """Hand-constructed SOFTWARE_ONLY static RAW and measurement originals."""
    module = api()
    case, directory = fixture_case(tmp_path)
    frames = []
    epoch = datetime(2026, 10, 5, tzinfo=UTC)
    marker = PoseMarkerRegistration(
        7, 0.045, "2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4"
    )
    for index, step in enumerate((120, 121)):
        template = observation().model_dump()
        template.update(
            frame_id=f"software-frame-{index}",
            observation_id="",
            captured_at=epoch + timedelta(seconds=step * 0.25),
            sim_time_s=step * case.context["physics_dt_s"],
            episode_id=case.context["episode_id"],
            scene_id=case.assignment["group_id"],
            intrinsics=(1066.6666666667, 1066.6666666667, 79.5, 79.5),
            checksum_sha256="",
            source="mujoco_camera",
        )
        frame = RGBDObservation.model_validate(template)
        frames.append(frame)
        folder = directory / "frames" / f"FRAME_{index}"
        folder.mkdir(parents=True)
        import base64

        (folder / "rgb.png").write_bytes(base64.b64decode(frame.rgb_png_base64))
        (folder / "depth.f32").write_bytes(base64.b64decode(frame.depth_float32_base64))
        (folder / "valid_mask.u8").write_bytes(frame.valid_mask_bytes())
        json_file(folder / "observation.json", frame.evidence())
        (folder / "observation-full.json").write_text(frame.model_dump_json() + "\n")
        result = detect_pose_marker(frame, marker)
        assert result.status == "OBSERVED"
        payload = asdict(result)
        payload["captured_at"] = result.captured_at.isoformat()
        json_file(folder / "marker-estimate.json", payload)
    case = replace(
        case,
        original_file_hashes=hashes(directory),
        marker_registration=marker,
        expected_counts={**dict(case.expected_counts), "frames": 2},
    )
    inventory = sources()
    for name in module.required_supervision_source_paths():
        inventory[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    raw = RiskSourceRegistration(
        tmp_path, ROOT, inventory, (case,), CompletionCriteria("object", "target_region")
    )
    allocations = tuple(
        module.RiskObservationAllocation(
            f"sample-{i}",
            case.case_id,
            frame.observation_id,
            split,
            None if i == 0 else "sample-0",
        )
        for i, frame in enumerate(frames)
    )
    measurements = tmp_path / "measurements"
    measurements.mkdir()
    clock = {
        "schema_version": "risk.clock-diagnostic.v1",
        "source_scope": "SOFTWARE_ONLY",
        "cases": {
            case.case_id: [
                {
                    "physics_step": step,
                    "sim_time_s": step * case.context["physics_dt_s"],
                    "monotonic_s": 1000 + step * 0.25,
                    "utc": (epoch + timedelta(seconds=step * 0.25)).isoformat(),
                }
                for step in range(122)
            ]
        },
    }
    json_file(measurements / "clock.json", clock)
    calibration = {
        "schema_version": "risk.calibration-diagnostic.v1",
        "source_scope": "SOFTWARE_ONLY",
        "geometry_scope": "MARKER_CENTER_TRANSLATION",
        "observation_ids": ["independent-cal-a", "independent-cal-b"],
        "camera_domain": {
            key: frames[0].model_dump(mode="json")[key]
            for key in (
                "calibration_version",
                "intrinsics",
                "camera_to_world",
                "width",
                "height",
                "source",
            )
        },
        "pairs_m": [
            {"estimate": [0.003, 0, 0], "reference": [0, 0, 0]},
            {"estimate": [0, 0.004, 0], "reference": [0, 0, 0]},
        ],
    }
    json_file(measurements / "calibration.json", calibration)
    measured = module.RiskDiagnosticMeasurements(
        measurements, hashes(measurements), "clock.json", "calibration.json"
    )
    registered = module.RiskSupervisionRegistration(
        raw,
        allocations,
        (module.RiskComponentHistory(case.assignment["group_id"], history),),
        diagnostic_measurements=measured,
    )
    return registered, directory, measurements, frames


def audit(registration):
    return api().RiskSupervisionAuditor({"source": registration}).audit("source")


def test_reconstructed_online_features_and_offline_failure_stay_software_only(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    result = audit(registration)
    assert result.status == result.actual_source_status == "UNKNOWN"
    assert result.diagnostic_status == "VALID", result.reasons
    assert result.counts["assigned_attempts"] == 1
    assert result.counts["allocated_observations"] == result.counts["task_labels"] == 2
    assert result.counts["feature_rows"] == result.counts["geometric_labels"] == 2
    assert [row["offline_labels"]["failure"] for row in result.rows] == [True, True]
    assert result.rows[0]["online_features"]["calibration_residual_m"] == 0.004
    assert result.rows[0]["online_features"]["invalid_depth_fraction"] == 0
    assert result.rows[1]["online_features"]["frame_interval_s"] == 0.25
    assert result.rows[1]["online_features"]["observed_motion_m_s"] == 0
    assert result.rows[0]["geometry_scope"] == "MARKER_CENTER_TRANSLATION"
    assert {
        "raw_v3_clock_publisher_unavailable",
        "independent_calibration_publisher_unavailable",
        "initial_source_registration_unavailable",
        "derived_risk_commits_unavailable",
    } <= set(result.reasons)
    assert "failure" not in result.rows[0]["online_features"]
    assert "geometric_error_m" not in result.rows[0]["online_features"]


def test_allocation_omission_cannot_shrink_original_frame_denominator(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    result = audit(replace(registration, allocations=registration.allocations[:1]))
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == 2
    assert result.counts["missing_observations"] == 2


def test_missing_attempt_retains_every_original_scheduled_observation(tmp_path: Path):
    registration, directory, _, _ = registered_fixture(tmp_path)
    import shutil

    shutil.rmtree(directory)
    result = audit(registration)
    assert result.status == "UNKNOWN"
    assert result.counts["allocated_observations"] == result.counts["missing_observations"] == 2
    assert len(result.original_file_hashes) >= 10


@pytest.mark.parametrize("split", ["calibration", "selection", "test"])
def test_development_feedback_cannot_be_renamed_independent_holdout(tmp_path: Path, split: str):
    registration, _, _, _ = registered_fixture(
        tmp_path, history=("DEVELOPMENT_FEEDBACK",), split=split
    )
    result = audit(registration)
    assert result.diagnostic_status == "INVALID"
    assert any("history" in value for value in result.reasons)


def test_authorized_development_train_preserves_original_history(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path, history=("DEVELOPMENT_FEEDBACK",))
    result = audit(registration)
    assert result.diagnostic_status == "VALID"
    assert result.rows[0]["used_purposes"] == ("DEVELOPMENT_FEEDBACK",)
    assert result.status == "UNKNOWN"


def test_unknown_history_is_unavailable_instead_of_independent(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path, history=("UNKNOWN",))
    result = audit(registration)
    assert result.diagnostic_status == "UNKNOWN"
    assert any("history" in value for value in result.reasons)


@pytest.mark.parametrize("mutation", ["omit_step", "bool", "huge", "reverse", "receipt"])
def test_rehashed_diagnostic_clock_rejects_incomplete_or_untyped_mapping(
    tmp_path: Path, mutation: str
):
    registration, _, measurements, _ = registered_fixture(tmp_path)
    payload = json.loads((measurements / "clock.json").read_bytes())
    rows = payload["cases"][registration.raw_registration.cases[0].case_id]
    if mutation == "omit_step":
        rows.pop(5)
    elif mutation == "bool":
        rows[5]["monotonic_s"] = False
    elif mutation == "huge":
        rows[5]["monotonic_s"] = 10**500
    elif mutation == "reverse":
        rows[5]["monotonic_s"] = rows[4]["monotonic_s"]
    else:
        payload["source_accepted"] = True
    json_file(measurements / "clock.json", payload)
    measured = replace(
        registration.diagnostic_measurements, original_file_hashes=hashes(measurements)
    )
    result = audit(replace(registration, diagnostic_measurements=measured))
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == 2


@pytest.mark.parametrize("mutation", ["target_overlap", "camera_drift", "receipt", "negative_bool"])
def test_calibration_diagnostics_do_not_accept_target_truth_or_receipt(
    tmp_path: Path, mutation: str
):
    registration, _, measurements, frames = registered_fixture(tmp_path)
    payload = json.loads((measurements / "calibration.json").read_bytes())
    if mutation == "target_overlap":
        payload["observation_ids"][0] = frames[0].observation_id
    elif mutation == "camera_drift":
        payload["camera_domain"]["width"] = 12
    elif mutation == "receipt":
        payload["source_accepted"] = True
    else:
        payload["pairs_m"][0]["reference"][0] = False
    json_file(measurements / "calibration.json", payload)
    measured = replace(
        registration.diagnostic_measurements, original_file_hashes=hashes(measurements)
    )
    result = audit(replace(registration, diagnostic_measurements=measured))
    assert result.diagnostic_status == "INVALID"


def test_future_or_cross_split_previous_observation_does_not_leak_online(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    allocations = list(registration.allocations)
    allocations[0] = replace(allocations[0], previous_sample_id="sample-1")
    result = audit(replace(registration, allocations=allocations))
    assert result.diagnostic_status == "INVALID"


def test_connected_source_observations_cannot_split_across_roles(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    allocations = list(registration.allocations)
    allocations[1] = replace(allocations[1], split="test")
    result = audit(replace(registration, allocations=allocations))
    assert result.diagnostic_status == "INVALID"


def test_supplied_auditor_or_serialized_valid_receipt_is_not_a_registration():
    module = api()
    with pytest.raises(TypeError):
        module.RiskSupervisionAuditor({"source": {"status": "VALID"}})
    with pytest.raises(TypeError):
        module.RiskSupervisionRegistration(module.RiskSupervisionAuditor({}), (), ())


def test_caller_copy_mutation_cannot_change_registered_sources_or_allocations(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    auditor = api().RiskSupervisionAuditor({"source": registration})
    allocations = list(registration.allocations)
    allocations.clear()
    assert auditor.audit("source").counts["allocated_observations"] == 2


def test_original_measurement_change_is_rechecked_on_every_audit(tmp_path: Path):
    registration, _, measurements, _ = registered_fixture(tmp_path)
    auditor = api().RiskSupervisionAuditor({"source": registration})
    assert auditor.audit("source").diagnostic_status == "VALID"
    (measurements / "clock.json").write_text("null\n")
    result = auditor.audit("source")
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == 2


def test_camera_calibration_numeric_boolean_is_not_a_measurement(tmp_path: Path):
    registration, _, measurements, _ = registered_fixture(tmp_path)
    payload = json.loads((measurements / "calibration.json").read_bytes())
    payload["camera_domain"]["camera_to_world"][-1] = True
    json_file(measurements / "calibration.json", payload)
    measured = replace(
        registration.diagnostic_measurements, original_file_hashes=hashes(measurements)
    )
    result = audit(replace(registration, diagnostic_measurements=measured))
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == result.counts["missing_observations"] == 2


def test_point_error_recomputed_from_registered_asset_and_raw_not_online_truth(tmp_path: Path):
    import math

    registration, directory, _, _ = registered_fixture(tmp_path)
    result = audit(registration)
    raw = json.loads((directory / "raw-physics.jsonl").read_text().splitlines()[120])
    local = (0, 0, 0.03505)  # top surface of the independently hash-bound color-v2 cells
    rotation = raw["object_geom_rotation_row_major"]
    truth = tuple(
        raw["object_geom_position_m"][i] + sum(rotation[3 * i + j] * local[j] for j in range(3))
        for i in range(3)
    )
    expected = math.dist((0, 0, 0.5), truth)
    assert result.rows[0]["offline_labels"]["geometric_error_m"] == pytest.approx(expected)
    assert result.rows[0]["offline_labels"]["motion_residual_m_s"] is None
    assert result.counts["motion_labels"] == 0
    assert "point_motion_label_reconstruction_unavailable" in result.reasons


def test_history_inventory_cannot_omit_original_group(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    result = audit(replace(registration, histories=()))
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == 2


def test_nested_results_and_caller_lists_are_isolated(tmp_path: Path):
    module = api()
    registration, _, _, _ = registered_fixture(tmp_path)
    allocations = list(registration.allocations)
    histories = list(registration.histories)
    copied = replace(registration, allocations=allocations, histories=histories)
    auditor = module.RiskSupervisionAuditor({"source": copied})
    allocations.clear()
    histories.clear()
    result = auditor.audit("source")
    assert result.diagnostic_status == "VALID"
    with pytest.raises(TypeError):
        result.rows[0]["offline_labels"]["failure"] = False
    with pytest.raises(TypeError):
        result.counts["allocated_observations"] = 0


def test_concrete_raw_and_initial_registrations_cannot_be_subclass_callbacks(tmp_path: Path):
    from cloud_edge_robot_arm.research.admission import InitialSourceRegistration
    from tests.test_research_admission import _registration

    registration, _, _, _ = registered_fixture(tmp_path)

    class PretendRaw(RiskSourceRegistration):
        pass

    raw = registration.raw_registration
    with pytest.raises(TypeError, match="concrete RAW"):
        replace(
            registration,
            raw_registration=PretendRaw(
                raw.artifact_root,
                raw.source_root,
                raw.current_source_hashes,
                raw.cases,
                raw.criteria,
            ),
        )
    initial_dir = tmp_path / "initial"
    initial_dir.mkdir()
    initial = _registration(initial_dir)

    class PretendInitial(InitialSourceRegistration):
        def audit(self):
            raise AssertionError("caller override must never execute")

    with pytest.raises(TypeError, match="concrete INITIAL"):
        replace(
            registration,
            initial_registration=PretendInitial(
                initial.evidence_root,
                initial.protocol_path,
                initial.current_role_binding,
                initial.current_source_hashes,
            ),
        )


def test_initial_registration_is_reaudited_from_missing_originals_not_metadata(tmp_path: Path):
    from tests.test_research_admission import _registration

    registration, _, _, _ = registered_fixture(tmp_path)
    initial_dir = tmp_path / "initial"
    initial_dir.mkdir()
    result = audit(replace(registration, initial_registration=_registration(initial_dir)))
    assert result.actual_source_status == "UNKNOWN"
    assert "initial:initial_source_missing" in result.reasons
    assert result.counts["allocated_observations"] == 2


@pytest.mark.parametrize("mutation", ["drift", "symlink", "extra"])
def test_current_helpers_and_original_measurement_paths_reject_drift(tmp_path: Path, mutation: str):
    registration, _, measurements, _ = registered_fixture(tmp_path)
    if mutation == "drift":
        raw = registration.raw_registration
        inventory = dict(raw.current_source_hashes)
        inventory["src/cloud_edge_robot_arm/vision/risk/features.py"] = "0" * 64
        registration = replace(
            registration, raw_registration=replace(raw, current_source_hashes=inventory)
        )
    elif mutation == "symlink":
        original = (measurements / "clock.json").read_bytes()
        target = tmp_path / "other-clock.json"
        target.write_bytes(original)
        (measurements / "clock.json").unlink()
        (measurements / "clock.json").symlink_to(target)
    else:
        (measurements / "unregistered.json").write_text("{}\n")
    result = audit(registration)
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == result.counts["missing_observations"] == 2


def test_old_raw_reader_hash_cannot_be_registered(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    raw = registration.raw_registration
    inventory = dict(raw.current_source_hashes)
    inventory["src/cloud_edge_robot_arm/research/risk_sources.py"] = "2" * 64
    with pytest.raises(ValueError, match="fix2"):
        replace(registration, raw_registration=replace(raw, current_source_hashes=inventory))


def test_saved_excluded_real_motion_retains_all_ten_frames_and_actual_unknown():
    from cloud_edge_robot_arm.research.risk_sources import RawCaseRegistration
    from tests.test_research_risk_sources import MOTION

    module = api()
    directory = MOTION / "attempt-1"
    header = json.loads((MOTION / "header.json").read_bytes())
    summary = json.loads((directory / "summary.json").read_bytes())
    case = RawCaseRegistration(
        "actual-excluded-motion",
        "attempt-1",
        "MARKER_MOTION_DEVELOPMENT_RAW_V1",
        hashes(directory),
        header["scene"],
        {
            "episode_id": summary["episode_id"],
            "physics_dt_s": header["config"]["physics_dt_s"],
            "evaluation_start_step": 120,
            "actuator_delay_steps": 0,
            "initial_controller_targets": {
                "joints_rad": [-0.8, 0, 0, 0, 0, 0, 0],
                "fingers_m": [0.039, 0.039],
            },
        },
        {"physics_steps": 4806, "commands": 743, "actions": 9, "frames": 10},
        source_kind="RECORDED_SIMULATION",
        marker_registration=PoseMarkerRegistration(
            7, 0.045, "2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4"
        ),
    )
    inventory = sources()
    inventory.update(
        {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in module.required_supervision_source_paths()
        }
    )
    raw = RiskSourceRegistration(
        MOTION, ROOT, inventory, (case,), CompletionCriteria("object", "target_region")
    )
    metadata = [
        json.loads(path.read_bytes()) for path in (directory / "frames").glob("*/observation.json")
    ]
    metadata.sort(key=lambda item: item["sim_time_s"])
    allocations = tuple(
        module.RiskObservationAllocation(
            f"actual-frame-{i}",
            case.case_id,
            item["observation_id"],
            "train",
            None if i == 0 else f"actual-frame-{i - 1}",
        )
        for i, item in enumerate(metadata)
    )
    registered = module.RiskSupervisionRegistration(
        raw,
        allocations,
        (module.RiskComponentHistory(header["scene"]["group_id"], ("DEVELOPMENT_FEEDBACK",)),),
    )
    result = audit(registered)
    assert result.status == result.actual_source_status == result.diagnostic_status == "UNKNOWN"
    assert result.counts["assigned_attempts"] == 1
    assert (
        result.counts["allocated_observations"]
        == result.counts["task_labels"]
        == len(result.rows)
        == 10
    )
    assert result.counts["feature_rows"] == 0
    assert result.counts["geometric_labels"] == 1
    assert sum(row["offline_labels"]["geometric_error_m"] is None for row in result.rows) == 9
    assert all(row["offline_labels"]["failure"] is False for row in result.rows)
    assert all(row["failure_horizon"]["terminal_step"] == 4806 for row in result.rows)
    assert "raw_v3_clock_publisher_unavailable" in result.reasons
    assert "initial_source_registration_unavailable" in result.reasons
    assert result.source_scope == "RECORDED_RAW_DIAGNOSTICS"


def test_known_development_history_is_not_erased_by_unknown_extra_history(tmp_path: Path):
    registration, _, _, _ = registered_fixture(
        tmp_path, history=("DEVELOPMENT_FEEDBACK", "UNKNOWN"), split="calibration"
    )
    result = audit(registration)
    assert result.diagnostic_status == "INVALID"
    assert result.counts["allocated_observations"] == 2


def test_nested_marker_registration_is_copied_before_caller_mutation(tmp_path: Path):
    registration, _, _, _ = registered_fixture(tmp_path)
    auditor = api().RiskSupervisionAuditor({"source": registration})
    caller_marker = registration.raw_registration.cases[0].marker_registration
    original = caller_marker.marker_size_m
    try:
        object.__setattr__(caller_marker, "marker_size_m", 0.2)
        result = auditor.audit("source")
        assert result.diagnostic_status == "VALID", result.reasons
        assert result.counts["geometric_labels"] == 2
    finally:
        object.__setattr__(caller_marker, "marker_size_m", original)


def test_initial_original_source_references_are_retained_even_when_unavailable(tmp_path: Path):
    from tests.test_research_admission import _registration

    registration, _, _, _ = registered_fixture(tmp_path)
    initial_dir = tmp_path / "initial"
    initial_dir.mkdir()
    result = audit(replace(registration, initial_registration=_registration(initial_dir)))
    assert any(name.startswith("initial/evidence:") for name in result.original_file_hashes)
    assert result.initial_source_status == "UNKNOWN"
    assert result.raw_execution_status == "VALID"
