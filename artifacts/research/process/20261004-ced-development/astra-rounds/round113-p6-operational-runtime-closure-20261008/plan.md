# P6 operational runtime closure — R113 implementation plan

> For the designated original GPT-6.1-sol implementer: use the executing-plans workflow for this bounded stage. ROOT activates exact frozen inputs. Only stage A is writable/runnable under this plan; later stages require their own actual Astra plans. No new user permission is required for already authorized T12 work.

**Goal:** complete the original P6 six units without a P6/P7 dependency cycle; first implement the genuine lease-broker/job-transaction foundation.

**Architecture:** the real worker retains original D_app; a dedicated broker owns and reads D_lease on its own OC1 thread. Actual repository-issued, single-use locked views and real commit acknowledgements bind row/fence state. Later stages combine both original-domain obligations as typed AND at publication and actual mutation boundaries, with no cross-domain numeric min.

**Tech stack:** existing Python3.12, OC1, concrete SQLite job repository, event Memory/SQLite, existing worker/executor/MuJoCo/RawRecorder. No new dependency or controller.

**Spec:** master `docs/superpowers/plans/2026-10-07-t12-sol-execution.md` Task6; accepted R91 design; P6 design/readiness and final P5 acceptance. The executable detail is `design.md`; exact stage paths,47-case mapping, temporal source lines and SHA/bytes are separate finite JSON files in this directory.

## State and evidence

P5 has ROOT software acceptance and was delivered as a08794857dc6ec40cec897250c62d845f396493c, parent f3b5ee32f4538acb8ebad86d000e126ddd5e2cba. Its saved receipt reports candidate compile12/three-node PASS, three equal SHAs and clean delivery worktree. All13 final P5 inputs were rehashed for this plan. This is a new implementation stage for an already identified scope gap, **not an executed product failure**. No products/imports/tests/static/actual/Git/network were run or changed while planning.

The read-only gap is concrete: publication_guard yields None; it does not certify a transaction. Acquire reads UTC before BEGIN. Heartbeat/release lack the unified guard. P5 still uses the old UTC lease reader. Main `_run` and the actual heartbeat thread both renew leases. Event locks are nonreentrant. Handler, queued joint start, direct gripper write and all three mj_step loops are separate real boundaries. Sol's final23-file API report and354 temporal source lines are preserved as finite inputs, not runtime evidence.

## Global constraints and review focus

- No OC1 thread/process/boot/domain weakening; each thread creates its own real identity and clock. No fake current-D from UTC, caller finite or shared cross-domain deadline.
- Original task/verification/recovery origins, smaller policies, spend/retry/no-progress and same-domain parent rules remain unchanged. Age<=5s is closed; hard deadlines are open. External1000ms future/5000ms age rules remain their original UTC route.
- A is **LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO**; it cannot claim full local temporal closure. B/C must migrate every identified local veto before that label is allowed.
- Safe cancellation/release remain reachable. No lock across an entire physical action; later short gates retain partial effects and deny late success, never promise arbitrary host-pause completion.
- Main delay-loop heartbeat and heartbeat-thread calls both need actual private lifecycle scope; public lease_id/repository alone is insufficient.
- The pre-attempt first heartbeat is legitimate: acquisition lifecycle ACQUIRED carries no action authority until the real start_attempt binds the unique open attempt. Never invent that attempt early.
- Source inventory must include the new module; all other source changes require listed ownership. No secret/raw/DB/SDK/weight copying, old evidence rewrites or history cleanup.

These review risks map to A's issuer, locked-view, acquisition, heartbeat, proposal and restart cases. Missing/late acknowledgement, transaction rollback/close and foreign callers must be observed as no new positive authority, not only a helper boolean.

## Full P6 path and denominator

