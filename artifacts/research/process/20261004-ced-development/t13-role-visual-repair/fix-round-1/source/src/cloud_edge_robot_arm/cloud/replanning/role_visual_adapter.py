"""Existing LocalReplanningService adapter seam for a role-bound visual candidate."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.replanning.context import ReplanningContext
from cloud_edge_robot_arm.cloud.replanning.role_visual_repair import (
    PROMPT_VERSION,
    GroundingProvider,
    RoleVisualRepairProvider,
    RoleVisualRepairSource,
    authorized_window,
    digest,
)
from cloud_edge_robot_arm.cloud.replanning.visual_repair import build_visual_repair, repair_window
from cloud_edge_robot_arm.contracts.models import LocalReplanningRequest, LocalReplanningResponse
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

SourceProvider = Callable[
    [LocalReplanningRequest, ReplanningContext | None], RoleVisualRepairSource | None
]


class RoleVisualReplannerAdapter:
    planner_name = "role-visual-repair"

    def __init__(
        self,
        *,
        planner: RGBDPlannerAdapter,
        binding: RoleRuntimeBinding | None,
        source_provider: SourceProvider | None = None,
        grounding_provider: GroundingProvider | None = None,
        full_remaining: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.planner = planner
        self.binding = binding
        self.source_provider = source_provider
        self.grounding_provider = grounding_provider
        if type(full_remaining) is not bool:
            raise ValueError("full_remaining must be a boolean")
        self.full_remaining = full_remaining
        self.clock = clock or (lambda: datetime.now(UTC))
        self.last_binding_hash: str | None = None

    def replan(
        self, request: LocalReplanningRequest, context: ReplanningContext | None = None
    ) -> LocalReplanningResponse:
        self.last_binding_hash = None

        def unavailable(reason: str) -> LocalReplanningResponse:
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="MORE_OBSERVATION_REQUIRED",
                reason=reason,
                new_steps=[],
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                created_at=self.clock(),
                planner_name="role-visual-repair-unavailable",
                prompt_version=PROMPT_VERSION,
            )

        if self.binding is None or self.source_provider is None or self.grounding_provider is None:
            return unavailable("actual_source_binding_or_geometry_missing")
        try:
            provider_context = deepcopy(context)
            context_hash = digest(provider_context)
            source = self.source_provider(request.model_copy(deep=True), provider_context)
            if digest(provider_context) != context_hash:
                return unavailable("source_provider_mutated_service_context")
            if not isinstance(source, RoleVisualRepairSource):
                return unavailable("typed_actual_source_missing")
            visual = source.context
            if context is not None and (
                digest(context.active_contract) != digest(visual.active_contract)
                or context.checkpoint is None
                or digest(context.checkpoint) != digest(visual.checkpoint)
            ):
                return unavailable("service_current_context_changed")
            if source.evidence_scope == "ACTUAL_SOURCE" and context is None:
                return unavailable("actual_service_context_missing")
            window = repair_window(visual)
            observation = visual.online_evidence.observation
            provider = RoleVisualRepairProvider(
                planner=self.planner,
                binding=self.binding,
                source=source,
                grounding_provider=self.grounding_provider,
                clock=self.clock,
                full_remaining=self.full_remaining,
            )
            provider.validate(
                request, authorized_window(visual, self.full_remaining), observation, visual
            )
            response = build_visual_repair(
                request,
                window,
                observation,
                context=visual,
                provider=provider,
                full_remaining=self.full_remaining,
                clock=self.clock,
            )
            self.last_binding_hash = provider.last_binding_hash
            if response.outcome == "REPLANNED":
                response = response.model_copy(
                    update={
                        "planner_name": (
                            "role-visual-repair-software"
                            if source.evidence_scope == "SOFTWARE_ONLY"
                            else "role-visual-repair-max"
                        ),
                        "prompt_version": PROMPT_VERSION,
                        "reason": "source_bound_candidate_requires_submit_revalidation",
                    }
                )
            return response
        except Exception:
            # Exceptions and remote content are never serialized into public evidence.
            return unavailable("role_source_or_canonical_geometry_unavailable")
