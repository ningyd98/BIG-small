# R100 — P5 worker startup authority and original-budget source

Status: ACTUAL_ASTRA_PLAN_ONLY / NOT_DISPATCHED. Planner: gpt-6-astra. Sole future implementer: gpt-6.1-sol. This corrects a source-readiness gap in P5, not a failing product test. No product imports, tests, Git, network or actual execution was performed. ROOT reports an active P4 actual run; do not change any product/config/test until ROOT records its termination and external-reader termination and separately activates implementation. Saving this plan is not activation.

## Original evidence and cause

Original `t12-sol-handoff-20261007/p5-author-readiness/readiness.md` SHA256 is `3c14bfc314bdf0b59b9e82af2b123868b2dbf3748a1c4104b7c30f4a573092c0`; JSON is `ccd7fd36572ff8067fbcc189fea4eb59c817a820ab80a2946565e673f7222425`. They remain unchanged. `input-pins.json` records 23 finite inputs; `bounded-observations.json` records seven original owned-source matches and two absent NEW files. These observations do not represent test/actual success. No active P4/R98 output is pinned.

`simulation_runtime/worker.py:179–193` validates actual job/lease and creates the unique attempt; `:211–213` creates the original task origin before `_run`. Normal visual runtime is created only after real RESET and 120 settle steps (`:878–914`), with a public `WorkerRuntimeSource` (`:824–839`). Creating OC1 there loses setup time and refreshes the effective budget. Original P5's nine paths omit the owner of the true startup. Public worker construction, a job string, descriptor or ended P4 handle cannot confer this authority.

OC1 binds exact process/boot/namespace/owner thread and issued handle identity; `before_deadline` requires current paired with its own origin. Current `worker_owner.read_visual_worker_lease` has a genuine repository/unique-attempt/fencing check but UTC expiry, not a D lease-expiry producer. `visual_bootstrap.py:745` reconstructs public requests; historical `_derive` is pure replay. Authority cannot reside only on a serialized request, and historical decoding cannot require or grant live authority.

## Exact ten-file scope

The only extension of original P5 is `simulation_runtime/worker.py`; operational_windows and its test are NEW.

- `src/cloud_edge_robot_arm/vision/operational_windows.py`
- `src/cloud_edge_robot_arm/vision/worker_runtime.py`
- `src/cloud_edge_robot_arm/vision/supervision.py`
- `src/cloud_edge_robot_arm/vision/marker_association.py`
- `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py`
- `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py`
- `src/cloud_edge_robot_arm/edge/evidence/models.py`
- `src/cloud_edge_robot_arm/edge/evidence/conditions.py`
- `src/cloud_edge_robot_arm/simulation_runtime/worker.py`
- `tests/test_operational_windows.py`

No changes to OC1/P4 prefix/worker_owner, repository protocol or SQLite infrastructure, execution, owner registration, recovery, research clock, native/R91, P3 roles or other tests. Do not modify raw/DB/credentials/SDK/weights. New implementation evidence uses a fresh local directory and preserves old originals. Required outside-file changes or additional window categories need a new bounded Astra decision.

## Genuine startup and private interfaces

1. In real `_execute`, after the unique attempt and RUNNING transition, create a private one-shot startup capability bound to exact worker/repository/job/lease/attempt/fencing. Eligibility comes from the real supported normal visual draft and binding, never a public flag. Operational/native prefix applications are excluded and keep their independent lifecycles; other legacy routes are unchanged.
2. Only there call `OperationalWindowOwner.from_worker(worker, job_id=...)`: validate real current repository ownership and consume the private startup capability once, creating a new OC1 owner. Begin its task-origin event immediately before the existing monotonic/UTC origin assignment, mark the actual assignment, end after it. Preserve the original tuple unchanged in meaning. Never convert UTC/float-monotonic into D. Runtime delay/RESET/settle must consume the original budget.
3. Freeze original job timeout conservatively in integer ns at startup. Bind the actual role verification budget, plan/robot/source inventory before backend initialization, and backend/episode identity when actually produced. Verification uses the original task origin, not binding time. No source or budget update refreshes that origin. Conversion cannot enlarge the actual duration; invalid values fail closed.
4. Add a private optional runtime handoff, consumed once by late `VisualWorkerRuntime`; keep `WorkerRuntimeSource` public/descriptive. Revalidate real lease/attempt and binding. Public construction alone cannot issue operational windows. A private owner-thread scope may propagate authority through current signatures, but scope installation requires the exact live startup registry entry; copied context, public descriptors and foreign threads cannot install/reuse authority. Python privacy is not a sandbox against arbitrary malicious in-process code; claim only the verified normal producer path and concrete registry/lifecycle checks.
5. Revoke pending handoff and windows and idempotently close OC1 on success, exception, cancellation, lease/attempt loss and cleanup. Integrate with `_execute` terminal/finally and poll cleanup without masking the original exception, replacing cleanup or changing publication order. Serialized recovery never recreates old live authority or refills old attempt budgets.

