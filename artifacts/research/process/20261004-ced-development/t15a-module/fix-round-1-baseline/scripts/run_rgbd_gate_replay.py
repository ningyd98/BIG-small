"""固定机会离线回放入口；正式来源未集成时只允许显式软件夹具。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec, OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract, VisualEvidence
from cloud_edge_robot_arm.edge.evidence.opportunities import Opportunity, summarize_gate_replay
from cloud_edge_robot_arm.research.protocol import load_protocol
from cloud_edge_robot_arm.research.runner import run_gate_replay
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _opportunity(payload: dict[str, Any]) -> Opportunity:
    values = dict(payload)
    observation = RGBDObservation.model_validate(values["observation"])
    action = dict(values["action_contract"])
    evidence = dict(action.pop("evidence"))
    evidence["captured_at"] = datetime.fromisoformat(evidence["captured_at"])
    action["evidence"] = VisualEvidence(**evidence)
    for name in ("preconditions", "postconditions"):
        action[name] = [ConditionSpec(**condition) for condition in action[name]]
    values["action_contract"] = ActionEvidenceContract(**action)
    values["observation"] = observation
    values["replay_at"] = datetime.fromisoformat(values["replay_at"])
    if values.get("online_evidence") is not None:
        online = dict(values["online_evidence"])
        online["observation"] = RGBDObservation.model_validate(online["observation"])
        online["robot_state"] = RobotState.model_validate(online["robot_state"])
        values["online_evidence"] = OnlineEvidenceSnapshot(**online)
    return Opportunity(**values)


def main(argv: list[str] | None = None) -> int:
    """保存所有固定机会判定；显式软件回放不计正式 G3 或物理成功。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--method", choices=("JOINT", "B3"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--software-fixture", action="store_true")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "report.json").exists():
        raise ValueError("existing gate replay evidence is preserved")
    summary: dict[str, Any] = {
        "schema_version": "ced.gate-replay.v1",
        "status": "NOT_RUN",
        "replayed_opportunities": 0,
        "method_id": args.method,
        "formal_source_accepted": False,
        "physical_success": 0,
    }
    exit_code = 3
    try:
        if not args.software_fixture:
            if args.protocol is None:
                raise ValueError("formal gate replay requires a FINAL protocol")
            load_protocol(args.protocol).require_formal()
            raise ValueError("formal G3 source acceptance verifier is not integrated")
        payload = json.loads(args.opportunities.read_text())
        if payload.get("schema_version") != "ced.opportunity-set.v1":
            raise ValueError("unsupported fixed opportunity artifact schema")
        raw = payload["opportunities"]
        if payload.get("content_hash") != content_digest(raw):
            raise ValueError("fixed opportunity artifact hash mismatch")
        values = [_opportunity(value) for value in raw]
        records = run_gate_replay(values, args.method)
        (args.output / "gate-records.json").write_text(
            canonical_json(
                {
                    "schema_version": "ced.gate-records.v1",
                    "evidence_kind": "MOCK",
                    "source_hash": payload["content_hash"],
                    "records": [asdict(row) for row in records],
                }
            )
            + "\n"
        )
        summary.update(
            status="SOFTWARE_ONLY",
            replayed_opportunities=len(records),
            evidence_kind="MOCK",
            metrics=summarize_gate_replay(values, records),
        )
        exit_code = 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary["reasons"] = [str(error)]
    (args.output / "report.json").write_text(canonical_json(summary) + "\n")
    print(canonical_json(summary))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
