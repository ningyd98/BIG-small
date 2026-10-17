# P6 readiness — read-only production and scope map

Status: READINESS_ONLY_NOT_IMPLEMENTATION_PLAN. Actual gpt-6-astra source mapping, not implementation/review PASS. P5/R100 remains with its Sol single writer. No product changes, imports, tests, static checks, actual, Git or agents. The earlier P4 run/readers have completed per ROOT; that does not activate P6. Wait for P5 final freeze/review before drafting the next activatable Astra plan.

## Binding objective

Master Task6 lines322–359 requires “原task→bootstrap→source publication→grounding→PRE_SAFETY→PRE_SKILL→ACK/start/effect”, transaction-current and true-dispatch reads, original budgets, actual lifecycle and complete `(D_BEGIN,D_END,S_BEGIN,S_END,kind,step,owner)` segments. It permits terminating an old attempt when same-boot reconnection is unsupported; actual suspend is NOT_RUN unless measured with separate authorization. Original Task6 thirteen paths are recorded in JSON. Twelve currently exist; the new test path is checked explicitly. This readiness does not grant an extra test/actual budget.

The scope covers both real `InMemoryEventAutonomyRepository` and `SQLiteEventAutonomyRepository`. Do not confuse them with `InMemorySimulationJobRepository`, which is a temporary-SQLite subclass and has the same job lease transaction semantics. A real positive CPU path must pass actual current repositories/issuers/verifiers; no mock final VALID or deserialized public live permissions. Native finite geometry/complete-action proof belongs to P7/P8: use a legally sourced supported fixture for CPU integration, not a fabricated native verifier result or a claim of actual physical qualification.

## Production map

### startup

Evidence: `simulation_runtime/worker.py:136-213; vision/worker_runtime.py:243-313`.

Current: Actual lease/heartbeat/unique attempt/original task origin, then late visual runtime. P5 is actively adding private original-origin authority.

P6 obligation: P5 freeze and actual startup registry/scope API required; no final pin/assertion on active source.

### persistent bootstrap / adoption

Evidence: `event_autonomy memory.py:278-350,456-627; sqlite.py:320-401,2882-3069; protocol.py:108-134`.

Current: Concrete lock/BEGIN IMMEDIATE and actual source promotion, detached strict codecs.

P6 obligation: Acquire live issuer scope after transaction wait, fresh D before admissible mutation/commit; keep replay descriptive and CAS original pools.

### publication / verification

Evidence: `memory.py:629-806; sqlite.py:2760-2829,3071-3175; visual_owner.py:449-534; visual_verification.py:1046-1152`.

Current: Immutable source checks, revisions and budget debit exist. Current route now/publication deadline checks are UTC.

P6 obligation: P6 live gate inside lock/transaction with current D and real job lease/fencing; duplicate history grants no effect permission.

### grounding

Evidence: `owner_registration.py:827-979; visual_owner.py:668-703; vision/worker_runtime.py:1128-1170 [active]`.

Current: Deterministic exact payload/frame/source binding with UTC expires=min(original,frameTTL), published under runtime transaction guard.

P6 obligation: Versioned original P5 event/budget/window checks, preserve all geometry/source/checkpoint constraints and frame identity; no TTL refresh.

### PRE_SAFETY / PRE_SKILL

Evidence: `vision/execution.py:1188-1260,1445-1518`.

Current: Safety and native rechecks, grounding refresh; then separate executor call. ACTION_STARTED emitted before that call.

P6 obligation: Fresh original-window plus lease/source/payload checks at both stages AND genuine final dispatch. P8 native proof integration remains separate.

### actual handler / ACK / start / effect

Evidence: `edge/runtime/skill_executor.py:58-150; simulation/mujoco/skill_robot.py:100-130,307-353; backend.py:765-812; vision/execution.py:1320-1385`.

Current: Handler runs after parameter/precondition evaluation; accepted command can be queued until a future physics step. After-return recapture/effect route is independent.

P6 obligation: Final live check before handler; typed accepted-command evidence != controller/physics start != whole effect. No start inference from outer log or success bool.

### lease / heartbeat / fencing

Evidence: `simulation_runtime/sqlite_repository.py:348-536; worker.py:149-172 [active]; vision/worker_owner.py:131-238`.

Current: Heartbeat samples UTC after BEGIN IMMEDIATE and excludes expired/cancelled/reassigned leases. It runs on another thread.

P6 obligation: Need actual D lease issuer/lifecycle or explicit mixed-veto stage. Never call P5 OC1 from heartbeat thread or subtract unlike domains. Preserve fencing/expiry no-revival.

### restart