Preserve P5 public APIs `from_worker`, `issue(kind,event,budget_ns,parent_ids)`, `check(id,after=token)` and `export_record`. Minimal new helpers are private startup/handoff/scope/revocation helpers and immutable internal registries; no public capability setters or descriptor-to-live factory.

## Algorithm and clock boundaries

Use OC1 `within_age`, `start_deadline`, `before_deadline`; no new counter or caller-now. Registry entries retain original acquisition token/receipt, task origin token/receipt, kind, original policy budget/source identity, parents and job/lease/attempt/fencing. `issue` requires genuine same-domain events and a budget permitted by the frozen kind policy; caller integer values cannot enlarge it. Parents must be issued in the same live context and cannot be imported/cyclic.

D deadline = min(original task deadline, original verification deadline, applicable original parent deadlines, original event lower + kind budget). Check each OC1 deadline with current paired with that deadline's own origin token; check age with current paired with the original acquisition token. An unrelated `after` current cannot be reused to satisfy OC1 causality. Validate `after` as genuinely issued and causally applicable. Five-second age accepts <=5,000,000,000ns and rejects +1ns; deadline requires current.upper < deadline, rejecting equality. Legal overlapping brackets still need logical event-before-current; missing pairs, future/out-of-order, copied and foreign-domain handles fail closed.

Lease clamp is an intersection: D constraints AND the actual current UTC lease/unique-attempt/fencing veto. Descriptor records `lease_deadline_domain=UTC_LEGACY_VETO`; never invent `lease_deadline_ns`. Retain old UTC task/verification/publication checks until their genuine P6 producer/transaction migration. Local D age is UTC-jump insensitive, while the mixed stack may still conservatively stop at a retained UTC guard. Do not claim total UTC-independent application closure. External UTC deadlines, third-party certificates/leases and remote frames stay UTC or UNKNOWN without a supported bridge; preserve the 1000ms future rule.

OC1 stays on the owner thread, not heartbeat/model IO threads. Main-thread reserve/send-effect-through-return/complete brackets may enclose queue/preprocessing/model time conservatively, explicitly labelled enclosing effect intervals rather than exact wire timestamps. Preserve true wire records. Exact dispatch/atomic transaction/cross-thread closure remains P6; never backdate an event or borrow P4 live handles.

## All named P5 producers and consumers

- `worker_runtime`: genuine owner for bootstrap/capture/plan/grounding/supervision reserve-complete-check paths; preserve private claim consumption before completion validation and original spend/retry accounting. Cached frames use the original acquisition ID/source/hash/window, never cache access time.
- `visual_bootstrap` and `visual_supervision`: explicit versioned descriptors alongside old UTC schema. A private one-shot live transition scope binds exact canonical request digest and issued windows around the real repository call. Reconstructed public payloads preserve descriptors/digests, not authority. Historical derivation/replay remains pure; duplicate history grants no new live effect. Preserve current CAS/UTC/lease guards; do not claim P6 transactional closure.
- `supervision`: actual request/reply/observation/source bindings plus the original observation window; preserve policy/uncertainty semantics.
- `marker_association`: resolve original actual frame/acquisition through the live scope while preserving camera/marker/object/registration bindings. Offline replay remains non-live. Operational descriptor without owner is UNKNOWN, not legacy fallback success.
- `edge/evidence/models` and `conditions`: optional explicit versioned descriptive references retain old callers. Operational evaluation resolves real registry entry and fresh D through private scope; caller now never authorizes D. Foreign/unsupported/unregistered evidence is UNKNOWN. Keep safety/calibration/identity and legacy UTC checks.

Before editing, Sol records a finite call-site map within the ten owned paths for seven categories: bootstrap, capture, plan, grounding, supervision, marker, condition. Each row names original event, policy budget, issue producer, check consumer and owner lifetime. If true current callers cannot be covered without another source change, stop before expanding scope. Valid ordinary startup-to-runtime positives are required; all-UNKNOWN is not P5 completion.

## Execution and exact budgets

ROOT activation requires current pins, no active P4 actual or source reader, no competing writer and reviewed plan. Never stop a live owner to obtain access. Preserve before files/full diff and every command/exit/stdout/stderr/JUnit. Initial used budgets are all zero.

