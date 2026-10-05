# Actual visual owner registration bridge design

Date: 2026-10-04. Scope: read-only architecture and implementation-ready interfaces. Root authorized the design; no production files, admission flags or dispatch paths are changed. All proposed types/APIs below are **new design**, not capabilities already implemented. The actual INITIAL, independently joined remote billing, calibrated risk/finite selection, native geometric/motion certificates and physical resume prerequisites remain unavailable.

The goal is to let the real visual worker publish one coherent, durable source of its original planned requirements, current checkpoint/mode and separately derived per-step intent. Runtime composition must read that real owner rather than a MOCK harness or caller VALID flags, and all physical operations remain on the existing `_VisualEpisode.execute` → native gate → SafetyShield → native gate → existing SkillExecutor path.

## Evidence and present behavior

`source/` freezes37 exact read-only Python references. `source-hashes.json` SHA256 is `5ca07e57a55b2b41f2a64592b6b89843c06f0ea8be999ceb55ed1554ffd73f15`; each file hash/AST and its live bytes were checked at capture. This is a design reference snapshot, not a full transitive runnable release or a new test acceptance claim. Exact file bytes and line locations below allow a reviewer to reconstruct the findings.

| Site | Current behavior | Bridge implication |
|---|---|---|
| `simulation_runtime/worker.py:620` `_run_visual_closed_loop` | Creates/reset/settles a new backend, creates one robot/capture, invokes the visual episode, shuts backend down, then appends evidence events. ExecutionPolicy receives remaining timeout/cancel callback but defaults to LEGACY and has no owner repositories. | Construct the bridge on this owner thread, bind actual job/attempt/lease and backend episode before planning, stream durable boundaries while live, detach before backend shutdown. This does not implicitly configure OPENCV or an actual method. |
| `worker.py:1200` `_active_job_cancelled` | Rechecks persisted worker/lease identity, expiry, cancel, heartbeat failure and released lease. | Keep this callback authoritative at model returns, actor commands and each physical boundary; registration cannot override it. |
| `vision/execution.py:534` episode constructor | Shares capture/robot backend, starts monotonic task deadline and a new in-process VerificationBudgetState, constructs the existing shield/SkillExecutor. Has local `_state_version`, `_plan_version`, active step, but no durable event/mode repository. | Inject an optional source bridge/observer; do not construct another task or physical executor. Replace new-budget initialization only for explicit registered-owner paths with initialize-if-absent durable state. |
| `execution.py:440` grounded_contract | Produces initial contract1/seq1 after planning, forces task ID to backend episode, removes optional HOME and applies reviewed runtime constraint normalization. Sets contract expiry to post-plan NOW+policy.timeout_s. | Freeze the exact compiled original contract and original cloud proposal hashes separately. Preserve the earlier episode absolute deadline; post-plan contract TTL must never extend the effective task/budget deadline. |
| `execution.py:492` resolved_step | Derives physical parameters from calibrated RGBD grasp/destination plus proprioception, changes timeout/retry and clears old pre/success lists. `run_online:1355` makes a different per-step contract at the same versions. | A derived execution view is never saved as another active original revision. Bind the exact transform/source/frame and original requirements in a sidecar, and keep the cleared legacy lists from erasing canonical requirements. |
| `vision/action_evidence.py:17` native_action_contract | Canonical specs are built from `step.preconditions`/`success_conditions`; current geometry/motion bounds are intentionally None, error policy.01m, rgbd, default TTL5s. | Freeze source-owned requirements before resolution; reconstruct current ActionEvidenceContract from the frozen requirements and genuine current source. Do not read empty derived legacy lists or model numeric bounds as proof. |
| `execution.py:823`, `983`, `1053` | Existing native gates run PRE_SAFETY/PRE_SKILL; hard estop/collision/disconnection precede unknown-evidence routing. Invalid PRE_SKILL stops without recapture into old shield. | Keep both gates, independent hard stop and fresh-time checks unchanged. Bridge checks supplement them and cannot turn UNKNOWN into physical authorization. |
| `execution.py:1066–1168` | Owner-thread physics hooks and supervision capture exist; ordinary supervisor returns are applied at skill boundary and cannot replace active contract. | Publish detached observations/generations only on the owner. A returned supervisor/planner context is stale unless full epoch/generation/current version/frame binding still matches. |
| `execution.py:1265–1368` | Iterates the initially compiled `contract.steps`; has no durable completed/pending prefix or resume cursor. | Future actual replan activation needs an owner-controlled loop that reads the first pending step from current registered plan at each boundary; merely adding repository hooks to the old cached loop is insufficient. |
| `edge/runtime/task_executor.py:908` | Existing checkpoint writer uses `robot.object_region(...)` as target truth, and its providers can be MOCK outside production profile. | Reuse checkpoint type/hash/CAS semantics, not this writer or the whole legacy executor loop for actual visual evidence. Write target_state from current canonical RGBD verdicts only. |
| `edge/event_mode/controller.py:108` | initialize_task registers `robot-unknown`, retry budget and existing event state. | Real visual registration supplies actual factory-owned robot/plan/episode identity. Do not call initialization with placeholder identity. |
| event repository `memory.py:571/638/769/802`, SQLite equivalents | Same-version original contract hash is immutable; active plan/replan apply uses CAS; checkpoints have idempotent writes and hash CAS. | Extend these repositories for sidecar/owner publication within their existing atomic domain; avoid another persistent task state machine. Revalidate complete models/hashes instead of trusting model_copy. |
| `auto_mode/transition_service.py:29/84` | Strict research service needs repository, current guard, verified boundary and actual source-bound selected mode policy; durable mode version CAS is independent. | Bridge reads real mode row and guard. Missing mode policy still blocks ordinary switching; hard STOP never waits for mode commit. |
| `cloud/replanning/apply_service.py:428` | Pure CAS submit callback validates checkpoint hash, first pending canonical requirements, candidate/current versions and action duration covering all pending steps; activation/resume/start are distinct durable stages. | Preserve this gate. T12 action context versus checkpoint context needs an explicit mapping, and future conditional planning cannot silently lower the existing full-window horizon. |
| `edge/recovery/lifecycle.py:786/953` | Recovery requires repository source/current checkpoint, atomic durable budget/retry authorization, actual execution receipt AND completion, fresh later canonical evidence; VERIFIED_RESOLVED is separate. | Feed real source providers/receipts from the visual owner, never planner candidate/ACK/independent physical score. Missing providers remain unavailable. |