Evidence: `simulation_runtime/service.py:87-96; recovery.py:29-84; sqlite_repository.py:497-536`.

Current: Startup invokes recovery before dispatcher; UTC-expired jobs interrupted; optional explicit recovery can requeue.

P6 obligation: Persist provenance/deadline/spend, terminate old operational attempt if not truly reconnectable. Explicit requeue must not silently refill same-task budget or revive handles.

### D/S segments

Evidence: `research/clock.py:10-37; vision/execution.py:1756-1774; vision/raw_recorder_v3.py:187-209,396-463,704-770; backend.py:245-268,306-355`.

Current: WAIT advances physics by elapsed monotonic; recorder already observes RESET/CONTROL/PHYSICS/COMMAND/CAPTURE and stores old monotonic/UTC+S pairs. Backend permits one observer and swallows observer failures as audit data.

P6 obligation: Join real P5 owner original D with real backend/episode S inside existing production hooks; do not add competing observer or treat swallowed callback exception as motion veto. Preserve partial/missing denominator.

## Scope decisions to make after P5 freeze

Original thirteen paths cover codecs, both event repositories, grounding, outer execution, worker and job SQLite implementation. They do not, by themselves, demonstrate the final dispatch or operation-observer D production seams. The following are specific pending changes in scope, not instructions to stop P5 or blanket permission to edit dependencies.

- **P6-S1 — LIKELY_REQUIRED_SCOPE_EXTENSION**: `src/cloud_edge_robot_arm/edge/runtime/skill_executor.py`. Parameter validation and evaluate_preconditions occur after execution outer PRE_SKILL; definition.handler is actual dispatch. No pre-handler admission callback currently exists. Decision: Specify private actual-owner checked one-shot dispatch hook in sole existing executor; preserve no-hook legacy semantics and SafetyShield. If proving an existing equally late seam, cite exact code before omitting this path.

- **P6-S2 — LIKELY_REQUIRED_SCOPE_EXTENSION**: `src/cloud_edge_robot_arm/vision/raw_recorder_v3.py`. Only recorder owns sole backend operation observer; its _clock_pair is monotonic_ns/UTC, not OC1. It has no current D sink. Decision: Integrate private operational recorder sink in existing observer/lifecycle, keeping old raw unchanged and new schema sidecar explicit. Complete request/wait/render/controller segments need original owner and exception/missing records.

- **P6-S3 — EXPLICIT_DESIGN_DECISION_NOT_AUTHORIZED**: `src/cloud_edge_robot_arm/simulation_runtime/repository.py`, `src/cloud_edge_robot_arm/simulation_runtime/recovery.py`. Worker depends on simulation repository protocol (distinct from Task6 event protocol); no D lease APIs there. Recovery implementation is outside 13 and can explicitly requeue. Decision: Choose exact new real lease interface and restart terminate policy. If methods introduced, extend simulation protocol. Recovery path change is needed only if concrete owned repository can not enforce old-attempt termination/no-budget-refill for every caller. Do not copy whole runtime tree.

- **P6-S4 — P5_FINAL_INTERFACE_DEPENDENCY**: `src/cloud_edge_robot_arm/vision/operational_windows.py`, `src/cloud_edge_robot_arm/vision/worker_runtime.py`, `src/cloud_edge_robot_arm/simulation_runtime/worker.py`. P5 is single-writer active; R100 authorizes startup private capability and scopes but leaves UTC_LEGACY_VETO. Decision: Read final source and reviewed API/freeze; determine whether existing private hooks suffice for transaction/current reads. If new owner method/context needed, explicitly extend scope in next Astra plan, do not edit active P5 now.

- **P6-S5 — DO_NOT_INFER_SUPPORT_OR_WEAKEN**: `src/cloud_edge_robot_arm/research/operational_time_v1.py`, `src/cloud_edge_robot_arm/simulation/mujoco/backend.py`. OC1 exact thread domain cannot simply cross to heartbeat; backend observer is readonly and swallows callback errors. Decision: Clock/lease broker or per-thread domain bridge requires explicit real authority and mathematical mapping; never relax OC1 checks. If latest required admission is backend mutation/start, add explicit veto hook separately with emergency-stop bypass, not reuse audit callback. Do not pre-authorize these extra paths.

## Transaction and lifecycle design requirements

