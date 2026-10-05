# Approved isolated role visual repair design

Ownership: two new source modules (`role_visual_repair.py`, `role_visual_adapter.py`) plus their software-only tests and process artifacts. No planner, service, builder, configuration, repository, executor, or dependency edits.

A dedicated RGBDPlannerAdapter is injected with the explicitly chosen Max profile/key, paid-call permission, current RoleRuntimeBinding, REPLANNER cost ledger, and real paired RGB/depth transport. No global profile activation or model fallback. `_request_visual` is reused through one isolated helper because public `plan` emits a fixed full pick/place contract unsuitable for preserving an authorized repair window. Existing builder `_inputs_valid` is reused read-only for identical direct-provider request/frame/completed-effect checks.

The source provider supplies the current full-bound VisualRepairContext and per-authorized-step ActionEvidenceContract. Missing role binding/profile/key/calibration/geometric error/motion bound/conditions/grounder produces unavailable before any paid request. The remote response is strict intent-only JSON: one original ID and skill per authorized step, image pixels, exact context binding hash. The injected local grounder returns detached TaskStep, full condition proof, source binding hash and exact candidate step payload hash. Original conditions/timing/retry remain frozen. Neither callback produces admission or execution.

The existing builder retains unrelated pending steps and completed effects. B4 explicitly expands only the authorized pending window, using the same failure/request/frame/source and all ordinary gates. Existing LocalReplanningService owns candidate persistence; ReplanApplyGuard and actual stage/resume gateway remain separate prerequisites.

Scope flags describe supplied evidence provenance. SOFTWARE_ONLY MockTransport tests cannot remove actual recovery blockers or certify physical task completion. ACTUAL_SOURCE does not itself admit a candidate: nonempty original requirements and genuine current geometry/proof/provider provenance are necessary; canonical submit guard must independently revalidate.

## Resolved remote payload ruling

Automatic approval review rejected a proposed full-state remote expansion before any edit or live call. The coordinator selected a safer alternative: remote payload now contains only the task instruction, paired RGB/depth-derived images, opaque request/frame/window/context/source/bundle/schema bindings, original authorized step ID + skill, and fixed STEP_REPAIR_REQUIRED enum. Full request state, checkpoint/robot/visual facts/dependencies, world/camera poses, step parameters/timing/retry and complete ConditionSpecs remain LOCAL. Exact local proof preservation and post-return grounding replace full-state remote reasoning. The rejected expansion and original RED remain archived; the revised intent-only allowlist regression passes. No rejected expansion was retried and no real network call occurred.

## Actual integration prerequisites

1. A genuine SourceProvider from current native RGBD and a local GroundingProvider with calibrated geometry, motion/error bounds and original frozen requirements. UNKNOWN angular-motion/source conditions remain unavailable before Max calls; legacy empty original conditions cannot acquire fabricated actual authority.
2. A newly frozen role bundle/source inventory including the new provider/adapter and existing builder/dependency/planner/message sources. Historical T3 snapshots do not authorize new code. Remote API unknown revision/weights/quantization remain null.
3. Canonical candidate submit proof and actual existing-executor stage/resume gateway/checkpoint reconciliation. ACK/resume receipt/observer.on_step_started are not evidence of motion completion.
4. Actual recovery execution evidence must bind canonical ReplanExecutionReceipt plus real SkillExecutionResult completion to durable recovery/attempt/repair identity and transaction-current checkpoint. A callback exposing only a step ID cannot invent these identities or timestamps. Root should instrument the existing executor/gateway, not add a third executor.
5. Full fresh canonical postconditions after real completed attempts, task verification pool reservations before real recapture, and actual source admission are required before any physical resolution/acceptance.
