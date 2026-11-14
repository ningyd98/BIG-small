"""关节诊断保留单位和逐步证据，不把越界幅度当成不可达证明。"""

import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research import freeze_evidence
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


@pytest.fixture
def observed():
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig())
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=42001))
        yield replace(
            backend.current_physics_observation(),
            joint_positions_rad=(0.0,) * 7,
            joint_velocities_rad_s=(0.0,) * 7,
            joint_ranges_rad=((-2.0, 2.0),) * 7,
            finger_positions_m=(0.02, 0.02),
            finger_ranges_m=((0.0, 0.04),) * 2,
            finger_velocities_m_s=(0.0, 0.0),
        )
    finally:
        backend.shutdown()


def save(observation, output):
    method = getattr(freeze_evidence, "_save_joint_limit_diagnostics", None)
    assert callable(method), "missing independent joint-limit diagnostic writer"
    method(observation, output)


def test_normal_and_tolerance_edge_do_not_create_diagnostic_file(observed, tmp_path):
    save(observed, tmp_path)
    save(replace(observed, finger_positions_m=(0.0401, 0.02)), tmp_path)
    assert not (tmp_path / "joint-limit-diagnostics.json").exists()


def test_finger_violation_records_units_velocity_bounds_and_accumulates(observed, tmp_path):
    first = replace(
        observed,
        physics_step=17,
        finger_positions_m=(0.0405, 0.02),
        finger_velocities_m_s=(0.03, -0.02),
    )
    save(first, tmp_path)
    save(replace(first, physics_step=18), tmp_path)
    data = json.loads((tmp_path / "joint-limit-diagnostics.json").read_text())
    assert data["episode_id"] == observed.episode_id
    assert [row["physics_step"] for row in data["violations"]] == [17, 18]
    row = data["violations"][0]
    assert row["finger_velocities_m_s"] == [0.03, -0.02]
    assert row["joint_positions_rad"] == [0.0] * 7
    assert len(row["violated_joints"]) == 1
    joint = row["violated_joints"][0]
    assert (joint["index"], joint["type"], joint["unit"], joint["bound_type"]) == (
        7,
        "finger",
        "m",
        "upper",
    )
    assert joint["position"] == 0.0405
    assert joint["upper_bound"] == 0.04
    assert joint["violation_magnitude"] == pytest.approx(0.0005)


def test_arm_lower_limit_has_radian_units(observed, tmp_path):
    save(replace(observed, joint_positions_rad=(0.0, 0.0, -2.003, 0.0, 0.0, 0.0, 0.0)), tmp_path)
    joint = json.loads((tmp_path / "joint-limit-diagnostics.json").read_text())["violations"][0][
        "violated_joints"
    ][0]
    assert (joint["index"], joint["type"], joint["unit"], joint["bound_type"]) == (
        2,
        "arm",
        "rad",
        "lower",
    )
    assert joint["violation_magnitude"] == pytest.approx(0.003)


def test_corrupt_or_different_episode_is_not_overwritten(observed, tmp_path):
    bad = replace(observed, finger_positions_m=(0.041, 0.02))
    save(bad, tmp_path)
    path = tmp_path / "joint-limit-diagnostics.json"
    original = path.read_bytes()
    with pytest.raises(ValueError, match="episode|step"):
        save(replace(bad, episode_id="another-episode", physics_step=1), tmp_path)
    assert path.read_bytes() == original


def test_invalid_snapshot_does_not_write_nan_or_partial_evidence(observed, tmp_path):
    with pytest.raises(ValueError):
        save(replace(observed, finger_positions_m=(float("nan"), 0.02)), tmp_path)
    assert not (tmp_path / "joint-limit-diagnostics.json").exists()


def script(name):
    root = Path(freeze_evidence.__file__).resolve().parents[3]
    path = root / "scripts" / (name + ".py")
    assert path.is_file(), f"missing diagnostic script: {name}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_refuses_output_inside_original_evidence(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    module = script("diagnose_joint_limits")
    with pytest.raises(ValueError, match="original|source|overlap"):
        module.validate_output(source, source / "diagnostics")


def test_manifest_uses_recorded_bytes_field_and_rejects_changed_input(tmp_path):
    module = script("diagnose_joint_limits")
    (tmp_path / "rgb.png").write_bytes(b"frame")
    manifest = {
        "files": [{"path": "rgb.png", "bytes": 5, "sha256": hashlib.sha256(b"frame").hexdigest()}]
    }
    (tmp_path / "evidence-manifest.json").write_text(json.dumps(manifest))
    assert "rgb.png" in module.validate_original(tmp_path)
    (tmp_path / "rgb.png").write_bytes(b"other")
    with pytest.raises(ValueError, match="mismatch"):
        module.validate_original(tmp_path)


def test_large_finger_excursion_supports_coverage_not_unreachable_arm():
    module = script("analyze_joint_limit_diagnostics")
    diagnostics, report = sealed_finger_evidence()
    result = module.classify(diagnostics, report)
    assert result["A"] == "SUPPORTED"
    assert result["B"] == "NOT_OBSERVED"
    assert result["C"] == "UNDETERMINED"


