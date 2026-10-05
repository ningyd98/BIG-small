# Raw episode v3 pure schema implementation plan

> Execute inline using the approved two-file ownership and TDD; root independently reviews the frozen release.

Goal: strict immutable raw physics/control/command/action/frame/clock records and a pure whole-episode coverage view. Scope is SOURCE_CONSISTENCY_ONLY; no sampling, file writer, callback, simulator/provider execution or actual clock/owner/method authority.

Owned NEW paths: src/cloud_edge_robot_arm/research/raw_episode_v3.py and tests/test_raw_episode_v3.py. Design references: a20b507772d006f02352c70318f3b5b1db224c45acce2d2a20b1526a1127ed92 / report b926fabe4926aa4354855a07f7c8d07a6b46398194bb1a5cea211c862b5f0803. Existing owner-registration types are cloned and revalidated as concrete types, not accepted through overridden digest/to_payload or opaque hash alone.

Exact public API:
- RawEpisodeIdentityV3(attempt_id, assignment_id, assignment_hash, episode_id, source_kind, owner_identity:VisualOwnerIdentity, scene_hash, asset_hash, config_hash, role_bundle_hash, model_snapshot_hash, source_hashes, clock_domain_id).
- ClockDescriptorV3(clock_domain_id, owner_epoch, monotonic_implementation, utc_implementation, monotonic_resolution_ns, utc_resolution_ns, utc_uncertainty_ns:int|None, source_hashes); ClockPairV3(clock_domain_id, descriptor_hash, sequence, mono_before_ns, utc_at, mono_after_ns).
- RawIntervalV3(interval_id, record_seq, identity, kind, start:ClockPairV3, end:ClockPairV3|None, start_step, end_step:int|None, start_sim_time_s, end_sim_time_s:float|None, disposition, error:str|None).
- RawPhysicsStepV3(record_seq, identity, physics_step, previous_state_hash, post_state_payload, control_payload, physics_interval_id, control_interval_id, purpose_interval_id).
- RawCommandV3(record_seq, identity, command_seq, command_payload, interval_id, parent_interval_id, owner_action_span_id:str|None, effective_from_step:int|None). Original accepted/rejected/overwritten commands are all retained; no inference of effective control from acceptance.
- TypedActionSpanV3(record_seq, identity, span_id, original_plan:VisualOriginalPlan, step_id, attempt, grounding:StepGroundingBinding|None, interval_id, command_seq_start, command_seq_end, returned_result:Mapping|None, disposition, error:str|None). Interval physics indices define `(n0,n1]`; command ranges are `[c0,c1)`. Grounding is required for ONLINE_CED started attempts, not forged for blocked/no-plan captures or teacher/source-only records.
- FrameAcquisitionV3(record_seq, identity, acquisition_id, interval_id, observation_payload:Mapping|None, pass_state_hashes, file_hashes, input_role, source_acquisition_id:str|None, transform_payload:Mapping|None, transform_source_hashes). Failed acquisition retains no frame and its actual interval/error. Derived ONLINE frames bind clean SOURCE acquisition and original transform policy/source separately.
- ActionFrameJoinV3(record_seq, identity, span_id, acquisition_id, relation, observation_id, checksum_sha256).
- RawEpisodeRecordsV3(intervals, physics, commands, actions, frames, joins).
- RawEpisodeEnvelopeV3(identity, clock_descriptor, reset_state_payload, terminal_state_payload, evaluation_start_step, physics_dt_s, terminal_command_seq, allocated_action_span_ids, allocated_acquisition_ids, original_file_hashes, task_deadline_at, verification_deadline_at, contract_deadline_at).
- validate_raw_episode_v3(envelope, records)->RawV3ConsistencyView(status:COMPLETE|INCOMPLETE|INVALID,scope,counts,reasons,monotonic_coverage,utc_mapping,source_digest). COMPLETE means internally coherent complete recorded source structure only. UTC uncertainty None remains UNAVAILABLE; continuous_motion NOT_CERTIFIED always.
- All concrete record/envelope/records types expose detached to_payload()/digest(); RawEpisodeEnvelopeV3.from_json and RawEpisodeRecordsV3.from_json reconstruct strict concrete nested classes. Duplicate keys/nonfinite/coercion/unknown fields/aliases/subclass overrides reject. No result to_json can produce reusable authority.

Tasks:
- [x] Save this API plan and review boundaries; create missing-module behavioral test via import_module inside a test and verify qualified RED.
- [x] Expand strict constructor/serialization and hand-built complete120-settle+one-skill fixture tests; verify before implementation RED.
- [x] Implement immutable cloning/strict JSON/models and time/identity predicates; implement full step/control/command/purpose/action/frame coverage and original requirements/grounding/deadline comparison.
- [x] Add targeted RED before any newly discovered constructor/coverage fix. Partial/missing/zero-step/rejected/exception and crossed-delay cases preserve denominators; malformed contradictions INVALID, omitted source INCOMPLETE.
- [x] Scoped owned+owner/conditional CPU tests, Ruff/format2/coldmypy1; no full suite, simulator state/step/renderer/provider, commit or existing-source edit. Freeze exact reviewed base/reference closure+owned2 with AST/hash checks and independent review handoff.

Review focus and tests: mutable subclass nested requirement/grounding or JSON alias; missing/duplicate recorded source without losing allocations; correct zero-step and same-step command semantics; source vs derived online frame/checksum confusion; wall-clock jump/domain mismatch or delayed callback falsely becoming actual UTC/continuous-motion authority. All fixtures SOFTWARE_ONLY.


Final interface additions discovered by qualified RED:
- TypedActionSpanV3 also requires `executed_step_payload:Mapping|None`; omission is INCOMPLETE and mismatched original/grounded full TaskStep arguments INVALID.
- FrameAcquisitionV3 also carries `camera_state_payload:Mapping|None` and `joined_physics_observation_hash:str|None`. Native camera binary-state digest is independently replayed and kept distinct from canonical PhysicsStepObservation payload hashing.
- RawEpisodeEnvelopeV3 also binds `initial_controller_targets:{joints_rad,fingers_m}` and `actuator_delay_steps:int`; applied targets are replayed from all accepted original command events including overwrites and cross-action delayed effects.
- Input-record denominator and distinct physical acquisition intervals are separate counts; SOURCE and ONLINE derivatives share one interval, with exact frozen corruption policy/pixels replayed.
- Reviewed immutable dependency basis is owner-repository fix1 772 files / manifest0271d4785ef84c7a4f5fdcf4efd0ded0e9baccec02f7351f04d7b9bde4a917d6, plus only owned2 =774; moving worker source is excluded.
