# Basic native calibration source and action reference design

This is a proposed revision for root review, not a native certificate or implementation. It follows the authorized full R&D scope: same controller and top camera, edge model deferred, no dependency on T9 failure probability or INITIAL. The purpose is a genuine action-specific evidence source that can eventually satisfy the existing 0.01 m completion criterion. Current development data must remain excluded and cannot become heldout calibration by rehashing it.

## Why a new registration alone is insufficient

`vision/action_evidence.py:native_action_contract()` currently assigns unavailable bounds and confirms the object identity for every skill. `edge/evidence/validator.py:validate_evidence()` applies `e + v * (age + full_duration) <= 0.01`. The builder uses `max(timeout_ms, expected_duration_ms)`; `execution.py:resolved_step()` sets moving-skill timeout to 10 s.

The actual excluded outboard episode demonstrates an incompatible interpretation if v means total physical object motion through the intended action:

| Action | Raw steps | Duration in simulation seconds | Object-center displacement | Necessary uniform speed lower bound | Minimum v*duration | Minimum v*10s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LIFT | 1534–2229 | 2.8958333565 | 0.0878292524 m | 0.0303295258 m/s | 0.0878292524 m | 0.3032952577 m |
| MOVE_TO_REGION | 2349–3554 | 5.0208333735 | 0.3452214690 m | 0.0687578024 m/s | 0.3452214690 m | 0.6875780240 m |

Even exact geometry and zero age cannot admit either action with that interpretation. These are mathematical lower bounds from actual endpoint displacement, not continuous-speed certificates. Actual sampled maximum linear speeds are 0.2191290574 and 0.2361825081 m/s; those sampled maxima also cannot be promoted to a continuous future bound. Simulation and acquisition clocks remain distinct. The numerical counterexample assumes a correctly joined common time domain; missing mapping is an additional blocker.

## Recommended explicit reference semantics

Keep the threshold, full timeout/expected duration, TTL, clocks, conditions, version checks and SafetyShield. Define the motion term as motion of the **reference used to resolve the action**, with intentional commanded transport separated from localization, attachment and controller error. Publish a new versioned reference kind; do not retrofit new semantics into an old scalar certificate.

| Skill | Registered reference and required source |
| --- | --- |
| MOVE_ABOVE, APPROACH | Current object's contact/top-grasp geometry plus offset. Bind complete object/marker/tool geometry, current owned RGBD and exact resolved TCP endpoint. A mutable object reference still requires its applicable motion/drift source; an absolute cached point cannot silently stand in for it. |
| GRASP | Current object pose/contact reference, identified by registered marker/object attachment and full object extent. Require current calibration and an actual applicable future target-motion source through the full close horizon. Zero motion cannot be inferred from two frames or from a NORMAL scene name. |
| LIFT, RETREAT | The immutable world TCP endpoint actually computed by `resolved_step()` from owned current TCP and the requested height. Bind calibrated proprioception/frame, height, exact target_pose, controller orientation, execution payload and full timeout. Actual payload transport is intentional; attachment/holding and endpoint tracking remain required independent evidence. |
| MOVE_TO_REGION | Immutable resolved world TCP endpoint derived from independently localized destination/support and registered grasp clearance. Destination/source immutability must be proved for the supported simulation asset, not asserted by the model. Holding/contact/attachment remain independent conditions. |
| PLACE | Destination/support plus registered object-to-TCP relation and exact immutable resolved world endpoint. Require calibrated region/support localization and horizon/endpoint tracking evidence; placement/release/stability remain later effect evidence. |
| RELEASE, HOLD, OBSERVE | No automatic fixed-goal exemption. Use the actual requirement's object/support/contact reference; only a registered supported reference class can supply bounds. Terminal conditions remain evaluated on subsequent current observations. |

For an immutable commanded endpoint, a zero **reference-coordinate velocity** can be derived from exact immutable source/payload identity and the frozen controller's use of that endpoint. It is not a zero object/TCP velocity assertion or a continuous physical-motion certificate. Endpoint localization and controller terminal error must be covered by independently calibrated, action/horizon-specific evidence. Source change or endpoint recompilation invalidates the proof. For a fixed world region, prove its supported static MJCF attachment/configuration and source binding; this is simulation scope, not a hardware mount certificate.

The existing controller holds `desired_position` constant but changes joint actuator targets, including bounded load compensation. Therefore numeric goal immutability is supportable now at the source level; physical tracking/attachment accuracy is not certified by that fact. A proposed geometric bound for fixed-goal actions must explicitly cover **reference localization plus terminal target/TCP error over the registered full action horizon**. This is an action-completion geometry calibration, not a relabeled marker-point residual. It needs separate empirical data and source auditing.

