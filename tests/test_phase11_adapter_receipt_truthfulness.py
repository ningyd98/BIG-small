"""回执声明必须受真实内层结果约束；软件验证不授予研究资格。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.final_evaluation.adapters import simulation_runtime as adapter
from cloud_edge_robot_arm.final_evaluation.adapters.base import Phase12RunContext
from cloud_edge_robot_arm.final_evaluation.models import (
    BlockerStage,
    MetricSource,
    Phase12Backend,
    Phase12Profile,
    Phase12RunManifest,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.final_evaluation.runner import (
    _authoritative_for_thesis,
    _result_from_adapter,
)
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus, SimulationJobLease


def _context(tmp_path):
    return Phase12RunContext(
        run_id="r419-receipt-proof",
        experiment_id="F20_STRESS_AND_RECOVERY",
        scenario_id="S15_SQLITE_RESTART_DURING_RUN",
        backend=Phase12Backend.MOCK,
        control_mode="PCSC",
        seed=0,
        repetition=0,
        output_root=tmp_path / "output",
    )


def _probes():
    """手写完整汇总边界输入，不替代原生集成对照。"""
    main = {
        "job_id": "main-job",
        "run_id": "sample-runtime",
        "status": "SUCCEEDED",
        "worker_consumed": True,
        "attempt_count": 1,
        "event_count": 8,
        "metric_count": 2,
        "lease_count": 1,
        "released_lease_count": 1,
        "heartbeat_observed": True,
        "terminal_artifacts_present": True,
        "evidence_consistency_present": True,
        "evidence_consistency_hash": "a" * 64,
        "artifact_paths": {"result": "main/result.json"},
    }
    recovery = {
        "job_id": "recovery-job",
        "run_id": "sample-recovery",
        "final_status": "SUCCEEDED",
        "lease_expired": True,
        "recovered_jobs": ["recovery-job"],
        "worker_consumed_after_recovery": True,
        "attempt_count": 2,
        "transitions": [
            ["RUNNING", "INTERRUPTED"],
            ["INTERRUPTED", "RECOVERY_PENDING"],
            ["RECOVERY_PENDING", "QUEUED"],
            ["FINALIZING", "SUCCEEDED"],
        ],
    }
    duplicate = {
        "job_id": "duplicate-job",
        "run_id": "sample-duplicate",
        "final_status": "SUCCEEDED",
        "competing_worker_ids": ["worker-a", "worker-b"],
        "lease_winner": "worker-a",
        "lease_loser": "worker-b",
        "worker_a_consumed": True,
        "worker_b_consumed": False,
        "runner_invocation_count": 1,
        "attempt_count": 1,
        "lease_count": 1,
    }
    values = {"main": main, "recovery": recovery, "duplicate": duplicate}
    for item in values.values():
        item["execution_evidence"] = {
            "job_id": item["job_id"],
            "run_id": item["run_id"],
            "attempt": item["attempt_count"],
            "status": "SUCCEEDED",
            "evidence_valid": True,
            "evidence_errors": [],
            "executor_invoked": True,
            "executor_returned": True,
            "task_success": True,
            "attempt_completed": True,
            "lease_released": True,
            "artifacts_verified": True,
            "input_mode": "LEGACY_PIPELINE",
            "execution_scope": "VISUAL_PLANNING",
            "publication_required": False,
            "publication_status": "NOT_APPLICABLE",
            "publication_confirmed": False,
            "failure_type": "",
        }
    return values


def _projection(monkeypatch, tmp_path, probes):
    """只隔离汇总边界；原生测试另走完整 Worker/SQLite 路径。"""
    monkeypatch.setattr(adapter, "_run_completed_job", lambda *_: probes["main"])
    monkeypatch.setattr(adapter, "_run_recovery_job", lambda *_: probes["recovery"])
    monkeypatch.setattr(adapter, "_run_duplicate_competition_job", lambda *_: probes["duplicate"])
    monkeypatch.setattr(
        adapter, "_sqlite_summary", lambda *_a, **_k: {"exists": True, "tables": {}}
    )
    return adapter.Phase11RuntimeAdapter().run(_context(tmp_path))


def test_job_succeeded_with_failed_task_is_not_task_success(monkeypatch, tmp_path):
    """防止把SQL成功或完整执行等同于任务达成。"""
    probes = _probes()
    probes["main"]["execution_evidence"]["task_success"] = False
    original = copy.deepcopy(probes)
    result = _projection(monkeypatch, tmp_path, probes)
    assert result.task_success is False
    assert result.status == Phase12RunStatus.FAILED
    assert result.runtime_completed is True
    assert result.authoritative_for_thesis is False
    assert probes == original


@pytest.mark.parametrize("blocked", [True, False])
def test_proxy_metrics_are_not_measured_or_authoritative(monkeypatch, tmp_path, blocked):
    """成功率依据执行事实，未测时长及质量占位不冒充实测或论文样本。"""
    probes = _probes()
    if blocked:
        for name, probe in probes.items():
            probe["status" if name == "main" else "final_status"] = "BLOCKED_BY_ENV"
            probe["execution_evidence"].update(
                status="BLOCKED_BY_ENV",
                task_success=False,
                executor_invoked=False,
                executor_returned=False,
            )
        probes["duplicate"]["runner_invocation_count"] = 0
    result = _projection(monkeypatch, tmp_path, probes)
    assert result.metrics["task_completion_rate"] == (0.0 if blocked else 1.0)
    assert result.metrics["planner_success"] is False
    assert result.metrics["valid_contract_rate"] == 0.0
    for name in (
        "total_completion_time_ms",
        "edge_execution_time_ms",
        "local_recovery_time_ms",
        "cloud_planning_time_ms",
        "communication_wait_time_ms",
        "response_latency_ms",
        "planner_success",
        "valid_contract_rate",
        "communication_count",
    ):
        assert result.metrics[name] == 0
        assert result.metric_provenance[name].source == MetricSource.NOT_AVAILABLE
    assert result.authoritative_for_thesis is False
    assert set(result.metrics) == set(result.metric_provenance)


def test_actual_consumer_preserves_adapter_metric_quarantine(monkeypatch, tmp_path):
    """干净manifest与有效source hash不能解除adapter自身指标资格隔离。"""
    result = _projection(monkeypatch, tmp_path, _probes())
    context = _context(tmp_path)
    manifest = Phase12RunManifest(
        run_id=context.run_id,
        experiment_id=context.experiment_id,
        research_question="RQ1",
        profile=Phase12Profile.VALIDATION,
        backend=context.backend,
        scenario_id=context.scenario_id,
        control_mode=context.control_mode,
        seed=context.seed,
        repetition=context.repetition,
        source_commit="consumer-boundary-fixture",
        source_tree_hash="fixture-tree",
        worktree_clean=True,
        config_hash="config",
        environment_hash="environment",
        planner_provider="NONE",
        model_name="",
    )
    assert result.runtime_completed is True and result.task_success is True
    assert _authoritative_for_thesis(manifest, result, output_root=context.output_root) is False
    row = _result_from_adapter(manifest, result)
    assert row.authoritative_for_thesis is False
    assert row.runtime_completed is True and row.task_success is True
    receipt = json.loads((context.output_root / result.source_artifact_path).read_text())
    assert (
        hashlib.sha256((context.output_root / result.source_artifact_path).read_bytes()).hexdigest()
        == result.source_artifact_hash
    )
    assert receipt["research_qualification"]["authoritative_for_thesis"] is False
    assert receipt["research_qualification"]["reason"] == "UNQUALIFIED_TIMING_AND_QUALITY_METRICS"


@pytest.mark.parametrize(
    "reason",
    [
        "missing_result",
        "wrong_run",
        "wrong_hash",
        "wrong_attempt",
        "empty_artifacts",
        "unfinished_attempt",
        "unconfirmed_publication",
    ],
)
def test_missing_mismatched_or_unconfirmed_receipt_fails_closed(monkeypatch, tmp_path, reason):
    """缺件、身份/hash错误及未确认发布都不能获得成功声明。"""
    probes = _probes()
    evidence = probes["main"]["execution_evidence"]
    if reason == "unfinished_attempt":
        evidence["attempt_completed"] = False
    elif reason == "unconfirmed_publication":
        evidence.update(publication_required=True, publication_status="UNCONFIRMED")
    else:
        evidence.update(evidence_valid=False, evidence_errors=[reason])
    result = _projection(monkeypatch, tmp_path, probes)
    assert result.status == Phase12RunStatus.FAILED
    assert result.blocker_stage == BlockerStage.FINALIZATION
    assert result.task_success is False and result.runtime_completed is False
    assert result.authoritative_for_thesis is False
    assert result.failure_type


@pytest.mark.parametrize("role", ["main", "recovery", "duplicate"])
@pytest.mark.parametrize(
    "state,want,completed",
    [
        ("BLOCKED_BY_ENV", Phase12RunStatus.BLOCKED_BY_ENV, False),
        ("TIMED_OUT", Phase12RunStatus.TIMEOUT, False),
        ("FAILED", Phase12RunStatus.FAILED, True),
    ],
)
def test_each_required_probe_can_veto_outer_success(
    monkeypatch, tmp_path, role, state, want, completed
):
    """任一必需probe都能否决成功；执行完成与任务结果分别判断。"""
    probes = _probes()
    probe = probes[role]
    probe["status" if role == "main" else "final_status"] = state
    probe["execution_evidence"].update(
        status=state,
        task_success=False,
        failure_type=role + "_" + state,
        executor_invoked=completed,
        executor_returned=completed,
    )
    result = _projection(monkeypatch, tmp_path, probes)
    assert result.status == want
    assert result.task_success is False
    assert result.runtime_completed is completed
    receipt = json.loads((_context(tmp_path).output_root / result.source_artifact_path).read_text())
    key = {
        "main": "main_job",
        "recovery": "recovery_evidence",
        "duplicate": "duplicate_competition_evidence",
    }[role]
    assert receipt[key]["execution_evidence"]["failure_type"] == role + "_" + state


def _unreleased_lease_count(database, *, connect=sqlite3.connect):
    """观测器只关闭自己为查询打开的连接。"""
    conn = connect(database)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM simulation_job_leases "
            "WHERE released_at = '' OR released_at IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()


def _run_sqlite_fds(output_root):
    """按实际路径边界记录本run DB/WAL/SHM的FD身份。"""
    fds = []
    for path in Path("/proc/self/fd").iterdir():
        try:
            target = path.readlink()
            actual = Path(str(target).removesuffix(" (deleted)"))
            actual.relative_to(output_root.resolve())
            if not actual.name.endswith((".sqlite3", ".sqlite", ".db", "-wal", "-shm")):
                continue
            metadata = path.stat()
        except (OSError, ValueError):
            continue
        fds.append(
            {
                "fd": int(path.name),
                "target": str(target),
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
            }
        )
    return fds


def _native_audit(context, result, label):
    """分开保存产品返回时及观测器关闭后的真实资源状态。"""
    receipt = json.loads((context.output_root / result.source_artifact_path).read_text())
    database = context.output_root / receipt["sqlite_evidence"]["relative_path"]
    before = _run_sqlite_fds(context.output_root)
    unreleased = _unreleased_lease_count(database)
    after = _run_sqlite_fds(context.output_root)
    threads = [
        thread.name for thread in threading.enumerate() if "heartbeat" in thread.name.lower()
    ]
    audit = {
        "label": label,
        "outer_status": result.status.value,
        "runtime_invoked": result.runtime_invoked,
        "runtime_completed": result.runtime_completed,
        "task_success": result.task_success,
        "authoritative": result.authoritative_for_thesis,
        "unreleased_leases": unreleased,
        "run_sqlite_fds": [row["target"] for row in after],
        "before_observer": before,
        "after_observer_close": after,
        "heartbeat_threads": threads,
        "receipt_path": str(context.output_root / result.source_artifact_path),
        "main_status": receipt["main_job"]["status"],
        "recovery_status": receipt["recovery_evidence"]["final_status"],
        "duplicate_status": receipt["duplicate_competition_evidence"]["final_status"],
    }
    directory = Path(os.environ.get("R419_EVIDENCE_DIR", context.output_root))
    with (directory / ("native-" + label + "-audit.json")).open("x") as stream:
        json.dump(audit, stream, indent=2)
        stream.write("\n")
    return receipt, audit


def test_native_adapter_closes_run_sqlite_before_observer(tmp_path):
    """单独验证资源关闭，不能被更早的status失败遮挡。"""
    context = _context(tmp_path)
    result = adapter.Phase11RuntimeAdapter().run(context)
    receipt, audit = _native_audit(context, result, "fd")
    assert audit["before_observer"] == []
    assert audit["after_observer_close"] == []
    assert audit["unreleased_leases"] == 0 and audit["heartbeat_threads"] == []
    database = context.output_root / receipt["sqlite_evidence"]["relative_path"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == receipt["sqlite_evidence"]["sha256"]


class _SQLiteSentinel(RuntimeError):
    pass


def _scratch_database(path, tables):
    connection = sqlite3.connect(path)
    try:
        for name in tables:
            connection.execute("CREATE TABLE " + name + " (released_at TEXT)")
        connection.commit()
    finally:
        connection.close()


def _test_audit(tmp_path, name, value):
    directory = Path(os.environ.get("R419_EVIDENCE_DIR", tmp_path))
    with (directory / (name + ".json")).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


@pytest.mark.parametrize("case", ["success", "count_error", "vacuum_error", "checkpoint_error"])
def test_sqlite_summary_closes_owned_connection(monkeypatch, tmp_path, case):
    """真实连接强引用下，成功及异常路径都必须显式关闭，且先close后hash。"""
    database = tmp_path / "summary.sqlite3"
    _scratch_database(
        database,
        [
            "simulation_jobs",
            "simulation_job_events",
            "simulation_job_leases",
            "simulation_job_attempts",
            "simulation_metrics",
            "simulation_artifacts",
        ],
    )
    original_connect = sqlite3.connect
    original_hash = adapter._path_hash
    connections = []
    log = {"close_calls": 0, "injected": False, "checkpoint_calls": 0, "hash_after_close": False}
    sentinel = _SQLiteSentinel(case)

    class TrackedConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith("PRAGMA wal_checkpoint"):
                log["checkpoint_calls"] += 1
            failure = (
                case == "count_error"
                and sql.startswith("SELECT COUNT")
                or case == "vacuum_error"
                and sql == "VACUUM"
                or case == "checkpoint_error"
                and sql.startswith("PRAGMA wal_checkpoint")
                and log["checkpoint_calls"] == 3
            )
            if failure:
                log["injected"] = True
                raise sentinel
            return super().execute(sql, *args, **kwargs)

        def close(self):
            log["close_calls"] += 1
            return super().close()

    def connect(path):
        connection = original_connect(path, factory=TrackedConnection)
        connections.append(connection)
        return connection

    def hash_after_close(path):
        log["hash_after_close"] = log["close_calls"] == 1
        assert log["hash_after_close"], "database hash must follow explicit close"
        return original_hash(path)

    monkeypatch.setattr(adapter, "sqlite3", SimpleNamespace(connect=connect))
    monkeypatch.setattr(adapter, "_path_hash", hash_after_close)
    try:
        if case == "success":
            summary = adapter._sqlite_summary(database, output_root=tmp_path)
            assert summary["sha256"] == hashlib.sha256(database.read_bytes()).hexdigest()
        else:
            with pytest.raises(_SQLiteSentinel) as observed:
                adapter._sqlite_summary(database, output_root=tmp_path)
            assert observed.value is sentinel and log["injected"] is True
        assert len(connections) == 1
        assert log["close_calls"] == 1
        assert _run_sqlite_fds(tmp_path) == []
    finally:
        _test_audit(tmp_path, "r420-summary-" + case, {**log, "held_connections": len(connections)})


@pytest.mark.parametrize("case", ["success", "query_error"])
def test_native_audit_observer_closes_own_connection(tmp_path, case):
    """观测器的真实连接在正常与错误查询后都关闭，不清理产品连接。"""
    database = tmp_path / "observer.sqlite3"
    _scratch_database(database, ["simulation_job_leases"])
    original_connect = sqlite3.connect
    connections = []
    log = {"close_calls": 0, "injected": False}
    sentinel = _SQLiteSentinel(case)

    class ObserverConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if case == "query_error":
                log["injected"] = True
                raise sentinel
            return super().execute(sql, *args, **kwargs)

        def close(self):
            log["close_calls"] += 1
            return super().close()

    def connect(path):
        connection = original_connect(path, factory=ObserverConnection)
        connections.append(connection)
        return connection

    assert _run_sqlite_fds(tmp_path) == []
    if case == "success":
        assert _unreleased_lease_count(database, connect=connect) == 0
    else:
        with pytest.raises(_SQLiteSentinel) as observed:
            _unreleased_lease_count(database, connect=connect)
        assert observed.value is sentinel and log["injected"] is True
    _test_audit(tmp_path, "r420-observer-" + case, {**log, "held_connections": len(connections)})
    assert len(connections) == 1 and log["close_calls"] == 1
    assert _run_sqlite_fds(tmp_path) == []


def test_unreleased_lease_observer_counts_empty_sentinel(tmp_path):
    """实际表用空串表示未释放，不能仅统计NULL。"""
    database = tmp_path / "empty-sentinel.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE simulation_job_leases (released_at TEXT NOT NULL DEFAULT '')"
        )
        connection.executemany(
            "INSERT INTO simulation_job_leases VALUES (?)",
            [
                ("",),
                ("",),
                ("2026-11-04T00:00:00+00:00",),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    count = _unreleased_lease_count(database)
    _test_audit(tmp_path, "r421-empty-sentinel", {"expected": 2, "observed": count})
    assert count == 2
    assert _run_sqlite_fds(tmp_path) == []


def test_recovery_archives_expired_simulated_lease_as_released(tmp_path):
    """独立恢复必须在duplicate运行前生成全部lease已释放的一致归档。"""
    context = _context(tmp_path)
    context.output_root.mkdir(parents=True)
    artifacts = context.output_root / "artifacts"
    repo = adapter.SQLiteSimulationJobRepository(
        context.output_root / "recovery.sqlite3", artifact_root=artifacts
    )
    probe = adapter._run_recovery_job(repo, context, artifacts)
    leases = repo.list_leases(probe["run_id"])
    attempts = repo.list_attempts(probe["run_id"])
    paths = repo.get_artifacts(probe["run_id"])
    originals = {
        key: {
            "path": str(artifacts / paths[key]),
            "sha256": hashlib.sha256((artifacts / paths[key]).read_bytes()).hexdigest(),
            "text": (artifacts / paths[key]).read_text(),
        }
        for key in ("leases", "attempts", "evidence_consistency")
    }
    consistency = json.loads(originals["evidence_consistency"]["text"])
    _test_audit(
        tmp_path,
        "r421-recovery-archive",
        {
            "probe": probe,
            "originals": originals,
            "run_sqlite_fds": _run_sqlite_fds(context.output_root),
        },
    )
    stale = [item for item in leases if item.lease_id == probe["stale_lease_id"]]
    assert len(stale) == 1 and stale[0].released_at is not None
    assert len(leases) == 2 and all(item.released_at is not None for item in leases)
    assert stale[0].released_at < leases[1].acquired_at
    assert probe["lease_expired"] is True
    assert [item.result for item in attempts] == ["INTERRUPTED", "BLOCKED_BY_ENV"]
    assert consistency["consistent"] is True
    archived_leases = [json.loads(line) for line in originals["leases"]["text"].splitlines()]
    assert all(item["released_at"] for item in archived_leases)
    assert probe["execution_evidence"]["lease_released"] is True
    assert probe["execution_evidence"]["evidence_valid"] is True
    assert _unreleased_lease_count(context.output_root / "recovery.sqlite3") == 0
    assert _run_sqlite_fds(context.output_root) == []


@pytest.mark.parametrize(
    "case",
    [
        "not_expired",
        "not_interrupted",
        "wrong_run",
        "wrong_job",
        "replacement_lease",
        "wrong_worker",
        "already_released",
    ],
)
def test_simulated_crash_cleanup_rejects_wrong_or_live_owner(case):
    """过期、原owner和身份必须同时成立，任一反例都不得释放租约。"""
    now = datetime.now(UTC)
    lease = SimulationJobLease(
        "old-lease",
        "job",
        "phase12-worker-crashed",
        now - timedelta(seconds=2),
        now - timedelta(seconds=1),
        now - timedelta(seconds=2),
    )
    job = SimpleNamespace(
        job_id="job",
        run_id="run",
        status=RuntimeJobStatus.INTERRUPTED,
        worker_id=lease.worker_id,
        lease_id=lease.lease_id,
        lease_expires_at=lease.expires_at,
    )
    current = lease
    if case == "not_expired":
        lease = replace(lease, expires_at=now + timedelta(seconds=30))
        current = lease
        job.lease_expires_at = lease.expires_at
    elif case == "not_interrupted":
        job.status = RuntimeJobStatus.RUNNING
    elif case == "wrong_run":
        job.run_id = "foreign-run"
    elif case == "wrong_job":
        current = replace(lease, job_id="foreign-job")
    elif case == "replacement_lease":
        job.lease_id = "new-owner-lease"
    elif case == "wrong_worker":
        current = replace(lease, worker_id="new-worker")
    elif case == "already_released":
        current = replace(lease, released_at=now)
    calls = []
    repo = SimpleNamespace(
        publication_guard=nullcontext,
        get_job_by_run_id=lambda _: job,
        list_leases=lambda _: [current],
        release_lease=calls.append,
    )
    with pytest.raises(RuntimeError, match="simulated_crash_cleanup_"):
        adapter._release_expired_simulated_crash_lease(
            repo, run_id="run", lease=lease, interrupted_jobs=["job"]
        )
    assert calls == []


def test_current_rgbd_mock_blocker_propagates_from_native_receipts(tmp_path):
    """防止真实RGBD_CAMERA_REQUIRED被外层无条件SUCCESS覆盖。"""
    context = _context(tmp_path)
    result = adapter.Phase11RuntimeAdapter().run(context)
    receipt, audit = _native_audit(context, result, "blocked")
    assert (
        audit["main_status"]
        == audit["recovery_status"]
        == audit["duplicate_status"]
        == "BLOCKED_BY_ENV"
    )
    assert receipt["duplicate_competition_evidence"]["runner_invocation_count"] == 0
    for key in ("main_job", "recovery_evidence", "duplicate_competition_evidence"):
        assert receipt[key]["execution_evidence"]["evidence_valid"] is True
        assert receipt[key]["execution_evidence"]["lease_released"] is True
    assert receipt["main_job"]["released_lease_count"] == receipt["main_job"]["lease_count"] == 1
    assert result.status == Phase12RunStatus.BLOCKED_BY_ENV
    assert result.runtime_invoked is False and result.runtime_completed is False
    assert result.task_success is False and result.authoritative_for_thesis is False
    assert not any(event["event_type"].endswith("_completed") for event in result.events)
    assert audit["unreleased_leases"] == 0
    assert audit["run_sqlite_fds"] == audit["heartbeat_threads"] == []


def test_explicit_legacy_input_uses_native_receipts_without_formal_acceptance(
    monkeypatch, tmp_path
):
    """仅明确测试输入，原生主任务/恢复/去重的软件完成不能提升为正式验收。"""
    original_draft = adapter._draft
    overrides = []

    def explicit_legacy(context, *, runtime_delay_ms=0):
        draft = original_draft(context, runtime_delay_ms=runtime_delay_ms)
        assert draft.get("execution_scope", "VISUAL_PLANNING") == "VISUAL_PLANNING"
        overrides.append(
            {
                "kind": "TEST_ONLY_INPUT_OVERRIDE",
                "input_mode": "LEGACY_PIPELINE",
                "effective_execution_scope": "VISUAL_PLANNING",
            }
        )
        return {**draft, "input_mode": "LEGACY_PIPELINE"}

    monkeypatch.setattr(adapter, "_draft", explicit_legacy)
    context = _context(tmp_path)
    result = adapter.Phase11RuntimeAdapter().run(context)
    receipt, audit = _native_audit(context, result, "legacy-positive")
    _test_audit(tmp_path, "legacy-input-override", {"overrides": overrides})
    artifacts = (
        context.output_root / "source_evidence" / context.run_id / "phase11_runtime" / "artifacts"
    )
    originals = []
    for key in ("main_job", "recovery_evidence", "duplicate_competition_evidence"):
        probe = receipt[key]
        path = artifacts / "phase11_1/runtime" / probe["run_id"] / "result.json"
        raw = path.read_bytes()
        originals.append(
            {
                "probe": key,
                "path": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "result": json.loads(raw),
            }
        )
    _test_audit(tmp_path, "legacy-native-results", {"originals": originals})
    assert len(overrides) == 3
    assert result.status == Phase12RunStatus.SUCCESS
    assert result.runtime_invoked is True and result.runtime_completed is True
    assert result.task_success is True and result.authoritative_for_thesis is False
    for item in originals:
        probe = receipt[item["probe"]]
        evidence = probe["execution_evidence"]
        assert evidence["evidence_valid"] is True and evidence["artifacts_verified"] is True
        assert evidence["executor_invoked"] is True and evidence["executor_returned"] is True
        assert evidence["lease_released"] is True and evidence["attempt_completed"] is True
        assert evidence["artifact_hashes"]["result"] == item["sha256"]
        assert item["result"]["task_success"] is True
        assert item["result"]["result_status"] == "SUCCESS"
        assert item["result"]["status"] == "SUCCEEDED"
        assert item["result"]["runner"] == "MOCK_SCENARIO"
        assert item["result"]["real_controller_contacted"] is False
        assert item["result"]["hardware_motion_observed"] is False
        assert item["result"]["hardware_write_operations"] == []
    recovery = receipt["recovery_evidence"]
    assert recovery["attempt_count"] == 2 and recovery["lease_expired"] is True
    assert recovery["job_id"] in recovery["recovered_jobs"]
    assert {
        ("RUNNING", "INTERRUPTED"),
        ("INTERRUPTED", "RECOVERY_PENDING"),
        ("RECOVERY_PENDING", "QUEUED"),
    }.issubset({tuple(pair) for pair in recovery["transitions"]})
    duplicate = receipt["duplicate_competition_evidence"]
    assert duplicate["runner_invocation_count"] == duplicate["attempt_count"] == 1
    assert duplicate["lease_winner"] != duplicate["lease_loser"]
    assert audit["unreleased_leases"] == 0
    assert (
        audit["before_observer"]
        == audit["after_observer_close"]
        == audit["heartbeat_threads"]
        == []
    )
    database = context.output_root / receipt["sqlite_evidence"]["relative_path"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == receipt["sqlite_evidence"]["sha256"]
    assert receipt["research_qualification"]["authoritative_for_thesis"] is False
    assert receipt["real_controller_contacted"] is False
    assert receipt["hardware_motion_observed"] is False
    assert receipt["hardware_write_operations"] == []


@pytest.mark.parametrize("corruption", ["hash", "identity", "attempt", "consistency_false"])
def test_native_artifact_corruption_is_rejected(monkeypatch, tmp_path, corruption):
    """原生发布后仅损坏本次新文件，校验器必须识别hash及身份错误。"""
    original = adapter.SimulationWorker._write_artifacts

    def write_and_corrupt(worker, job, **kwargs):
        paths = original(worker, job, **kwargs)
        if not job.run_id.endswith("-runtime"):
            return paths
        key = {
            "hash": "result",
            "identity": "runtime_job",
            "attempt": "attempts",
            "consistency_false": "evidence_consistency",
        }[corruption]
        path = worker.artifact_root / paths[key]
        if corruption == "hash":
            path.write_bytes(path.read_bytes() + b" ")
        elif corruption == "identity":
            payload = json.loads(path.read_text())
            payload["run_id"] = "foreign-run"
            path.write_text(json.dumps(payload))
        elif corruption == "attempt":
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[-1]["attempt"] += 1
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        else:
            payload = json.loads(path.read_text())
            payload["consistent"] = False
            path.write_text(json.dumps(payload))
        if corruption in {"identity", "attempt"}:
            consistency_path = worker.artifact_root / paths["evidence_consistency"]
            payload = json.loads(consistency_path.read_text())
            payload["file_hashes"][key] = hashlib.sha256(path.read_bytes()).hexdigest()
            consistency_path.write_text(json.dumps(payload))
        return paths

    monkeypatch.setattr(adapter.SimulationWorker, "_write_artifacts", write_and_corrupt)
    context = _context(tmp_path)
    result = adapter.Phase11RuntimeAdapter().run(context)
    receipt, audit = _native_audit(context, result, "corrupt-" + corruption)
    assert receipt["runtime_outcome"]["invalid_probes"] == ["main"]
    for key in ("recovery_evidence", "duplicate_competition_evidence"):
        assert receipt[key]["execution_evidence"]["evidence_valid"] is True
    expected_error = {
        "hash": "artifact_hash_manifest_mismatch",
        "identity": "runtime_job_identity_mismatch",
        "attempt": "artifact_attempt_mismatch_or_incomplete",
        "consistency_false": "terminal_consistency_identity_or_status_mismatch",
    }[corruption]
    assert expected_error in receipt["main_job"]["execution_evidence"]["evidence_errors"]
    assert result.status == Phase12RunStatus.FAILED
    assert result.blocker_stage == BlockerStage.FINALIZATION
    assert result.task_success is False and result.runtime_completed is False
    assert result.authoritative_for_thesis is False
    assert audit["unreleased_leases"] == 0
    assert (
        audit["before_observer"]
        == audit["after_observer_close"]
        == audit["heartbeat_threads"]
        == []
    )
