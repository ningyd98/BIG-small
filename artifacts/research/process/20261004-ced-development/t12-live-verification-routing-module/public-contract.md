# Persistent verification public contract (SOURCE_ROUTE_ONLY)

API stable; implementation is under scoped CPU verification, not actual factory integration. No callback returning a verdict/action/VALID, scope override, new executor or actual permission is accepted. Stored history is information, never capture/execution authority.

```python
EventAutonomyRepository.route_visual_verification_if_current(
    *, request: VisualVerificationRouteInput,
) -> VisualVerificationRouteWriteResult | None
EventAutonomyRepository.get_visual_verification_route(
    task_id: str, event_key: str,
) -> VisualVerificationRouteRecord | None

VisualVerificationRouteInput(
    *, original: VisualOriginalPlan, publication: VisualOwnerPublicationRecord,
    online: OnlineEvidenceSnapshot, step_id: str, attempt: int, phase: str,
    event_key: str, execution_contract: TaskContract,
    completion: VisualEffectCompletion | None = None,
)
```

Phases: PRECONDITION, NATIVE_PRE_SAFETY, NATIVE_PRE_SKILL, CLOUD_RETURN, AFTER_EFFECT, POST_HOLD, TERMINAL. Input deep snapshots complete raw original/publication/model schemas; to_payload returns detached dictionaries, from_payload/from_json strictly reconstruct all nested sources. Publication provides exact expected epoch/revision/generation/contract/checkpoint/pool/retry identities. `online.context_hash` is still source_checkpoint.checkpoint_hash. Currentstep execution_contract must equal original or exact current published grounding view; timing/retry/all other steps/policy remain unchanged. Safety-limited changes require their own fresh authorized grounding/publication.

The result has `.record` and `.write_disposition`: NEW_COMMIT or HISTORICAL_DUPLICATE. Both have fixed source scope; NEW_COMMIT means only this transaction wrote once. REOBSERVE irrevocably reserves and claims one source capture attempt; only a separately source/lease/current-bound worker consumer of the unique NEW_COMMIT may consider capture. Duplicate/history/restart never recaptures or refunds. None means missing/changed source/CAS, no debit or permission. The initial capabilities are only CONTINUE/REOBSERVE/STOP; retry authority remains the existing recovery producer.

The immutable record exposes `.route`, `.reasons`, `.scope`, `.to_payload()`, `.to_json()`, `.digest()`, `from_json`. It contains complete request, stable source and input/semantic hashes, canonical verdicts/reasons, transaction clock, before/after verification pool, produced normal publication/hash, contexts and one-shot capture claim. Constructor/load recompute the source transition, not merely its summary hash. Pool/publication/history commit together under memory lock or SQLite BEGIN IMMEDIATE.

```python
VisualEffectCompletion(
    *, result: SkillExecutionResult, task_id: str, plan_id: str, robot_id: str,
    step_id: str, attempt: int, plan_version: int, command_seq: int,
    started_at: datetime, returned_at: datetime, before_observation_id: str,
    execution_payload_hash: str, source_checkpoint_hash: str,
    source_hashes: Mapping[str, str],
)
```

This completion source carrier authenticates nothing. AFTER_EFFECT requires complete binding and an independently new frame after returned_at; absent carrier, mismatched versions/result/source or FAILED result stops. POST_HOLD and TERMINAL additionally require their full registered canonical condition mapping. No boolean success alone resolves an actual recovery or grants completion. Missing actual producer stays unavailable.

Exact context/hash domains for root factory:

- `source_context_hash` is the original checkpoint hash; record domain `visual.checkpoint-context.v1`.
- `native_action_context_hash(role_bundle_hash, execution_contract, step_id)` computes SHA256 of canonical JSON `{role_bundle_hash, contract: complete execution_contract.model_dump(mode='json'), step: exact currentstep.model_dump(mode='json')}`. This preserves existing execution.py payload and hash, named `visual.native-action-context.v1` by the record; do not add the domain label to the old hash payload.
- `evidence_content_hash(online)` computes SHA256 of canonical JSON `{schema_version:'visual.verification.evidence-content.v1', observation:complete model JSON, robot_state:complete model JSON, visual_facts:complete strict JSON, plan_version, command_seq}`. It deliberately excludes only context_hash. Native/checkpoint OnlineEvidenceSnapshot views use this exact same evidence body; their distinct contexts cannot substitute for each other.
- `camera_source_descriptor_sha256(observation)` hashes canonical JSON `{schema_version:'visual.rgbd.camera-source-descriptor.v1', source,width,height,intrinsics,camera_to_world,depth_convention,calibration_version}` using the observation's model JSON fields. If an original ConditionSpec tolerance carries `camera_source_descriptor_sha256`, the producer recomputes and requires exact match. Without it, only registered version/spec software consistency is checked: no calibrated camera/source acceptance is invented.

Canonical JSON: sort_keys=True, separators=(',', ':'), default ASCII escaping, allow_nan=False; tuple/list representations use JSON arrays. Integers are strict at schema-defined integer boundaries; legitimate evidence booleans remain booleans. Whole observation hashes/checksums and camera descriptor are different hash meanings.

Actual initial planning still has a concrete bootstrap gap: before cloud draft/compiled immutable original exists, there is no coherent original/active/checkpoint/publication group for these methods. Initializing only the pool creates a partial group correctly rejected by reviewed initializer. Root must supply a separately reviewed bootstrap registration/atomic promotion or a genuinely registered original. This module never invents an original or promotes its source-only records to live owner/mode/native/METHOD authority. No worker/execution/evaluation hook is changed here.