Two decisive excerpts from the captured source:

```python
# resolved_step: the execution view intentionally removes legacy checks
"preconditions": [],
"success_conditions": [],

# native_action_contract: requirements currently come from the supplied step
0.01, ("rgbd",), specs(step.preconditions), specs(step.success_conditions),
```

```python
# current visual episode starts these deadlines before planning
self.deadline = self.started_at + policy.timeout_s
self.budget = VerificationBudgetState.start(policy.verification_budget)
# grounded_contract later uses NOW + the same timeout
valid_until=now + timedelta(seconds=policy.timeout_s),
```

Existing check_active enforces the earlier deadline already. The new durable bridge must preserve that relationship rather than claim a new timeout vulnerability was executed.

## Approach and boundaries

Recommended: an actor-bound source observer and durable sidecar in the existing event repository. The actual visual worker alone owns robot/backend/capture, plan cursor and command mailbox. Repositories own atomic persisted mutations; composition remains a read-only consumer; existing native/Safety/SkillExecutor owns physical submission.

Routing the entire visual plan through the existing legacy TaskExecutor would require replacing its scene/condition/checkpoint truth sources and carefully avoiding a second loop/shield; that is a larger behavior change. A new parallel executor would duplicate ownership and recovery state. Neither is needed for initial registration software.

The minimal deliverable is original requirement registration, coherent read-only snapshots and boundary persistence with actual method/execution admission still UNKNOWN. Stage/resume, recovery completion and conditional-future proposal support can be developed and independently reviewed as subsequent software increments; missing calibration/selection/native sources cannot be replaced by their presence.

## Proposed data types

Create `vision/owner_registration.py` for detached immutable types and source bridge. No public HTTP constructor accepts these as authority. Names/signatures are proposed and must be implemented/verified before use.

