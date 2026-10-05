"""Foundation pilot report; absent baseline successes block timeout freeze."""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, canonical_json, content_digest
from cloud_edge_robot_arm.research.network import NetworkSchedule
from cloud_edge_robot_arm.research.protocol import NETWORKS, STRATA

B0_PERIODS = (0.5, 1.0, 2.0, 5.0)
PILOT_POOL_SIZES = {
    "selection": 120,
    "foundation": 120,
    "power": 120,
    "formal": 2400,
    "recovery": 200,
    "ood": 300,
}
BUDGET_SELECTION_RULE = {
    "schema_version": "ced.pilot-selection-rule.v1",
    "periods_s": list(B0_PERIODS),
    "minimum_nominal_success": 0.9,
    "minimum_overall_success": 0.8,
    "maximum_safety_violation": 0.01,
    "rank": ["cloud_requests_total", "mean_wall_duration_s", "fixed_period_order"],
    "tcap": "ceil(2*P99(successful_B0_wall_seconds)/10)*10 clamped to [120,600]",
    "all_assigned_denominator": True,
}


def stage_source_paths() -> list[Path]:
    """Full collector inventory; a caller cannot narrow source attestation."""
    return [
        *sorted(Path("src/cloud_edge_robot_arm").rglob("*.py")),
        *sorted(Path("scripts").rglob("*.py")),
        *sorted(Path("configs/research").glob("*.yaml")),
        Path("assets/robots/franka_panda/scene.xml"),
        Path("pyproject.toml"),
    ]


def validate_pilot_pools(pools: Mapping[str, Any]) -> None:
    """Validate the entire frozen topology before using any developmental pool."""
    if set(pools) != set(PILOT_POOL_SIZES):
        raise ValueError("v2 pilot requires all six complete isolated pools")
    groups: set[str] = set()
    for name, count in PILOT_POOL_SIZES.items():
        rows = pools[name]
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError(f"incomplete {name} pool")
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise ValueError("pool assignment must be an object")
            scene = SceneSpec.model_validate(row["scene"])
            if row["assignment_id"] != f"{name}-{index + 1:04d}" or (
                row["stratum_id"] != STRATA[index % len(STRATA)]
                or row["scene_hash"] != scene.scene_hash
                or not isinstance(row.get("perturbation"), Mapping)
            ):
                raise ValueError("full pool assignment identity/scene/stratum drift")
            if scene.group_id in groups:
                raise ValueError("cross-pool scene group leakage")
            groups.add(scene.group_id)


def build_pilot_assignments(
    pools: Mapping[str, Any],
    stage: str,
    *,
    role_bundle_hash: str | None = None,
    period_s: float | None = None,
    seed: int = 20261004,
) -> list[dict[str, Any]]:
    """Full paired scenes/schedules; order is randomized once and then persisted."""
    validate_pilot_pools(pools)
    if stage not in {"selection", "foundation", "power"}:
        raise ValueError("unsupported explicit pilot stage")
    if period_s is not None and period_s not in B0_PERIODS:
        raise ValueError("unsupported B0 period")
    if role_bundle_hash is not None and (
        len(role_bundle_hash) != 64
        or any(char not in "0123456789abcdef" for char in role_bundle_hash)
    ):
        raise ValueError("role bundle hash must be SHA256")
    periods = B0_PERIODS if stage == "selection" else (period_s,)
    assignments = []
    pools_hash = content_digest(pools)
    for base in pools[stage]:
        scene = SceneSpec.model_validate(base["scene"])
        rtt = int(base["stratum_id"].split("RTT")[1])
        schedule = NetworkSchedule(
            schedule_id=base["assignment_id"],
            rtt_ms=rtt,
            loss_rate=dict(NETWORKS)[rtt],
            seed=scene.seed,
        ).model_dump(mode="json")
        for period in periods:
            identity = base["assignment_id"] + (
                f"::B0@{period:g}"
                if period is not None
                else (
                    "::METHODS_NOT_INTEGRATED" if stage == "power" else "::B0_PERIOD_NOT_SELECTED"
                )
            )
            assignments.append(
                {
                    "assignment_id": identity,
                    "stage": stage,
                    "stratum_id": base["stratum_id"],
                    "group_id": scene.group_id,
                    "scene_hash": scene.scene_hash,
                    "physics_seed": scene.seed,
                    "base_assignment": json.loads(canonical_json(base)),
                    "network_schedule": schedule,
                    "period_s": period,
                    "role_bundle_hash": role_bundle_hash,
                    "pools_hash": pools_hash,
                }
            )
    random.Random(f"{seed}:{stage}").shuffle(assignments)
    return assignments