GRASP's mutable object reference is a remaining explicit prerequisite. The preferred first implementation must not invent a motion certificate to close it. A later alternative is an independently calibrated full-horizon contact-completion error source that absorbs target drift into the geometric term; that changes the error quantity's semantics and needs its own versioned recipe/review. It cannot be introduced by writing zero into the current object-motion field. Neither route may weaken the 0.01 m or full-horizon condition.

## Exact proposed interfaces

Create `vision/native_references.py` for source-derived reference semantics and `vision/native_calibration.py` for registered originals/calibration verification and online consumption. Keep offline truth reconstruction in `research/native_geometry_calibration.py`.

```python
@dataclass(frozen=True)
class NativeActionReference:
    # Full detached command/step/target and source hashes, not a VALID carrier.
    kind: Literal['OBJECT_CONTACT', 'FIXED_WORLD_TCP_GOAL', 'RIGID_GRASP_CONTACT']
    reference_id: str
    reference_digest: str
    execution_payload_digest: str
    registration_digest: str
    observation_id: str
    observation_sha256: str
    plan_version: int
    command_seq: int
    context_hash: str
    role_bundle_hash: str

def resolve_native_reference(
    online: OnlineEvidenceSnapshot, contract: TaskContract, step: TaskStep, *,
    source: NativeCalibrationSource, role_binding: RoleRuntimeBinding,
) -> NativeActionReference | None: ...

@dataclass(frozen=True)
class NativeCalibrationRegistration:
    registry_path: str
    registry_sha256: str
    original_file_hashes: Mapping[str, str]
    current_source_hashes: Mapping[str, str]
    # Detached complete assignments, components/history, domain and geometry below.

class NativeCalibrationSource:
    def revalidate(self, role_binding: RoleRuntimeBinding) -> None: ...
    def estimate(
        self, online: OnlineEvidenceSnapshot, contract: TaskContract, step: TaskStep, *,
        reference: NativeActionReference, full_horizon_s: float,
        now: datetime, role_binding: RoleRuntimeBinding,
    ) -> NativeCalibrationEstimate: ...

def native_action_contract(
    online: OnlineEvidenceSnapshot, contract: TaskContract, step: TaskStep, *,
    native_source: NativeCalibrationSource | None = None,
    role_binding: RoleRuntimeBinding | None = None, now: datetime | None = None,
) -> ActionEvidenceContract: ...

def validate_native_action_evidence(
    action: ActionEvidenceContract, online: OnlineEvidenceSnapshot, *,
    native_source: NativeCalibrationSource | None,
    role_binding: RoleRuntimeBinding, now: datetime,
) -> EvidenceVerdict: ...
```

The concrete source is constructed from the application's pinned registry and owned capture/grounding source, not from request JSON or an audit-result token. A requested reference/result is recomputed from the exact current registered command and sources. Caller finite scalars, status flags, expected hashes supplied by the same untrusted request, injected oracle fields and arbitrary provider subclasses do not admit anything. Python object construction/hashes alone do not prove measurement authenticity; the application-owned publisher/registry and original acquisition provenance are separate required sources.

The new native validation wrapper first recomputes reference, effective action horizon and registered-source quantities, comparing the current action's values/proof and exact owned payload; then it delegates unchanged numerical/precondition checks to canonical `validate_evidence()`. All three actual native consumers use this wrapper. Generic non-native replay contracts retain their existing validator behavior. Thus a manually constructed finite `VisualEvidence`, even with forged native metadata, cannot take an actual native execution route.

`NativeCalibrationEstimate` carries independent optional geometry and reference-motion quantities plus reasons, the reference kind/digest, calibration original/source digests, observation/checksum/acquisition domain, action/horizon, target, role/context and versions. Its source verifier recomputes every quantity from registered originals before each use. Partial geometry may be inspectable, but `native_action_contract()` copies usable action bounds only after the applicable full source supports the action. Unsupported quantities remain unavailable. A fixed-goal coordinate proof is issued only by recomputing the exact goal/source invariant, not by accepting `motion_bound=0`.

## Artifact and empirical requirements

The registry binds exact asset, camera descriptor/calibration version, marker ID/45 mm/attachment `[0.1,0,0.03505]`, complete object half-extents, object class/identity/appearance source, tool/TCP and grasp profile, region/support registration, controller/config/estimator sources, reference kinds/actions/horizon limits and clock domain. Do not silently extend the old grasp-profile asset hash to outboard-v3.