```python
@dataclass(frozen=True)
class VisualOwnerIdentity:
    job_id: str
    run_id: str
    attempt: int
    worker_id: str
    lease_id: str
    owner_epoch: str       # fresh factory-owned process/attachment nonce
    episode_id: str       # actual capture/backend episode, not caller ID
    task_id: str
    plan_id: str
    robot_id: str         # explicit registered runtime robot identity

@dataclass(frozen=True)
class OriginalActionRequirements:
    step_id: str
    skill: SkillName
    original_step_hash: str
    preconditions: tuple[ConditionSpec, ...]
    postconditions: tuple[ConditionSpec, ...]
    allowed_error_m: float
    sensor_requirements: tuple[str, ...]
    ordinary_ttl_s: float
    expected_duration_s: float
    policy_source_hashes: Mapping[str, str]

@dataclass(frozen=True)
class VisualOriginalPlan:
    identity: VisualOwnerIdentity
    contract: TaskContract              # exact compiled ORIGINAL active plan
    contract_hash: str
    proposal_hash: str                  # original validated cloud syntax/evidence
    compiler_source_hashes: Mapping[str, str]
    role_bundle_hash: str
    source_hashes: Mapping[str, str]
    requirements: Mapping[str, OriginalActionRequirements]
    dependencies: tuple[StepDependency, ...]
    task_deadline_at: datetime          # aware absolute initial deadline
    verification_deadline_at: datetime
    registered_at: datetime

@dataclass(frozen=True)
class StepGroundingBinding:
    owner_epoch: str
    owner_revision: int
    state_generation: int
    source_checkpoint_hash: str         # checkpoint BEFORE this derived binding
    original_contract_hash: str
    original_step_hash: str
    requirements_hash: str
    observation_id: str
    observation_checksum_sha256: str
    episode_id: str
    calibration_version: str
    plan_version: int
    command_seq: int
    grounding_source_hashes: Mapping[str, str]
    grounded_step: TaskStep             # exact parameters/timeout/retry intent
    expected_duration_s: float          # recomputed from actual constrained intent
    binding_hash: str
    created_at: datetime
    valid_until: datetime

@dataclass(frozen=True)
class VisualOwnerPublication:
    identity: VisualOwnerIdentity
    owner_revision: int                # durable repository CAS revision
    state_generation: int              # owner-local live source generation
    original_plan_hash: str
    checkpoint: ExecutionCheckpoint
    mode_status: AutoModeStatus
    budget_record: VerificationBudgetRecord
    online_evidence: OnlineEvidenceSnapshot
    grounding: StepGroundingBinding | None
    atomic_action_active: bool
    cancelled: bool
    publication_hash: str
```

All constructors revalidate Pydantic bytes/checksums and copy every nested map/sequence. A provider receives detached publication/context only, never owner, repository, robot, mutable pool or mailbox references. ConditionSpec requirements are the union of registered original semantic requirements and reviewed local per-skill visual pre/effect requirements, including existing LIFT-hold/terminal requirements where relevant. Their targets/tolerances must remain canonical; calibration-dependent fields bind the current registered calibration during grounding. Missing/unknown condition names, target mapping or changed calibration yield unavailable, not removal or an empty PASS.

Action requirements reuse the exact existing source policy.01m/rgbd/5s and the actual timeout/duration derivation until a separately reviewed registered policy changes them. No arbitrary new bound/confidence/error tuning appears in this bridge. The normalized runtime original and raw proposal remain distinct hashes. Each grounding transformation is deterministic and bound to its reviewed source, original skill/targets/safety and actual frame. Runtime motion parameters/timeout may change only within an explicit immutable transform policy; arbitrary changes require a new versioned plan through ReplanApplyService. Any actual constrained duration longer than the registered evidence horizon requires a newly checked action contract, never reuse of the shorter claim. SafetyShield limiting is recorded as an additional derived intent binding and must be rechecked PRE_SKILL; it cannot relax the original requirements.

The visual worker has no persisted hardware robot serial today. For MuJoCo, the trusted factory supplies an explicit unique runtime robot identity tied to job/attempt/backend, labeled simulation, not hardware. Future hardware requires its actual device identity/lease source. `robot-unknown` or a user-provided arbitrary string cannot stand in for that owner binding.

## Proposed minimal APIs and durable atomic domains

Extend `EventAutonomyRepository` and its existing memory/SQLite implementations; store sidecars in the SAME event database/lock domain, not an extra task state-machine service.

```python
initialize_visual_owner_if_absent(
    original: VisualOriginalPlan,
    checkpoint: ExecutionCheckpoint,
    verification_state: VerificationBudgetState,
    retry_budget: RecoveryBudget,
) -> VisualOwnerPublicationRecord

get_visual_original_plan(task_id: str, plan_version: int) -> VisualOriginalPlan | None
get_visual_owner_publication(task_id: str) -> VisualOwnerPublicationRecord | None

publish_visual_boundary_if_current(
    *, task_id: str, owner_epoch: str, expected_owner_revision: int,
    expected_contract_hash: str, expected_checkpoint_hash: str,
    checkpoint: ExecutionCheckpoint, grounding: StepGroundingBinding | None,
    state_generation: int,
) -> VisualOwnerPublicationRecord | None

record_visual_decision_and_reserve_if_current(
    *, task_id: str, owner_epoch: str, expected_owner_revision: int,
    expected_checkpoint_hash: str, expected_budget_revision: int,
    event: DecisionEvent, trace: DecisionTrace,
) -> VisualDecisionReservation | None

close_visual_owner_if_current(
    *, task_id: str, owner_epoch: str, expected_owner_revision: int,
    terminal_checkpoint: ExecutionCheckpoint,
) -> bool
```