def sealed_finger_evidence():
    """独立手写的原件身份、步数与封存散列，供篡改负例使用。"""
    diagnostics = {
        "schema": "joint-limit-diagnostics.v1",
        "source_case": "case-one",
        "episode_id": "new-episode",
        "original_episode_id": "original-episode",
        "violations": [
            {
                "physics_step": 17,
                "online_guard_result": "PASS",
                "violated_joints": [
                    {"type": "finger", "index": 7, "unit": "m", "violation_magnitude": 0.002}
                ],
            }
        ],
    }
    report = {
        "replay_matches_original": True,
        "original_evidence_unchanged": True,
        "case": "case-one",
        "replay_episode_id": "new-episode",
        "original_episode_id": "original-episode",
        "online_guard_coverage": ["arm"],
        "original_flagged_steps": [17],
        "replayed_flagged_steps": [17],
        "diagnostic_file_hash_matches": True,
        "diagnostic_errors": [],
        "diagnostic_content_sha256": hashlib.sha256(
            json.dumps(diagnostics, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
    }
    return diagnostics, report


@pytest.mark.parametrize(
    "damage",
    [
        "old_integrity",
        "wrong_case",
        "wrong_episode",
        "wrong_original_episode",
        "truncated",
        "negative_step",
        "missing_guard",
        "changed_coverage",
        "changed_hash",
        "wrong_file_hash",
        "writer_error",
        "invalid_joint_rows",
        "invalid_joint_unit",
        "missing_guard_coverage",
    ],
)
def test_analyzer_rejects_unbound_or_incomplete_evidence(damage):
    module = script("analyze_joint_limit_diagnostics")
    diagnostics, report = sealed_finger_evidence()
    if damage == "old_integrity":
        report["original_evidence_unchanged"] = False
    elif damage == "wrong_case":
        diagnostics["source_case"] = "other"
    elif damage == "wrong_episode":
        diagnostics["episode_id"] = "other"
    elif damage == "wrong_original_episode":
        diagnostics["original_episode_id"] = "other"
    elif damage == "truncated":
        diagnostics["violations"] = []
    elif damage == "negative_step":
        diagnostics["violations"][0]["physics_step"] = -123
    elif damage == "missing_guard":
        del diagnostics["violations"][0]["online_guard_result"]
    elif damage == "changed_coverage":
        report["original_flagged_steps"] = [17, 18]
    elif damage == "changed_hash":
        report["diagnostic_content_sha256"] = "0" * 64
    elif damage == "wrong_file_hash":
        report["diagnostic_file_hash_matches"] = False
    elif damage == "invalid_joint_rows":
        diagnostics["violations"][0]["violated_joints"] = []
    elif damage == "invalid_joint_unit":
        diagnostics["violations"][0]["violated_joints"][0]["unit"] = "rad"
    elif damage == "missing_guard_coverage":
        report["online_guard_coverage"] = None
    else:
        report["diagnostic_errors"] = [{"error": "writer failed"}]
    # Re-seal edited records except the dedicated hash failure: coverage and
    # identity checks must hold even when a partial file has a valid hash.
    if damage != "changed_hash":
        report["diagnostic_content_sha256"] = hashlib.sha256(
            json.dumps(diagnostics, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    assert module.classify(diagnostics, report) == {
        "A": "UNDETERMINED",
        "B": "UNDETERMINED",
        "C": "UNDETERMINED",
    }


@pytest.mark.parametrize("contents", [None, [], [{}]])
def test_writer_rejects_corrupt_existing_structure(observed, tmp_path, contents):
    path = tmp_path / "joint-limit-diagnostics.json"
    payload = {"schema": "joint-limit-diagnostics.v1", "episode_id": observed.episode_id}
    if contents is not None:
        payload["violations"] = contents
    path.write_text(json.dumps(payload))
    original = path.read_bytes()
    with pytest.raises(ValueError):
        save(replace(observed, finger_positions_m=(0.041, 0.02)), tmp_path)
    assert path.read_bytes() == original


def test_corrupt_final_diagnostic_records_error_without_aborting(tmp_path):
    module = script("diagnose_joint_limits")
    method = getattr(module, "finish_diagnostics", None)
    assert callable(method), "missing nonfatal final diagnostic reader"
    path = tmp_path / "joint-limit-diagnostics.json"
    path.write_text("broken JSON")
    errors = []
    assert method(path, "case", "old-episode", {}, errors) is None
    assert errors and path.read_text() == "broken JSON"


def test_runtime_guard_covers_independent_evaluator(monkeypatch):
    module = script("diagnose_joint_limits")
    method = getattr(module, "verify_runtime", None)
    assert callable(method), "missing pinned runtime verification"
    original = module.sha
    monkeypatch.setattr(
        module,
        "sha",
        lambda path: ("0" * 64 if str(path).endswith("/episode_evaluator.py") else original(path)),
    )
    with pytest.raises(ValueError, match="runtime|changed"):
        method()


def test_nonmatching_replay_does_not_claim_original_root_cause():
    module = script("analyze_joint_limit_diagnostics")
    diagnostics = {
        "violations": [
            {
                "violated_joints": [
                    {"type": "finger", "index": 7, "unit": "m", "violation_magnitude": 0.002}
                ]
            }
        ]
    }
    result = module.classify(
        diagnostics, {"replay_matches_original": False, "online_guard_coverage": ["arm"]}
    )
    assert result == {"A": "UNDETERMINED", "B": "UNDETERMINED", "C": "UNDETERMINED"}
