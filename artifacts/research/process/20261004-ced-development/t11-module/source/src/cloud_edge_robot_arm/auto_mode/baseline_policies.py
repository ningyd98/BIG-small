"""共同事件上的B0/B1/B2适配；所有策略只返回动作，不执行机器人。"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cloud_edge_robot_arm.auto_mode.models import AutoModePolicy, AutoModeState
from cloud_edge_robot_arm.auto_mode.runtime_events import (
    DecisionAction,
    DecisionContext,
    DecisionEvent,
    DecisionEventKind,
)
from cloud_edge_robot_arm.auto_mode.selector import AutoModeSelector
from cloud_edge_robot_arm.contracts import AutoModeDecision, AutoModeDecisionType
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionStatus
from cloud_edge_robot_arm.research.pilot_audit import audit_pilot
from cloud_edge_robot_arm.research.protocol import STRATA
from cloud_edge_robot_arm.research.supervision import PeriodicSupervision
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.skill_cache.models import SkillCacheLookupResult

B0_PERIODS = (0.5, 1.0, 2.0, 5.0)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _source_hashes() -> dict[str, str]:
    from cloud_edge_robot_arm.auto_mode import selector
    from cloud_edge_robot_arm.risk import evaluator, models

    sources = {
        "auto_mode/selector.py": Path(selector.__file__),
        "risk/evaluator.py": Path(evaluator.__file__),
        "risk/models.py": Path(models.__file__),
        "auto_mode/models.py": Path(__file__).with_name("models.py"),
    }
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sources.items()}


@dataclass(frozen=True)
class FrozenLegacyRuleSnapshot:
    """冻结原风险权重、AUTO阈值和实现源码；不包含校准概率。"""

    risk_policy: Mapping[str, Any]
    auto_policy: Mapping[str, Any]
    source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        risk = RiskPolicy.model_validate(dict(self.risk_policy))
        auto = AutoModePolicy.model_validate(dict(self.auto_policy))
        object.__setattr__(self, "risk_policy", MappingProxyType(risk.model_dump(mode="json")))
        object.__setattr__(self, "auto_policy", MappingProxyType(auto.model_dump(mode="json")))
        object.__setattr__(self, "source_hashes", MappingProxyType(dict(self.source_hashes)))

    def digest(self) -> str:
        """返回原规则参数和源码的确定性内容hash。"""
        return _canonical_hash(
            {
                "risk_policy": dict(self.risk_policy),
                "auto_policy": dict(self.auto_policy),
                "source_hashes": dict(self.source_hashes),
            }
        )


def freeze_legacy_rule_snapshot(
    risk_policy: RiskPolicy | None = None,
    auto_policy: AutoModePolicy | None = None,
) -> FrozenLegacyRuleSnapshot:
    """从现有policy的实际参数冻结B2；默认值保持原risk-v1/auto-v1。"""
    return FrozenLegacyRuleSnapshot(
        (risk_policy or RiskPolicy(version="risk-v1")).model_dump(mode="json"),
        (auto_policy or AutoModePolicy(version="auto-v1")).model_dump(mode="json"),
        _source_hashes(),
    )


@dataclass(frozen=True)
class LegacyRuleEvidence:
    """原B2需要的可观测缓存、合同和checkpoint输入，不接收独立结果。"""

    current_state: AutoModeState
    risk_input: RiskSnapshotInput
    cache_lookup: SkillCacheLookupResult
    active_contract_complete: bool
    checkpoint_persisted: bool
    event_autonomy_ready: bool
    supervision_available: bool
    mode_history: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_state", self.current_state.model_copy(deep=True))
        object.__setattr__(self, "risk_input", self.risk_input.model_copy(deep=True))
        object.__setattr__(self, "cache_lookup", self.cache_lookup.model_copy(deep=True))
        object.__setattr__(self, "mode_history", tuple(self.mode_history))


class _BaselinePolicy:
    def __init__(self) -> None:
        self._decisions: OrderedDict[str, tuple[tuple[Any, ...], DecisionAction]] = OrderedDict()

    def _remember(
        self, context: DecisionContext, choose: Callable[[], DecisionAction]
    ) -> DecisionAction:
        if self._hard_stop(context):
            return DecisionAction.STOP
        key = (
            context.task_id,
            context.episode_id,
            context.event.observation_id,
            context.plan_version,
            context.command_seq,
            context.mode_version,
            context.online_evidence.context_hash,
            context.online_evidence.observation.checksum_sha256,
            context.event.kind,
            context.event.atomic_action_active,
            context.event.verification_status,
            context.evidence_verdict.status,
            tuple((v.condition_name, v.status) for v in context.condition_verdicts),
            tuple(sorted(context.capabilities)),
        )
        existing = self._decisions.get(context.event.event_id)
        # This bounded policy cache only prevents charging an allowance twice;
        # the envelope/repository performs durable execution deduplication.
        if existing is not None:
            return existing[1] if existing[0] == key else DecisionAction.STOP
        result = choose()
        self._decisions[context.event.event_id] = (key, result)
        if len(self._decisions) > 128:
            self._decisions.popitem(last=False)
        return result

    def _hard_stop(self, context: DecisionContext) -> bool:
        state = context.online_evidence.robot_state
        budget = context.verification_budget
        return (
            state.estop_engaged
            or state.collision_detected
            or not state.connected
            or any(
                v.measured_values.get("hard_safety_fault") is True
                for v in context.condition_verdicts
            )
            or budget.exhausted_reason is not None
            or context.event.occurred_at >= budget.deadline_at
            or budget.consecutive_no_progress >= budget.limits.max_no_progress
        )

    def _guard(self, context: DecisionContext) -> DecisionAction | None:
        budget = context.verification_budget
        if self._hard_stop(context):
            return DecisionAction.STOP
        if context.event.atomic_action_active:
            return self._available(context, DecisionAction.CONTINUE)
        if (
            context.evidence_verdict.status == "UNKNOWN"
            or context.event.verification_status == ConditionStatus.UNKNOWN
            or not context.condition_verdicts
            or any(v.status == ConditionStatus.UNKNOWN for v in context.condition_verdicts)
        ):
            return self._observe(context)
        if (
            context.evidence_verdict.status == "INVALID"
            or any(v.status == ConditionStatus.FAIL for v in context.condition_verdicts)
            or context.event.verification_status == ConditionStatus.FAIL
        ):
            if (
                DecisionAction.REQUEST_CLOUD in context.capabilities
                and budget.remaining_retries > 0
            ):
                budget.remaining_retries -= 1
                return DecisionAction.REQUEST_CLOUD
            return DecisionAction.STOP
        return None

    def _observe(self, context: DecisionContext) -> DecisionAction:
        budget = context.verification_budget
        if DecisionAction.REOBSERVE in context.capabilities and budget.remaining_reobservations > 0:
            budget.remaining_reobservations -= 1
            return DecisionAction.REOBSERVE
        return DecisionAction.STOP

    def _available(self, context: DecisionContext, action: DecisionAction) -> DecisionAction:
        return action if action in context.capabilities else DecisionAction.STOP


class PeriodicPolicy(_BaselinePolicy):
    """B0复用现有独立PCSC ticker，周期tick提出监督请求。"""

    def __init__(self, period_s: float) -> None:
        if type(period_s) not in (int, float) or period_s not in B0_PERIODS:
            raise ValueError("B0 period must be one of .5, 1, 2, 5 seconds")
        super().__init__()
        self.period_s = float(period_s)
        self._observed_ticks = 0
        self.merged_tick_events = 0

    def supervision(
        self, infer: Callable[[Any], Any], capture: Callable[[], Any]
    ) -> PeriodicSupervision:
        """返回既有有界单在途监督器，不建立另一套调度/执行器。"""
        return PeriodicSupervision(self.period_s, infer, capture)

    def tick_events(
        self,
        snapshot: Mapping[str, Any],
        *,
        occurred_at: datetime,
        observation_id: str,
        atomic_action_active: bool,
    ) -> tuple[DecisionEvent, ...]:
        """把既有ticker计数转为最新事件，保留被合并的tick计数。"""
        ticks = snapshot.get("ticks")
        if type(ticks) is not int or ticks < self._observed_ticks:
            raise ValueError("supervision ticks must be monotonic nonnegative integers")
        if ticks == self._observed_ticks:
            return ()
        self.merged_tick_events += max(0, ticks - self._observed_ticks - 1)
        self._observed_ticks = ticks
        return (
            DecisionEvent(
                f"b0-tick-{ticks}",
                DecisionEventKind.SUPERVISION_TICK,
                occurred_at,
                observation_id,
                atomic_action_active,
                ConditionStatus.PASS,
            ),
        )

    def decide(self, context: DecisionContext) -> DecisionAction:
        """在所有业务事件上复核安全和证据，在独立tick上请求云端。"""

        def choose() -> DecisionAction:
            guarded = self._guard(context)
            if guarded is not None:
                return guarded
            action = (
                DecisionAction.REQUEST_CLOUD
                if context.event.kind == DecisionEventKind.SUPERVISION_TICK
                else DecisionAction.CONTINUE
            )
            return self._available(context, action)

        return self._remember(context, choose)


class ThresholdPolicy(_BaselinePolicy):
    """B1仅比较T9校准的CONTINUE失败概率，未知风险先重新观测。"""

    def __init__(self, threshold: float) -> None:
        if (
            type(threshold) not in (int, float)
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("B1 threshold must be a finite probability in [0,1]")
        super().__init__()
        self.threshold = float(threshold)

    def decide(self, context: DecisionContext) -> DecisionAction:
        """每个运行中事件都重新判断，规则分数和自报confidence不作概率。"""

        def choose() -> DecisionAction:
            guarded = self._guard(context)
            if guarded is not None:
                return guarded
            estimate = context.risk_estimate
            probability = estimate.failure_probability_by_action.get(DecisionAction.CONTINUE.value)
            if (
                estimate.status != "VALID"
                or not isinstance(probability, (int, float))
                or isinstance(probability, bool)
                or not math.isfinite(probability)
                or not 0 <= probability <= 1
            ):
                return self._observe(context)
            action = (
                DecisionAction.REQUEST_CLOUD
                if probability >= self.threshold
                else DecisionAction.CONTINUE
            )
            return self._available(context, action)

        return self._remember(context, choose)


class FrozenRuleAutoPolicy(_BaselinePolicy):
    """B2直接复用冻结的原RiskEvaluator和AutoModeSelector。"""

    def __init__(self, rule_snapshot: FrozenLegacyRuleSnapshot) -> None:
        if dict(rule_snapshot.source_hashes) != _source_hashes():
            raise ValueError("B2 original rule source hash differs from frozen snapshot")
        super().__init__()
        self.rule_snapshot = rule_snapshot
        self.last_mode_decision: AutoModeDecision | None = None

    def decide_mode(self, context: DecisionContext) -> AutoModeDecision | None:
        """重算原风险分数并调用原模式选择器，不修改原权重或切换条件。"""
        legacy = context.legacy_rule_evidence
        if legacy is None or dict(self.rule_snapshot.source_hashes) != _source_hashes():
            return None
        state, risk_input = legacy.current_state, legacy.risk_input
        if (
            state.task_id != context.task_id
            or risk_input.task_id != context.task_id
            or state.mode_version != context.mode_version
            or state.current_mode != context.mode
            or risk_input.current_mode != context.mode
            or risk_input.current_time != context.event.occurred_at
        ):
            return None
        risk_policy = RiskPolicy.model_validate(dict(self.rule_snapshot.risk_policy))
        if risk_input.policy_version != risk_policy.version:
            return None
        risk = RiskEvaluator(policy=risk_policy).evaluate(risk_input)
        return AutoModeSelector(
            policy=AutoModePolicy.model_validate(dict(self.rule_snapshot.auto_policy)),
            clock=lambda: context.event.occurred_at,
        ).decide(
            current_state=state,
            risk_snapshot=risk,
            cache_lookup=legacy.cache_lookup,
            active_contract_complete=legacy.active_contract_complete,
            checkpoint_persisted=legacy.checkpoint_persisted,
            event_autonomy_ready=legacy.event_autonomy_ready,
            supervision_available=legacy.supervision_available,
            atomic_step_active=context.event.atomic_action_active,
            mode_history=list(legacy.mode_history),
        )

    def decide(self, context: DecisionContext) -> DecisionAction:
        """先过共同安全证据门，再把原AUTO决策映射到同一动作词汇。"""

        def choose() -> DecisionAction:
            guarded = self._guard(context)
            if guarded is not None:
                return guarded
            decision = self.decide_mode(context)
            self.last_mode_decision = decision
            if decision is None:
                return DecisionAction.STOP
            actions = {
                AutoModeDecisionType.KEEP_CURRENT_MODE: DecisionAction.CONTINUE,
                AutoModeDecisionType.SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY: (
                    DecisionAction.CONTINUE
                ),
                AutoModeDecisionType.SWITCH_TO_PERIODIC_CLOUD_SUPERVISION: (
                    DecisionAction.REQUEST_CLOUD
                ),
                AutoModeDecisionType.REQUEST_MORE_OBSERVATION: DecisionAction.REOBSERVE,
            }
            action = actions.get(decision.action, DecisionAction.STOP)
            return (
                self._observe(context)
                if action == DecisionAction.REOBSERVE
                else self._available(context, action)
            )

        return self._remember(context, choose)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit_curve(period: float, directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "selection-manifest.json").read_text())
    if manifest.get("stage") != "SELECTION" or manifest.get("period_s") != period:
        raise ValueError("curve must be an explicitly bound selection run at the registered period")
    for name in ("assignments", "results"):
        if manifest.get(f"{name}_sha256") != _file_hash(directory / f"{name}.json"):
            raise ValueError(f"{name} source hash mismatch")
    bindings = {
        name: manifest[name]
        for name in (
            "snapshot_id",
            "role_bundle_hash",
            "device_pipeline_hash",
            "edge_provider_hash",
        )
    }
    if any(not isinstance(v, str) or not v for v in bindings.values()):
        raise ValueError("common frozen role/device/provider identities are required")
    assignments = json.loads((directory / "assignments.json").read_text())
    groups = [row["scene"]["group_id"] for row in assignments]
    ids = [row["assignment_id"] for row in assignments]
    counts = Counter(row["stratum_id"] for row in assignments)
    if (
        len(ids) != 120
        or len(set(ids)) != 120
        or len(set(groups)) != 120
        or set(counts) != set(STRATA)
        or set(counts.values()) != {10}
        or sum(n for key, n in counts.items() if key.startswith("STATIC")) != 40
    ):
        raise ValueError(
            "selection requires all 120 unique groups, 12 strata of 10, including 40 static"
        )
    results = json.loads((directory / "results.json").read_text())
    result_ids = [row["assignment_id"] for row in results]
    if len(result_ids) != 120 or len(set(result_ids)) != 120 or set(result_ids) != set(ids):
        raise ValueError("selection result denominator is duplicated or incomplete")
    if any(not str(value).startswith("selection-") for value in ids):
        raise ValueError("selection cannot relabel foundation/formal assignment identities")
    episode_ids = set()
    for assignment in assignments:
        case = directory / "cases" / assignment["assignment_id"]
        episode = json.loads((case / "episode.json").read_text())
        samples = json.loads((case / "physical-evidence.json").read_text())
        outcome = json.loads((case / "physical-outcome.json").read_text())
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id or episode_id in episode_ids:
            raise ValueError("selection needs a unique actual episode identity per assigned group")
        episode_ids.add(episode_id)
        if not samples or any(sample.get("episode_id") != episode_id for sample in samples):
            raise ValueError("selection physical samples belong to a foreign episode")
        initial = samples[0]
        target = assignment["scene"]["scene_parameters"]["target"]
        destination = assignment["scene"]["scene_parameters"]["destination"]
        if any(
            abs(a - b) > 0.005
            for a, b in zip(initial["object_position_m"][:2], target["position"][:2], strict=True)
        ) or any(
            abs(a - b) > 0.003
            for a, b in zip(
                initial["object_half_extent_xy_m"], target["half_size"][:2], strict=True
            )
        ):
            raise ValueError("selection physical source does not match assigned object geometry")
        if any(
            any(
                abs(a - b) > 1e-6
                for a, b in zip(
                    sample["region_center_xy_m"], destination["position"][:2], strict=True
                )
            )
            or any(
                abs(a - b) > 1e-6
                for a, b in zip(
                    sample["region_half_extent_xy_m"], destination["half_size"][:2], strict=True
                )
            )
            for sample in samples
        ):
            raise ValueError("selection physical source does not match fixed destination geometry")
        if outcome.get("safety_assessment") not in {"SCOPED_NO_VIOLATION", "VIOLATION"}:
            raise ValueError("selection physical safety assessment is incomplete")
    audit = audit_pilot(directory)
    summary = audit["summary"]
    if (
        not audit["physical_reconstruction_valid"]
        or summary["recorded"] != 120
        or summary["cost_publication_mismatches"]
        or summary["inflight_requests"]
    ):
        raise ValueError("selection raw physical/cost reconstruction is incomplete or inconsistent")
    cases = audit["cases"]
    if any(case.get("errors") or type(case.get("safety_violation")) is not bool for case in cases):
        raise ValueError(
            "selection safety outcomes must be independently reconstructed for every assigned case"
        )
    durations = [case.get("wall_duration_s") for case in cases]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in durations):
        raise ValueError("every assigned case needs a finite measured wall duration")
    requests = sum(case["costs"]["cloud_model_requests"] for case in cases)
    return {
        "period_s": period,
        "assigned": 120,
        "static_assigned": 40,
        "stratum_counts": dict(counts),
        "group_ids": groups,
        "assignment_hash": audit["assignment_hash"],
        "bindings": bindings,
        "success_rate": summary["success_rate_all_assigned"],
        "static_success_rate": summary["nominal_success_rate"],
        "safety_violation_rate": summary["safety_violations"] / 120,
        "actual_cloud_requests": requests,
        "mean_wall_duration_s": sum(durations) / 120,
        "false_completion_claims": summary["false_completion_claims"],
        "audit_hash": _canonical_hash(audit),
        "manifest_hash": _file_hash(directory / "selection-manifest.json"),
    }


def select_b0(period_directories: Mapping[float, Path]) -> dict[str, Any]:
    """从四条完整原始曲线独立重算，先质量筛选再按云请求和延迟排序。"""
    result: dict[str, Any] = {
        "status": "INCOMPLETE",
        "selected_period_s": None,
        "savings_claim_allowed": False,
        "curves": [],
        "errors": [],
    }
    if set(period_directories) != set(B0_PERIODS):
        result["errors"].append("all four registered periods .5/1/2/5 are required")
        return result
    for period in B0_PERIODS:
        try:
            result["curves"].append(_audit_curve(period, Path(period_directories[period])))
        except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
            result["errors"].append(f"{period}: {type(exc).__name__}: {exc}")
    if result["errors"]:
        return result
    curves = result["curves"]
    reference = curves[0]
    if any(
        row["assignment_hash"] != reference["assignment_hash"]
        or row["bindings"] != reference["bindings"]
        for row in curves[1:]
    ):
        result["errors"].append(
            "all methods must share fixed assignment/role/device/provider bindings"
        )
        return result
    feasible = [
        row
        for row in curves
        if row["static_success_rate"] >= 0.9
        and row["success_rate"] >= 0.8
        and row["safety_violation_rate"] <= 0.01
    ]
    if not feasible:
        result["status"] = "NO_FEASIBLE_BASELINE"
        return result
    winner = min(
        feasible,
        key=lambda row: (
            row["actual_cloud_requests"],
            row["mean_wall_duration_s"],
            row["period_s"],
        ),
    )
    result.update(
        status="SELECTED", selected_period_s=winner["period_s"], savings_claim_allowed=True
    )
    return result


def mode_switch_source_hashes() -> dict[str, str]:
    """读取模式提交和共同基线的实际源码hash，供selection冻结绑定。"""
    base = Path(__file__).parent
    return {
        **_source_hashes(),
        **{
            f"auto_mode/{name}": _file_hash(base / name)
            for name in (
                "models.py",
                "baseline_policies.py",
                "transition_service.py",
                "repository.py",
            )
        },
    }


def verify_mode_switch_policy(snapshot: Any) -> dict[str, Any]:
    """独立重算全部selection候选物理/成本和模式日志，拒绝只有hash的声明。"""
    from cloud_edge_robot_arm.auto_mode.models import ModeSwitchPolicySnapshot
    from cloud_edge_robot_arm.contracts import AutoModeTransition, AutoModeTransitionStatus

    verdict: dict[str, Any] = {"accepted": False, "errors": []}
    try:
        snapshot = ModeSwitchPolicySnapshot.model_validate(snapshot.model_dump())
        if snapshot.method_id == "B2":
            original = AutoModePolicy(version="auto-v1")
            if (
                snapshot.policy_version != original.version
                or snapshot.min_dwell_s != original.min_dwell_seconds
                or snapshot.cooldown_s != original.switch_cooldown_seconds
                or snapshot.max_switches != original.max_switches_per_task
                or snapshot.confirmation_count != original.confirmation_count
            ):
                raise ValueError("B2 original frozen mode rules cannot be rewritten by selection")
        if snapshot.source_hashes != mode_switch_source_hashes():
            raise ValueError("mode policy source identity changed")
        directory = Path(snapshot.selection_directory)
        path = directory / "mode-policy-selection.json"
        if _file_hash(path) != snapshot.selection_manifest_hash:
            raise ValueError("mode selection manifest hash mismatch")
        manifest = json.loads(path.read_text())
        if (
            manifest.get("schema_version") != "ced.mode-selection.v1"
            or manifest.get("stage") != "SELECTION"
        ):
            raise ValueError("mode policy requires an explicit selection manifest")
        candidates = manifest["candidates"]
        if not candidates or len({row["candidate_id"] for row in candidates}) != len(candidates):
            raise ValueError("mode selection candidates are empty or duplicated")
        curves = []
        for candidate in candidates:
            params = candidate["parameters"]
            if candidate["source_hashes"] != snapshot.source_hashes:
                raise ValueError("mode selection candidate source mismatch")
            relative = Path(candidate["directory"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("mode selection raw directory must stay inside its snapshot")
            raw = (directory / relative).resolve()
            if not raw.is_relative_to(directory.resolve()):
                raise ValueError("mode selection directory escapes snapshot")
            curve = _audit_curve(float(candidate["b0_period_s"]), raw)
            assignments = json.loads((raw / "assignments.json").read_text())
            commits = 0
            for assignment in assignments:
                log = json.loads(
                    (
                        raw / "cases" / assignment["assignment_id"] / "mode-transition-events.json"
                    ).read_text()
                )
                if (
                    log["policy_parameters"] != params
                    or log["source_hashes"] != snapshot.source_hashes
                ):
                    raise ValueError("case mode policy binding mismatch")
                transitions = [
                    AutoModeTransition.model_validate(row) for row in log["committed_transitions"]
                ]
                from cloud_edge_robot_arm.auto_mode.models import ModeTransitionCheckpoint

                checkpoints = [
                    ModeTransitionCheckpoint.model_validate(row) for row in log["checkpoints"]
                ]
                if len(checkpoints) != len(transitions):
                    raise ValueError("every mode commit must have one verified checkpoint")
                episode = json.loads(
                    (raw / "cases" / assignment["assignment_id"] / "episode.json").read_text()
                )
                previous_at = None
                previous_version = None
                for ordinal, transition in enumerate(transitions):
                    checkpoint = checkpoints[ordinal]
                    if (
                        checkpoint.task_id != transition.task_id
                        or transition.task_id != episode["episode_id"]
                        or checkpoint.mode_version != transition.expected_mode_version
                        or checkpoint.atomic_action_active
                        or checkpoint.confirmation_count < params["confirmation_count"]
                        or transition.committed_at is None
                        or checkpoint.persisted_at > transition.committed_at
                    ):
                        raise ValueError(
                            "mode selection checkpoint identity/boundary/confirmation is invalid"
                        )
                    if (
                        transition.status != AutoModeTransitionStatus.COMMITTED
                        or transition.committed_at is None
                        or transition.committed_at < transition.prepared_at
                        or transition.new_mode_version != transition.expected_mode_version + 1
                        or (
                            previous_version is not None
                            and transition.expected_mode_version != previous_version
                        )
                        or ordinal >= params["max_switches"]
                    ):
                        raise ValueError(
                            "mode selection transition CAS/order/limit evidence is invalid"
                        )
                    baseline_at = previous_at or datetime.fromisoformat(
                        log["initial_last_switch_at"]
                    )
                    required = max(float(params["min_dwell_s"]), float(params["cooldown_s"]))
                    if (
                        baseline_at.tzinfo is None
                        or transition.committed_at.tzinfo is None
                        or (transition.committed_at - baseline_at).total_seconds() < required
                    ):
                        raise ValueError("mode selection transition violates frozen dwell/cooldown")
                    previous_at = transition.committed_at
                    previous_version = transition.new_mode_version
                    commits += 1
            if commits == 0:
                raise ValueError("mode selection did not exercise any actual mode commits")
            curve.update(candidate_id=candidate["candidate_id"], parameters=params)
            curves.append(curve)
        reference = curves[0]
        if any(
            curve["assignment_hash"] != reference["assignment_hash"]
            or curve["bindings"] != reference["bindings"]
            for curve in curves[1:]
        ):
            raise ValueError("mode selection candidates do not share assignments and frozen roles")
        feasible = [
            curve
            for curve in curves
            if curve["static_success_rate"] >= 0.9
            and curve["success_rate"] >= 0.8
            and curve["safety_violation_rate"] <= 0.01
        ]
        if not feasible:
            raise ValueError("mode selection has no feasible candidate")
        winner = min(
            feasible,
            key=lambda curve: (
                curve["actual_cloud_requests"],
                curve["mean_wall_duration_s"],
                curve["candidate_id"],
            ),
        )
        if (
            manifest["selected_candidate_id"] != winner["candidate_id"]
            or snapshot.parameters() != winner["parameters"]
        ):
            raise ValueError("mode policy snapshot is not the verified selection winner")
        verdict.update(
            accepted=True,
            selection_manifest_hash=snapshot.selection_manifest_hash,
            policy_parameters=snapshot.parameters(),
        )
    except (ValueError, TypeError, KeyError, OSError, OverflowError, AttributeError) as exc:
        verdict["errors"].append(f"{type(exc).__name__}: {exc}")
    return verdict
