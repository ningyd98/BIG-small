# R358 Observer Persistence Neutrality Implementation Plan

Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**. Sole future author/operator: `/root/p6_t3_sol`. ROOT reviews metadata and gates. This is a source-only plan; no execution is released.

**Goal:** prevent optional diagnostic persistence from skipping or replacing the original application call while preserving genuine ownership rejection and native safety controls.

**Architecture:** isolate optional telemetry behind a bounded invalid latch; use an explicit non-instrumenting continuation after persistence failure. Actual ownership evidence remains required before seam attachment. Safety-critical READY/state persistence remains fail-closed.

**Tech stack:** existing Python observer; inert stdlib AST/hash/symtable proof only. The user-required R358 directory overrides generic skill plan locations. Same-author execution after ROOT activation; no agents or tests are added.

**Spec:** `root-intake.json`, frozen R354/R356/R357 plans and R357 ROOT implementation interpretation. `plan.json` contains exact inputs, SHA256, scope and branch matrix; `source-readout.json` contains the original finite definition slices. Both files are part of this contract.

## Evidence and diagnosis

ROOT's frozen 61,006-byte observer has SHA256 `faf1699a2a785e6d07d8ea5d64ff3ab99caca8fdd249cc8f537e783f6f20c8a3`. The original finding SHA256 is `f3c5dbab6d8d5bd6493898b2098fc352e3a48d26aa672b9137c19c062d663ccf`. The source branch is established; no runtime reproduction is claimed.

At lines 1022–1034, bridge-entry serialization/write shares the ownership try and its bare raise. The saved original is only called at 1037. A logging error therefore prevents that call. The session-start log is also unprotected; naïvely neutralizing its write still leaves `enabled=True` able to undo the fault. Callback disable before authentic fixture receipt capture can create a second synthetic rejection unless the inactive path is explicit. Native optional `_log` calls similarly sit inside actual guard/rejection/retirement paths. Existing callback, bridge-finally, finish and final-status handlers already protect most late logging failures and need no broad rewrite.

The ROOT full-read checkpoint is NOT_ACCEPTED, not an execution/source gate. All 16 planning inputs were read and hash-verified. Original evidence and plans remain unchanged.

## Exact permitted implementation

### Telemetry Boundary

- Make _Profiler._append exception-neutral at its narrow serialization/size/read/write boundary. On the first persistence failure latch persistence_failed=True, invalid=True, enabled=False; retain at most the existing16 primitive fault records; best-effort bounded stderr via existing _stderr_fault. Return False. Do not throw, recursively log, retry, reopen, truncate, repair torn bytes or re-enable sampling. The low-level _write_all remains throwing for safety-critical callers.
- Do not conflate genuine identity/ownership guards with telemetry. Preserve the directory and hook safety checks; failed telemetry filesystem validation invalidates diagnostic evidence, never certifies safety or a product failure. Preserve source-gate/directory creation preconditions before any behavior. Failure to establish required initial descriptors remains truthful prebehavior setup rejection; this is not an optional log failure after setup.
- Keep callback/hook identity stable until the genuine resource helper restores/asserts its previous hooks. _fault must itself remain bounded and no-throw, not detach hooks inside an active item. Subsequent optional profile writes stop including emergency/final aggregate writes after persistence_failed; best-effort close/fsync and final status are separate. Original saturation rules remain; saturation is not a fabricated persistence failure.
- At sessionstart, a start-record failure must not escape or be overwritten by enabled=True. Install the same stable callbacks after valid native/source ownership setup; enable measurement only if no persistence fault/invalid/saturation. If already disabled, callbacks are inert under the original limits; no forced owner receipt is fabricated.

### Adapter

