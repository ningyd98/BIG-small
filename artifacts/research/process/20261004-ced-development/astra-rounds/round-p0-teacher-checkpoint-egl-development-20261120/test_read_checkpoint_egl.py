"""Software controls for the independent checkpoint reader."""

import json
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path

import pytest
from read_checkpoint_egl import (
    ASSIGNMENT,
    SCHEMA,
    SCOPE,
    SEED,
    WINDOW_NS,
    canonical_digest,
    read_frames,
    verified_worker,
    verify_active,
    verify_inventory,
    verify_registration,
    verify_stop,
    verify_window,
)


@pytest.fixture
def registration(tmp_path):
    run = tmp_path / "run"
    protocol = {
        "schema_version": SCHEMA,
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "step_wall_budget_ns": WINDOW_NS,
        "qualification_credit": 0,
        "registration_directory": str(tmp_path),
        "output": str(run),
    }
    claim = {
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "output": str(run),
        "registration_sha256": canonical_digest(protocol),
        "application_id": "app",
    }
    return protocol, claim, run


def test_registration_binds_fixed_schema_and_output(registration):
    protocol, claim, run = registration
    assert verify_registration(protocol, claim, run) == canonical_digest(protocol)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", "native.calibration.operational.v9"),
        ("seed", 11919001),
        ("step_wall_budget_ns", WINDOW_NS + 1),
        ("qualification_credit", False),
    ],
)
def test_registration_rejects_formal_or_changed_release(registration, key, value):
    protocol, claim, run = registration
    protocol[key] = value
    claim["registration_sha256"] = canonical_digest(protocol)
    with pytest.raises(ValueError, match="fixed development registration"):
        verify_registration(protocol, claim, run)


def test_inventory_rejects_replaced_same_size_original_and_symlink(tmp_path):
    path = tmp_path / "frame"
    path.write_bytes(b"pixels")
    files = {"frame": {"bytes": 6, "sha256": sha256(b"pixels").hexdigest()}}
    inventory = {
        "files": files,
        "file_count": 1,
        "inventory_sha256": canonical_digest(files),
        "original_bytes": 6,
        "schema_version": "native.registered.full-horizon.inventory.v2",
        "native_qualification": "UNKNOWN",
    }
    assert verify_inventory(tmp_path, inventory) == files
    path.write_bytes(b"pixeLs")
    with pytest.raises(ValueError, match="file hash mismatch"):
        verify_inventory(tmp_path, inventory)
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"pixels")
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="linked original"):
        verify_inventory(tmp_path, inventory)


def timestamp(second):
    return f"2026-11-20T00:00:{second:02}+00:00"


def sql_table(connection, name, rows):
    keys, values = tuple(rows[0]), [tuple(row.values()) for row in rows]
    connection.execute(f"CREATE TABLE {name} ({', '.join(keys)})")
    placeholders = ", ".join("?" for _ in keys)
    connection.executemany(f"INSERT INTO {name} VALUES ({placeholders})", values)


@pytest.fixture
def runtime_sqlite(tmp_path):
    # This database is a unit-test fixture, never admitted as a real dispatch.
    job = {
        "job_id": "job",
        "run_id": "runtime",
        "worker_id": "worker",
        "lease_id": "lease",
        "backend": "MUJOCO",
        "seed": SEED,
        "attempt": 1,
        "max_attempts": 1,
        "status": "BLOCKED_BY_ENV",
        "started_at": timestamp(2),
        "completed_at": timestamp(9),
    }
    attempt = {
        "job_id": "job",
        "run_id": "runtime",
        "worker_id": "worker",
        "attempt": 1,
        "started_at": timestamp(1),
        "ended_at": timestamp(9),
        "result": job["status"],
    }
    lease = {
        "lease_id": "lease",
        "job_id": "job",
        "worker_id": "worker",
        "acquired_at": timestamp(1),
        "expires_at": timestamp(20),
        "heartbeat_at": timestamp(5),
        "released_at": timestamp(10),
    }
    events = [
        {
            "job_id": "job",
            "run_id": "runtime",
            "stream_sequence": i,
            "next_status": phase,
            "payload_json": json.dumps({"lease_id": "lease"}),
        }
        for i, phase in enumerate(("LEASED", "RUNNING", job["status"]), 1)
    ]
    with closing(sqlite3.connect(tmp_path / "runtime.db")) as connection:
        sql_table(connection, "simulation_jobs", [job])
        sql_table(connection, "simulation_job_attempts", [attempt])
        sql_table(connection, "simulation_job_leases", [lease])
        sql_table(connection, "simulation_job_events", events)
        connection.commit()
    return tmp_path, {"worker_snapshot": {"job": job, "attempts": [attempt]}}


def test_lease_readback_copies_database_without_writing_original(runtime_sqlite):
    run, lifecycle = runtime_sqlite
    before = {p.name: p.read_bytes() for p in run.iterdir()}
    output = verified_worker(run, lifecycle)
    assert output["worker_dispatched"] and output["lease_released"]
    assert output["lease_id"] == "lease"
    assert output["database_sha256"]["runtime.db"] == sha256(before["runtime.db"]).hexdigest()
    assert {p.name: p.read_bytes() for p in run.iterdir()} == before


def test_worker_refuses_changed_terminal_lease(runtime_sqlite):
    run, lifecycle = runtime_sqlite
    with closing(sqlite3.connect(run / "runtime.db")) as connection:
        connection.execute("UPDATE simulation_job_leases SET lease_id='foreign'")
        connection.commit()
    with pytest.raises(ValueError, match="identity does not join"):
        verified_worker(run, lifecycle)


