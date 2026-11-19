"""Exercise the new registered teacher release without running a renderer."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
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
)
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    read_native_full_horizon_group,
    reconstruct_native_full_horizon_registry,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/native_registered_single_teacher_p0_20261119.yaml"
FIRST = "native-p0-20261119-0001"
SECOND = "native-p0-20261119-0002"


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