`VisualOwnerPublicationRecord` is the durable subset: identity/original hashes/revision/generation/current checkpoint ID+hash/registered deadlines+source identities/closed_at; it does not serialize a robot/backend. `VisualDecisionReservation` binds event/trace/payload hash, before/after durable budget revisions, owner epoch/revision and checkpoint hash. Neither is an acceptance receipt. Repeated same-key/same-content operations return the original detached result; altered content conflicts. These methods revalidate complete model/hash/identity and current original/cursor/deadline inside the event transaction. Registration atomically creates original sidecar, initial active contract/checkpoint and task pools only if absent. Existing deadlines/counts cannot be refilled by attachment/restart/replan. Ordinary reservation records trace and consumes its original durable pool once in one event transaction; an audit failure cannot invisibly double-charge. Hard STOP consumes no optional observation/retry budget.

Existing recovery methods already atomically reserve reobservation and consume retry+authorize with recovery/budget/source revisions. Reuse them for recovery events; do not route a recovery request through a second ordinary reservation and double-charge it. Ordinary non-recovery decisions need the new method above because T12's reviewed software charge after trace ACK is expressly not a durable budget transaction.

Mode state remains in the existing AutoModeRepository. Add narrowly scoped `initialize_status_if_absent(status: AutoModeStatus) -> AutoModeStatus` to avoid overwriting an existing mode/version during owner attachment. The initial mode comes from the explicit registered task/method configuration and its actual admissibility, not an inferred from_mode or a decision score. Construct `ModeTransitionService(repository=..., commit_guard=owner.mode_boundary, require_verified_boundary=True, mode_switch_policy=verified_snapshot_or_none)`. Missing actual policy still rejects ordinary switching.

**There are two existing transaction domains.** Event-side CAS atomically updates its original/owner/checkpoint/budget/recovery rows; T11 mode CAS atomically updates mode/transition in its own repository. Do not claim these two writes or a physical operation form one transaction. All actual mode/replan mutation commands go through the owner mailbox while ordinary motion is inactive. Mode guard uses a pinned coherent owner publication and current durable checkpoint/version; no provider/network callback runs under a repository lock. If mode commit succeeds but publication fails, current mode versus published mode mismatch makes future snapshot/submission UNKNOWN until explicit reconciliation of the durable committed record. Do not roll back mode or infer that an action ran.

Likewise an actual replan must extend the existing active-contract CAS transaction to also register the new immutable original requirements/owner revision, or temporarily remain unavailable between active CAS and sidecar registration. A proposed optional typed `VisualOwnerAdvance` argument contains the new original plan, expected owner epoch/revision and checkpoint hash. The existing CAS validates it and writes active/apply/sidecar/owner changes together; legacy nonvisual callers preserve their API semantics. A pure source-bound guard validates actual proof, not a caller boolean. No live I/O/provider callback is allowed inside that transaction.

## Source registration with missing INITIAL/method evidence

An authoritative owner record is a persistence statement about the factory-owned current job/attempt/lease/episode and exact original plan/source bytes. It is not INITIAL, calibration, METHOD or execution acceptance. Its installation may complete before external credentials/evidence exist: register the trustworthy identity and immutable plan, persist original absolute deadlines/pools, and expose current detached state while the adapter returns UNKNOWN/STOP for physical dispatch. Registration results have no method/execution admitted flag and cannot be supplied as a VALID callback/receipt. The actual source type and software-only fixture scope are explicit; fixture-created identities cannot become actual owner evidence.

No complete INITIAL protocol is required to save this source record. However every proposed actual dispatch must independently require the accepted INITIAL reconstruction AND actual risk/finite selection/method evidence AND current owner/checkpoint/mode binding AND native/Safety proof. Missing any one remains unavailable. The existing `InitialSourceAdmissionAuditor` supplies INITIAL_SOURCE only and METHOD stays UNKNOWN. The reviewed composition adapter's missing-method guard remains closed throughout this installation. Persisting a mode label/current plan or observing a real frame cannot bypass that guard.

## Owner actor API and current generation

```python
class VisualOwnerBridge:
    def attach(
        self, identity: VisualOwnerIdentity, *, task_started_at: datetime,
        task_deadline_at: datetime, verification_state: VerificationBudgetState,
    ) -> None: ...
    def register_original(
        self, original: VisualOriginalPlan, *, initial_online: OnlineEvidenceSnapshot,
        initial_mode: AutoModeStatus, retry_budget: RecoveryBudget,
    ) -> VisualOwnerPublicationRecord: ...
    def bind_grounding(
        self, grounded_step: TaskStep, *, original_step_id: str,
        online: OnlineEvidenceSnapshot, source_checkpoint_hash: str,
        state_generation: int, now: datetime,
    ) -> StepGroundingBinding: ...
    def snapshot(self, event: DecisionEvent) -> RuntimeCompositionSnapshot: ...
    def publish_boundary(
        self, checkpoint: ExecutionCheckpoint, *, expected_owner_revision: int,
        expected_checkpoint_hash: str, grounding: StepGroundingBinding | None,
        state_generation: int,
    ) -> VisualOwnerPublicationRecord | None: ...
    def stage(self, contract: TaskContract, repair_id: str) -> CommandAck: ...
    def resume(self, repair_id: str, activation_token: str) -> CommandAck: ...
    def close(self, terminal_checkpoint: ExecutionCheckpoint) -> bool: ...
```

