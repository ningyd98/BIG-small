"""Exercise the new registered teacher release without running a renderer."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
    collect_native_calibration_once,
    digest,
    load_json,
    prepare_native_calibration,
    prepare_registered_collection_protocol_v2,
    read_protocol,
    save_exclusive,
    verify_native_calibration_collection,
)
from cloud_edge_robot_arm.research.native_collection_application import (
    _REGISTRY,
    NativeCollectionApplication,
    _check_protocol_sources,
)
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    read_native_full_horizon_group,
    reconstruct_native_full_horizon_registry,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/native_registered_single_teacher_p0_20261119.yaml"
FIRST = "native-p0-20261119-0001"
SECOND = "native-p0-20261119-0002"
V10_CONFIG = ROOT / "configs/research/native_registered_single_teacher_p0_v10_20261121.yaml"
V10_FIRST = "native-p0-v10-20261121-0001"
V10_SECOND = "native-p0-v10-20261121-0002"


def test_v10_prepared_protocol_reaches_the_single_release_gate(tmp_path, monkeypatch):
    registration = tmp_path / "protocol"
    prepared = prepare_native_calibration(V10_CONFIG, output=registration)
    protocol = read_protocol(registration)
    assert prepared["released_assignments"] == protocol["released_assignments"] == [V10_FIRST]
    assert protocol["schema_version"] == "native.calibration.operational.v10"
    assert protocol["timeout_basis"] == "physics_steps"
    assert protocol["wall_clock_metric"] is True
    assert [a["seed"] for a in protocol["assignments"]] == list(range(11921001, 11921010))
    assert [a["status"] for a in protocol["assignments"]] == ["RELEASED"] + [
        "PREASSIGNED_NOT_RUN"
    ] * 8
    assert protocol["authorized_actual_budget"]["teacher_acquisitions"] == 1
    _check_protocol_sources(protocol)

    output = tmp_path / "run"
    with pytest.raises(ValueError, match="only the first preregistered"):
        NativeCollectionApplication.from_startup(
            registration, assignment_id=V10_SECOND, output=output
        )
    assert not output.exists()

    def prepare_without_worker(app):
        live = _REGISTRY[app]
        try:
            job = app.prepare_once()
            assert job.status == "QUEUED" and job.max_attempts == 1 and job.seed == 11921001
            assert job.manifest_id == protocol["schema_version"]
            assert live.deadline.deadline_ns == live.origin.lower_ns + 1800 * 10**9
            return {"queued": True}
        finally:
            if live.owner is not None:
                live.owner.close()

    monkeypatch.setattr(NativeCollectionApplication, "execute_once", prepare_without_worker)
    assert collect_native_calibration_once(
        registration, assignment_id=V10_FIRST, output=output
    ) == {"queued": True}
    with pytest.raises(RuntimeError, match="already claimed"):
        NativeCollectionApplication.from_startup(
            registration, assignment_id=V10_FIRST, output=tmp_path / "retry"
        )
    assert not (tmp_path / "retry").exists()


@pytest.mark.parametrize(
    "field",
    ["release", "second", "deadline", "terminal", "clock", "metric", "source", "generation"],
)
def test_v10_drift_is_rejected_before_creating_runtime(tmp_path, field):
    registration = tmp_path / "protocol"
    prepare_native_calibration(V10_CONFIG, output=registration)
    protocol = load_json(registration / "protocol.json")
    if field == "release":
        protocol["assignments"][0]["status"] = "PREASSIGNED_NOT_RUN"
    elif field == "second":
        protocol["released_assignments"].append(V10_SECOND)
    elif field in {"deadline", "terminal"}:
        name = "controller_deadline_steps" if field == "deadline" else "terminal_steps"
        protocol["actions"][3]["horizon"][name] += 1
    elif field == "clock":
        protocol["timeout_basis"] = "wall_clock"
    elif field == "metric":
        protocol["wall_clock_metric"] = False
    elif field == "source":
        protocol["source_hashes"]["pyproject.toml"] = "0" * 64
        protocol["source_generation"] = digest(protocol["source_hashes"])
    else:
        protocol["source_generation"] = "0" * 64
    candidate = tmp_path / "drift"
    candidate.mkdir()
    save_exclusive(candidate / "protocol.json", protocol)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="recipe/source"):
        NativeCollectionApplication.from_startup(candidate, assignment_id=V10_FIRST, output=output)
    assert not output.exists()
    assert not (candidate / "claims").exists()


def test_v10_fixed_config_and_live_source_cannot_be_replaced(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research import native_calibration_collection as collection

    config = tmp_path / "copied.yaml"
    config.write_bytes(V10_CONFIG.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="release config bytes"):
        prepare_native_calibration(config, output=tmp_path / "invalid-config")
    assert not (tmp_path / "invalid-config").exists()

    registration = tmp_path / "protocol"
    prepare_native_calibration(V10_CONFIG, output=registration)
    frozen = read_protocol(registration)
    real_inventory = collection.source_inventory

    def drifted_inventory(**kwargs):
        sources = real_inventory(**kwargs)
        sources["src/cloud_edge_robot_arm/research/native_calibration_collection.py"] = "0" * 64
        return sources

    monkeypatch.setattr(collection, "source_inventory", drifted_inventory)
    assert read_protocol(registration, current_sources=False) == frozen
    with pytest.raises(ValueError, match="recipe/source"):
        read_protocol(registration)
    with pytest.raises(ValueError, match="source or recipe"):
        _check_protocol_sources(frozen)


def test_v10_verify_empty_registry_and_refuse_unreleased_group(tmp_path):
    registration = tmp_path / "protocol"
    prepare_native_calibration(V10_CONFIG, output=registration)
    output = tmp_path / "verify"
    result = verify_native_calibration_collection(registration, output=output)
    assert result["assigned_groups"] == 9
    assert result["native_qualification"] == "UNKNOWN" and result["joint_bound_m"] is None
    assert [row["state"] for row in load_json(output / "groups.json")] == ["NOT_RUN"] * 9
    with pytest.raises(ValueError, match="unreleased"):
        read_native_full_horizon_group(
            registration, assignment_id=V10_SECOND, root=tmp_path / "unused"
        )


def test_v9_new_single_release_preserves_v8_recipe(tmp_path):
    v8 = tmp_path / "v8"
    v9 = tmp_path / "v9"
    prepare_registered_collection_protocol_v2(output=v8)
    receipt = prepare_native_calibration(CONFIG, output=v9)
    old, new = read_protocol(v8), read_protocol(v9)
    assert receipt["released_assignments"] == [FIRST]
    assert new["schema_version"] == "native.calibration.operational.v9"
    assert [row["seed"] for row in new["assignments"]] == list(range(11919001, 11919010))
    assert [row["status"] for row in new["assignments"]] == ["RELEASED"] + [
        "PREASSIGNED_NOT_RUN"
    ] * 8
    assert new["release_reference"]["source_generation"] == new["source_generation"]
    assert new["role"]["model_requests"] == 0
    assert new["authorized_actual_budget"]["teacher_acquisitions"] == 1
    for name in ("geometry", "actions", "sampling", "region_policy"):
        assert new[name] == old[name]
    for name in ("ordinary_max_age_ns", "timeout_expected_ms", "max_attempts"):
        assert new["settings"][name] == old["settings"][name]
    assert old["released_assignments"] == []
    assert old["execution_release"] == "PREPARE_ONLY_NOT_RELEASED"


@pytest.mark.parametrize("mutation", ["wrong_group", "wall_limit", "source", "extra_release"])
def test_v9_mutation_refuses_before_creating_runtime(tmp_path, mutation):
    admitted = tmp_path / "protocol"
    prepare_native_calibration(CONFIG, output=admitted)
    protocol = deepcopy(load_json(admitted / "protocol.json"))
    if mutation == "wrong_group":
        protocol["settings"]["released_assignment"] = SECOND
    elif mutation == "wall_limit":
        protocol["settings"]["timeout_expected_ms"][0] += 1
    elif mutation == "source":
        protocol["source_hashes"]["pyproject.toml"] = "0" * 64
    else:
        protocol["released_assignments"].append(SECOND)
    invalid = tmp_path / "changed"
    invalid.mkdir()
    save_exclusive(invalid / "protocol.json", protocol)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="recipe/source"):
        NativeCollectionApplication.from_startup(invalid, assignment_id=FIRST, output=output)
    assert not output.exists()


def test_factory_single_release_and_missing_readout_preserve_unknown(tmp_path):
    registration = tmp_path / "protocol"
    prepare_native_calibration(CONFIG, output=registration)
    rejected = tmp_path / "rejected"
    with pytest.raises(ValueError, match="only the first preregistered"):
        NativeCollectionApplication.from_startup(
            registration, assignment_id=SECOND, output=rejected
        )
    assert not rejected.exists()
    runtime = tmp_path / "runtime"
    app = NativeCollectionApplication.from_startup(
        registration, assignment_id=FIRST, output=runtime
    )
    assert app.output == runtime
    assert (runtime / "runtime.db").is_file()
    report = read_native_full_horizon_group(registration, assignment_id=FIRST, root=runtime)
    assert not report.source_complete and not report.horizon_complete and report.group_score is None
    out = reconstruct_native_full_horizon_registry(registration, roots={FIRST: runtime})
    assert out.assigned_group_count == 9 and out.joint_bound_m is None
    with pytest.raises(ValueError, match="unreleased"):
        read_native_full_horizon_group(registration, assignment_id=SECOND, root=runtime)

    live = _REGISTRY[app]
    try:
        job = app.prepare_once()
        assert job.status == "QUEUED"
        assert job.manifest_id == "native.calibration.operational.v9"
        assert job.seed == 11919001 and job.max_attempts == 1
        assert live.deadline.deadline_ns == live.origin.lower_ns + 1800 * 10**9
        with pytest.raises(RuntimeError, match="claimed"):
            NativeCollectionApplication.from_startup(
                registration, assignment_id=FIRST, output=tmp_path / "retry"
            )
        assert not (tmp_path / "retry").exists()
        reader = tmp_path / "readout"
        result = verify_native_calibration_collection(registration, output=reader)
        assert result["assigned_groups"] == 9 and result["joint_bound_m"] is None
        groups = load_json(reader / "groups.json")
        assert groups[0]["assignment_id"] == FIRST and groups[0]["group_score"] is None
        assert all(row["state"] == "NOT_RUN" for row in groups[1:])
    finally:
        if live.owner is not None:
            live.owner.close()