The independent original inventory contains preregistered groups and every assigned attempt/frame/action, source connected-component identities and prior usage histories; all heldout allocations are retained, including missing/UNKNOWN/failed captures and action failures. Calibration groups exclude fit/development/selection/test ancestors and the already inspected outboard group. A certificate cannot be built from favorable surviving frames. Before/after inventories reject source drift, symlinks, extra/missing files and mismatched source/replayed labels.

Offline reconstruction reruns the frozen estimator on genuine RGBD without truth inputs, then compares inferred complete rigid geometry and the actual reference/TCP quantities to independently joined simulator references. Marker-center error is insufficient: transform the eight object vertices and registered contact/TCP points through both estimated and reference poses, including angular lever arms. For fixed-goal action completion, include the independent actual terminal/reference error through the declared full horizon, including timeouts/failures. Use joint group maxima of the defined error quantity; do not add unrelated marginal 90% bounds while claiming joint 90% coverage.

Grouped split-conformal rank is `ceil((n+1)*coverage)`; at coverage0.9 at least nine independent supported calibration groups are needed for a finite rank. The artifact records complete groups, residuals, rank, domain/support and every missing/ineligible record. A content hash or `source_accepted` flag is insufficient: recompute grouping, residuals, rank, exact recipe and source provenance. SOFTWARE_ONLY data tests arithmetic/source guards but cannot certify the online source. One development episode's maximum is not a calibration bound.

Clock/horizon records must join actual acquisition, local monotonic ownership, simulation advancement and complete action bounds without assuming wall seconds equal simulation seconds. Fixed-goal immutability removes physical goal-coordinate drift, not acquisition-age/version/horizon requirements. Mutable reference motion needs its own valid continuous/horizon certificate; discrete endpoint/state samples remain diagnostics. No online API accepts future truth, physics geometry labels, fault labels or terminal outcomes.

## Downstream seams and completion criteria

`runtime_binding.py:RoleRuntimeBinding` gains an optional concrete pinned native registration/source anchor; registry/calibration originals and both new native source modules participate in device source identity. Registry digest must be bound by the frozen device inventory. Avoid digest cycles: calibration artifacts bind device/controller/calibration component versions, while per-call estimates bind the current role bundle. Absence preserves the current closed path.

`execution.py:worker_dispatch_guard()` and `require_native_action_evidence()` pass the same owned source, role binding and now, revalidating at each existing boundary through `validate_native_action_evidence()`. The fixed-goal proof must match `resolved_step()` and the actual payload sent to SafetyShield/SkillExecutor; recompilation invalidates it. `evaluation.py:ExecutionPolicy` carries the concrete source as an optional private field and rejects a provider that differs from its role-bound anchor.

An existing important horizon seam is `owner_registration.py:bind_step_grounding()` around lines933–955: it takes the maximum of original duration and resolved timeout/expected duration and requires an independent duration calculation when resolution extends it. Worker native wrappers currently substitute `requirement.expected_duration_s`. The new source and all native rewraps must use the effective registered grounding duration, never shorten to the original requirement. A stale/missing required duration check rejects the reference before any numeric gate.

`repositories/event_autonomy/visual_verification.py:_phase_verdicts()` must use that same application-owned source, not a serialized finite result. Thread an optional `native_source` through `derive_route()` and its private pure helpers from the memory/SQLite repository's application-owned source registry. Defaults remain None. Worker runtime/owner capture and grounding receipts supply the exact original/current source identities; request JSON cannot select another provider or reference. Include changed repository/worker/native sources in the frozen worker inventory.

Native provenance/reference metadata must survive every `ActionEvidenceContract` rewrap; add a keyword-only `native_reference`/source-proof field to the evidence or action contract and preserve it at all three callers. Canonical native validation reruns the concrete source or consumes only the just-recomputed source inside the same boundary; old generic replay fixtures can retain their existing non-native contract semantics. Emit explicit source/reference/horizon reasons. Current malformed/incomplete/changed sources are INVALID or UNKNOWN; only fully supported references receive usable numeric bounds. The generic criterion, SafetyShield, hard-stop priority and ordinary condition evaluator stay intact.

Software completion is a source-bound implementation with tested exact reconstruction and all three consumers aligned. Native admission and full task completion require actual independent calibration, supported mutable/contact reference sources, source/horizon/clock checks and later physical/online validation. They remain tracked work; an UNKNOWN-only module does not complete the full objective.
