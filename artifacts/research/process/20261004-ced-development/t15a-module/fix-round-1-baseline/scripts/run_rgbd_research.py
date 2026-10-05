"""正式研究入口与断点记录；真实运行方法未接入时保留全部 BLOCKED。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
from cloud_edge_robot_arm.research.assignments import build_assignments, episode_record_from_payload
from cloud_edge_robot_arm.research.protocol import load_protocol
from cloud_edge_robot_arm.research.runner import run_assignment


def main(argv: list[str] | None = None) -> int:
    """验证固定分配并保存原始记录；缺正式前置时返回非零状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/research/formal.yaml"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--pools", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "report.json"
    if report_path.exists() and not args.resume:
        raise ValueError("existing research output is preserved; use explicit --resume")
    summary: dict[str, Any] = {
        "schema_version": "ced.research-run.v1",
        "status": "NOT_RUN",
        "assigned_denominator": 0,
        "executed_assignments": 0,
        "physical_success": 0,
        "real_runtime_integrated": False,
        "reasons": [],
    }
    try:
        protocol = load_protocol(args.protocol)
        protocol.require_formal()
        settings = yaml.safe_load(args.config.read_text())
        if not isinstance(settings, dict) or set(settings) != {"schema_version", "methods"}:
            raise ValueError("formal config cannot override protocol thresholds, pools or N")
        if settings["schema_version"] != "ced.formal.v1" or (
            not isinstance(settings["methods"], list)
        ):
            raise ValueError("unsupported formal config schema")
        if args.pools is None:
            raise ValueError("full frozen scene pools artifact is required via --pools")
        pools = json.loads(args.pools.read_text())
        rows = pools.get("formal") if isinstance(pools, dict) else None
        if not isinstance(rows, list):
            raise ValueError("formal pool source missing")
        assignments = build_assignments(protocol, settings["methods"], scene_pool=rows)
        manifest = {
            "schema_version": "ced.assignments.v1",
            "protocol_hash": protocol.content_hash,
            "assignments": [asdict(value) for value in assignments],
        }
        manifest["content_hash"] = content_digest(manifest)
        manifest_path = args.output / "assignments.json"
        if manifest_path.exists():
            if not args.resume or json.loads(manifest_path.read_text()) != manifest:
                raise ValueError("resume assignments differ from frozen manifest")
        else:
            manifest_path.write_text(canonical_json(manifest) + "\n")
        record_path = args.output / "records.jsonl"
        completed = {}
        if record_path.exists():
            if not args.resume:
                raise ValueError("existing original records require explicit resume")
            for line in record_path.read_text().splitlines():
                record = episode_record_from_payload(json.loads(line))
                key = record.assignment.assignment_id
                if key in completed:
                    raise ValueError("duplicate original run record")
                completed[key] = record
        expected = {value.assignment_id: value for value in assignments}
        if any(
            key not in expected or record.assignment != expected[key]
            for key, record in completed.items()
        ):
            raise ValueError("resume record identity differs from frozen assignments")
        with record_path.open("a") as stream:
            for assignment in assignments:
                if assignment.assignment_id in completed:
                    continue
                record = run_assignment(assignment, protocol)
                stream.write(canonical_json(record.to_payload()) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                completed[assignment.assignment_id] = record
        summary.update(
            status="BLOCKED",
            assigned_denominator=len(assignments),
            recorded_assignments=len(completed),
            protocol_hash=protocol.content_hash,
            blocked_assignments=sum(
                record.run_status == "BLOCKED" for record in completed.values()
            ),
            reasons=["actual research runtime and accepted source verification are not integrated"],
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary["reasons"] = [str(error)]
    # A resume recomputes only the summary, preserving all original assignments/records.
    report_path.write_text(canonical_json(summary) + "\n")
    print(canonical_json(summary))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
