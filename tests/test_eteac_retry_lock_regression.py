"""Bounded real-repository liveness and native MOCK queue regression."""
from __future__ import annotations

import faulthandler
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
ORIGINAL_AUDIT = ROUNDS / "round396-eteac-noncompletion-diagnosis-20261102/input-audit.json"


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def _run_child(case, backend, tmp_path, cap=8):
    evidence = Path(os.environ.get("R399_EVIDENCE_DIR", str(tmp_path)))
    prefix = evidence / f"child-{case}-{backend}"
    argv = [sys.executable, "-B", "-u", str(Path(__file__).resolve()),
            "--child", case, backend, str(tmp_path)]
    process = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    started = time.monotonic()
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate(timeout=2)
    prefix.with_suffix(".stdout").write_bytes(stdout)
    prefix.with_suffix(".stderr").write_bytes(stderr)
    _save(prefix.with_suffix(".json"), {
        "argv": argv, "returncode": process.returncode, "timed_out": timed_out,
        "reaped": process.returncode is not None, "elapsed_s": time.monotonic() - started,
    })
    assert not timed_out, (
        "real repository call did not return; bounded child killed and reaped\n"
        + stdout.decode(errors="replace") + stderr.decode(errors="replace")
    )
    assert process.returncode == 0, (
        stdout.decode(errors="replace") + stderr.decode(errors="replace")
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_retry_initializer_returns_without_reentrant_lock(tmp_path, backend):
    """A decorated reader inside the initializer must not prevent its return."""
    _run_child("retry", backend, tmp_path)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_recovery_initialization_and_conflict_reads_return(tmp_path, backend):
    """Verification/recovery reads retain idempotency and reject stale CAS."""
    _run_child("recovery", backend, tmp_path)


def test_native_eteac_then_queued_pcsc(tmp_path):
    """A real ETEAC poll returns so its already queued successor can run."""
    _run_child("native", "sqlite", tmp_path, cap=75)


def _repository(backend, directory):
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import (
        SQLiteEventAutonomyRepository,
    )

    return (SQLiteEventAutonomyRepository(directory / "events.sqlite") if backend == "sqlite"
            else InMemoryEventAutonomyRepository())


def _retry_case(repo):
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget

    now = datetime.now(UTC)
    original = RecoveryBudget(
        budget_id="original", task_id="task", per_step_retry_limit=3,
        per_skill_retry_limit=5, task_total_retry_limit=8,
        retry_count_used=2, task_retry_count=2, step_retry_counts={"step": 2},
        skill_retry_counts={"GRASP": 2}, event_retry_counts={"old": 1},
        remaining_retries=1, retry_deadline=now + timedelta(seconds=60),
        created_at=now, updated_at=now,
    )
    print("READY; ENTER initialize_retry_budget_if_absent", flush=True)
    saved = repo.initialize_retry_budget_if_absent(original)
    assert saved == original
    replacement = original.model_copy(update={"remaining_retries": 99, "retry_count_used": 0})
    assert repo.initialize_retry_budget_if_absent(replacement) == original
    saved.step_retry_counts.clear()
    assert repo.get_retry_budget("task").step_retry_counts == {"step": 2}
    consumed, budget = repo.consume_retry_if_available("task", "step", "GRASP", 2, "new")
    assert consumed and budget.retry_count_used == 3 and budget.remaining_retries == 0
    assert not repo.consume_retry_if_available("task", "step", "GRASP", 2, "new")[0]
    assert not repo.consume_retry_if_available("task", "step", "GRASP", 3, "new")[0]
    assert repo.get_retry_budget("task").event_retry_counts == {"old": 1, "new": 1}


def _recovery_case(repo):
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryTransitionEvidence
    from tests.test_recovery_lifecycle_module import detected_record

    print("READY; ENTER actual recovery fixture and repository", flush=True)
    proposed = detected_record(repo)
    saved = repo.initialize_recovery_if_absent(proposed)
    assert repo.initialize_recovery_if_absent(proposed) == saved
    assert repo.list_recoveries("task") == [saved]
    assert repo.list_unresolved_recoveries("task") == [saved]
    assert repo.get_event("event-1").task_id == "task"
    pool = repo.get_verification_budget("task")
    assert repo.advance_recovery_if_current(
        saved, expected_state="DETECTED", expected_revision=saved.revision + 1,
        expected_budget_revision=pool.revision,
        verified_transition=RecoveryTransitionEvidence("DETECTED"),
    ) is None
    assert repo.reserve_reobservation_if_current(
        recovery_id=saved.recovery_id, expected_revision=saved.revision + 1,
        expected_budget_revision=pool.revision,
    ) is None
    assert repo.get_recovery(saved.recovery_id) == saved


def _native_case(directory):
    from cloud_edge_robot_arm.experiments.models import ExperimentResult
    from cloud_edge_robot_arm.experiments.runner import git_sha
    from cloud_edge_robot_arm.real_robot.provenance import current_source_tree_hash
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
    from cloud_edge_robot_arm.simulation_workbench.models import (
        ExperimentDraft,
        ExperimentManifest,
        SimulationRunType,
    )
    from tests.test_phase11_1_simulation_runtime import _sqlite_fd_targets

    assert hashlib.sha256(ORIGINAL_AUDIT.read_bytes()).hexdigest() == (
        "2bc88e98cb417e566380f49b24f1c8eb64790a253d2df83e5addb8ce8bf050b1"
    )
    original = json.loads(ORIGINAL_AUDIT.read_text())
    source_commit = git_sha()
    listing = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT
    )
    assert listing and source_commit != "UNKNOWN" and len(source_commit) == 40
    source_tree_hash = current_source_tree_hash()
    source_paths = [p["path"] for p in original["source_pins"]] + [
        str(Path(__file__).relative_to(ROOT))
    ]
    pins = [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
            for name in source_paths]
    pinset_hash = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()
    provenance = {
        "scope": "DEVELOPMENT_ONLY_NATIVE_MOCK", "git_head_before_fix_commit": source_commit,
        "patched_worktree": True, "source_tree_hash": source_tree_hash,
        "actual_source_pinset_sha256": pinset_hash, "source_pins": pins,
        "original_request_sha256": original["frozen_input"]["request_sha256"],
    }
    artifacts = directory / "artifacts"
    repository = SQLiteSimulationJobRepository(
        directory / "runtime.sqlite", artifact_root=artifacts
    )
    worker = SimulationWorker(worker_id="r399-native-mock", backend="MOCK",
                              repository=repository, artifact_root=artifacts)
    jobs = []
    manifests = []
    for mode in ("ETEAC", "PCSC"):
        base = ExperimentDraft.model_validate(original["frozen_input"]["request"])
        draft = base.model_copy(update={"run_type": SimulationRunType.SINGLE,
            "control_modes": [mode], "scenarios": ["S01_NORMAL_STATIC"], "seeds": [0],
            "repetitions": 1}, deep=True)
        normalized = draft.model_dump(mode="json")
        reproducibility = hashlib.sha256(json.dumps({"draft": normalized,
            "source_commit": source_commit, "source_tree_hash": source_tree_hash,
            "source_pinset_sha256": pinset_hash}, sort_keys=True).encode()).hexdigest()
        manifest = ExperimentManifest(
            manifest_id="r399-" + mode.lower(), normalized_config=normalized,
            source_commit=source_commit, source_tree_hash=source_tree_hash,
            run_count=1, reproducibility_hash=reproducibility).model_dump(mode="json")
        manifest["development_provenance"] = provenance
        run_id = "r399-native-" + mode.lower()
        job = repository.create_job(run_id=run_id, batch_id="r399-native-pair", backend="MOCK",
            scenario_id="S01_NORMAL_STATIC", control_mode=mode, seed=0,
            manifest_id=manifest["manifest_id"], reproducibility_hash=reproducibility,
            draft=normalized,
            timeout_seconds=30, max_attempts=2, artifact_root=run_id,
            source_commit=source_commit, source_tree_hash=source_tree_hash,
            manifest=manifest, provenance=provenance)
        assert repository.update_status_cas(job.job_id, expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED, reason_code="r399_native_queue",
            worker_id="", lease_id="") is not None
        jobs.append(job)
        manifests.append(manifest)
    assert jobs[0].created_at < jobs[1].created_at
    evidence_path = (
        Path(os.environ.get("R399_EVIDENCE_DIR", str(directory))) / "native-queue-receipt.json"
    )
    receipt = {"provenance": provenance, "manifests": manifests,
               "queue_order": [job.run_id for job in jobs], "runs": [],
               "browser_retest": False, "physical_or_formal_acceptance": False}
    _save(evidence_path, receipt)
    for index, job in enumerate(jobs):
        print("ENTER native poll " + job.run_id, flush=True)
        began = time.monotonic()
        faulthandler.dump_traceback_later(30, exit=True)
        try:
            consumed = worker.poll_once()
        finally:
            faulthandler.cancel_dump_traceback_later()
        duration = time.monotonic() - began
        current = repository.get_job(job.job_id)
        attempts = repository.list_attempts(job.run_id)
        leases = repository.list_leases(job.run_id)
        result_path = artifacts / current.artifact_paths["result"]
        experiment = ExperimentResult.model_validate_json(result_path.read_text())
        heartbeat = [t.name for t in threading.enumerate() if t.name == "simulation-lease"]
        handles = _sqlite_fd_targets(artifacts / job.artifact_root)
        snapshot = {"job": asdict(current), "attempts": [asdict(a) for a in attempts],
            "leases": [asdict(lease) for lease in leases], "elapsed_s": duration,
            "consumed": consumed, "heartbeat_threads_after": heartbeat,
            "run_sqlite_fds_after": handles,
            "result": experiment.model_dump(mode="json"),
            "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest()}
        receipt["runs"].append(snapshot)
        if index == 0:
            successor = repository.get_job(jobs[1].job_id)
            receipt["sentinel_after_eteac"] = asdict(successor)
        _save(evidence_path, receipt)
        assert consumed and duration < 30 and current.status == RuntimeJobStatus.SUCCEEDED
        assert current.attempt == 1 and current.completed_at is not None
        assert experiment.task_success and experiment.experiment_id == job.run_id
        assert (
            experiment.mode.value == job.control_mode and experiment.scenario_id == job.scenario_id
        )
        assert len(attempts) == 1 and attempts[0].ended_at is not None
        assert attempts[0].result == "SUCCEEDED"
        assert len(leases) == 1 and leases[0].released_at is not None
        assert not heartbeat and not handles and not worker.active_job_id
        if index == 0:
            assert successor.status == RuntimeJobStatus.QUEUED and successor.attempt == 0
    receipt["accepted_native_mock"] = True
    _save(evidence_path, receipt)


if __name__ == "__main__":
    assert len(sys.argv) == 5 and sys.argv[1] == "--child"
    case, backend, directory = sys.argv[2], sys.argv[3], Path(sys.argv[4])
    # The final directory argument is separate from the command selector/backend.
    faulthandler.enable()
    if case == "native":
        _native_case(directory)
    else:
        repository = _repository(backend, directory)
        faulthandler.dump_traceback_later(2)
        try:
            (_retry_case if case == "retry" else _recovery_case)(repository)
        finally:
            faulthandler.cancel_dump_traceback_later()
            if backend == "sqlite":
                repository.close()