`attach/register/bind/snapshot/publish/stage/resume/close` run on the actual worker owner thread. The owner exposes an enqueue-only gateway proxy to other threads; queued ordinary commands are processed at existing skill boundaries. An API caller cannot read MuJoCo directly, invoke the executor or substitute a publication. Commands carry attempt/epoch, exact versions/payload/expiry/idempotency and are freshly checked after queue waits. Missing/late commands reject without new capture. Hard stop/cancel remains the independent existing cancel/proprioceptive/Safety path and does not wait for the mailbox or selected dwell policy.

Separate `state_generation` from durable `owner_revision`. Increment live generation whenever the current online observation, sampled robot state, next step, atomic flag, cancelled/lease state or detected source/role binding changes. Physics hooks can increment in memory; persist at actual boundaries rather than doing database I/O for every simulator tick. Each restart/attachment gets a new owner epoch, so an old generation number is never reused as current. Snapshot atomically detaches all online fields on the owner; recheck generation/fingerprint, lease/cancel, clock, current rows and source bytes after provider/model/audit return and before commit. Nonowner readers receive the latest detached publication only and cannot call backend/capture methods.

Map the publication to the already reviewed `RuntimeCompositionSnapshot` exact fields: ORIGINAL active contract, durable current checkpoint, real mode row, current online RGBD/proprioception/facts, original durable budget copy, actual capability set, genuine network-cost snapshot (unknown values remain None), registered canonical ConditionSpecs, and current ActionEvidenceContracts. Risk/selection admission remains the independent missing method verifier; INITIAL_SOURCE validity alone does not enable it. LOCAL_RECOVER is absent until actual activation/recovery/calibration prerequisites exist.

### Context hash mapping, with no circular bindings

Current native execution hashes a resolved contract+step; T13/recovery require `online.context_hash == checkpoint_digest(checkpoint)`. Preserve both meanings explicitly rather than falsely treating them as equal.

1. Build StepGroundingBinding against the previous checkpoint hash and immutable original/requirements/current frame. Its hash includes the resolved intent and source versions.
2. Publish a new pre-submit checkpoint carrying that grounding hash and original requirement hash in `safety_state`, plus only online frame/source/verdict diagnostics in `target_state`. Its canonical checkpoint digest binds the grounding transitively and becomes the T12/T13/recovery context hash for that boundary.
3. Construct action/native intent context from the same registered original+grounding+checkpoint. Native gate still validates its own actual submit proof; an explicit adapter verifies both context bindings and never relabels one hash as the other.
4. Any new frame/intent/limit/plan/checkpoint invalidates the previous envelope. Recompile grounding/action evidence and SafetyShield from the new state. PRE_SKILL invalidation still stops; it cannot recapture and reuse the old shield.

An action attempt must be claimed against the exact pre-submit checkpoint/generation/nonce before invoking the existing executor. Extend the owner boundary CAS to persist STEP_STARTED/attempt and its authorization context/hash, enforcing expected ready checkpoint and single-use identity. That prior claim is **not** an execution-start receipt. Immediately recheck independent hard stop/lease/deadline, enter the existing executor, and emit a start receipt only from that actual owner handoff; journal/ACK/candidate alone cannot emit it. Once the CAS advances the checkpoint, use the explicitly bound pre-submit authorization context for the claimed action, not a mismatched stale envelope as if it described the new checkpoint. If an intervening state/source change occurs before actual handoff, stop and persist rejection/uncertainty; do not execute, refund authority silently or automatically replay after restart.

## Deadlines, durable checkpoints and safe restart

Persist the original aware task start/deadline when the worker attempt/episode begins. Effective expiry is `min(original task deadline, original VerificationBudgetState.deadline_at, active contract.valid_until, observation/action actual expiry, job/lease expiry where applicable)`. Snapshot and actual submit use fresh clocks after every callback/ACK. Within the live process retain the current monotonic deadline; wall-clock reversal must not extend it. Restart cannot recreate a fresh budget or policy.timeout_s. If stored start/deadline/lease is missing or inconsistent, report unavailable.

Checkpoint completion is an exact original-plan prefix. After an actual skill return, save actual attempt/completion and fresh observation/canonical effect verdict; add a step to completed only after those checks pass. Exceptions/partial physics are persisted as uncertain/failed, never completed or retried automatically. Preserve unrelated pending steps and completed physical effects; a new named compensation requires its own approved/versioned policy and identity.

