"""实验计数器和指标聚合。

这些计数器从实验事件和安全决策中累积，不代表真实硬件遥测；用于比较模式、
故障恢复和论文图表指标。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cloud_edge_robot_arm.contracts import SafetyDecision


@dataclass
class ExperimentCounters:
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    step_attempts: dict[str, int] = field(default_factory=dict)
    cloud_invocation_count: int = 0
    supervisory_decision_count: int = 0
    replan_count: int = 0
    command_count: int = 0
    telemetry_count: int = 0
    uploaded_bytes: int = 0
    downloaded_bytes: int = 0
    local_retry_count: int = 0
    safety_allow_count: int = 0
    safety_allow_with_limits_count: int = 0
    safety_pause_count: int = 0
    safety_reject_count: int = 0
    emergency_stop_count: int = 0
    stale_command_rejection_count: int = 0
    duplicate_command_rejection_count: int = 0
    reordered_command_rejection_count: int = 0
    simulated_collision_count: int = 0
    unsafe_counterfactual_count: int = 0
    mode_switch_count: int = 0
    deferred_switch_count: int = 0
    aborted_transition_count: int = 0
    dwell_block_count: int = 0
    cooldown_block_count: int = 0
    switch_limit_block_count: int = 0
    time_in_pcsc_ms: int = 0
    time_in_eteac_ms: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    cache_promotion_count: int = 0
    cache_quarantine_count: int = 0
    cache_invalidation_count: int = 0
    trusted_template_execution_count: int = 0
    fault_detection_latency_ms: int | None = None
    cloud_response_latency_ms: int | None = None
    recovery_latency_ms: int | None = None
    recovery_success: bool = False

    def record_safety(self, decision: SafetyDecision) -> None:
        if decision == SafetyDecision.ALLOW:
            self.safety_allow_count += 1
        elif decision == SafetyDecision.ALLOW_WITH_LIMITS:
            self.safety_allow_with_limits_count += 1
        elif decision == SafetyDecision.PAUSE:
            self.safety_pause_count += 1
        elif decision in {SafetyDecision.REJECT, SafetyDecision.REQUEST_CORRECTION}:
            self.safety_reject_count += 1
        elif decision == SafetyDecision.EMERGENCY_STOP:
            self.emergency_stop_count += 1

    def safety_decision_counts(self) -> dict[SafetyDecision, int]:
        return {
            SafetyDecision.ALLOW: self.safety_allow_count,
            SafetyDecision.ALLOW_WITH_LIMITS: self.safety_allow_with_limits_count,
            SafetyDecision.PAUSE: self.safety_pause_count,
            SafetyDecision.REJECT: self.safety_reject_count,
            SafetyDecision.EMERGENCY_STOP: self.emergency_stop_count,
        }

    def repeated_completed_step_count(self) -> int:
        return len(self.completed_steps) - len(set(self.completed_steps))