| Stage | New nodes | Exit and dependency |
|---|---:|---|
| A |20| Genuine worker/broker, all job writers, locked view/CAS/commit and restart foundation; eligible now after ROOT activation. |
| B |9| Actual Memory/SQLite publication/grounding/budget and complete versioned local temporal branch; next Astra binds A's outputs. |
| C |16| Actual handler/queue/gripper/every physics iteration, complete D/S observer and private TEACHER_COLLECTION source/time exit; next Astra binds B. |
| D |2| Required complete native positive Memory and SQLite chains after P7/P8 sources and consumers are qualified. |

Total47, with disjoint nodeids in cpu-matrix.json. Master Task7 explicitly permits CPU producer/reader work before actual and depends on P6's corresponding source/time scope. Thus `A->B->C->P7/P8->D` is acyclic; D does not block C or source/time prerequisites for P7. It remains mandatory for full P6 acceptance. TEACHER_COLLECTION is app-owned and recorded as not native-qualified; it is not a public skip_native or fabricated VALID.

Original two regression files have source-derived46+29=75 nodes. Reserve one run at final ABC integration under its later plan; actual collection/JUnit must establish that denominator then. Do not run them in A, or repeatedly run the old P5/OC1/full closure suite. Later changes that truly invalidate prior stage results require explicit justified revalidation, not silent reuse or repeated whole suites.

## Stage A files and interfaces

Create:

- src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py
- tests/test_operational_runtime_closure.py

Modify only:

- src/cloud_edge_robot_arm/simulation_runtime/repository.py
- src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py
- src/cloud_edge_robot_arm/simulation_runtime/worker.py
- src/cloud_edge_robot_arm/simulation_runtime/recovery.py

The other18 roadmap paths are **not writable in this activation**. P5 operational_windows/worker_runtime and all accepted tests/fixtures remain unchanged. No service.py, in_memory_repository.py, models.py, OC1 or package configuration edit is authorized.

`design.md` section2 fixes the new worker mode request, private session/scope/close APIs, transaction-issued LockedLeaseView, broker evaluate/propose/confirm interfaces, additive lease table, lifecycle and orphan-termination API. Existing public repository call signatures remain compatible; new mode is configuration, not permission. Real poll_once establishes authority before acquire and revokes it on every path. Broker opens/reads/closes OC1 only in its real dedicated thread. Both true heartbeat callers get narrowly bound actual thread scopes. The initial ACQUIRED/no-attempt lease permits acquisition/heartbeat/start/termination only; actual guarded start_attempt is the sole ATTEMPT_BOUND transition.

Broker RPC wait cap is `min(1.0,max(0.05,frozen_ttl_seconds/3))`, derived from existing heartbeat and join policy. It is failure handling only. Cancelled requests and late replies cannot become ACTIVE. Original D bounds are rechecked; no future-wall guarantee or new successful-execution allowance is claimed.

## Stage A implementation sequence

