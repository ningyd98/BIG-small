"""Bound a real development worker to bootstrap and one PRE decision."""

import hashlib
import os
import shutil
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from cloud_edge_robot_arm.research import native_calibration_collection as protocols
from cloud_edge_robot_arm.research.native_collection_application import (
    _REGISTRY,
    NativeCollectionApplication,
)
from cloud_edge_robot_arm.research.native_full_horizon_recorder import NativeFullHorizonRecorder
from cloud_edge_robot_arm.simulation.mujoco.native_horizon import NativeHorizonSession


@pytest.fixture
def development_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    pytest.importorskip("mujoco")
    if not os.environ.get("DISPLAY") and os.environ.get("MUJOCO_GL") not in {"egl", "osmesa"}:
        pytest.skip("requires a headless MuJoCo renderer or a display")

    release = protocols.load_json(protocols.ROOT / protocols._REGISTERED_TEACHER_V10_CONFIG)
    assignment = "native-phase7-fixture-0001"
    release.update(release_id="phase7-fixture", released_assignment=assignment, first_seed=7001)
    config = tmp_path / "development-release.json"
    protocols.save_exclusive(config, release)
    monkeypatch.setattr(protocols, "_REGISTERED_TEACHER_V10_CONFIG", str(config))
    monkeypatch.setattr(
        protocols,
        "_REGISTERED_TEACHER_V10_CONFIG_SHA",
        hashlib.sha256(config.read_bytes()).hexdigest(),
    )
    protocol = tmp_path / "registration"
    protocols.prepare_native_calibration(config, output=protocol)
    registration = protocols.read_protocol(protocol)
    if shutil.disk_usage(tmp_path).free < registration["settings"]["free_disk_min_bytes"]:
        pytest.skip("requires the registered free disk space for native capture")

    return protocol, assignment