- Keep original function capture, selected-item/module/code checks and maximum3 bridge invocations. Split pure ownership validation from optional record writes. Always validate actual current resource-hook identity/code, state closure object identity and empty wait_observer before doing any seam attachment. An existing receipt proving foreign previous hooks or wrong state is a real rejection even when telemetry has failed.
- For an active measurement, require the existing authentic primitive receipt exactly as R357. Missing/false receipt without a latched persistence fault remains a genuine coexistence rejection. A receipt is never inferred from a logfile, serialized authority, a caller flag or a fabricated value.
- If and only if a locally latched persistence failure has disabled measurement, permit transparent non-instrumenting continuation when the receipt is absent because disabled callback no longer captures it: do not attach delegate, do not read more fixture frames, do not claim receipt ownership passed. Record coverage/receipt UNKNOWN in bounded memory/final status when possible. Keep all independently available actual code/state/current-hook/foreign-seam and present-receipt guards. This is no-seam continuation, not permission to install under unknown ownership.
- Write bridge_entry through neutral telemetry after guards. Attach delegate only if append succeeded and measurement is still enabled with all authenticated receipt checks true. If writing fails, fall through to the SAME sole saved original(monkeypatch,directory,backend,observed,callback) call. Never put that original call inside an observer exception-catching block, retry it, convert its exception, force pytest outcome, or return a diagnostic surrogate.
- On original return or unwind, remove only own delegate; preserve foreign seam and mark invalid. Clear active_bridge_epoch in finally even if bridge_exit logging fails; finalize only actually opened diagnostic bookkeeping. Missing return and fixture cleanup tail remain UNKNOWN. Propagate exact original return/exception. No synthetic stage completion or resource sidecar.

### Native Same Cause

- Only optional _SignalControl._log gets a narrow exception-neutral wrapper and latched telemetry-failed flag. Wire a bounded direct fault callback to the already constructed profiler (or equivalently explicit shared primitive state), so native telemetry failure also marks observation invalid and stops profile sampling. No observer callback imports or executes product. Skip subsequent native telemetry writes after failure.
- This ensures failed rejection logging cannot replace the original _snapshot exception and optional state/saved-mask logging cannot abort otherwise valid control steps. Keep _state atomic control persistence, stack-ready.json, descriptor/lock/mask checks, deadlines, eligibility, register/unregister and fd lifetime fail-closed EXACTLY as R356. Do not make READY from a failed write; do not treat a log failure as proof of ownership. Native constructor log-fd creation remains required setup; retirement fsync errors retain existing conservative process-exit-only behavior.
- Do not alter parent OS sampling, signal protocol, 0.1s guard deadlines, four snapshots/phase,19 stack slots, locks or restoration. No blanket exception swallowing around native.start(), _state() or the original application.

### Status

- Final bounded observer-status includes persistence_failed and native telemetry failure, coverage after disable UNKNOWN and truthful restoration. status write/fsync/close failure itself marks observation invalid in memory and best-effort stderr without recursive JSON write. Missing status/partial logs cannot be accepted as valid observation by ROOT; no success inferred from absence.
- No new filenames, worker counters, measurement targets or expanded budgets. All optional stderr/fault reporting remains bounded; at most first persistent fault per channel plus existing bounded final-report fallback, not one write per future callback.

## Files and source review

Modify the specified source sections of `R354/implementation/r354_live_observer.py`, in the exact definitions enumerated by `plan.json`. The sole additional permission is the following prospective metadata binding. Add R358 implementation source-proof and step-report artifacts. Protected product, tests, helper, prerequisite and historical evidence remain byte-identical. Do not treat a whole independently evolving WIP file as a rollback target: compare the frozen local definition slices, preserve unrelated authorized edits, then ROOT freezes the completed successor as one new whole-file gate input.

The native allowance is only telemetry-latch plumbing and `_log`; no native ownership algorithm changes. Directory creation and required initial descriptors remain setup prerequisites. A safety-critical state/readiness write failure still rejects setup or uses the existing conservative retirement path. Optional telemetry failure neither proves safety nor creates READY.