The current worker ALWAYS resets a fresh backend; it cannot physically resume an old checkpoint merely because qpos/robot_state was serialized. On detach/lease expiry/backend shutdown, close the owner and fence all queued tokens. A new backend episode/attempt cannot reuse the old task's action authority/frame. Actual resume requires a separately verified current device/episode/robot-state continuity source and fresh canonical/native evidence; unavailable continuity remains STOP. Stored robot_state is a diagnostic snapshot, not a command to teleport/reconstruct physical state. An actual hardware restart/reconnect needs its own source protocol; none is implemented here.

## Recovery, activation, resume and completion

The new visual gateway implements the existing ReplanDispatchGateway `stage/resume` protocol while retaining ReplanApplyService's stages.

- `stage` queues/validates a typed versioned candidate for this exact idle owner/repair. It preserves the completed prefix and registered requirements, stores the candidate without execution, and returns a real owner ACK with matching payload/repair/token only after durable staging. Candidate readiness is not accepted/start/physical success.
- ReplanApplyService performs its existing current checkpoint/cancel/proof rechecks and active/apply CAS. Future visual sidecar advance is part of that same event transaction. Failed/missing actual method/native proof keeps activation unavailable.
- `resume` rechecks the actually ACTIVATED record/token, current original/checkpoint/mode/owner, fresh frame/native action/Safety constraints and absolute deadline. It resumes only the existing owner loop at the first pending step; it does not invoke a parallel TaskExecutor or execute from a cloud thread. ACK merely means actual owner accepted the scheduling coordination.
- On real executor entry, produce exact ReplanExecutionReceipt and call confirm_execution_started. On return, convert the actual StepExecutionResult into existing SkillExecutionResult with its real timestamp/error/result and recovery_id/attempt_id details. Exceptions do not produce a fictitious successful completion.
- Supply RecoveryExecutionEvidence with BOTH matching actual start receipt and completion plus the executed checkpoint hash. Existing lifecycle CAS changes RECOVERY_AUTHORIZED→RETRY_EXECUTED only when these agree.
- Capture genuinely later evidence through the reserved original durable pool. Supply the real OnlineEvidenceSnapshot; lifecycle reevaluates registered canonical conditions and only a fresh later all-PASS set can become VERIFIED_RESOLVED. Candidate, stage/resume ACK, retry authorization, current condition flag or independent physical evaluator score cannot resolve it.

The existing LocalRecoveryExecutor remains authorization only. The bridge does not invent a third recovery state machine, compensation, physical success badge or model-driven low-level command path.

## Conditional future GRASP→LIFT compatibility

The preserved corrected integration probe shows a coherent pending GRASP→LIFT window is refused before a model request: `gripper_holding` for LIFT is canonically FAIL while the gripper is still open before GRASP. That result is correct for **current LIFT submission** and must not be relabeled PASS. The current RoleVisualRepairProvider checks all future actions against the current frame and the existing submit gate retains a full-pending-duration bound. This design does not weaken either default.

Introduce a separate no-authority `ConditionalRepairProposal` with immutable original/window/dependency hashes, explicit preserved future ConditionSpec requirements, replacement semantic intents and `requires_fresh_grounding_before_step=True`. It can describe the future LIFT requirement as conditional on the separately verified GRASP effect. It contains no future ActionEvidenceContract/DecisionEnvelope/physical-ready assertion. Planner output cannot remove or satisfy that condition. Completed effects still require fresh current confirmation; ordinary windows never replay them.

A subsequent reviewed planning-only validator may persist this proposal for diagnostic exploration without requiring future gripper_holding to be true NOW. This is not an accepted/staged executable contract. Any later executable versioned candidate must still satisfy the unchanged existing all-pending duration/evidence gate, ground the current first pending action with fresh actual canonical/native proof, and pass existing CAS/Safety/Skill checks. The owner must preserve all future requirements and re-ground/re-prove each later action after real effects and a new checkpoint/frame. If GRASP fails or holding remains UNKNOWN/FAIL, LIFT is never submitted.

No horizon reduction or weakening of the all-pending evidence gate is proposed. If that existing gate cannot be independently satisfied, the proposal remains diagnostic and no activation/resume/action is allowed. First-pending proof is an additional immediate physical boundary, never a substitute for the existing full-window requirements. The smallest current software task is the planning-only typed proposal/validation, not a workaround around submit evidence. No actual B4 capability is claimed.

## Proposed files and integration ownership

