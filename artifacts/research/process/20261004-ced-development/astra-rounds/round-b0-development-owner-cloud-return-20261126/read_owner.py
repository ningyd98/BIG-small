"""Read only the closed diagnostic SQLite owner and compare the sealed boundary."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / "plan.json").read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def db_path(folder, name):
    paths = list((folder / "worker-runtime").glob(f"*/{name}"))
    need(len(paths) == 1, f"{name} must identify one owner")
    wal = paths[0].with_name(name + "-wal")
    need(not wal.exists() or wal.stat().st_size == 0, "unsealed nonempty SQLite WAL")
    return paths[0]


def rows(connection, query):
    return [dict(row) for row in connection.execute(query)]


def select(con, table):
    return rows(con, "SELECT * FROM " + table)


def one(items, name):
    need(len(items) == 1, f"expected exactly one {name}")
    return items[0]


def from_sqlite(folder):
    result = {}
    for name, tables in (
        ("jobs.sqlite", ("simulation_jobs", "simulation_job_leases", "simulation_job_attempts")),
        (
            "events.sqlite",
            (
                "visual_bootstraps",
                "visual_original_plans",
                "visual_owner_publications",
                "visual_verification_routes",
            ),
        ),
    ):
        path = db_path(folder, name)
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        ) as con:
            con.row_factory = sqlite3.Row
            need(con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check")
            for table in tables:
                result[table] = select(con, table)
        result[name] = sha(path)
    job = one(result["simulation_jobs"], "job")
    lease = one(result["simulation_job_leases"], "lease")
    attempt = one(result["simulation_job_attempts"], "attempt")
    boot = one(result["visual_bootstraps"], "bootstrap")
    payload = json.loads(boot["payload_json"])
    lease_source = payload["definition"]["lease"]
    need(
        job["job_id"]
        == lease["job_id"]
        == attempt["job_id"]
        == boot["job_id"]
        == lease_source["job_id"]
        and job["run_id"] == attempt["run_id"] == boot["run_id"] == lease_source["run_id"]
        and job["worker_id"]
        == lease["worker_id"]
        == attempt["worker_id"]
        == lease_source["worker_id"]
        and job["lease_id"] == lease["lease_id"] == lease_source["lease_id"]
        and attempt["attempt"] == lease_source["attempt"] == 1
        and job["status"] == attempt["result"] == "FAILED"
        and datetime.fromisoformat(lease["acquired_at"])
        <= datetime.fromisoformat(attempt["started_at"])
        <= datetime.fromisoformat(attempt["ended_at"])
        <= datetime.fromisoformat(lease["released_at"])
        <= datetime.fromisoformat(lease["expires_at"]),
        "source identity or lease closure differs",
    )
    return result, payload, boot, job, lease, attempt


def stage_a(root):
    result, payload, boot, job, lease, attempt = from_sqlite(root / "A")
    source = Path(PLAN["frozen_scene"]) / "capture/step-0120/observation.json"
    need(sha(source) == PLAN["evidence_sha256"][str(source)], "original observation hash changed")
    old = read(source)
    pending = payload["pending"]
    history = [event["request"]["kind"] for event in payload["history"]]
    need(
        payload["revision"] == 1
        and history == ["RESERVE_INITIAL_CAPTURE"]
        and old["episode_id"] == boot["episode_id"]
        and old["calibration_version"]
        and pending["effect"] == "CAPTURE"
        and payload["observation"] is None
        and payload["draft"] is None
        and payload["adopted_original_hash"] is None,
        "A did not preserve the live uncompleted source",
    )
    need(
        datetime.fromisoformat(old["captured_at"])
        < datetime.fromisoformat(pending["claimed_at"])
        < datetime.fromisoformat(attempt["ended_at"]),
        "original exposure did not predate claim",
    )
    for table in (
        "visual_original_plans",
        "visual_owner_publications",
        "visual_verification_routes",
    ):
        need(not result[table], f"A unexpectedly reached {table}")
    log = root / "stage-a.log"
    exterior = "RuntimeError: source claim is stale or historical; no effect replay allowed"
    need(log.read_text().rstrip().endswith(exterior), "actual A RuntimeError not identified")
    return {
        "stage": "A",
        "plan_sha256": sha(HERE / "plan.json"),
        "pass": True,
        "job_status": job["status"],
        "bootstrap_revision": payload["revision"],
        "captured_at": old["captured_at"],
        "claimed_at": pending["claimed_at"],
        "pending_claim_id": pending["claim_id"],
        "actual_exception": exterior,
        "bottom_gate_evidence": "Capture predates live claim; no committed completion.",
        "original_plan_count": 0,
        "lease_released_at": lease["released_at"],
        "closed_database_sha256": {name: result[name] for name in ("jobs.sqlite", "events.sqlite")},
        "log_sha256": sha(log),
        "driver_sha256": sha(root / "stage-a-run_owner.py"),
    }


def stage_b(root):
    from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import (
        SQLiteEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
        record_binding_valid,
        validate_group,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
        current_supervision_publication,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
        current_models_exact,
    )

    folder = root / "B"
    result, payload, boot, job, lease, attempt = from_sqlite(folder)
    original = one(result["visual_original_plans"], "original")
    publication = one(result["visual_owner_publications"], "owner publication")
    post = json.loads(publication["payload_json"])
    source_observation = payload["observation"]
    original_payload = json.loads(original["payload_json"])
    history = [e.get("request", {}).get("kind", "PROMOTION") for e in payload["history"]]
    need(
        history
        == [
            "RESERVE_INITIAL_CAPTURE",
            "COMPLETE_CAPTURE",
            "RESERVE_PLAN",
            "COMPLETE_PLAN",
            "PROMOTION",
        ],
        "wrong actual bootstrap history",
    )
    need(
        original["original_hash"] == payload["adopted_original_hash"] == post["original_plan_hash"]
        and original_payload["identity"]["episode_id"]
        == boot["episode_id"]
        == source_observation["episode_id"]
        and post["grounding"] is None,
        "original and publication do not match capture",
    )
    need(
        datetime.fromisoformat(payload["history"][0]["committed_at"])
        <= datetime.fromisoformat(source_observation["captured_at"])
        <= datetime.fromisoformat(payload["history"][1]["committed_at"]),
        "fresh exposure outside committed claim window",
    )
    path = db_path(folder, "events.sqlite")
    with closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    ) as con:
        con.row_factory = sqlite3.Row
        # Run repository row readers without its initializer or any schema/write operations.
        repo = object.__new__(SQLiteEventAutonomyRepository)
        repo._conn = con
        task_id = original["task_id"]
        durable = repo._visual_record_locked(task_id)
        original_model = repo._visual_original_locked(task_id, 1)
        active, checkpoint, pool, retry = repo._visual_verification_group_locked(task_id)
        need(
            repo._visual_versions_match(original_model)
            and not repo._replan_cancelled_locked(task_id),
            "versions/cancellation fail the independent join",
        )
        validate_group(original_model, active, checkpoint, pool, retry)
        need(record_binding_valid(durable, original_model, None), "publication hash failed")
        need(
            not current_models_exact(active) and current_models_exact(checkpoint, retry),
            "first active source failure changed",
        )
        need(
            not current_supervision_publication(
                durable,
                original_model,
                active,
                checkpoint,
                pool,
                retry,
                None,
                now=datetime.fromisoformat(post["published_at"]),
            ),
            "publication unexpectedly passes the observer source check",
        )
        missing_step_keys = [
            sorted(set(type(step).model_fields) - set(step.model_dump(mode="json")))
            for step in active.contract.steps
        ]
        need(
            missing_step_keys == [["metadata"]] * 8
            and all(step.metadata is None for step in active.contract.steps),
            "unexpected strict nested-model difference",
        )
        need(
            con.execute("SELECT count(*) FROM visual_supervision").fetchone()[0] == 0,
            "supervision persisted unexpectedly",
        )
    need(
        not result["visual_verification_routes"]
        and read(folder / "policy.json")["advance_physics_during_wait"] is True,
        "durable CLOUD_RETURN evidence or unexpected entry path",
    )
    archive = folder / "raw_episode_v3"
    raw_receipt = read(archive / "raw-artifacts.json")
    for name, expected in raw_receipt["file_hashes"].items():
        need(sha(archive / name) == expected, f"raw member changed: {name}")
    ledger = read(archive / "allocation-ledger.json")
    operation = ledger["backend_operation_ledger"]
    ended = [(r["kind"], r["physics_step"]) for r in operation if r["phase"] == "END"]
    captures = [step for name, step in ended if name == "CAPTURE"]
    steps = [step for name, step in ended if name == "PHYSICS"]
    controls = [step for name, step in ended if name == "CONTROL"]
    need(
        ledger["actual_observed_reset"]
        and ledger["source_binding"] == "UNBOUND"
        and captures == [0, 120, 120]
        and steps == list(range(1, 121))
        and len(controls) == 120
        and not ledger["observer_failures"]
        and not any(item["error"] is not None for item in operation)
        and not ledger["allocated_action_span_ids"]
        and not any(name == "COMMAND" for name, _ in ended),
        "recorded diagnostic exceeds its action/step budget",
    )
    frame = read(archive / "frames/acquisition-3/source-frame.json")["observation"]
    need(
        frame["frame_id"] == source_observation["frame_id"]
        and frame["checksum_sha256"] == source_observation["checksum_sha256"],
        "native first explicit frame not bound by bootstrap",
    )
    return {
        "stage": "B",
        "job_status": job["status"],
        "lease_released_at": lease["released_at"],
        "original_plan_hash": original["original_hash"],
        "checkpoint_hash": post["checkpoint"]["checkpoint_hash"],
        "owner_revision": publication["owner_revision"],
        "bootstrap_history": history,
        "native_capture_steps": captures,
        "normal_settle_control_updates": len(controls),
        "settle_steps": len(steps),
        "raw_acquisitions": raw_receipt["allocated_acquisitions"],
        "raw_action_spans": raw_receipt["allocated_actions"],
        "raw_source_consistency": raw_receipt["source_consistency"],
        "recorded_backend_command_count": 0,
        "supervision_registered": False,
        "cloud_return": "NOT_REACHED",
        "pre_safety": "NOT_REACHED",
        "pre_skill": "NOT_REACHED",
        "grounding": None,
        "runtime_gate_records": "UNAVAILABLE",
        "strict_roundtrip_missing_nullable_step_fields": missing_step_keys,
        "replayed_owner_source_available_at_publication_clock": False,
        "log_sha256": sha(root / "stage-b.log"),
        "closed_database_sha256": {name: result[name] for name in ("jobs.sqlite", "events.sqlite")},
        "raw_manifest_sha256": sha(archive / "raw-artifacts.json"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("A", "B"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(PLAN["private_output"])
    output = (stage_a if args.stage == "A" else stage_b)(root)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(output, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    main()