- [ ] **1. Verify and snapshot.** ROOT binds plan/input SHA/bytes and absence of new targets/output leaves; no actual/source reader may overlap. Save four existing production before snapshots; record two absent targets. Do not assert the whole round directory absent. Input JSON shape/optional fields are checked explicitly. Original P5/OC1 files and prior artifacts remain immutable.
- [ ] **2. Write only A20 tests.** Use exact nodeids/explicit parameter IDs in plan.json. Build the real worker, SQLite job, original P5 startup and actual broker thread. Reuse finite fixture construction from software_factory/_cpu_visual_worker; a new local helper may wire the new worker mode without editing existing helpers. CPU physical seams/counters are explicit; never replace authority checks, CAS, locked views or verdicts. Every test owns and closes its actual repositories and worker/broker resources. Test identities are created in their owner thread. No future-phase skipped placeholders.
- [ ] **3. Run RED once.** The exact20-node pytest argv is in plan.json. Expected failures are named missing proposed API/behavior assertions, not import/collection errors. Lazy API lookup confines absence to those named cases. Preserve actual exit/stdout/stderr/JUnit and classify each failure. Unexpected root cause pauses for Astra; no RED retry.
- [ ] **4. Implement private broker and concrete repository.** Register exact live worker/repo/epoch before acquire. Issue views only after real guard/BEGIN, with exact purpose/digest/row revision and connection lifecycle. Integrate every actual writer and source inventory. Implement ACQUIRED->ATTEMPT_BOUND, PENDING->ACTIVE through true CAS+commit acknowledgement; rollback/close/CAS0/lost-ack invalidate. Prevent nested writer transactions and broker/repository lock inversion. Renewal creates a legitimate segment without resetting any app budget. No fake UTC lease object is used for broker decisions.
- [ ] **5. Implement lifecycle/termination.** Preserve actual P5 origin and handoff sequence. Include both heartbeat producers. Revoke before cleanup waits; close the OC1 broker clock on its own thread. Controlled orphan recovery terminates old operational attempts and bars same-job recovery/manual retry/CAS requeue; uncertain foreign-live processes are not silently overwritten. Legacy recovery policy is retained. Do not add real suspend/resume support.
- [ ] **6. Freeze semantic snapshot, sort imports once and format once.** Both commands are explicitly limited to the six A Python files. Save before/after evidence; no broad --fix. This is the only authorized formatting/import pass.
- [ ] **7. Run one scope proof, Ruff, format-check and mypy.** Exact commands in plan.json. Proof checks file scope, original P5/OC1 protection, same import names/aliases, nonimport AST/type-comments/anchored ignore/comments before/after formatting, true writer/issuer mapping,20 nodeids and no permission mocks/skips. It is source evidence, not runtime PASS. Mypy checks the five production paths under project policy, with imported modules followed silently rather than reporting unrelated repository-wide errors. Each command once; an unexpected nonzero stops.
- [ ] **8. Run GREEN once.** Exactly the same A20 cases in a fresh independent basetemp. Require20PASS/0error/0skip/0xfail. Preserve actual SQL row transitions, thread IDs/domains, proposal/view terminal states, original app bounds, rejected forbidden mutations and cleanup evidence. No need to separately rerun proof/static after nothing changed.
- [ ] **9. Freeze and hand off.** Save exact six-source states, original raw outputs, nodeids/counts, budget used/remaining, source/finite CPU artifact manifests and step report. Different-author review must cover all actual writers and lifecycle, not accept the author's proof alone. Report A software foundation only; update phase summary truthfully. ROOT schedules finite Git for verified work and next actual Astra B plan; no Git mutation under this implementation activation.

## Exact budgets and required controls

Eight command budgets, each1: RED20; import-sort; formatter; source-proof; Ruff; format-check; mypy; GREEN20. Standalone collect, compile, additional repro, old tests/proofs, extra static, network/model calls, actual and Git are0. All output directories and unique /tmp leaves are listed in plan.json; preserve real UTC start/end, argv/cwd/env/exit and full raw stdout/stderr. Metadata inspection/hash reads do not create test budgets or authorize repeat commands. At most64 finite worker lifecycles per RED/GREEN invocation accommodates the declared controls; no soak or random search.

Required controls within the named cases include: identical numeric ns with distinct issuer domains; forged/copy/foreign views cannot write; rollback/CAS0/connection-close/commit-close/replay cannot authorize; lock wait advances the acquisition read; true early heartbeat before actual attempt remains legal but cannot dispatch; both owned heartbeat callers work while unrelated caller fails; valid renewal preserves original app bounds; equality expiry/cancel/reassign cannot revive; committed-but-unacknowledged proposal stays blocked even after late reply; restart/manual retry/direct CAS cannot refill same job. Keep e-stop behavior untouched and all source/runtime limits explicit.

## Acceptance and stop conditions

Successful A needs exact scope and static proof, actual20 GREEN and independent review. It proves D_lease/job-transaction foundation with the stated remaining UTC veto, not complete P6/native/actual/formal acceptance. B/C's migration/mutation/observer requirements and D's two positive chains remain open. Any new root cause or unlisted product need stops affected work with original evidence, freeze and remaining budgets, then returns to actual Astra. Do not fix by weakening schema/thread/lease checks, hiding partial effects, reissuing budgets or replacing the normal positive target with all STOP.
