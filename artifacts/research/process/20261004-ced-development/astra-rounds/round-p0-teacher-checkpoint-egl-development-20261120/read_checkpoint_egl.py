"""Verify original records from one bounded MuJoCo checkpoint development run."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from collections import Counter
from collections.abc import Mapping
from contextlib import closing
from datetime import datetime
from hashlib import file_digest, sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cloud_edge_robot_arm.harness.config import strict_json
from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit

SCHEMA = "native.checkpoint-egl.development.v1"
SCOPE = "CHECKPOINT_EGL_DEVELOPMENT"
ASSIGNMENT = "native-dev-checkpoint-20261120-0001"
SEED = 11920067
WINDOW_NS = 8_000_000_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def original(root: Path, relative: str) -> Path:
    selected = Path(relative)
    require(
        type(relative) is str
        and selected.parts
        and not selected.is_absolute()
        and all(part not in {"", ".", ".."} for part in relative.split("/"))
        and "\\" not in relative
        and "\x00" not in relative,
        "source path escapes its original root",
    )
    path = (root / selected).absolute()
    require(path.resolve() == path and path.is_file(), f"missing or linked original: {relative}")
    return path


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def read_json(root: Path, relative: str) -> Any:
    return strict_json(original(root, relative).read_bytes())


def verify_registration(protocol: Any, claim: Any, run: Path) -> str:
    for key, expected in (
        ("schema_version", SCHEMA),
        ("scope", SCOPE),
        ("assignment_id", ASSIGNMENT),
        ("seed", SEED),
        ("step_wall_budget_ns", WINDOW_NS),
        ("qualification_credit", 0),
    ):
        require(
            type(protocol.get(key)) is type(expected) and protocol[key] == expected,
            f"invalid fixed development registration field: {key}",
        )
    require(
        protocol["output"] == str(run) and protocol["registration_directory"] == str(run.parent),
        "development protocol output was moved",
    )
    registration_sha = canonical_digest(protocol)
    require(
        claim.get("scope") == SCOPE
        and claim.get("assignment_id") == ASSIGNMENT
        and type(claim.get("seed")) is int
        and claim["seed"] == SEED
        and claim.get("output") == str(run)
        and claim.get("registration_sha256") == registration_sha
        and isinstance(claim.get("application_id"), str)
        and bool(claim["application_id"]),
        "development claim does not identify this source and output",
    )
    return registration_sha


def verify_inventory(root: Path, inventory: Any) -> dict[str, dict[str, Any]]:
    files = inventory["files"]
    require(
        inventory["schema_version"] == "native.registered.full-horizon.inventory.v2"
        and inventory["native_qualification"] == "UNKNOWN",
        "foreign inventory schema or formal qualification",
    )
    require(
        isinstance(files, dict) and inventory["file_count"] == len(files),
        "original inventory count mismatch",
    )
    require(
        inventory["inventory_sha256"] == canonical_digest(files), "original inventory hash mismatch"
    )
    require("inventory.json" not in files, "inventory cannot include itself")
    total = 0
    for name, receipt in files.items():
        path = original(root, name)
        size = receipt["bytes"]
        require(
            type(size) is int and size >= 0 and path.stat().st_size == size,
            f"original length mismatch: {name}",
        )
        require(digest_file(path) == receipt["sha256"], f"original file hash mismatch: {name}")
        total += size
    require(total == inventory["original_bytes"], "original inventory byte total mismatch")
    return files


def one(connection: sqlite3.Connection, query: str) -> dict[str, Any]:
    rows = connection.execute(query).fetchall()
    require(len(rows) == 1, "expected exactly one persisted job, attempt or lease")
    return dict(rows[0])


def _sqlite_rows(connection: sqlite3.Connection) -> tuple[dict[str, Any], ...]:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return (
        one(connection, "SELECT * FROM simulation_jobs"),
        one(connection, "SELECT * FROM simulation_job_attempts"),
        one(connection, "SELECT * FROM simulation_job_leases"),
        {
            "events": [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM simulation_job_events ORDER BY stream_sequence"
                )
            ]
        },
    )


def verified_worker(run: Path, lifecycle: Any) -> dict[str, Any]:
    snapshot: dict[str, str] = {}
    database = original(run, "runtime.db")
    wal = database.with_name(database.name + "-wal")
    with TemporaryDirectory(prefix="checkpoint-readback-") as temporary:
        copy_root = Path(temporary)
        names = ("runtime.db", "runtime.db-wal") if wal.exists() else ("runtime.db",)
        for name in names:
            source = original(run, name)
            snapshot[name] = digest_file(source)
            copied = copy_root / name
            shutil.copyfile(source, copied)
            require(digest_file(copied) == snapshot[name], "unstable SQLite input during copy")
        uri = (copy_root / "runtime.db").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            job, attempt, lease, stream = _sqlite_rows(connection)
        require((wal.exists()) == ("runtime.db-wal" in snapshot), "SQLite WAL presence changed")
        for name, expected in snapshot.items():
            require(
                digest_file(original(run, name)) == expected, "SQLite source changed during read"
            )

    def timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        require(
            parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "SQLite worker timestamp lacks UTC offset",
        )
        return parsed

    require(
        type(job["seed"]) is int and job["seed"] == SEED and job["backend"] == "MUJOCO",
        "SQLite job belongs to another seed or backend",
    )
    require(
        job["job_id"] == attempt["job_id"] == lease["job_id"]
        and job["run_id"] == attempt["run_id"]
        and job["worker_id"] == attempt["worker_id"] == lease["worker_id"]
        and job["lease_id"] == lease["lease_id"]
        and job["attempt"] == job["max_attempts"] == attempt["attempt"] == 1,
        "SQLite job/attempt/lease identity does not join",
    )
    require(
        job["status"] == attempt["result"]
        and job["status"] not in {"CREATED", "QUEUED", "LEASED", "STARTING", "RUNNING"},
        "SQLite job and attempt do not have the same terminal status",
    )
    require(
        timestamp(lease["acquired_at"])
        <= timestamp(attempt["started_at"])
        <= timestamp(job["started_at"])
        <= timestamp(job["completed_at"])
        <= timestamp(attempt["ended_at"])
        and timestamp(lease["acquired_at"])
        <= timestamp(lease["heartbeat_at"])
        <= timestamp(lease["expires_at"])
        and timestamp(job["completed_at"]) <= timestamp(lease["released_at"]),
        "SQLite attempt, heartbeat or lease-release chronology mismatch",
    )

    events = stream["events"]
    require(
        all((row["job_id"], row["run_id"]) == (job["job_id"], job["run_id"]) for row in events),
        "foreign SQLite event",
    )
    phases = [row["next_status"] for row in events]
    require(
        phases.count("RUNNING") == 1
        and phases.count("LEASED") == 1
        and phases.count(job["status"]) == 1
        and phases.index("LEASED") < phases.index("RUNNING") < phases.index(job["status"]),
        "SQLite worker did not publish a unique dispatch and terminal transition",
    )
    running = events[phases.index("RUNNING")]
    terminal = events[phases.index(job["status"])]
    require(
        all(
            read["lease_id"] == lease["lease_id"]
            for read in (
                strict_json(running["payload_json"].encode()),
                strict_json(terminal["payload_json"].encode()),
            )
        ),
        "SQLite event lease does not match the dispatched lease",
    )
    declared = lifecycle["worker_snapshot"]
    for key in ("job_id", "run_id", "lease_id", "worker_id", "status", "attempt"):
        require(declared["job"][key] == job[key], f"lifecycle disagrees with SQLite: {key}")
    require(
        len(declared["attempts"]) == 1 and declared["attempts"][0]["result"] == attempt["result"],
        "lifecycle attempt does not match SQLite",
    )
    return {
        "database_sha256": snapshot,
        "source": "PRIVATE_READ_ONLY_COPY_OF_ORIGINAL_SQLITE",
        "job_id": job["job_id"],
        "run_id": job["run_id"],
        "lease_id": lease["lease_id"],
        "worker_id": lease["worker_id"],
        "attempt": 1,
        "status": job["status"],
        "started_at": job["started_at"],
        "ended_at": attempt["ended_at"],
        "heartbeat_at": lease["heartbeat_at"],
        "lease_released_at": lease["released_at"],
        "worker_dispatched": True,
        "lease_released": True,
    }


def _tuple(checkpoint: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        checkpoint[key] for key in ("kind", "phase", "physics_step", "operation_id", "episode_id")
    )


def _strict_steps(rows: list[dict[str, Any]], count: int) -> dict[int, Any]:
    require(type(count) is int and count >= 0, "physical step count is invalid")
    steps = [row["physics_step"] for row in rows]
    require(
        all(type(step) is int for step in steps) and steps == list(range(1, count + 1)),
        "physical source steps are missing, duplicated or out of order",
    )
    return {row["physics_step"]: row["post_state_payload"] for row in rows}


def read_frames(
    run: Path,
    recipe: dict[str, Any],
    raw: Any,
    files: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    states = _strict_steps(raw["physics"], raw["total_physics_steps"])
    reset = raw.get("reset")
    if isinstance(reset, dict) and isinstance(reset.get("physics_state"), dict):
        states[0] = reset["physics_state"]
    audit = _Audit(recipe, {"assignment_id": ASSIGNMENT, "seed": SEED}, run)
    audit.raw = raw
    audit.states = states
    audit.intervals = {row["interval_id"]: row for row in raw["intervals"]}

    names = raw["allocated_frames"]
    paths = raw["frame_sources"]
    require(
        len(names) == len(set(names)) and set(paths) <= set(names),
        "duplicate acquisition or unallocated published frame",
    )
    observations = set()
    roles: Counter[str] = Counter()
    passes = 0
    per_step = []
    for acquisition in names:
        if acquisition not in paths:
            continue
        name = f"frames/{acquisition}/source-frame.json"
        require(paths[acquisition] == name and name in files, "frame source is not manifest-bound")
        observation, metadata, state = audit.frame(acquisition)
        require(observation.observation_id not in observations, "acquisition identity reused")
        observations.add(observation.observation_id)
        for name in metadata["frame"]["file_hashes"]:
            require(name in files, "frame original blob is absent from inventory")
        role = metadata["capture_source"]["role"]
        roles[role] += 1
        passes += metadata["pass_count"]
        if role == "REGISTERED_PER_PHYSICS_STEP":
            require(
                metadata["capture_source"]["sample_slot"] == state["physics_step"],
                "frame role slot differs from current physical step",
            )
            per_step.append(state["physics_step"])

    require(per_step == sorted(set(per_step)), "per-step original frames are reordered or repeated")
    require(set(per_step) <= (set(states) - {0}), "per-step frame lacks physical source")
    missing_steps = sorted(set(range(1, raw["total_physics_steps"] + 1)) - set(per_step))
    return {
        "allocated_acquisitions": len(names),
        "reconstructed_acquisitions": len(observations),
        "allocated_acquisitions_without_published_frame": [
            name for name in names if name not in paths
        ],
        "reconstructed_render_passes": passes,
        "roles": dict(roles),
        "per_step_original_count": len(per_step),
        "physical_steps_without_reconstructed_per_step_frame": missing_steps,
    }, raw["total_physics_steps"]


def verify_active(active: list[Any], raw: Any, worker: Any, source: Any) -> dict[str, Any]:
    rows = [row for row in raw["guard_events"] if "outcome" in row]
    eligible = Counter(_tuple(row) for row in rows)
    allowed = Counter(_tuple(row) for row in rows if row["outcome"] == "ALLOWED")
    seen: Counter[tuple[Any, ...]] = Counter()
    receipt_ids: set[str] = set()
    action_samples: list[tuple[int, int, str]] = []
    guard_by_sequence = {row["sequence"]: row for row in rows}
    require(len(guard_by_sequence) == len(rows), "guard source sequence is duplicated")
    previous: int | None = None
    for row in active:
        require(row["lease_id"] == worker["lease_id"], "active checkpoint uses another lease")
        checkpoint = row["checkpoint"]
        require(row["step"] == checkpoint["physics_step"], "active checkpoint has conflicting step")
        bracket = row["current"]
        lower, upper = bracket["lower_ns"], bracket["upper_ns"]
        require(
            type(lower) is int
            and type(upper) is int
            and 0 <= lower <= upper
            and (previous is None or upper >= previous),
            "active owner order or bracket mismatch",
        )
        require(
            bracket["domain"] == source["origin"]["domain"]
            and lower >= source["origin"]["lower_ns"]
            and upper < source["deadline"]["deadline_ns"],
            "active checkpoint left its original owner or task deadline",
        )
        identity = bracket["event_identity"]
        require(
            isinstance(identity, str)
            and bool(identity)
            and identity != source["origin"]["event_identity"]
            and identity not in receipt_ids,
            "active owner receipt identity was reused",
        )
        receipt_ids.add(identity)
        previous = upper
        key = _tuple(checkpoint)
        seen[key] += 1
        require(
            seen[key] <= eligible[key], "active checkpoint is absent from the actual guard ledger"
        )
        if "diagnostic_authorized_monotonic_ns" in row or "guard_sequence" in row:
            sequence = row["guard_sequence"]
            now = row["diagnostic_authorized_monotonic_ns"]
            earlier_sequence, earlier_now, _ = action_samples[-1] if action_samples else (0, 0, "")
            require(
                type(sequence) is int
                and type(now) is int
                and sequence > earlier_sequence
                and now >= earlier_now
                and sequence in guard_by_sequence
                and key == _tuple(guard_by_sequence[sequence]),
                "action-timed worker checkpoint has no exact original guard sequence",
            )
            action_samples.append((sequence, now, guard_by_sequence[sequence]["outcome"]))
    require(
        all(seen[key] >= amount for key, amount in allowed.items()),
        "allowed control did not retain corresponding original worker check",
    )
    return {
        "guard_checkpoints": len(rows),
        "owner_active_checks": len(active),
        "allowed_guard_checkpoints": sum(allowed.values()),
        "rejected_guard_checkpoints": sum(row["outcome"] == "REJECTED" for row in rows),
        "action_owner_timed_checks": len(action_samples),
        "action_owner_guard_allowed": sum(status == "ALLOWED" for _, _, status in action_samples),
        "action_authorization_last_monotonic_ns": max(
            (now for _, now, status in action_samples if status == "ALLOWED"),
            default=None,
        ),
        "action_callback_last_monotonic_ns": action_samples[-1][1] if action_samples else None,
    }


def verify_source(source_root: Path, recipe: Mapping[str, Any], raw: Any) -> dict[str, Any]:
    manifest = recipe["source_hashes"]
    require(
        type(manifest) is dict and manifest and raw["source_hashes"] == manifest,
        "recorder source does not match the development registration",
    )
    for name, value in manifest.items():
        require(
            digest_file(original(source_root, name)) == value, f"frozen source mismatch: {name}"
        )
    return {
        "registered_sources": len(manifest),
        "source_manifest_sha256": canonical_digest(manifest),
    }


def verify_imports(run: Path, source_root: Path, registration_sha: str) -> dict[str, Any]:
    receipt = read_json(run, "imported-source-manifest.json")
    require(
        receipt["registration_sha256"] == registration_sha,
        "imported source manifest belongs to another registration",
    )
    phases = {name: receipt[name] for name in ("before", "after")}
    for phase, modules in phases.items():
        require(type(modules) is dict and modules, f"missing original actual import phase: {phase}")
        for name, record in modules.items():
            file = Path(record["path"])
            require(file.is_absolute(), f"loaded module has no recorded absolute path: {name}")
            selected = original(file.parent, file.name)
            if name == "cloud_edge_robot_arm" or name.startswith("cloud_edge_robot_arm."):
                relative = file.relative_to(source_root)
                require(
                    relative.parts[:2] == ("src", "cloud_edge_robot_arm"),
                    f"loaded project module is outside the frozen project: {name}",
                )
            require(
                digest_file(selected) == record["sha256"],
                f"loaded module bytes disagree with the frozen file: {name}",
            )
    require(
        all(phases["after"].get(name) == record for name, record in phases["before"].items()),
        "loaded project module path or bytes changed across the run",
    )
    required_modules = {
        "cloud_edge_robot_arm.research.native_collection_application",
        "cloud_edge_robot_arm.research.native_full_horizon_recorder",
        "cloud_edge_robot_arm.simulation_runtime.sqlite_repository",
        "cloud_edge_robot_arm.simulation_runtime.worker",
        "cloud_edge_robot_arm.simulation.mujoco.backend",
    }
    require(required_modules <= set(phases["after"]), "required production imports lack a witness")
    return {
        "provenance": "ORIGINAL_ACTUAL_IMPORT_WITNESS_VERIFIED_AGAINST_FROZEN_FILES",
        "file_modules_before": len(phases["before"]),
        "file_modules_after": len(phases["after"]),
        "project_modules_after": sum(
            name.startswith("cloud_edge_robot_arm") for name in phases["after"]
        ),
        "receipt_file_sha256": digest_file(original(run, "imported-source-manifest.json")),
    }


def verify_stop(raw: Any, final_step: int) -> dict[str, Any]:
    tail = raw["guard_events"][-1]
    rejected = tail["kind"] == "FAILURE"
    require(
        tail["physics_step"] == final_step and tail["kind"] in {"FAILURE", "CLOSED"},
        "execution guard has no original closure at the final physical step",
    )
    require(
        not {"stop_error", "stop_error_type"}.intersection(tail),
        "original execution guard recorded a stop failure",
    )
    stops = [
        row
        for row in raw["commands"]
        if row["command_payload"]["type"] == "emergency_stop"
        and row["command_payload"]["accepted"] is True
        and row["command_payload"]["physics_step"] == final_step
    ]
    require(stops, "no accepted emergency stop at final observed physical step")
    stop = stops[-1]
    op_id = int(stop["interval_id"].removeprefix("operation-"))
    source_boundaries = [
        row for row in raw["backend_operation_ledger"] if row["operation_id"] == op_id
    ]
    require(
        [(row["kind"], row["phase"]) for row in source_boundaries]
        == [
            ("COMMAND", "BEGIN"),
            ("COMMAND", "END"),
        ]
        and all(row["error"] is None and row["error_type"] is None for row in source_boundaries),
        "emergency stop command has no complete original backend boundaries",
    )
    require(
        stop["effective_from_step"] > final_step,
        "emergency stop effect was assigned an already observed physical step",
    )
    pre_stop = (
        tail["physics_state"]["estop_engaged"] if rejected and "physics_state" in tail else None
    )
    return {
        "closure": tail["kind"],
        "pre_stop_estop_snapshot": pre_stop,
        "accepted_emergency_stop": True,
        "stop_command_seq": stop["command_seq"],
        "stop_effective_from_step": stop["effective_from_step"],
        "physical_state_at_stop_effective_step": None,
    }


def _integer(value: Any, name: str, *, nullable: bool = False) -> int | None:
    require(
        (nullable and value is None) or (type(value) is int and value >= 0),
        f"invalid original integer: {name}",
    )
    return value


def verify_window(
    original_root: Path,
    diagnostic: Any,
    raw: Any,
    registration_sha: str,
    final_step: int,
    active: Mapping[str, Any],
) -> dict[str, Any]:
    require(
        diagnostic["scope"] == SCOPE
        and type(diagnostic["qualification_credit"]) is int
        and diagnostic["qualification_credit"] == 0
        and diagnostic["registration_sha256"] == registration_sha,
        "diagnostic timing original belongs to another scope or release",
    )
    status = diagnostic["status"]
    require(
        status in {"CUTOFF", "EARLY_STOP", "PREFIX_COMPLETE"}, "unknown development terminal scope"
    )
    require(
        diagnostic["final_physics_step"] == final_step,
        "diagnostic final step contradicts originals",
    )
    start, cutoff, allowed, observed, guard_exit, cleanup = (
        _integer(diagnostic.get(name), name, nullable=True)
        for name in (
            "first_action_started_monotonic_ns",
            "cutoff_monotonic_ns",
            "last_authorized_monotonic_ns",
            "cutoff_observed_monotonic_ns",
            "guard_exit_monotonic_ns",
            "body_cleanup_finished_monotonic_ns",
        )
    )
    rows = [row for row in raw["guard_events"] if "outcome" in row]
    if start is not None:
        require(
            cutoff == start + WINDOW_NS,
            "diagnostic cutoff changed the original eight-second budget",
        )
        pre = read_json(original_root, "shield/step-1-pre-input.json")
        pre_ns = round(pre["context"]["step_started_at"] * 1_000_000_000)
        require(abs(pre_ns - start) <= 1, "diagnostic start disagrees with original Shield PRE")
    else:
        require(
            cutoff is None and allowed is None and observed is None and status == "EARLY_STOP",
            "diagnostic reports a window that was never armed",
        )
    if allowed is not None:
        require(
            start is not None and cutoff is not None and start <= allowed < cutoff,
            "authorization exceeded the eight-second monotonic window",
        )
        latest = next((row for row in reversed(rows) if row["outcome"] == "ALLOWED"), None)
        require(
            latest is not None
            and _tuple(latest) == _tuple(diagnostic["last_authorized_checkpoint"]),
            "last authorization is not present as ALLOWED in the actual guard ledger",
        )
    require(
        allowed == active["action_authorization_last_monotonic_ns"],
        "last action authorization differs from original timed owner checks",
    )
    latest_callback = active["action_callback_last_monotonic_ns"]
    require(
        latest_callback is None or (cutoff is not None and latest_callback < cutoff),
        "a timed callback was authorized after the development cutoff",
    )
    if status == "CUTOFF":
        require(
            cutoff is not None and observed is not None and observed >= cutoff,
            "cutoff rejection preceded the registered deadline",
        )
        reject_indices = [
            index
            for index, row in enumerate(rows)
            if row["outcome"] == "REJECTED"
            and _tuple(row) == _tuple(diagnostic["rejected_checkpoint"])
        ]
        require(
            len(reject_indices) == 1, "cutoff did not retain a unique original REJECTED checkpoint"
        )
        require(
            rows[reject_indices[0]]["physics_step"] == final_step,
            "physical step advanced after the recorded cutoff rejection",
        )
        require(
            not any(row["outcome"] == "ALLOWED" for row in rows[reject_indices[0] + 1 :]),
            "new action authorization followed the cutoff rejection",
        )
    if guard_exit is not None and cleanup is not None:
        require(
            guard_exit <= cleanup and (observed is None or observed <= guard_exit),
            "cutoff, guard exit and cleanup order differs",
        )
    dispatch = _integer(
        diagnostic.get("dispatch_physics_step"), "dispatch_physics_step", nullable=True
    )
    if dispatch is not None:
        require(dispatch <= final_step, "negative physical prefix coverage")
    return {
        "status": status,
        "window_fixed_ns": WINDOW_NS,
        "started_monotonic_ns": start,
        "cutoff_monotonic_ns": cutoff,
        "last_authorized_monotonic_ns": allowed,
        "observed_cutoff_monotonic_ns": observed,
        "guard_exit_monotonic_ns": guard_exit,
        "body_cleanup_finished_monotonic_ns": cleanup,
        "last_authorized_checkpoint": diagnostic.get("last_authorized_checkpoint"),
        "rejected_checkpoint": diagnostic.get("rejected_checkpoint"),
        "dispatch_physics_step": dispatch,
        "physical_prefix_steps": None if dispatch is None else final_step - dispatch,
        "clock_provenance": "MONOTONIC_ORIGINAL_SHIELD_ANCHOR_AND_TIMED_OWNER_ROWS_JOINED_TO_GUARD",
    }


def verify_sqlite_diagnostic(diagnostic: Any, active: Any) -> dict[str, Any]:
    sql = diagnostic["sqlite"]
    keys = (
        "reads_attempted",
        "reads_completed",
        "readonly_snapshots",
        "read_wall_ns",
        "action_reads_attempted",
        "action_reads_completed",
        "action_read_wall_ns",
    )
    for key in keys:
        _integer(sql[key], key)
    require(
        sql["mode"] == "UTC_LEGACY_VETO"
        and sql["reads_completed"] <= sql["reads_attempted"]
        and sql["readonly_snapshots"] <= sql["reads_completed"]
        and sql["action_reads_completed"] <= sql["action_reads_attempted"] <= sql["reads_attempted"]
        and sql["action_reads_completed"] <= sql["reads_completed"]
        and sql["action_read_wall_ns"] <= sql["read_wall_ns"],
        "invalid SQLite counters in original diagnostic",
    )
    require(
        sql["reads_completed"] >= active["owner_active_checks"],
        "SQLite witness cannot account for the retained owner checkpoints",
    )
    return {
        **{key: sql[key] for key in ("mode", *keys)},
        "counts_provenance": "ORIGINAL_PRODUCER_WITNESS_INVENTORY",
        "independent_crosscheck": "DATABASE_WORKER_LEASE_AND_ORIGINAL_GUARD_CHECKPOINT_JOIN",
        "independent_sql_statement_trace": None,
        "per_check_sqlite_time_reconstructed": False,
    }


def read_run(root: Path, source_root: Path) -> dict[str, Any]:
    root, source_root = root.absolute(), source_root.absolute()
    run = root / "run"
    originals = run / "originals"
    protocol = read_json(root, "protocol.json")
    claim = read_json(root, "diagnostic-claim.json")
    registration_sha = verify_registration(protocol, claim, run)
    startup = read_json(run, "startup.json")
    lifecycle = read_json(run, "collection-result.json")
    require(
        startup["application_id"] == claim["application_id"]
        and startup["assignment"]["assignment_id"] == ASSIGNMENT
        and startup["assignment"]["seed"] == SEED
        and lifecycle["assignment_id"] == ASSIGNMENT,
        "claim, startup and lifecycle assignment do not join",
    )
    require(
        startup["role"]["model_requests"] == 0 and startup["role"]["provider"] is None,
        "development worker role requests a task model",
    )
    require(
        lifecycle["native_qualification"] == "UNKNOWN"
        and lifecycle["qualified_group_score"] is None
        and lifecycle["joint_bound_m"] is None
        and lifecycle["execution_admitted"] is False
        and lifecycle["teacher_collection_admitted"] is False,
        "diagnostic reported formal eligibility",
    )
    worker = verified_worker(run, lifecycle)
    require(
        all(
            lifecycle["progress"].get(key) is True
            for key in (
                "backend_shutdown_completed",
                "capture_close_completed",
                "recorder_close_completed",
            )
        )
        and lifecycle["owner_closure"]["completed"] is True,
        "worker omitted native cleanup originals",
    )
    inventory = read_json(originals, "inventory.json")
    files = verify_inventory(originals, inventory)
    needed = {
        "partial-originals.json",
        "active-checks.json",
        "checkpoint-diagnostic.json",
        "source-binding.json",
    }
    require(
        needed <= set(files),
        "original inventory lacks diagnostic, frame, guard or ownership records",
    )
    raw = read_json(originals, "partial-originals.json")
    diagnostic = read_json(originals, "checkpoint-diagnostic.json")
    source = read_json(originals, "source-binding.json")
    require(source["assignment_id"] == ASSIGNMENT, "recorder belongs to another assignment")
    require(
        raw["source_scope"] == SCOPE and source["scope"] == SCOPE,
        "recorder reported a formal or foreign source scope",
    )
    identity = raw["identity"]["owner_identity"]
    require(
        all(
            identity[key] == worker[key]
            for key in ("job_id", "run_id", "lease_id", "worker_id", "attempt")
        ),
        "recorder original is not from the SQLite worker",
    )
    require(
        lifecycle["lifecycle_links"]["originals/inventory.json"]
        == digest_file(original(originals, "inventory.json")),
        "lifecycle points to another inventory",
    )
    final_diagnostic = lifecycle["checkpoint_diagnostic"]
    cleanup_key = "body_cleanup_finished_monotonic_ns"
    require(
        diagnostic["body_cleanup_finished_monotonic_ns"] is None
        and {**final_diagnostic, cleanup_key: None} == diagnostic,
        "lifecycle changed the original checkpoint timing witness",
    )

    recipe = protocol["recipe"]
    environment = protocol["expected_environment"]
    interpreter = Path(environment["interpreter"])
    require(
        environment["source_root"] == str(source_root)
        and environment["mujoco_gl"] == "egl"
        and digest_file(original(interpreter.parent, interpreter.name))
        == environment["interpreter_sha256"]
        and digest_file(
            original(
                source_root, "configs/research/native_registered_single_teacher_p0_20261119.yaml"
            )
        )
        == environment["recipe_config_sha256"],
        "development environment source or interpreter changed",
    )
    verified_source = verify_source(source_root, recipe, raw)
    verified_imports = verify_imports(run, source_root, registration_sha)
    active = verify_active(read_json(originals, "active-checks.json"), raw, worker, source)
    frames, final_step = read_frames(run, recipe, raw, files)
    require(lifecycle["physics_steps"] == final_step, "worker total steps conflict with originals")
    window = verify_window(originals, final_diagnostic, raw, registration_sha, final_step, active)
    stop = verify_stop(raw, final_step)
    sqlite_observed = verify_sqlite_diagnostic(diagnostic, active)
    return {
        "status": "DEVELOPMENT_ORIGINALS_READ",
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "qualification_credit": 0,
        "qualified_group_score": None,
        "joint_bound_m": None,
        "formal_eligibility": False,
        "native_qualification": "UNKNOWN",
        "registration_sha256": registration_sha,
        "claim_file_sha256": digest_file(original(root, "diagnostic-claim.json")),
        "protocol_file_sha256": digest_file(original(root, "protocol.json")),
        "inventory_file_sha256": digest_file(original(originals, "inventory.json")),
        "lifecycle_file_sha256": digest_file(original(run, "collection-result.json")),
        "verified_original_files": len(files),
        "verified_original_bytes": inventory["original_bytes"],
        "source": {**verified_source, "imports": verified_imports},
        "worker": worker,
        "active": active,
        "window": window,
        "stop": stop,
        "frames": frames,
        "physical_steps_including_settle": final_step,
        "sqlite": sqlite_observed,
        "requested_task_model_calls": startup["role"]["model_requests"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="original development registration directory")
    parser.add_argument(
        "--source-root", type=Path, required=True, help="the matching frozen source checkout"
    )
    args = parser.parse_args()
    try:
        report = read_run(args.root, args.source_root)
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        OSError,
        IndexError,
        sqlite3.Error,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "DEVELOPMENT_ORIGINALS_REJECTED_OR_UNAVAILABLE",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "formal_eligibility": False,
                    "qualification_credit": 0,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