def test_stopped_development_worker_replays_from_fresh_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, development_registration: tuple[Path, str]
) -> None:
    protocol, assignment = development_registration
    failure = "development fixture interrupted before controller dispatch"
    entries: list[int] = []

    def first_dispatch(
        self: NativeHorizonSession, *, index: int, contract: object, step: object, binding: object
    ) -> None:
        entries.append(index)
        raise RuntimeError(failure)

    monkeypatch.setattr(NativeHorizonSession, "execute", first_dispatch)
    output = tmp_path / "run"
    app = NativeCollectionApplication.from_startup(
        protocol, assignment_id=assignment, output=output
    )
    with pytest.raises(RuntimeError, match=failure):
        app.execute_once()
    assert len(entries) == 1
    final = protocols.load_json(output / "collection-result.json")
    assert final["owner_closure"] == {"attempted": True, "completed": True}
    assert all(
        final["progress"][name]
        for name in (
            "backend_shutdown_completed",
            "capture_close_completed",
            "recorder_close_completed",
            "freeze_completed",
        )
    )
    assert final["physics_steps"] == 120
    assert final["completed_action_count"] == 0
    assert final["teacher_collection_admitted"] is False
    assert failure in final["worker_snapshot"]["job"]["error_message"]
    for name, digest in final["lifecycle_links"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest

    snapshot = tmp_path / "worker-snapshot.db"
    shutil.copyfile(output / "runtime.db", snapshot)
    wal = output / "runtime.db-wal"
    if wal.exists():
        shutil.copyfile(wal, tmp_path / "worker-snapshot.db-wal")
    with closing(sqlite3.connect(snapshot)) as db:
        assert db.execute(
            "SELECT status, attempt, max_attempts FROM simulation_jobs"
        ).fetchall() == [("BLOCKED_BY_ENV", 1, 1)]
        assert db.execute("SELECT COUNT(*) FROM simulation_job_attempts").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM simulation_job_leases").fetchone() == (1,)

    original = protocols.load_json(output / "originals/partial-originals.json")
    assert not original["actions"]
    (pre,) = original["decisions"]
    assert pre["inputs"]["phase"] == "PRE"
    assert pre["inputs"]["shield"]["decision"] == "ALLOW"
    assert pre["decision"]["allowed"] is True
    stops = [
        row
        for row in original["commands"]
        if row["command_payload"]["type"] in {"hold_current_joints", "emergency_stop"}
    ]
    assert [row["command_payload"]["type"] for row in stops] == [
        "hold_current_joints",
        "emergency_stop",
    ]
    intervals = {row["interval_id"]: row for row in original["intervals"]}
    parents = [row["parent_interval_id"] for row in stops]
    assert all(parent in intervals for parent in parents), parents
    assert parents[0] == parents[1]
    termination = intervals[parents[0]]
    assert termination["kind"] == "TERMINATION"
    assert termination["start_step"] == termination["end_step"] == final["physics_steps"]
    assert all(row["effective_from_step"] == final["physics_steps"] + 1 for row in stops)

    with pytest.raises(RuntimeError, match="already claimed"):
        NativeCollectionApplication.from_startup(
            protocol, assignment_id=assignment, output=tmp_path / "retry"
        )
    assert not (tmp_path / "retry").exists()
    readback = tmp_path / "verify"
    result = protocols.verify_native_calibration_collection(protocol, output=readback)
    groups = protocols.load_json(readback / "groups.json")
    assert result["assigned_groups"] == len(groups) == 9
    assert groups[0]["assignment_id"] == assignment
    assert groups[0]["total_physics_steps"] == 120
    assert (
        groups[0]["reconstructed_frames"]
        == groups[0]["allocated_frames"]
        == len(original["allocated_frames"])
    )
    assert groups[0]["reconstructed_frames"] > 0
    reasons = groups[0]["reasons"]
    assert not any(reason.startswith("physics:") for reason in reasons), reasons
    assert "operations:ValueError:source guard failed or did not close" in reasons
    assert groups[0]["execution_admitted"] is False
    assert groups[0]["native_qualification"] == "UNKNOWN"
    assert all(group["state"] == "NOT_RUN" for group in groups[1:])


@pytest.mark.parametrize("fail_foreign_control", [False, True], ids=["foreign-stop", "owner-retry"])
def test_worker_waits_for_brake_before_freezing_and_releasing_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    development_registration: tuple[Path, str],
    fail_foreign_control: bool,
) -> None:
    protocol, assignment = development_registration
    output = tmp_path / "run"
    app = NativeCollectionApplication.from_startup(
        protocol, assignment_id=assignment, output=output
    )
    live = _REGISTRY[app]
    holding, release, owner_unwinding, freeze_entered = (threading.Event() for _ in range(4))
    threads: list[threading.Thread] = []
    before_brake: dict[str, bool] = {}
    foreign_errors: list[BaseException] = []
    original_freeze = NativeFullHorizonRecorder.freeze

    def observe_freeze(recorder: NativeFullHorizonRecorder) -> dict[str, Any]:
        freeze_entered.set()
        return original_freeze(recorder)

    def interrupt_before_controller(
        self: NativeHorizonSession, *, index: int, contract: object, step: object, binding: object
    ) -> None:
        backend = live.backend
        actual_hold = backend.hold_current_joints
        if fail_foreign_control:
            owner_thread = threading.get_ident()
            actual_target_motion = backend._apply_target_motion

            def fail_inside_control() -> None:
                if threading.get_ident() != owner_thread:
                    raise OSError("development fault inside foreign CONTROL")
                actual_target_motion()

            monkeypatch.setattr(backend, "_apply_target_motion", fail_inside_control)

        def hold() -> None:
            holding.set()
            if not release.wait(10):
                raise RuntimeError("development brake barrier timed out")
            before_brake.update(
                has_backend=backend._data is not None,
                guard_exited=live.progress.get("guard_exited", False),
                freeze_started=freeze_entered.is_set(),
                recorder_close=live.progress.get("recorder_close_attempted", False),
                capture_close=live.progress.get("capture_close_attempted", False),
                backend_shutdown=live.progress.get("backend_shutdown_attempted", False),
            )
            actual_hold()

        def foreign_step() -> None:
            try:
                backend.step(1)
            except BaseException as exc:
                foreign_errors.append(exc)

        def release_writer() -> None:
            try:
                if owner_unwinding.wait(8):
                    # Give a premature real freeze a chance to signal the old lifecycle bug.
                    # A correct owner waits here for the independent writer.
                    freeze_entered.wait(1)
            finally:
                release.set()

        monkeypatch.setattr(backend, "hold_current_joints", hold)
        threads.extend(
            [threading.Thread(target=release_writer), threading.Thread(target=foreign_step)]
        )
        for thread in threads:
            thread.start()
        assert holding.wait(5), "foreign step must trigger the owner-thread guard before dispatch"
        owner_unwinding.set()
        raise RuntimeError("development worker unwinds with a brake in progress")

    monkeypatch.setattr(NativeFullHorizonRecorder, "freeze", observe_freeze)
    monkeypatch.setattr(NativeHorizonSession, "execute", interrupt_before_controller)
    try:
        with pytest.raises(RuntimeError):
            app.execute_once()
    finally:
        owner_unwinding.set()
        release.set()
        for thread in threads:
            thread.join(5)
    assert len(threads) == 2 and all(not thread.is_alive() for thread in threads)
    assert len(foreign_errors) == 1 and "thread" in str(foreign_errors[0]).lower(), foreign_errors
    assert before_brake == dict(
        has_backend=True,
        guard_exited=False,
        freeze_started=False,
        recorder_close=False,
        capture_close=False,
        backend_shutdown=False,
    ), before_brake
    assert live.backend.estop_engaged
    stop_pair = ["hold_current_joints", "emergency_stop"]
    assert [row["type"] for row in live.backend.command_records] == stop_pair * (
        2 if fail_foreign_control else 1
    )
    originals = protocols.load_json(output / "originals/partial-originals.json")
    rejected = originals["observer_failures"]
    assert rejected and all(
        "active actual owner thread" in row["observer_error"] for row in rejected
    )
    rejected_ids = {row["operation_id"] for row in rejected}
    assert len(rejected_ids) == 3
    assert all(row["operation_id"] not in rejected_ids for row in originals["operational_events"])
    assert all(row["operation_id"] not in rejected_ids for row in originals["control_sources"])
    recorded = originals["commands"]
    if fail_foreign_control:
        assert [row["command_seq"] for row in recorded] == [3, 4]
        assert [row["command_payload"]["type"] for row in recorded] == stop_pair
        (parent,) = [row for row in originals["intervals"] if row["kind"] == "TERMINATION"]
        assert all(row["parent_interval_id"] == parent["interval_id"] for row in recorded)
        owner_events = originals["operational_events"][-3:]
        assert [row["kind"] for row in owner_events] == ["COMMAND", "COMMAND", "CONTROL"]
        assert all(row["token"] == row["bracket"]["event_identity"] for row in owner_events)
        assert len({row["token"] for row in owner_events}) == 3
        assert any(
            row.get("stop_error") == "development fault inside foreign CONTROL"
            for row in originals["guard_events"]
        )
    else:
        assert recorded == []
    receipt = protocols.load_json(output / "collection-result.json")
    assert receipt["physics_steps"] == 120 and receipt["completed_action_count"] == 0
    assert receipt["worker_snapshot"]["job"]["status"] == "BLOCKED_BY_ENV"
    assert (
        len(receipt["worker_snapshot"]["attempts"]) == 1 and receipt["owner_closure"]["completed"]
    )
    assert all(
        receipt["progress"][name]
        for name in (
            "freeze_completed",
            "recorder_close_completed",
            "capture_close_completed",
            "backend_shutdown_completed",
        )
    )
    readback = tmp_path / "verify"
    protocols.verify_native_calibration_collection(protocol, output=readback)
    groups = protocols.load_json(readback / "groups.json")
    assert groups[0]["reconstructed_frames"] == groups[0]["allocated_frames"] == 124
    assert groups[0]["total_physics_steps"] == 120
    assert groups[0]["native_qualification"] == "UNKNOWN" and not groups[0]["execution_admitted"]
    assert all(row["state"] == "NOT_RUN" for row in groups[1:])
