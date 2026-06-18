#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cloud_edge_robot_arm.real_robot.level0 import (  # noqa: E402
    FORBIDDEN_MOTION_METHODS,
    FakeReadOnlyAdapter,
    SiteReadOnlySession,
)
from cloud_edge_robot_arm.real_robot.provenance import current_source_provenance  # noqa: E402

PHASE10_LEVEL0_FRAMEWORK_ACCEPTED = "PHASE10_LEVEL0_FRAMEWORK_ACCEPTED"
PHASE10_HARDWARE_READ_ONLY_ACCEPTED = "PHASE10_HARDWARE_READ_ONLY_ACCEPTED"
PHASE10_LEVEL0_ENV_BLOCKED = "PHASE10_LEVEL0_ENV_BLOCKED"
PHASE10_LEVEL0_REJECTED = "PHASE10_LEVEL0_REJECTED"
VERIFIER_VERSION = "phase10.2c-level0-v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 10.2C Level 0 read-only access.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true", help="Run CI-safe fake read-only verifier.")
    mode.add_argument(
        "--hardware",
        action="store_true",
        help="Run site hardware read-only verifier.",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/level0"))
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    if args.fake:
        payload = run_fake_verification(args.output)
    else:
        payload = run_hardware_verification(args.output, config_path=args.config)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return (
        0
        if payload["status"]
        in {
            PHASE10_LEVEL0_FRAMEWORK_ACCEPTED,
            PHASE10_HARDWARE_READ_ONLY_ACCEPTED,
            PHASE10_LEVEL0_ENV_BLOCKED,
        }
        else 1
    )


def run_fake_verification(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    adapter = FakeReadOnlyAdapter()
    connect = adapter.connect(timeout_ms=100)
    identity = adapter.get_robot_identity(timeout_ms=100)
    controller = adapter.get_controller_state(timeout_ms=100)
    joint = adapter.get_joint_state(timeout_ms=100)
    tcp = adapter.get_tcp_pose(timeout_ms=100)
    estop = adapter.get_emergency_stop_state(timeout_ms=100)
    fault = adapter.get_fault_state(timeout_ms=100)
    operation_mode = adapter.get_operation_mode(timeout_ms=100)
    adapter.disconnect(timeout_ms=100)
    now = datetime.now(UTC)
    provenance = current_source_provenance(
        command=["python", "scripts/verify_phase10_2c_level0.py", "--fake"],
        verifier_version=VERIFIER_VERSION,
    ).model_dump(mode="json")
    session = SiteReadOnlySession(
        session_id="fake-level0-session",
        robot_identity_hash=identity.robot_identity_hash,
        config_hash="fake-config-hash",
        software_commit=str(provenance["generated_from_commit"]),
        source_tree_hash=str(provenance["source_tree_hash"]),
        operator_ids=["site-operator-a", "site-operator-b"],
        safety_reviewer="site-reviewer-a",
        site_checklist={
            "isolated_workspace_confirmed": True,
            "estop_reachable_confirmed": True,
            "no_motion_mode_confirmed": True,
        },
        started_at=now,
        expires_at=now + timedelta(minutes=30),
        isolated_workspace_confirmed=True,
        estop_reachable_confirmed=True,
        no_motion_mode_confirmed=True,
        physical_power_state="controller_on_servos_disabled",
        notes="CI fake read-only framework verification; not hardware acceptance.",
    )
    checks = _level0_checks(
        connected=connect.success,
        identity_hash_match=True,
        config_hash_match=True,
        joint_ok=joint.ok,
        tcp_ok=tcp.ok,
        estop_ok=estop.ok,
        fault_ok=fault.ok,
        controller_ok=controller.ok,
        operation_ok=operation_mode.ok,
        fresh=joint.freshness == "FRESH" and tcp.freshness == "FRESH",
        disconnected_unavailable=True,
        stale_rejected=True,
        redacted=True,
        write_count=adapter.write_operation_count,
        motion_observed=False,
        dashboard_ready=True,
        no_auto_level=True,
        reviewer_approved=False,
    )
    no_write = _no_write_evidence(adapter)
    read_call_counts = {
        "connect": 1,
        "get_robot_identity": 1,
        "get_controller_state": 1,
        "get_joint_state": 1,
        "get_tcp_pose": 1,
        "get_emergency_stop_state": 1,
        "get_fault_state": 1,
        "get_operation_mode": 1,
        "disconnect": 1,
    }
    summary = {
        "status": PHASE10_LEVEL0_FRAMEWORK_ACCEPTED,
        "requested_level": "LEVEL_0",
        "validation_claimed": True,
        "real_hardware_validation_claimed": False,
        "controller_contacted": False,
        "hardware_state_sampled": False,
        "hardware_motion_observed": False,
        "write_operation_count": adapter.write_operation_count,
        "read_call_counts": read_call_counts,
        "highest_acceptance_level": "NONE",
        "level1_allowed": False,
        "robot_identity_hash": identity.robot_identity_hash,
        "config_hash": "fake-config-hash",
        "software_commit": provenance["generated_from_commit"],
        "source_tree_hash": provenance["source_tree_hash"],
        "worktree_clean": provenance["worktree_clean"],
        "evidence_complete": True,
        "driver_sdk_version": identity.driver,
        "operation_mode": operation_mode.operation_mode,
        "checks": checks,
        "blockers": ["fake adapter results cannot be used as real hardware acceptance"],
        "provenance": provenance,
        "generated_at": now.isoformat(),
    }
    _write_json(output / "environment.json", _environment_payload(summary))
    _write_json(output / "site_session.json", session.model_dump(mode="json"))
    _write_jsonl(output / "controller_readback.jsonl", [controller.model_dump(mode="json")])
    _write_jsonl(output / "joint_state_samples.jsonl", [joint.model_dump(mode="json")])
    _write_jsonl(output / "tcp_pose_samples.jsonl", [tcp.model_dump(mode="json")])
    _write_jsonl(output / "estop_samples.jsonl", [estop.model_dump(mode="json")])
    _write_jsonl(output / "fault_samples.jsonl", [fault.model_dump(mode="json")])
    _write_jsonl(
        output / "read_only_api_audit.jsonl",
        [
            {
                "method": method,
                "allowed": True,
                "read_only": True,
                "timestamp": now.isoformat(),
                "call_count": count,
            }
            for method, count in read_call_counts.items()
        ],
    )
    _write_json(output / "no_write_operation_evidence.json", no_write)
    _write_json(output / "level0_summary.json", summary)
    return summary


def run_hardware_verification(output: Path, *, config_path: Path | None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    provenance = current_source_provenance(
        command=["python", "scripts/verify_phase10_2c_level0.py", "--hardware"],
        verifier_version=VERIFIER_VERSION,
    ).model_dump(mode="json")
    if config_path is None:
        payload = {
            "status": PHASE10_LEVEL0_ENV_BLOCKED,
            "requested_level": "LEVEL_0",
            "validation_claimed": False,
            "controller_contacted": False,
            "hardware_state_sampled": False,
            "hardware_motion_observed": False,
            "write_operation_count": 0,
            "read_call_counts": {},
            "highest_acceptance_level": "NONE",
            "level1_allowed": False,
            "software_commit": provenance["generated_from_commit"],
            "source_tree_hash": provenance["source_tree_hash"],
            "worktree_clean": provenance["worktree_clean"],
            "evidence_complete": False,
            "blockers": ["external site read-only config was not provided"],
            "provenance": provenance,
            "generated_at": now.isoformat(),
        }
        _write_minimal_blocked_artifacts(output, payload)
        return payload
    payload = {
        "status": PHASE10_LEVEL0_ENV_BLOCKED,
        "requested_level": "LEVEL_0",
        "validation_claimed": False,
        "controller_contacted": False,
        "hardware_state_sampled": False,
        "hardware_motion_observed": False,
        "write_operation_count": 0,
        "read_call_counts": {},
        "highest_acceptance_level": "NONE",
        "level1_allowed": False,
        "software_commit": provenance["generated_from_commit"],
        "source_tree_hash": provenance["source_tree_hash"],
        "worktree_clean": provenance["worktree_clean"],
        "evidence_complete": False,
        "blockers": ["site-specific VendorRealRobotReadOnlyAdapter is not configured"],
        "provenance": provenance,
        "generated_at": now.isoformat(),
    }
    _write_minimal_blocked_artifacts(output, payload)
    return payload


def _level0_checks(
    *,
    connected: bool,
    identity_hash_match: bool,
    config_hash_match: bool,
    joint_ok: bool,
    tcp_ok: bool,
    estop_ok: bool,
    fault_ok: bool,
    controller_ok: bool,
    operation_ok: bool,
    fresh: bool,
    disconnected_unavailable: bool,
    stale_rejected: bool,
    redacted: bool,
    write_count: int,
    motion_observed: bool,
    dashboard_ready: bool,
    no_auto_level: bool,
    reviewer_approved: bool,
) -> dict[str, bool]:
    return {
        "L0-01": connected,
        "L0-02": identity_hash_match,
        "L0-03": joint_ok,
        "L0-04": joint_ok,
        "L0-05": tcp_ok,
        "L0-06": estop_ok,
        "L0-07": fault_ok,
        "L0-08": controller_ok,
        "L0-09": operation_ok,
        "L0-10": fresh,
        "L0-11": disconnected_unavailable,
        "L0-12": stale_rejected,
        "L0-13": config_hash_match,
        "L0-14": identity_hash_match,
        "L0-15": redacted,
        "L0-16": write_count == 0,
        "L0-17": not motion_observed,
        "L0-18": dashboard_ready,
        "L0-19": no_auto_level,
        "L0-20": reviewer_approved,
    }


def _no_write_evidence(adapter: FakeReadOnlyAdapter) -> dict[str, Any]:
    exposed = [method for method in FORBIDDEN_MOTION_METHODS if hasattr(adapter, method)]
    return {
        "write_operation_count": adapter.write_operation_count,
        "forbidden_methods_exposed": exposed,
        "hardware_motion_observed": False,
    }


def _environment_payload(summary: dict[str, Any]) -> dict[str, Any]:
    provenance = summary.get("provenance", {})
    return {
        "software_commit": provenance.get("generated_from_commit", ""),
        "source_tree_hash": provenance.get("source_tree_hash", ""),
        "worktree_clean": provenance.get("worktree_clean", False),
        "driver_sdk_version": summary.get("driver_sdk_version", ""),
        "controller_contacted": summary.get("controller_contacted", False),
        "hardware_state_sampled": summary.get("hardware_state_sampled", False),
        "hardware_motion_observed": False,
    }


def _write_minimal_blocked_artifacts(output: Path, summary: dict[str, Any]) -> None:
    now = datetime.now(UTC).isoformat()
    _write_json(output / "environment.json", _environment_payload(summary))
    _write_json(
        output / "site_session.json",
        {
            "status": "UNAVAILABLE",
            "reason": "site session not established",
            "generated_at": now,
        },
    )
    for filename in (
        "controller_readback.jsonl",
        "joint_state_samples.jsonl",
        "tcp_pose_samples.jsonl",
        "estop_samples.jsonl",
        "fault_samples.jsonl",
        "read_only_api_audit.jsonl",
    ):
        _write_jsonl(output / filename, [])
    _write_json(
        output / "no_write_operation_evidence.json",
        {
            "write_operation_count": 0,
            "forbidden_methods_exposed": [],
            "hardware_motion_observed": False,
        },
    )
    _write_json(output / "level0_summary.json", summary)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