def choose_b0_period(
    assignments: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pure software diagnostic. Actual selection requires separate raw-source audit."""
    expected = {row["assignment_id"]: row for row in assignments}
    actual = {row["assignment_id"]: row for row in records}
    if (
        len(assignments) != 480
        or len(expected) != 480
        or len(records) != len(actual)
        or (set(expected) != set(actual))
    ):
        raise ValueError("selection must retain all 120 groups across all four periods")
    periods = []
    for period in B0_PERIODS:
        assigned = [r for r in assignments if r["period_s"] == period]
        if len(assigned) != 120 or Counter(r["stratum_id"] for r in assigned) != (
            Counter({s: 10 for s in STRATA})
        ):
            raise ValueError("selection periods must retain fixed twelve-stratum coverage")
        rows = [actual[row["assignment_id"]] for row in assigned]
        for row in rows:
            if (
                type(row.get("success")) is not bool
                or type(row.get("safety_violation")) is not bool
            ):
                raise ValueError("selection outcomes require explicit measured boolean outcomes")
            if any(
                type(row.get(key)) not in {int, float}
                or (not math.isfinite(row[key]) or row[key] < 0)
                for key in ("wall_duration_s", "cloud_requests")
            ) or (type(row["cloud_requests"]) is not int):
                raise ValueError(
                    "selection costs require finite durations and actual integer counts"
                )
        nominal = [
            actual[r["assignment_id"]] for r in assigned if r["stratum_id"].startswith("STATIC")
        ]
        overall = sum(r["success"] for r in rows) / 120
        nominal_rate = sum(r["success"] for r in nominal) / 40
        safety = sum(r["safety_violation"] for r in rows) / 120
        eligible = nominal_rate >= 0.9 and overall >= 0.8 and safety <= 0.01
        periods.append(
            {
                "period_s": period,
                "assigned_denominator": 120,
                "nominal_denominator": 40,
                "overall_success_rate": overall,
                "nominal_success_rate": nominal_rate,
                "safety_violation_rate": safety,
                "cloud_requests_total": sum(r["cloud_requests"] for r in rows),
                "mean_wall_duration_s": sum(r["wall_duration_s"] for r in rows) / 120,
                "eligible": eligible,
                "terminal_status_counts": dict(Counter(r["status"] for r in rows)),
            }
        )
    qualified = [row for row in periods if row["eligible"]]
    chosen = (
        min(
            qualified,
            key=lambda r: (
                r["cloud_requests_total"],
                r["mean_wall_duration_s"],
                B0_PERIODS.index(r["period_s"]),
            ),
        )
        if qualified
        else None
    )
    return {
        "scope": "SOFTWARE_ONLY",
        "actual_research_status": "NOT_RUN",
        "selected_period_s": None,
        "diagnostic_selected_period_s": chosen["period_s"] if chosen else None,
        "diagnostic_status": "FEASIBLE" if chosen else "NO_FEASIBLE_BASELINE",
        "periods": periods,
        "selection_rule_hash": content_digest(BUDGET_SELECTION_RULE),
    }


def run_pilot_stage(
    stage: str,
    pools: Mapping[str, Any],
    output: Path,
    *,
    period_s: float | None = None,
    role_bundle_hash: str | None = None,
    software_only: bool = False,
    software_adapter: Callable[[Mapping[str, Any], Path], Mapping[str, Any]] | None = None,
    _real_executor: Callable[[Mapping[str, Any], Path], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preregister and retain all originals; no actual runtime is inferred from fixtures."""
    if software_adapter is not None and not software_only:
        raise ValueError("injected adapters require explicit SOFTWARE_ONLY")
    if stage == "power" and software_adapter is not None:
        raise ValueError("power method runtime is not integrated")
    if _real_executor is not None and (
        software_adapter is not None or software_only or stage == "power"
    ):
        raise ValueError("real executor and software/power modes cannot be combined")
    assignments = build_pilot_assignments(
        pools, stage, period_s=period_s, role_bundle_hash=role_bundle_hash
    )
    output.mkdir(parents=True, exist_ok=False)
    for name, data in (
        ("pools.json", pools),
        ("assignments.json", assignments),
        ("selection-rule.json", BUDGET_SELECTION_RULE),
    ):
        (output / name).write_text(canonical_json(data) + "\n")
    records = []
    for assignment in assignments:
        directory = output / "cases" / assignment["assignment_id"]
        directory.mkdir(parents=True)
        (directory / "assignment.json").write_text(canonical_json(assignment) + "\n")
        row = {
            "assignment_id": assignment["assignment_id"],
            "status": "NOT_EXECUTED",
            "success": False,
            "safety_violation": False,
            "wall_duration_s": 0.0,
            "cloud_requests": 0,
            "accepted_success": False,
            "scope": "UNVERIFIED",
            "reason": "actual role-bound runtime/accepted prerequisites not supplied",
        }
        executor = software_adapter or _real_executor
        if executor is not None:
            try:
                supplied = dict(executor(assignment, directory))
            except Exception as error:
                # Preserve the original assigned case and any partial raw execution.
                supplied = {
                    "status": "FAILED",
                    "success": False,
                    "safety_violation": False,
                    "reason": f"executor failed: {type(error).__name__}",
                }
            if (
                supplied.get("assignment_id", assignment["assignment_id"])
                != assignment["assignment_id"]
            ):
                raise ValueError("software adapter returned foreign assignment")
            row.update(supplied)
            row.update(
                assignment_id=assignment["assignment_id"],
                accepted_success=False,
                scope="SOFTWARE_ONLY" if software_adapter is not None else "REAL_RUNTIME",
            )
            if software_adapter is not None:
                row["reason"] = "explicit software fixture; no physical acceptance"
        records.append(row)
        (directory / "case-result.json").write_text(canonical_json(row) + "\n")
    (output / "results.json").write_text(canonical_json(records) + "\n")
    summary = {
        "schema_version": "ced.pilot-stage.v1",
        "protocol_version": "ced.research.v2",
        "stage": stage,
        "scope": "SOFTWARE_ONLY" if software_only else "UNVERIFIED",
        "actual_research_status": "NOT_RUN",
        "status": "SOFTWARE_ONLY" if software_only else "NOT_RUN",
        "group_denominator": 120,
        "assigned_denominator": len(assignments) if stage != "power" else None,
        "recorded_denominator": len(records),
        "accepted_success": 0,
        "freeze_ready": False,
        "selected_period_s": None,
        "role_bundle_hash": role_bundle_hash,
        "assignment_manifest_hash": content_digest(assignments),
        "pools_hash": content_digest(pools),
        "method_runtime_integrated": False if stage == "power" else None,
        "execution_mode": "REAL_RUNTIME" if _real_executor is not None else "NOT_EXECUTED",
        "b0_period_s": period_s if stage == "foundation" else None,
        "terminal_status_counts": dict(Counter(r["status"] for r in records)),
    }
    if stage == "selection":
        summary["selection_diagnostic"] = choose_b0_period(assignments, records)
    (output / "summary.json").write_text(canonical_json(summary) + "\n")
    return summary


def derive_tcap(successful_b0_durations_s: list[float]) -> int:
    if not successful_b0_durations_s:
        raise ValueError("no B0 successes; Tcap freeze is BLOCKED")
    if any(not math.isfinite(v) or v <= 0 for v in successful_b0_durations_s):
        raise ValueError("successful durations must be positive finite measured seconds")
    p99 = float(np.quantile(successful_b0_durations_s, 0.99))
    return min(600, max(120, math.ceil(2 * p99 / 10) * 10))


@dataclass
class PilotReport:
    assigned: int
    records: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        successes = [row for row in self.records if row.get("success", False)]
        return {
            "assigned": self.assigned,
            "recorded": len(self.records),
            "unrecorded": self.assigned - len(self.records),
            "succeeded": len(successes),
            "blocked": sum(bool(row.get("blocked")) for row in self.records),
            "success_rate_all_assigned": len(successes) / self.assigned if self.assigned else None,
            "tcap_derivable": len(self.records) == self.assigned
            and bool(successes)
            and not any(row.get("blocked") for row in self.records),
            # Only the independent evidence verifier can accept a protocol.
            "freeze_ready": False,
        }
