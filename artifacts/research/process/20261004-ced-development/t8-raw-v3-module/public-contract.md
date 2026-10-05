# Frozen raw-v3 public contract

All objects are detached strict immutable source records. Constructors and from_json recursively revalidate concrete nested types; no callbacks, source IO, sampler, actual owner/method/admission flag or dispatcher.

`RawEpisodeIdentityV3`

```python
attempt_id: str
assignment_id: str
assignment_hash: str
episode_id: str
source_kind: Literal['SOFTWARE_ONLY', 'ONLINE_CED', 'GROUND_TRUTH_TEACHER']
owner_identity: VisualOwnerIdentity
scene_hash: str
asset_hash: str
config_hash: str
role_bundle_hash: str | None
model_snapshot_hash: str | None
source_hashes: Mapping[str, str]
clock_domain_id: str
```

`ClockDescriptorV3`

```python
clock_domain_id: str
owner_epoch: str
monotonic_implementation: str
utc_implementation: str
monotonic_resolution_ns: int
utc_resolution_ns: int
utc_uncertainty_ns: int | None
source_hashes: Mapping[str, str]
```

`ClockPairV3`

```python
clock_domain_id: str
descriptor_hash: str
sequence: int
mono_before_ns: int
utc_at: datetime
mono_after_ns: int
```

`RawIntervalV3`

```python
interval_id: str
record_seq: int
identity: RawEpisodeIdentityV3
kind: Literal['PHYSICS_STEP', 'CONTROL_APPLY', 'COMMAND', 'ACQUISITION', 'EXECUTOR_ATTEMPT', 'SETTLE', 'WAIT', 'VERIFY_ADVANCE', 'HOLD', 'TERMINATION']
start: ClockPairV3
end: ClockPairV3 | None
start_step: int
end_step: int | None
start_sim_time_s: float
end_sim_time_s: float | None
disposition: Literal['COMPLETE', 'PARTIAL', 'ABORTED']
error: str | None
```

`RawPhysicsStepV3`

```python
record_seq: int
identity: RawEpisodeIdentityV3
physics_step: int
previous_state_hash: str
post_state_payload: Mapping[str, Any]
control_payload: Mapping[str, Any]
physics_interval_id: str
control_interval_id: str
purpose_interval_id: str
```

`RawCommandV3`

```python
record_seq: int
identity: RawEpisodeIdentityV3
command_seq: int
command_payload: Mapping[str, Any]
interval_id: str
parent_interval_id: str
owner_action_span_id: str | None
effective_from_step: int | None
```

`TypedActionSpanV3`

```python
record_seq: int
identity: RawEpisodeIdentityV3
span_id: str
original_plan: VisualOriginalPlan
step_id: str
attempt: int
grounding: StepGroundingBinding | None
interval_id: str
command_seq_start: int
command_seq_end: int
returned_result: Mapping[str, Any] | None
disposition: Literal['RETURNED', 'REJECTED', 'PARTIAL', 'ABORTED']
error: str | None
executed_step_payload: Mapping[str, Any] | None
```

`FrameAcquisitionV3`

```python
record_seq: int
identity: RawEpisodeIdentityV3
acquisition_id: str
interval_id: str
observation_payload: Mapping[str, Any] | None
camera_state_payload: Mapping[str, Any] | None
joined_physics_observation_hash: str | None
pass_state_hashes: tuple[str, ...]
file_hashes: Mapping[str, str]
input_role: Literal['SOURCE', 'ONLINE']
source_acquisition_id: str | None
transform_payload: Mapping[str, Any] | None
transform_source_hashes: Mapping[str, str]
```

`ActionFrameJoinV3`

```python
record_seq: int
identity: RawEpisodeIdentityV3
span_id: str
acquisition_id: str
relation: Literal['BEFORE_SUBMIT', 'DURING_ACTION', 'AFTER_RETURN', 'TERMINAL']
observation_id: str
checksum_sha256: str
```

`RawEpisodeRecordsV3`

```python
intervals: tuple[RawIntervalV3, ...]
physics: tuple[RawPhysicsStepV3, ...]
commands: tuple[RawCommandV3, ...]
actions: tuple[TypedActionSpanV3, ...]
frames: tuple[FrameAcquisitionV3, ...]
joins: tuple[ActionFrameJoinV3, ...]
```

`RawEpisodeEnvelopeV3`

```python
identity: RawEpisodeIdentityV3
clock_descriptor: ClockDescriptorV3
reset_state_payload: Mapping[str, Any]
terminal_state_payload: Mapping[str, Any]
evaluation_start_step: int
physics_dt_s: float
terminal_command_seq: int
allocated_action_span_ids: tuple[str, ...]
allocated_acquisition_ids: tuple[str, ...]
original_file_hashes: Mapping[str, str]
task_deadline_at: datetime
verification_deadline_at: datetime
contract_deadline_at: datetime
initial_controller_targets: Mapping[str, Any]
actuator_delay_steps: int
schema_version: ClassVar[str]
scope: ClassVar[str]
```

`RawV3ConsistencyView`

```python
status: Literal['COMPLETE', 'INCOMPLETE', 'INVALID']
counts: Mapping[str, int]
reasons: tuple[str, ...]
monotonic_coverage: Literal['COMPLETE', 'INCOMPLETE']
utc_mapping: Literal['BRACKETED', 'UNAVAILABLE']
source_digest: str
scope: ClassVar[str]
continuous_motion: ClassVar[str]
```

`validate_raw_episode_v3(envelope, records) -> RawV3ConsistencyView` reconstructs and compares the entire supplied graph. COMPLETE is source consistency only; unknown UTC uncertainty remains UNAVAILABLE, and continuous_motion remains NOT_CERTIFIED. A later concrete disk/source/owner auditor is still required before real integration.
