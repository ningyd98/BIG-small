"""Development-only registration, real worker admission and synchronous cutoff."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
    ROOT,
    load_json,
    prepare_native_calibration,
    read_protocol,
)
from cloud_edge_robot_arm.research.native_collection_application import (
    NativeCollectionApplication,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import ExecutionGuardBoundaryV1


def test_checkpoint_diagnostic_release_has_no_formal_admission(tmp_path):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
        DIAGNOSTIC_ASSIGNMENT,
        DIAGNOSTIC_SEED,
        register_checkpoint_diagnostic,
    )

    root = tmp_path / "development"
    formal = tmp_path / "formal"
    prepare_native_calibration(
        ROOT / "configs/research/native_registered_single_teacher_p0_20261119.yaml",
        output=formal,
    )
    original = (formal / "protocol.json").read_bytes()
    register_checkpoint_diagnostic(root)
    release = load_json(root / "protocol.json")
    assert release["assignment_id"] == DIAGNOSTIC_ASSIGNMENT
    assert release["seed"] == DIAGNOSTIC_SEED
    assert release["scope"] == "CHECKPOINT_EGL_DEVELOPMENT"
    assert release["step_wall_budget_ns"] == 8_000_000_000
    assert release["qualification_credit"] == 0
    with pytest.raises(ValueError, match="protocol required"):
        read_protocol(root)
    with pytest.raises(ValueError):
        NativeCollectionApplication.from_startup(
            root, assignment_id=DIAGNOSTIC_ASSIGNMENT, output=root / "formal-output"
        )
    with pytest.raises(ValueError, match="diagnostic registration"):
        NativeCollectionApplication.from_checkpoint_diagnostic(formal)
    assert not (formal / "diagnostic-claim.json").exists()
    assert (formal / "protocol.json").read_bytes() == original
    assert not (root / "run").exists()


def test_checkpoint_relocated_edited_or_symlink_release_refused(tmp_path):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
        register_checkpoint_diagnostic,
    )

    root = tmp_path / "canonical"
    register_checkpoint_diagnostic(root)
    with pytest.raises((RuntimeError, ValueError)):
        register_checkpoint_diagnostic(root)
    copy = tmp_path / "copy"
    copy.mkdir()
    original = (root / "protocol.json").read_bytes()
    (copy / "protocol.json").write_bytes(original)
    with pytest.raises(ValueError, match="diagnostic registration"):
        NativeCollectionApplication.from_checkpoint_diagnostic(copy)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        NativeCollectionApplication.from_checkpoint_diagnostic(alias)
    edited = json.loads(original)
    edited["recipe"]["source_generation"] = "0" * 64
    (root / "protocol.json").write_text(json.dumps(edited))
    with pytest.raises(ValueError, match="diagnostic registration"):
        NativeCollectionApplication.from_checkpoint_diagnostic(root)
    assert not (root / "diagnostic-claim.json").exists()
    assert not (root / "run").exists()


def test_checkpoint_actual_dispatch_captures_fresh_sqlite_read_and_cannot_resume(
    tmp_path, monkeypatch
):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
        DIAGNOSTIC_ASSIGNMENT,
        DIAGNOSTIC_SCOPE,
        DIAGNOSTIC_SEED,
        register_checkpoint_diagnostic,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    root = tmp_path / "development"
    register_checkpoint_diagnostic(root)
    monkeypatch.setenv("MUJOCO_GL", "egl")
    monkeypatch.chdir(ROOT)
    app = NativeCollectionApplication.from_checkpoint_diagnostic(root)
    assert type(app.worker) is SimulationWorker
    job = app.prepare_once()
    assert job.seed == DIAGNOSTIC_SEED
    assert job.max_attempts == 1
    assert job.manifest_id == "native.checkpoint-egl.development.v1"
    assert load_json(root / "diagnostic-claim.json")["assignment_id"] == DIAGNOSTIC_ASSIGNMENT
    assert not (root / "claims").exists()
    with pytest.raises(RuntimeError, match="actual running worker"):
        app.check_active()
    with pytest.raises(RuntimeError, match="already claimed"):
        NativeCollectionApplication.from_checkpoint_diagnostic(root)

    def stop_after_first_sql_checkpoint(path):
        if Path(path) == root / "run":
            return type("Disk", (), {"free": 0})()
        return disk_usage(path)

    # Exercise actual worker dispatch, then the native disk preflight veto. No EGL object yet.
    from cloud_edge_robot_arm.research import native_collection_application

    disk_usage = native_collection_application.shutil.disk_usage
    monkeypatch.setattr(
        native_collection_application.shutil, "disk_usage", stop_after_first_sql_checkpoint
    )
    with pytest.raises(RuntimeError, match="worker terminal outcome"):
        app.execute_once()
    result = load_json(root / "run/collection-result.json")
    sql = result["checkpoint_diagnostic"]["sqlite"]
    assert result["qualification_credit"] == 0
    assert result["scope"] == DIAGNOSTIC_SCOPE
    assert result["checkpoint_diagnostic"]["status"] == "EARLY_STOP"
    assert result["worker_snapshot"]["job"]["status"] == "BLOCKED_BY_ENV"
    assert "32GiB" in result["failures"][0]["error"]
    assert len(result["worker_snapshot"]["attempts"]) == 1
    assert result["owner_closure"]["completed"]
    assert sql["mode"] == "UTC_LEGACY_VETO"
    assert sql["reads_attempted"] == sql["reads_completed"] == 1
    assert sql["readonly_snapshots"] == 1
    assert sql["read_wall_ns"] > 0
    assert sql["action_reads_attempted"] == 0


def test_checkpoint_deadline_is_exclusive_and_records_unobserved_tail():
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
        _CheckpointDiagnostic,
        _CheckpointDiagnosticDeadline,
    )

    state = _CheckpointDiagnostic(registration_sha256="a" * 64)
    start = 10_000_000_000
    end = start + 8_000_000_000
    step = ExecutionGuardBoundaryV1("PHYSICS", "BEFORE", "episode", 120, 70)
    later = ExecutionGuardBoundaryV1("PHYSICS", "BEFORE", "episode", 121, 71)
    state.authorize(step, start - 1)
    state.start_action(start, 120)
    state.authorize(step, end - 1)
    with pytest.raises(_CheckpointDiagnosticDeadline, match="8-second"):
        state.authorize(later, end)
    assert state.last_authorized_monotonic_ns == end - 1
    assert state.last_authorized_checkpoint == asdict(step)
    assert state.cutoff_observed_monotonic_ns == end
    assert state.rejected_checkpoint == asdict(later)
    with pytest.raises(RuntimeError, match="once"):
        state.start_action(end, 121)


def test_real_backend_cutoff_leaves_no_physics_authorized():
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
        _CheckpointDiagnostic,
        _CheckpointDiagnosticDeadline,
    )
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(domain_randomization=False))
    state = _CheckpointDiagnostic(registration_sha256="b" * 64)
    start = 10_000_000_000
    state.start_action(start, 0)

    def cutoff_at_physics_start(boundary):
        assert state.cutoff_monotonic_ns is not None
        now = state.cutoff_monotonic_ns
        if (boundary.kind, boundary.phase) != ("PHYSICS", "BEFORE"):
            now -= 1
        state.authorize(boundary, now)

    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=11920067))
        with pytest.raises(_CheckpointDiagnosticDeadline):
            with backend.enforce_execution_guard(cutoff_at_physics_start):
                backend.step(1)
        assert backend.estop_engaged
        assert backend.total_physics_steps == 0
        events = backend.execution_guard_events
        assert any(
            row.get("kind") == "PHYSICS"
            and row.get("phase") == "BEFORE"
            and row.get("outcome") == "REJECTED"
            for row in events
        )
        assert events[-1]["error_type"] == "_CheckpointDiagnosticDeadline"
    finally:
        backend.shutdown()


@pytest.fixture
def cutoff_receipt():
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import (
        DIAGNOSTIC_ASSIGNMENT,
        DIAGNOSTIC_SCOPE,
    )

    return dict(
        status="COLLECTION_PARTIAL",
        assignment_id=DIAGNOSTIC_ASSIGNMENT,
        scope=DIAGNOSTIC_SCOPE,
        qualification_credit=0,
        final_lifecycle_receipt=True,
        execution_admitted=False,
        teacher_collection_admitted=False,
        native_qualification="UNKNOWN",
        checkpoint_diagnostic=dict(
            scope=DIAGNOSTIC_SCOPE,
            status="CUTOFF",
            qualification_credit=0,
            registration_sha256="a" * 64,
        ),
        failures=[
            dict(
                phase="collection_body",
                role="PRIMARY",
                error_type="_CheckpointDiagnosticDeadline",
                error=(
                    "_CheckpointDiagnosticDeadline: "
                    "8-second development first-action deadline reached"
                ),
            )
        ],
        worker_snapshot={"job": {"status": "BLOCKED_BY_ENV"}, "attempts": [], "events": []},
        owner_closure={"completed": True},
    )


def test_read_cutoff_result_retains_original_mapping(tmp_path, cutoff_receipt):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import _read_cutoff_result

    path = tmp_path / "collection-result.json"
    path.write_text(json.dumps(cutoff_receipt))
    assert _read_cutoff_result(path, registration_sha256="a" * 64) == cutoff_receipt


@pytest.mark.parametrize(
    "raw", [None, "0", "[]", "null", "{}", "{bad JSON", '{"status":1,"status":2}']
)
def test_read_cutoff_result_rejects_missing_scalar_and_bad_json(tmp_path, raw):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import _read_cutoff_result

    path = tmp_path / "collection-result.json"
    if raw is not None:
        path.write_text(raw)
    assert _read_cutoff_result(path, registration_sha256="a" * 64) is None


@pytest.mark.parametrize(
    ("section", "name", "value"),
    [
        (None, "assignment_id", "wrong-assignment"),
        (None, "status", "COLLECTION_COMPLETE_WITH_UNRESOLVED_EFFECTS"),
        (None, "scope", "TEACHER_COLLECTION"),
        (None, "qualification_credit", False),
        (None, "qualification_credit", 1),
        (None, "final_lifecycle_receipt", False),
        (None, "execution_admitted", True),
        (None, "teacher_collection_admitted", True),
        (None, "native_qualification", "QUALIFIED"),
        (None, "checkpoint_diagnostic", []),
        (None, "failures", []),
        (None, "failures", [None]),
        ("checkpoint_diagnostic", "status", "EARLY_STOP"),
        ("checkpoint_diagnostic", "scope", "TEACHER_COLLECTION"),
        ("checkpoint_diagnostic", "qualification_credit", False),
        ("checkpoint_diagnostic", "qualification_credit", 1),
        ("checkpoint_diagnostic", "registration_sha256", "b" * 64),
    ],
)
def test_read_cutoff_result_rejects_wrong_identity_or_state(
    tmp_path, cutoff_receipt, section, name, value
):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import _read_cutoff_result

    receipt = cutoff_receipt if section is None else cutoff_receipt[section]
    receipt[name] = value
    path = tmp_path / "collection-result.json"
    path.write_text(json.dumps(cutoff_receipt))
    assert _read_cutoff_result(path, registration_sha256="a" * 64) is None


@pytest.mark.parametrize(
    ("name", "value"),
    [("role", "SECONDARY"), ("phase", "preflight"), ("error", "unrelated deadline")],
)
def test_read_cutoff_result_rejects_nonprimary_or_unrelated_cutoff(
    tmp_path, cutoff_receipt, name, value
):
    from cloud_edge_robot_arm.research.native_checkpoint_diagnostic import _read_cutoff_result

    cutoff_receipt["failures"][0][name] = value
    path = tmp_path / "collection-result.json"
    path.write_text(json.dumps(cutoff_receipt))
    assert _read_cutoff_result(path, registration_sha256="a" * 64) is None


@pytest.mark.parametrize(
    "case", ["bound-cutoff", "unrelated", "different-worker", "malformed-receipt"]
)
def test_checkpoint_runtime_readback_preserves_unrelated_exception(
    tmp_path, monkeypatch, cutoff_receipt, case
):
    from cloud_edge_robot_arm.research import native_checkpoint_diagnostic as diagnostic
    from cloud_edge_robot_arm.research.native_calibration_collection import digest

    release = {"recipe": {"source_hashes": {}}}
    cutoff_receipt["checkpoint_diagnostic"]["registration_sha256"] = digest(release)
    path = tmp_path / "collection-result.json"
    path.write_text("{bad JSON" if case == "malformed-receipt" else json.dumps(cutoff_receipt))
    snapshot = cutoff_receipt["worker_snapshot"]
    failure = RuntimeError("worker terminal outcome: " + json.dumps(snapshot, ensure_ascii=False))
    if case == "unrelated":
        failure = RuntimeError("lease expired")
    if case == "different-worker":
        failure = RuntimeError('worker terminal outcome: {"job":{"status":"TIMED_OUT"}}')

    class FailingApplication:
        output = tmp_path

        def execute_once(self):
            raise failure

    monkeypatch.setattr(diagnostic, "_read_registration", lambda _: release)
    monkeypatch.setattr(diagnostic, "_import_sources", lambda _: {})
    monkeypatch.setattr(
        NativeCollectionApplication,
        "from_checkpoint_diagnostic",
        lambda _: FailingApplication(),
    )
    if case == "bound-cutoff":
        assert diagnostic.run_checkpoint_diagnostic(tmp_path) == cutoff_receipt
    else:
        with pytest.raises(RuntimeError) as caught:
            diagnostic.run_checkpoint_diagnostic(tmp_path)
        assert caught.value is failure
    assert load_json(tmp_path / "imported-source-manifest.json")["registration_sha256"] == digest(
        release
    )