- [ ] ROOT verifies plan applicability and activates the same Sol for the specified source edits.
- [ ] Sol makes the bounded changes and writes source proof with exact definition diff/hashes and every branch in the matrix below.
- [ ] ROOT reads the complete successor and independently verifies protected bytes, source proof and limits. A new unexpected cause pauses its affected scope for Astra.
- [ ] ROOT records source-only acceptance and pins the accepted successor in a future complete R354 gate. Historical gates/checkpoints remain intact.

No candidate import, execution, pytest collection, probe, test, fault injection, DB engine or helper invocation is permitted for this repair. Verification consists of text reads, SHA256, AST/symtable and source control-flow proof, not simulated function calls.

## Required branch proof

- **bridge_entry serialization/write failure:** invalid + persistence latch; no delegate; sole original still called; exact return/exception preserved.
- **start telemetry fails before fixture receipt:** no re-enable; stable callbacks inert; actual hook/code/state checks still apply; absent receipt permits only explicit no-seam continuation.
- **profile callback telemetry fails during scenario:** stop measurement; genuine resource accounting unchanged; own seam may stay inert until existing cleanup; no second original call.
- **present foreign owner receipt / wrong actual resource code or state / nonempty foreign seam:** truthful ownership rejection; logging failure cannot suppress or replace guard.
- **missing owner receipt without persistence fault:** existing fail-closed coexistence rejection.
- **bridge_exit/summary/status failure during original exception:** retain original exception; cleanup and invalid-state reporting independent; no invented completed coverage.
- **native optional log fails while snapshot rejects:** retain actual snapshot/guard exception; log failure separately invalidates observation.
- **native state/readiness persistence fails:** existing R356 fail-closed control, no READY/signal permission; no relaxation.
- **stderr itself fails:** best effort ends; raw missingness invalid; never another application exception.

All 23 target tuples and genuine resource counters remain unchanged. Check there is exactly one saved original call outside diagnostic exception handlers; guard failures remain distinct; no persistence-fault path re-enables sampling or attaches a delegate; failure reporting cannot recursively log. Prove native eligibility/mask/lock/deadline/register/unregister/state/readiness/fd paths unchanged. Preserve original fixture early seam clear and UNKNOWN tail/return coverage; no fabricated completion record.

## Prospective metadata binding

The new observer `_startup_contract` and the still-preparing new R354 runner may add exactly two required references: `observer_persistence_clarification` binds this actual frozen R358 plan; `observer_persistence_acceptance` binds ROOT’s limited source acceptance of the actual successor and plan. Validate their existing path/bytes/SHA256 representations using the existing metadata mechanism. The acceptance cannot impersonate a historical acceptance. This is the only runner permission: no algorithm, command, capture, budget, reservation or old-gate change. ROOT verifies both checks before final gate freeze; adding the references releases no runtime.

## Preconditions and acceptance boundary

Exact HEAD remains `729bce11bbd55a4a869e25e52174da3d0db1825b`, branch `research/20261004-continuation`. Future runtime requires ROOT acceptance of the complete new observer, parent runner, proof, native/coexistence contracts and gate; actor binding; then a separate explicit dual-ledger reservation/activation. This plan grants none. The historical HELD ledger hash is preparation evidence, not a recursive obstacle to a later authorized reservation.

The single R354 diagnostic remains HELD 0/1. R350 three SPENT and six HELD remain unchanged. Limits remain 23 targets, three scenarios, 19 stack requests, 121 OS observations, 600-second child, 15-second cleanup, 240-second capture and 900-second outer bound. Profile limits remain 512 coarse events, 1M matched hotspots, 50M callbacks, 256 active frames/thread, 64 threads, 30 seconds measured observer CPU and 16 MiB combined JSONL. There is no extra output/storage/runtime allowance, behavioral credit or final-review seat consumption.

Acceptance establishes a source-level correction only. A persistence fault makes observation invalid and subsequent coverage UNKNOWN even if the application continues. Partial/torn bytes, missing status and stderr failures remain honest missingness. ROOT must not infer pass, baseline performance or completed scenarios from them. The original UTC noncompletion cause remains unresolved; no unrelated repair is authorized.