| Future source | Responsibility |
|---|---|
| NEW `vision/owner_registration.py` | Typed immutable original requirements/grounding/owner publication and actor bridge; no second executor or admission receipt. |
| NEW `tests/test_visual_owner_registration.py` | Typed source isolation, generation/identity/deadline and closed snapshots. |
| Existing `repositories/event_autonomy/{protocol,memory,sqlite}.py` | Sidecar tables, registration/publication/trace+budget CAS, optional visual sidecar advancement in existing replan CAS; both backends tested. |
| NEW `tests/test_visual_owner_repository.py` | Durable identity/idempotency/atomicity/restart/CAS and no-refill regressions. |
| Existing `auto_mode/repository.py` | Narrow initialize-status-if-absent only; preserve T11 transitions and immutable records. |
| Existing `vision/{evaluation,execution,action_evidence}.py` | Optional actor/source hooks; retain original requirements in native evidence; actual cursor/completion hooks and existing Safety/Skill boundaries. Root native-gate ownership required. |
| Existing `simulation_runtime/worker.py` | Real lease/job/attempt factory, durable deadline/actor lifecycle; detach before backend shutdown; no implicit OPENCV/method toggle. |
| Existing `auto_mode/runtime_composition.py` | Consume registered snapshots only; later independent METHOD verifier remains a separate task and default UNKNOWN. No current change is proposed to its closed admission. |
| NEW `vision/owner_gateway.py` + tests | Enqueue-only existing ReplanDispatchGateway implementation and real receipt/completion mapping to the single owner loop; actual admission stays unavailable initially. |
| Existing `cloud/replanning/{apply_service,role_visual_repair}.py` | Optional visual sidecar binding; future planning-only conditional proposal support as a separately reviewed source/policy version. Preserve existing strict gates by default. |

These edits require explicit per-file ownership assignment from root before implementation because several files are already frozen under other modules. Preserve old reviewed snapshots. Additive repository APIs/default-None observer hooks are the first bounded software increments; wiring an accepted actual METHOD remains external-evidence dependent.

## Regression matrix

All future fixture math/source tests explicitly SOFTWARE_ONLY. Real success/receipt tests cannot substitute synthetic fixtures for actual acceptance. Each implementation increment follows RED→GREEN, freezes exact refs and receives independent review.

| Regression input | Required result | Scope/owner |
|---|---|---|
| Same plan/seq but resolved params/empty old lists saved as active | Idempotency conflict; original canonical requirements unchanged | Repository + bridge |
| Source requirement tolerance/target/error/sensor/TTL/duration removed/relaxed by provider | Reject; original immutable policy hash/current native gate retained | Bridge + action evidence |
| Nested provider mutates observation/robot/capability/condition maps/budget | Authoritative owner/publication unchanged; invalid provider digest | Bridge |
| Frame/robot/cancel/lease/mode/checkpoint changes during cloud/judge/audit wait | Fresh return check rejects old generation; no capture/physical commit | Bridge + worker |
| Actor mailbox command is foreign epoch/job/attempt/token/version/payload, duplicated or late | Reject altered/late; duplicate exact staging coordination idempotent, no repeated action | Gateway + repositories |
| Two workers/SQLite connections attach same task differently | One immutable identity wins; conflicting identity rejected; stale owner cannot publish | Repository |
| Two event transactions race on owner/checkpoint/budget revision | One CAS wins; trace/reservation counts agree; original pool not refilled | Repository |
| Audit/trace persistence fails | No reservation or action; retry exact event cannot invisibly charge twice | Repository |
| Retry uses ordinary plus recovery reservation paths | One original durable pool charge only | Recovery adapter |
| Task plans slowly, replan/restart/reattach happens | Effective deadline never later than original task/budget; no new timeout allocation | Worker + bridge |
| Hard estop/collision/disconnect before UNKNOWN or mid-queue | Existing immediate STOP, no ordinary capture/retry/mode dwell wait | Native + bridge |
| State invalid after SafetyShield or PRE_SKILL | STOP; no recapture/reuse of earlier shield | Existing native regression + hook tests |
| Mode commits but actor publication crashes | Mismatch UNKNOWN; reconcile exact durable commit, no invented global transaction/action | Mode + bridge |
| Replan activates but original sidecar/checkpoint binding differs | Atomic visual CAS fails or closed unregistered interval; no old cached loop step | Event repo + owner loop |
| STEP_STARTED/attempt claim persists then process dies before or during executor | No fabricated receipt/completion; uncertain restart STOP, no automatic replay | Bridge + gateway |
| Skill returns success but current canonical effect UNKNOWN/FAIL | Persist return, keep completed prefix unchanged; recovery not resolved | Bridge + lifecycle |
| Receipt with no completion / wrong recovery details / stale completion | No RETRY_EXECUTED; existing CAS rejects | Lifecycle adapter |
| New evidence before execution completion, stale/duplicate/foreign frame | No VERIFIED_RESOLVED, no quota reset | Lifecycle |
| Worker resets a new backend after old checkpoint | No resume/teleport/old frame reuse; actual continuity unavailable | Worker |
| Legacy checkpoint target truth/independent evaluator/saved summary fed online | Rejected or unavailable; snapshot uses only RGBD/proprioception/canonical facts | Bridge |
| Missing INITIAL/METHOD/risk/finite weights/selection/native certificate | UNKNOWN/STOP, LOCAL_RECOVER absent; no flag/hash bypass | Admission + composition |
| GRASP→LIFT future holding FAIL before GRASP | Planning-only conditional proposal may preserve it; no LIFT authority/envelope | Future planning-only module |
| Failed GRASP or later holding UNKNOWN/FAIL after a new frame | No LIFT executor invocation | Owner loop |
| Unrelated pending or completed effect inside repair window | Preserved exactly; no replay or invented compensation | Existing T13 + owner |