1. P5's live owner registry/scope must be resolved inside the real Memory lock or SQLite BEGIN IMMEDIATE, after any wait. The transaction must bind exact job/lease/attempt/fencing, publication/checkpoint revision, canonical request/payload/source and original window IDs. Read current D at the actual commit-admission point, not at request serialization. Distinguish fresh effect permission from an idempotent historical duplicate. Keep original verification/retry/no-progress counters immutable except their legitimate decrements.
2. Event and job repositories are separate stores. P5 currently uses the job publication guard around event operations. The next plan must explicitly establish one consistent guard/transaction lock order, list every ownership-changing job path, and close reassignment between transaction/decision and dispatch. A copied lease observation or earlier source hash is not that closure. Do not hold a SQLite transaction over a whole long physical action as an unexplained workaround; define the short atomic admission/command boundary and subsequent cancellation/lease checks.
3. P5's OC1 owner is strictly thread-bound; its private handle cannot be read by heartbeat. Legitimate heartbeat may extend its own lease but must not reset task/verification/recovery deadlines or revive an already expired lease. Choose a genuine broker/lifecycle or explicitly supported domain bridge after P5 freeze; two arbitrary counters sharing numeric CLOCK_BOOTTIME are not automatically the same issued domain. Keep existing UTC lease veto until actual D lease production exists, but label that intermediate branch MIXED_DOMAIN, never complete same-domain P6. A final supported D route needs real lease/acquisition/heartbeat/reassignment/expiry provenance and full fencing with legacy UTC as an explicitly separate optional additional veto.
4. Restart must preserve absolute originals and every spent counter. Safest already allowed first support boundary is terminate old operational attempts, including pending capture/dispatch/effect claims, and prohibit automatic same-task budget refill through explicit requeue. Same-boot resume requires actual issuer reconnection evidence, not JSON handles or matching boot ID alone. Across boot/namespace/process authority loss fails closed. Do not advertise recovery/real suspend until the precise branch is implemented and tested/actually measured as applicable.
5. A synchronous local simulator need not invent a network ACK. Its actual command-record accepted/queued event is an acceptance boundary; first controller/physics evidence and full post-effect frames are separate. `ACTION_STARTED` before executor, ActionResult success or ACK accepted cannot substitute for start/effect. Keep SkillExecutor and SafetyShield unique. If native path remains unsupported pending P7/P8, accurately separate that dependency from a real supported CPU closure test; all-STOP is not final T12 completion.
6. Segment completeness must include original startup/setup, every request including failed/late response, WAIT, render/capture, controller/command/physics, hold and teardown where in the claimed run interval. Each record needs actual D domain/owner and S backend/episode/step identities, observed begin/end or explicit missing/partial disposition, nesting/causal IDs, and a complete allocation denominator. Observer failure remains retained and prevents qualification; it cannot silently skip a segment. D elapsed and S step count are distinct. Existing recorder and ExperimentClock outputs are old diagnostics, not new OC1 authority; do not convert them after the fact or rewrite old raw.

## Verification map for future plan, not authorization

Preserve master Task6 GREEN command exactly as the inherited starting boundary: `.venv/bin/python -m pytest -q tests/test_operational_runtime_closure.py tests/test_visual_worker_runtime.py tests/test_visual_worker_supervision_runtime.py`. Scoped Ruff/format-check/mypy are required by Task6, but exact added paths, named new denominator, fixture and invocation budgets must be fixed in the post-P5 Astra plan before execution. Nothing has run here.

Named original negatives remain: lease reassignment between decision/dispatch; ACK without start; restart preserves deadline or terminates; missing required suspend scope; foreign worker domains; reply at4.9s versus dispatch5.1s. Add concrete coverage in that future plan for transaction lock-wait crossing deadline; same-event history versus new effect; heartbeat-thread identity; queued command without applied start; source/cancel/fencing race at final handler; observer exception/missing D/S segment; explicit recovery requeue; exact Memory/SQLite matching behavior. No false finite native verifier and no real suspend of user's host. Software, source actual and formal remain separate denominators.

## Activation handoff

P5 may continue. After its final source/receipt/review freeze, re-read only its changed interface and shared worker/runtime; replace ACTIVE_OBSERVATION hashes with that accepted dependency. Revalidate stable readiness inputs, resolve P6-S1–S5 into exact approved paths/interfaces, then produce a new Astra plan with original evidence, budget, CPU fixture support, source qualification and acceptance. Do not regard this readiness as permission to edit 13 paths or as proof that the original 13 are sufficient. Do not block lawful P5 changes because observed hashes differ.

Read provenance: local bounded rg/sed/stdlib AST and byte hashes only. A few guessed read-only paths were absent (old executor/recorder and memory/manager spellings); those commands returned exit2 and made no changes. Correct paths were obtained from actual imports and `rg --files`; this is navigation evidence, not a product failure, test result or additional repair task. Relevant sources and observed hashes are embedded in JSON; no raw/DB/credential/model payload was read or copied.
