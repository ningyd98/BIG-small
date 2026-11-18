"""Collect opt-in Mock lifecycle evidence separately from Phase 12 physical evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cloud_edge_robot_arm.final_evaluation import registry as evaluation_registry  # noqa: E402
from cloud_edge_robot_arm.final_evaluation import validation  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.adapters import simulation_runtime  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.adapters.base import Phase12RunContext  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.adapters.simulation_runtime import (  # noqa: E402
    Phase11RuntimeAdapter,
)
from cloud_edge_robot_arm.final_evaluation.models import Phase12Backend  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.provenance import git_commit  # noqa: E402


def source_identity() -> dict[str, Any]:
    """Bind the script checkout and the implementation actually imported in this process."""
    paths = (
        Path(__file__).resolve(),
        Path(simulation_runtime.__file__).resolve(),
        Path(evaluation_registry.__file__).resolve(),
    )
    if any(not path.is_relative_to(ROOT) for path in paths):
        raise ValueError("lifecycle implementation was imported outside the script checkout")
    return {
        "commit": git_commit(ROOT),
        "files": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON source key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite JSON source value: " + value)


def _camera_block_clauses(value: str) -> bool:
    # These are the probe stages and camera error emitted by the registered
    # Mock/RGB-D runtime. A mention or denial of the code is not a block receipt.
    message = (
        r"(?:RuntimeError:\s*)?RGBD_CAMERA_REQUIRED"
        r"(?:: select MuJoCo or Isaac; Mock is legacy only)?"
    )
    stages: set[str] = set()
    for clause in re.split(r";\s*(?=(?:main|recovery|duplicate):)", value):
        match = re.fullmatch(r"(main|recovery|duplicate):\s*" + message, clause)
        if match is None or match[1] in stages:
            return False
        stages.add(match[1])
    return stages == {"main", "recovery", "duplicate"}


def read_original_rows(raw: bytes, *, count: int) -> list[dict[str, Any]]:
    """Validate the whole source cohort before selecting rows or starting an executor."""
    parsed = [
        json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        for line in raw.splitlines()
        if line.strip()
    ]
    if any(type(row) is not dict for row in parsed):
        raise ValueError("source rows must be JSON objects")
    originals = [
        row
        for row in parsed
        if row.get("experiment_id") == "F20_STRESS_AND_RECOVERY" and row.get("backend") == "MOCK"
    ]
    seen: set[str] = set()
    definitions = [
        definition
        for definition in evaluation_registry.final_experiment_registry()
        if definition.experiment_id == "F20_STRESS_AND_RECOVERY"
    ]
    scenarios = {scenario for definition in definitions for scenario in definition.scenario_ids}
    modes = {mode for definition in definitions for mode in definition.control_modes}
    backends = {backend.value for definition in definitions for backend in definition.backends}
    for row in originals:
        identity = row.get("run_id")
        if type(identity) is not str or not identity.strip() or identity in seen:
            raise ValueError("source F20 rows require unique nonempty run IDs")
        seen.add(identity)
        if (
            row.get("profile") != "validation"
            or row.get("backend") not in backends
            or row.get("status") != "BLOCKED_BY_ENV"
            or row.get("runtime_invoked") is not False
            or row.get("runtime_completed") is not False
            or ("actual_runner_invoked" in row and row["actual_runner_invoked"] is not False)
            or not isinstance(row.get("failure_type"), str)
            or not _camera_block_clauses(row["failure_type"])
        ):
            raise ValueError(
                "source F20 rows must prove a camera block before any runtime execution"
            )
        if (
            type(row.get("scenario_id")) is not str
            or row["scenario_id"] not in scenarios
            or type(row.get("control_mode")) is not str
            or row.get("control_mode") not in modes
            or any(
                type(row.get(key)) is not int or not 0 <= row[key] < 2**31
                for key in ("seed", "repetition")
            )
        ):
            raise ValueError("source F20 scenario and sampling fields are incomplete or invalid")
    if len(originals) < count:
        raise ValueError("not enough original F20 Mock rows for the requested count")
    return originals[:count]


def run_supplement(
    *,
    output: Path,
    source_rows: Path | None = None,
    count: int = 1,
) -> dict[str, Any]:
    """Use the real runtime adapter; never amend an original row or authoritative summary."""
    if type(count) is not int or not 1 <= count <= 18:
        raise ValueError("supplement count must be an integer from 1 to 18")
    source_hash = None
    if source_rows is not None:
        raw = source_rows.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()
        originals = read_original_rows(raw, count=count)
    else:
        originals = [
            {
                "run_id": None,
                "scenario_id": "S01_NORMAL_STATIC",
                "control_mode": "PCSC",
                "seed": index,
                "repetition": 0,
            }
            for index in range(count)
        ]
    identity = source_identity()
    output.mkdir(parents=True, exist_ok=False)
    adapter = Phase11RuntimeAdapter(lifecycle_only=True)
    rows = []
    started = time.monotonic()
    for index, original in enumerate(originals[:count], 1):
        new_id = f"phase12-lifecycle-{index:05d}"
        context = Phase12RunContext(
            run_id=new_id,
            experiment_id="F20_STRESS_AND_RECOVERY",
            scenario_id=original["scenario_id"],
            backend=Phase12Backend.MOCK,
            control_mode=original["control_mode"],
            seed=original["seed"],
            repetition=original["repetition"],
            output_root=output,
        )
        result = adapter.run(context)
        path = output / result.source_artifact_path
        receipt = json.loads(path.read_bytes())
        probes = [
            receipt["main_job"],
            receipt["recovery_evidence"],
            receipt["duplicate_competition_evidence"],
        ]
        checks = {
            "runtime_returned": result.runtime_invoked
            and result.runtime_completed
            and result.status == "SUCCESS",
            "receipt_hash": hashlib.sha256(path.read_bytes()).hexdigest()
            == result.source_artifact_hash
            and validation._runtime_receipt_internal_hash_valid(receipt),
            "recovery": validation._recovery_evidence_valid(receipt),
            "duplicate_competition": validation._duplicate_competition_evidence_valid(receipt),
            "terminal_artifacts": validation._terminal_artifact_paths_valid(receipt),
            "executors_and_artifacts": all(
                all(
                    probe["execution_evidence"].get(key) is True
                    for key in (
                        "executor_invoked",
                        "executor_returned",
                        "evidence_valid",
                        "artifacts_verified",
                        "attempt_completed",
                        "lease_released",
                    )
                )
                for probe in probes
            ),
            "software_scope": receipt["validation_scope"] == "SOFTWARE_LIFECYCLE_ONLY"
            and result.authoritative_for_thesis is False
            and receipt["real_controller_contacted"]
            is receipt["hardware_motion_observed"]
            is False,
        }
        row = {
            "original_run_id": original["run_id"],
            "new_run_id": new_id,
            "source_artifact_path": result.source_artifact_path,
            "source_artifact_hash": result.source_artifact_hash,
            "checks": checks,
            "status": str(result.status),
            "failure_type": result.failure_type,
        }
        rows.append(row)
        (output / f"row-{index:02d}.json").write_text(json.dumps(row, indent=2) + "\n")
    complete = all(all(row["checks"].values()) for row in rows)
    summary = {
        "schema_version": "phase12.lifecycle-supplement.v1",
        "status": "SOFTWARE_LIFECYCLE_EVIDENCE_COMPLETE" if complete else "SOFTWARE_LIFECYCLE_GAP",
        "scope": "SOFTWARE_LIFECYCLE_ONLY",
        "source_commit": identity["commit"],
        "source_identity": identity,
        "source_kind": "LINKED_BLOCKED_F20" if source_rows is not None else "STANDALONE_PROBE",
        "original_rows_sha256": source_hash,
        "count": len(rows),
        "rows": rows,
        "elapsed_s": time.monotonic() - started,
        "full_profile_execution": "NOT_RUN",
        "physical_qualification": "NOT_GRANTED",
        "formal_research": "NOT_ACCEPTED",
        "authoritative_thesis_run_count": 0,
        "hardware_dispatch": False,
        "paid_model_calls": 0,
    }
    (output / "supplement-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-rows", type=Path)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args(argv)
    result = run_supplement(output=args.output, source_rows=args.source_rows, count=args.count)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return 0 if result["status"] == "SOFTWARE_LIFECYCLE_EVIDENCE_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