1. New tests first; one RED execution of `tests/test_operational_windows.py`. Planned absent APIs use local test-body imports so missing behavior is a named RED rather than unrelated collection failure. Only the specified missing authority/window behavior is expected RED.
2. Implement startup/lifecycle then window registry then all consumers/replay distinction. CPU fixtures exercise real worker `poll_once`/`_execute` and a temporary real SQLite repository; replace the rendering body with a bounded CPU seam and use the existing OC1 controlled-source seam. Do not mock `from_worker` into accepted authority or run MuJoCo/provider/network actual.
3. One GREEN execution: `.venv/bin/python -m pytest -q tests/test_operational_windows.py tests/test_operational_time_v1.py`. New file has exactly 27 cases below; the OC1 denominator is the actual JUnit collected/executed count, not guessed or borrowed from old runs. One Ruff check over exactly ten owned paths; one format-check over only the two NEW paths. No auto --fix/whole-file formatter, mypy, broad suites or extra attempts. Planned local syntax-preserving import/format cleanup is allowed before these checks with before/after evidence. Any unexpected failure preserves evidence and stops for Astra.
4. Freeze sources and finite evidence. Different-author review must inspect startup factory, all consumers, old-route preservation, original failure/raw output and normal positive path, then ROOT accepts the bounded software deliverable. This plan does not authorize Git mutation; later exact-path delivery follows existing verbatim/raw and non-force three-SHA rules.

Fixed 27 new CPU cases (freeze exact parameter IDs before RED):

- `test_five_seconds_inclusive_and_plus_one_ns_rejected`: 1 case(s).
- `test_deadline_equality_rejected`: 1 case(s).
- `test_missing_pair_foreign_domain_and_copied_handle_rejected`: 1 case(s).
- `test_valid_overlap_accepted_future_and_out_of_order_rejected`: 1 case(s).
- `test_reply_reobserve_and_new_event_do_not_refresh_origin`: 1 case(s).
- `test_cached_frame_preserves_original_acquisition_window`: 1 case(s).
- `test_external_utc_deadline_cannot_be_relabelled_operational`: 1 case(s).
- `test_utc_jump_is_diagnostic_only_for_supported_local_domain`: 1 case(s).
- `test_source_and_budget_changes_invalidate_window`: 1 case(s).
- `test_public_worker_or_source_without_startup_capability_cannot_issue`: 1 case(s).
- `test_ended_prefix_owner_or_lease_cannot_authorize_new_attempt`: 1 case(s).
- `test_closed_owner_or_changed_live_lease_attempt_fencing_rejected`: 1 case(s).
- `test_startup_origin_precedes_reset_and_settle`: 1 case(s).
- `test_startup_failure_and_cleanup_revoke_once`: 4 case(s).
- `test_all_p5_categories_use_same_original_owner`: 7 case(s).
- `test_public_replay_descriptor_never_live_authority`: 1 case(s).
- `test_utc_lease_guard_remains_independent`: 1 case(s).
- `test_foreign_thread_has_no_owner_context`: 1 case(s).

The four cleanup parameters are normal return/exception/cancellation/lease loss. Seven category parameters match the seven listed categories, each with valid live positive and expired/rebound negative assertions. Startup case proves pre-RESET/settle origin and late runtime cannot refill it. Replay case proves public history round-trip remains readable without live authority and intended canonical request reconstruction preserves only its private live scope. UTC case proves D-valid plus UTC-lease-invalid cannot authorize. Foreign-thread case includes copied-context rejection.

No rerun of P3 90/P4 31/old 799/94/93 suites, R94 controls or provider probes. RED1/GREEN1/Ruff1/format-check1 maximum; actual0/formal0. Read-only pins/diff/metadata inspection is not a test result.

## Acceptance and future actual gates

SOFTWARE only: genuine normal worker original-origin-to-runtime positive chain; 27 new cases + original OC1 GREEN; scoped static; exact source freeze and independent review. Clearly label ORIGINAL_TASK_D, UTC_LEGACY_VETO and historical descriptor semantics. Original RED and all failures remain; a missing genuine D lease producer stays an explicit P6 dependency, never marked complete by this work.

Later actual needs separate ROOT activation, applicable accepted P4 real source qualification, reviewed P5, applicable P6 owner/lease/dispatch/transaction closure, frozen workload/budget and complete denominator. No ended P4 handle is reusable. R91 native, physical effects/calibration, full future H_D and P7–P12/formal acceptance remain separate. CPU tests and this plan certify none of those outcomes. Active P4 inputs/readers remain untouched throughout this planning task.

## Planning-tool observation

The first metadata-only save attempt used unavailable `python`: tool chunk `0fabae`, exit127, exact output `/bin/bash: line 1: python: command not found`. The heredoc did not execute; no files/product/test changes occurred. This actual Astra plan records the tool-environment cause and uses available `python3` only to save/check its own metadata. No fabricated pre-execution script hash or product traceback is claimed.