@pytest.fixture
def cutoff(tmp_path):
    (tmp_path / "shield").mkdir()
    (tmp_path / "shield/step-1-pre-input.json").write_text(
        json.dumps(
            {
                "context": {"step_started_at": 17.0},
            }
        )
    )
    allowed = {
        "kind": "PHYSICS",
        "phase": "AFTER",
        "physics_step": 121,
        "operation_id": 8,
        "episode_id": "episode",
    }
    rejected = {**allowed, "kind": "CAPTURE", "phase": "BEFORE"}
    start = 17_000_000_000
    witness = {
        "scope": SCOPE,
        "qualification_credit": 0,
        "registration_sha256": "registered",
        "status": "CUTOFF",
        "first_action_started_monotonic_ns": start,
        "cutoff_monotonic_ns": start + WINDOW_NS,
        "last_authorized_monotonic_ns": start + WINDOW_NS - 1,
        "cutoff_observed_monotonic_ns": start + WINDOW_NS + 1,
        "guard_exit_monotonic_ns": start + WINDOW_NS + 2,
        "body_cleanup_finished_monotonic_ns": start + WINDOW_NS + 3,
        "last_authorized_checkpoint": allowed,
        "rejected_checkpoint": rejected,
        "dispatch_physics_step": 120,
        "final_physics_step": 121,
    }
    raw = {
        "guard_events": [
            {**allowed, "outcome": "ALLOWED", "sequence": 1},
            {**rejected, "outcome": "REJECTED", "sequence": 2},
        ]
    }
    active_times = {
        "action_authorization_last_monotonic_ns": witness["last_authorized_monotonic_ns"],
        "action_callback_last_monotonic_ns": witness["last_authorized_monotonic_ns"],
    }
    return tmp_path, witness, raw, active_times


def test_wall_cutoff_joins_shield_and_guard_ledger(cutoff):
    path, witness, raw, active = cutoff
    result = verify_window(path, witness, raw, "registered", 121, active)
    assert result["physical_prefix_steps"] == 1
    assert result["status"] == "CUTOFF"


def test_wall_cutoff_rejects_authorization_after_cutoff(cutoff):
    path, witness, raw, active = cutoff
    witness["last_authorized_monotonic_ns"] = witness["cutoff_monotonic_ns"]
    with pytest.raises(ValueError, match="authorization exceeded"):
        verify_window(path, witness, raw, "registered", 121, active)


def test_wall_cutoff_rejects_physics_advance_after_rejection(cutoff):
    path, witness, raw, active = cutoff
    witness["final_physics_step"] = 122
    with pytest.raises(ValueError, match="physical step advanced"):
        verify_window(path, witness, raw, "registered", 122, active)


def test_active_read_joins_live_lease_and_owner(cutoff):
    _, witness, raw, _ = cutoff
    bracket = {"domain": {"pid": 8}, "event_identity": "owner", "lower_ns": 1, "upper_ns": 2}
    original = {"origin": {**bracket, "event_identity": "origin"}, "deadline": {"deadline_ns": 110}}
    active = [
        {
            "checkpoint": witness["last_authorized_checkpoint"],
            "current": bracket,
            "lease_id": "lease",
            "step": 121,
            "guard_sequence": 1,
            "diagnostic_authorized_monotonic_ns": witness["last_authorized_monotonic_ns"],
        }
    ]
    report = verify_active(active, raw, {"lease_id": "lease"}, original)
    assert report["owner_active_checks"] == 1
    assert (
        report["action_authorization_last_monotonic_ns"] == witness["last_authorized_monotonic_ns"]
    )
    active[0]["guard_sequence"] = 2
    with pytest.raises(ValueError, match="no exact original guard sequence"):
        verify_active(active, raw, {"lease_id": "lease"}, original)
    active[0]["guard_sequence"] = 1
    active[0]["lease_id"] = "foreign"
    with pytest.raises(ValueError, match="another lease"):
        verify_active(active, raw, {"lease_id": "lease"}, original)


def test_stop_preserves_pre_stop_snapshot_and_unobserved_effect():
    boundary = {"operation_id": 13, "kind": "COMMAND", "error": None, "error_type": None}
    raw = {
        "guard_events": [
            {"kind": "FAILURE", "physics_step": 1, "physics_state": {"estop_engaged": False}}
        ],
        "commands": [
            {
                "interval_id": "operation-13",
                "command_seq": 1,
                "effective_from_step": 2,
                "command_payload": {"accepted": True, "type": "emergency_stop", "physics_step": 1},
            }
        ],
        "backend_operation_ledger": [{**boundary, "phase": "BEGIN"}, {**boundary, "phase": "END"}],
    }
    result = verify_stop(raw, 1)
    assert result["accepted_emergency_stop"]
    assert result["pre_stop_estop_snapshot"] is False
    assert result["physical_state_at_stop_effective_step"] is None
    raw["guard_events"][-1]["stop_error"] = "unavailable"
    with pytest.raises(ValueError, match="stop failure"):
        verify_stop(raw, 1)


def test_frames_reject_reordered_physics_before_observation_reconstruction(tmp_path: Path):
    raw = {"physics": [{"physics_step": 2}, {"physics_step": 1}], "total_physics_steps": 2}
    with pytest.raises(ValueError, match="missing, duplicated or out of order"):
        read_frames(tmp_path, {}, raw, {})