## First bounded implementation task: two new files only

Own exactly NEW `src/cloud_edge_robot_arm/vision/owner_registration.py` and NEW `tests/test_visual_owner_registration.py`, plus a separate module artifact directory. Deliver immutable `VisualOwnerIdentity`, `OriginalActionRequirements`, `VisualOriginalPlan`, `StepGroundingBinding` and pure validation/binding functions. No existing repository/vision/worker/policy writes and no executor references are given to providers.

Concrete initial interfaces:

```python
freeze_original_visual_plan(
    *, identity: VisualOwnerIdentity, contract: TaskContract, proposal_hash: str,
    role_bundle_hash: str, compiler_source_hashes: Mapping[str, str],
    source_hashes: Mapping[str, str],
    requirements: Mapping[str, OriginalActionRequirements],
    dependencies: Sequence[StepDependency], task_deadline_at: datetime,
    verification_deadline_at: datetime, registered_at: datetime,
) -> VisualOriginalPlan

bind_step_grounding(
    original: VisualOriginalPlan, *, original_step_id: str, grounded_step: TaskStep,
    online: OnlineEvidenceSnapshot, source_checkpoint: ExecutionCheckpoint,
    owner_revision: int, state_generation: int,
    grounding_source_hashes: Mapping[str, str], now: datetime,
) -> StepGroundingBinding
```

The pure binding checks source integrity and preserves the original skill/semantic targets/canonical requirements and complete original hash; it does not certify that caller coordinates are geometrically correct. The later ROOT owner must recompute the intent from its actual reviewed grounding source before any physical use. The binder validates current task/episode/frame/checksum/calibration/plan/seq/deadline; uses the exact approved transform source and registered policy; computes complete binding hashes and returns detached data. Missing genuine bounds do not invalidate source registration itself, but the result carries no physical authority or action evidence grant. Pure math fixtures exercise preservation and negative drift cases, never actual admission. First RED cases are the missing module, empty/relaxed original requirements, mutation through nested caller maps, same-version original replacement, late/foreign/current-checkpoint mismatch and original deadline extension. GREEN is a source-binding component only.

After this small component's frozen independent review, ROOT owns the additive existing-repository and worker/native integration tasks described above. ROOT can install its persistent owner row while dispatch remains closed; source integrity and authoritative persistence are independently testable without INITIAL credentials. Actual method admission must not be added to the two-file component. The later real owner source factory must construct requirements from registered original/local canonical policy rather than accept public caller requirements as authoritative.

## Software sequence and self-review

1. Implement detached original requirements/grounding types and no-oracle snapshot construction with default closed method admission; exact source tests.
2. Add existing-repository atomic sidecar/register/publish/reservation APIs and immutable mode initialization; memory/SQLite race/restart tests.
3. Add optional worker/episode hooks and durable deadline/cursor/checkpoint observers using the existing single SkillExecutor/native/Safety path; remain NOT_RUN when actual method/native sources are absent.
4. Add enqueue-only staging/resume plus real executor receipt/completion adapters and existing recovery lifecycle integration; actual capabilities remain absent until independent source prerequisites are satisfied.
5. Separately implement conditional planning-only proposal semantics; current submit gates unchanged. Actual activation/admission still requires the unchanged all-pending gate and independent method/native sources; a proposal is not a boolean switch.

Self-review: source sites and existing type names are exact; proposed types are marked new; original versus grounded, live generation versus durable revision, initial source versus METHOD, stage versus accepted/resumed/started/completed/resolved and event versus mode atomic domains are distinct. Existing immediate stop, default UNKNOWN bounds, no post-Safety recapture and independent offline evaluator separation are preserved. No source proof or synthetic fixture is described as physical admission. This document does not assert the core runtime is implemented or ready to execute.
