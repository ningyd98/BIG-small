"""预注册目标判定及可复用分析入口；正式来源未验收时严格 NOT_RUN。"""

from __future__ import annotations

import csv
import json
import math
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
from cloud_edge_robot_arm.research.assignments import (
    EpisodeAssignment,
    build_assignments,
    episode_record_from_payload,
    validate_formal_protocol,
)
from cloud_edge_robot_arm.research.metrics import compute_research_metrics
from cloud_edge_robot_arm.research.protocol import FrozenProtocol, load_protocol
from cloud_edge_robot_arm.research.statistics import EffectEstimate, holm_adjust

GoalStatus = Literal["PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "NOT_RUN"]
GOAL_IDS = ("G0", "G1", "G2", "G2a", "G3", "G4", "G5", "C1", "C2")
CORE_METHODS = ("JOINT", "B0", "B1", "B2", "NO_UNCERTAINTY", "NO_TIME_VALIDITY", "NO_LOCAL_REPAIR")


@dataclass(frozen=True)
class GoalVerdict:
    """明确区分数学软件判定、未执行和实际来源验收状态。"""

    goal_id: str
    status: GoalStatus
    estimate: object
    reasons: tuple[str, ...]
    evidence_scope: str = field(default="UNVERIFIED", kw_only=True)


def noninferiority_passes(success: EffectEstimate, safety: EffectEstimate) -> bool:
    """成功差单侧下界严格大于 -.03，安全差上界不超过 +.01。"""
    return bool(
        success.one_sided_lower95 is not None
        and safety.one_sided_upper95 is not None
        and success.one_sided_lower95 > -0.03
        and safety.one_sided_upper95 <= 0.01
    )


def improvement_status(estimate: EffectEstimate, target: float) -> GoalStatus:
    """点目标和可靠改善分别检查；基线零、区间跨零均不是可靠收益。"""
    if estimate.point is None or estimate.lower95 is None or estimate.upper95 is None:
        return "INSUFFICIENT_EVIDENCE"
    if estimate.point < target:
        return "FAIL"
    if estimate.lower95 <= 0:
        return "INSUFFICIENT_EVIDENCE"
    return "PASS"


def g1_status(localization_p90_m: float | None, static_success_rate: float | None) -> GoalStatus:
    """标称定位10毫米与独立静态成功90%分别满足才通过数值门。"""
    if localization_p90_m is None or static_success_rate is None:
        return "NOT_RUN"
    if (
        not math.isfinite(localization_p90_m)
        or localization_p90_m < 0
        or (not math.isfinite(static_success_rate) or not 0 <= static_success_rate <= 1)
    ):
        raise ValueError("nominal metric invalid")
    return "PASS" if localization_p90_m <= 0.01 and static_success_rate >= 0.9 else "FAIL"


def g3_status(
    reduction: EffectEstimate,
    absolute_false_acceptance: float | None,
    false_rejection: float | None,
) -> GoalStatus:
    """误放行绝对2%、错误拒绝5%与相对改善50%分列，UNKNOWN不补拒绝。"""
    if absolute_false_acceptance is None or false_rejection is None:
        return "NOT_RUN"
    if any(
        not math.isfinite(value) or not 0 <= value <= 1
        for value in (absolute_false_acceptance, false_rejection)
    ):
        raise ValueError("gate replay rates invalid")
    if absolute_false_acceptance > 0.02 or false_rejection > 0.05:
        return "FAIL"
    return improvement_status(reduction, 0.5)


def g4_status(
    fault_groups: int,
    recovery_success_rate: float | None,
    duration_reduction: EffectEstimate,
    completed_resubmissions: int | None,
) -> GoalStatus:
    """固定200故障、恢复80%、可靠中位数减少30%且完成动作重提0。"""
    if type(fault_groups) is not int or fault_groups < 0:
        raise ValueError("fault group denominator invalid")
    if fault_groups != 200:
        return "INSUFFICIENT_EVIDENCE"
    if recovery_success_rate is None or completed_resubmissions is None:
        return "NOT_RUN"
    if (
        not math.isfinite(recovery_success_rate)
        or not 0 <= recovery_success_rate <= 1
        or (type(completed_resubmissions) is not int or completed_resubmissions < 0)
    ):
        raise ValueError("recovery success/resubmission metric invalid")
    if recovery_success_rate < 0.8 or completed_resubmissions:
        return "FAIL"
    return improvement_status(duration_reduction, 0.3)


def _effect(values: Mapping[str, Any], key: str) -> EffectEstimate | None:
    raw = values.get(key)
    return EffectEstimate(**raw) if isinstance(raw, Mapping) else None


def evaluate_goals(
    metrics: Mapping[str, object],
    protocol: FrozenProtocol,
    *,
    software_only: bool = False,
) -> list[GoalVerdict]:
    """评估同一冻结规则；缺真实来源验收器时正式目标一律未执行。"""
    scope = "SOFTWARE_ONLY" if software_only else "UNVERIFIED"
    # This module exposes no declaration flag that can make formal acceptance true.
    # Integration must supply independent raw-source verification before replacing
    # this closed boundary; source_verified/formal_accepted metadata are insufficient.
    if not software_only:
        return [
            GoalVerdict(
                goal,
                "NOT_RUN",
                None,
                ("independent raw source verification is not integrated",),
                evidence_scope=scope,
            )
            for goal in GOAL_IDS
        ]
    if metrics.get("scope") != "SOFTWARE_ONLY":
        raise ValueError(
            "software goal diagnostics require an explicit SOFTWARE_ONLY metrics scope"
        )
    validate_formal_protocol(protocol)
    if protocol.spec.hypothesis_family != (
        "G2_REQUESTS",
        "G2_SUCCESS",
        "G2_SAFETY",
        "G3_FALSE_ACCEPT",
        "G4_DURATION",
    ):
        raise ValueError("pre-registered five hypothesis family cannot change")
    effects = metrics.get("effects", {})
    if not isinstance(effects, Mapping):
        raise ValueError("goal effect table malformed")
    raw_p = {
        key: (effects[key].get("p_value") if isinstance(effects.get(key), Mapping) else None)
        for key in protocol.spec.hypothesis_family
    }
    adjusted = holm_adjust(
        {key: float(value) if value is not None else 1.0 for key, value in raw_p.items()}
    )
    estimates = {
        key: _effect(effects, key)
        for key in (*protocol.spec.hypothesis_family, "G2A_BYTES", "G2A_DURATION")
    }
    verdicts: dict[str, GoalVerdict] = {}
    for goal in GOAL_IDS:
        verdicts[goal] = GoalVerdict(
            goal,
            "NOT_RUN",
            None,
            ("required source-bound metric has not been produced",),
            evidence_scope=scope,
        )
    n = metrics.get("main_paired_group_denominator", 0)
    required = protocol.spec.selected_n or 0
    if n != required:
        verdicts["G2"] = GoalVerdict(
            "G2",
            "INSUFFICIENT_EVIDENCE",
            {"paired_groups": n, "required": required},
            ("complete frozen N paired groups are required",),
            evidence_scope=scope,
        )
    else:
        requests, success, safety = (
            estimates[key] for key in ("G2_REQUESTS", "G2_SUCCESS", "G2_SAFETY")
        )
        if requests is not None and success is not None and safety is not None:
            status = improvement_status(requests, 0.3)
            if not noninferiority_passes(success, safety):
                status = "INSUFFICIENT_EVIDENCE"
            if any(adjusted[key] > 0.05 for key in ("G2_REQUESTS", "G2_SUCCESS", "G2_SAFETY")):
                status = "INSUFFICIENT_EVIDENCE" if status != "FAIL" else status
            verdicts["G2"] = GoalVerdict(
                "G2",
                status,
                {
                    "requests": asdict(requests),
                    "success": asdict(success),
                    "safety": asdict(safety),
                    "holm_adjusted_p": adjusted,
                },
                ("software threshold evaluation only; no accepted physical evidence",),
                evidence_scope=scope,
            )
    secondary: dict[str, GoalStatus] = {}
    for key, target in (("G2A_BYTES", 0.25), ("G2A_DURATION", 0.15)):
        estimate = estimates[key]
        secondary[key] = improvement_status(estimate, target) if estimate is not None else "NOT_RUN"
    if any(status != "NOT_RUN" for status in secondary.values()):
        secondary_status: GoalStatus = (
            "PASS"
            if all(value == "PASS" for value in secondary.values())
            else ("FAIL" if "FAIL" in secondary.values() else "INSUFFICIENT_EVIDENCE")
        )
        verdicts["G2a"] = GoalVerdict(
            "G2a",
            secondary_status,
            secondary,
            ("bytes and penalized P95 duration are separate secondary targets",),
            evidence_scope=scope,
        )
    nominal = metrics.get("nominal")
    if isinstance(nominal, Mapping):
        verdicts["G1"] = GoalVerdict(
            "G1",
            g1_status(nominal.get("localization_p90_m"), nominal.get("static_success_rate")),
            dict(nominal),
            ("coverage and correct identity/valid depth eligibility must be reported separately",),
            evidence_scope=scope,
        )
    gate = metrics.get("gate")
    reduction = estimates["G3_FALSE_ACCEPT"]
    if isinstance(gate, Mapping) and isinstance(gate.get("JOINT"), Mapping) and reduction:
        joint = gate["JOINT"]
        gate_status = g3_status(
            reduction, joint.get("false_acceptance_rate"), joint.get("false_rejection_rate")
        )
        if gate_status == "PASS" and adjusted["G3_FALSE_ACCEPT"] > 0.05:
            gate_status = "INSUFFICIENT_EVIDENCE"
        if metrics.get("fixed_opportunity_group_denominator") != required:
            gate_status = "INSUFFICIENT_EVIDENCE"
        verdicts["G3"] = GoalVerdict(
            "G3",
            gate_status,
            {
                "reduction": asdict(reduction),
                "rates": dict(joint),
                "holm_adjusted_p": adjusted["G3_FALSE_ACCEPT"],
            },
            ("fixed group-clustered replay only",),
            evidence_scope=scope,
        )
    recovery = metrics.get("recovery")
    duration = estimates["G4_DURATION"]
    if isinstance(recovery, Mapping) and duration:
        recovery_status = g4_status(
            recovery.get("assigned_groups", 0),
            recovery.get("success_rate"),
            duration,
            recovery.get("completed_resubmissions"),
        )
        if recovery_status == "PASS" and adjusted["G4_DURATION"] > 0.05:
            recovery_status = "INSUFFICIENT_EVIDENCE"
        verdicts["G4"] = GoalVerdict(
            "G4",
            recovery_status,
            {
                "duration": asdict(duration),
                "rates": dict(recovery),
                "holm_adjusted_p": adjusted["G4_DURATION"],
            },
            ("requires complete200 verified fault episodes",),
            evidence_scope=scope,
        )
    # G0/G5 still need independent stage/data evidence.
    # Neither a replay nor a success declaration fills those prerequisites.
    return [verdicts[goal] for goal in GOAL_IDS]


def _write_outputs(output: Path, report: Mapping[str, Any], metrics: Mapping[str, object]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("report.json", report),
        ("metrics.json", metrics),
        ("goal_verdicts.json", report["goal_verdicts"]),
    ):
        text = canonical_json(payload) + "\n"
        path = output / name
        if path.exists() and path.read_text() != text:
            raise ValueError(
                "existing analysis output differs; preserve it and use a new directory"
            )
        path.write_text(text)
    with (output / "goal_verdicts.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("goal_id", "status", "evidence_scope", "reasons"))
        for value in report["goal_verdicts"]:
            writer.writerow(
                (
                    value["goal_id"],
                    value["status"],
                    value["evidence_scope"],
                    "; ".join(value["reasons"]),
                )
            )
    _render_goal_status(output, report)


def _render_goal_status(output: Path, report: Mapping[str, Any]) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(output / "mpl-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {
        "NOT_RUN": "#64748b",
        "INSUFFICIENT_EVIDENCE": "#a16207",
        "FAIL": "#b91c1c",
        "PASS": "#15803d",
    }
    with plt.rc_context({"svg.hashsalt": "ced.research-analysis.v1", "font.family": "DejaVu Sans"}):
        figure, axis = plt.subplots(figsize=(7, 4.2))
        for index, value in enumerate(report["goal_verdicts"]):
            axis.barh(index, 1, color=colors[value["status"]], height=0.65)
            axis.text(0.03, index, value["status"], color="white", va="center", fontsize=9)
        axis.set_yticks(
            range(len(report["goal_verdicts"])),
            [value["goal_id"] for value in report["goal_verdicts"]],
        )
        axis.set_xticks([])
        axis.set_xlim(0, 1)
        axis.invert_yaxis()
        axis.set_title(str(report["status"]) + " / no physical acceptance")
        for spine in axis.spines.values():
            spine.set_visible(False)
        figure.tight_layout()
        temporary = output / "goal_status.svg.tmp"
        figure.savefig(temporary, format="svg", metadata={"Date": None})
        plt.close(figure)
        target = output / "goal_status.svg"
        if target.exists() and target.read_bytes() != temporary.read_bytes():
            temporary.unlink()
            raise ValueError("existing analysis chart differs; preserve original output")
        temporary.replace(target)


def analyze_research_runs(
    runs: Path,
    protocol: Path,
    output: Path,
    *,
    software_only: bool = False,
) -> Mapping[str, object]:
    """从不可变记录重建确定性分析；复现工具调用同一函数而不执行存储命令。"""
    scope = "SOFTWARE_ONLY" if software_only else "UNVERIFIED"
    metrics: Mapping[str, object] = {
        "schema_version": "ced.research-metrics.v1",
        "scope": scope,
        "formal_accepted": False,
        "accepted_physical_success": 0,
        "source_validation_status": "NOT_CONFIGURED",
        "coverage_status": "INCOMPLETE",
    }
    verdicts = [
        GoalVerdict(
            goal, "NOT_RUN", None, ("analysis prerequisites missing",), evidence_scope=scope
        )
        for goal in GOAL_IDS
    ]
    status = "NOT_RUN"
    reasons = []
    source_hashes: dict[str, str] = {}
    try:
        frozen = load_protocol(protocol)
        validate_formal_protocol(frozen)
        manifest_path = runs / "assignments.json"
        record_path = runs / "records.jsonl"
        manifest = json.loads(manifest_path.read_text())
        expected_hash = manifest.pop("content_hash", None)
        if (
            manifest.get("schema_version") != "ced.assignments.v1"
            or content_digest(manifest) != expected_hash
        ):
            raise ValueError("frozen assignment manifest schema/hash mismatch")
        if manifest.get("protocol_hash") != frozen.content_hash:
            raise ValueError("assignment manifest differs from frozen protocol")
        assignments = [EpisodeAssignment(**raw) for raw in manifest["assignments"]]
        expected = {value.assignment_id: value for value in assignments}
        if len(expected) != len(assignments) or not assignments:
            raise ValueError("assignment manifest missing or duplicate entries")
        # A self-hashed manifest cannot prove that assigned failures were retained.
        # Rebuild from the full independently hash-bound 2400-scene pool. This checks
        # fixed N, seven methods, twelve strata, prefix selection, paired physics and
        # network facts, full scene/perturbation content and frozen random execution order.
        pool_path = runs / "pools.json"
        if not pool_path.exists():
            raise ValueError("coverage incomplete: full frozen scene pool archive is required")
        pools = json.loads(pool_path.read_text())
        pool = pools.get("formal") if isinstance(pools, Mapping) else None
        if not isinstance(pool, list):
            raise ValueError("coverage incomplete: archived formal scene pool is missing")
        rebuilt = build_assignments(frozen, CORE_METHODS, scene_pool=pool)
        if assignments != rebuilt:
            raise ValueError(
                "coverage incomplete: manifest must retain exact frozen N, all methods, "
                "balanced strata and paired scene/schedule/order bindings"
            )
        rows = [
            episode_record_from_payload(json.loads(line), protocol=frozen)
            for line in record_path.read_text().splitlines()
        ]
        actual = {row.assignment.assignment_id: row for row in rows}
        if len(actual) != len(rows) or set(actual) != set(expected):
            raise ValueError(
                "coverage incomplete: every preassigned episode, including blocked failures, "
                "must have its original record"
            )
        if any(row.assignment != expected[key] for key, row in actual.items()):
            raise ValueError("episode differs from its frozen preassigned identity")
        metrics = compute_research_metrics(rows, (), (), software_only=software_only)
        metrics = {
            **metrics,
            "coverage_status": "COMPLETE",
            "coverage_assignment_denominator": len(rebuilt),
            "coverage_group_denominator": frozen.spec.selected_n,
            "coverage_methods": list(CORE_METHODS),
        }
        verdicts = evaluate_goals(metrics, frozen, software_only=software_only)
        status = "SOFTWARE_ONLY" if software_only else "NOT_RUN"
        reasons = ["independent raw physical source verifier is not integrated"]
        import hashlib

        source_hashes = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (
                ("protocol", protocol / "protocol.json"),
                ("assignments", manifest_path),
                ("records", record_path),
                ("pools", pool_path),
            )
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        reasons = [str(error)]
    report = {
        "schema_version": "ced.research-analysis.v1",
        "status": status,
        "scope": scope,
        "formal_accepted": False,
        "physical_success": 0,
        "source_hashes": source_hashes,
        "reasons": reasons,
        "goal_verdicts": [asdict(value) for value in verdicts],
    }
    _write_outputs(output, report, metrics)
    return report
