# Fresh independent frozen review — stopped on an Important finding

**Status: STOPPED_ON_IMPORTANT_PRODUCT_FINDING. Stage A is not accepted; this is not Ready to merge or whole-P6 acceptance.** Reviewer: /root/p6_a_review. Authorized ceiling: LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO.

## Strengths

The frozen code has substantive repairs to the original E1–E7 concerns: private immutable issuance records, actual repository guard/BEGIN owners, same-job nested writer checks, single commit with same-connection ack, broker response consumption that retains the original previous bound, original ACQUIRED/null-attempt and real ATTEMPT_BOUND lifecycle, and negative residual/orphan cleanup. Final test source uses a true queue timeout/late-reply barrier and an actual unfinished-attempt crash backup. Main-thread and installed maintenance-thread producer assertions preserve original D_app handles and task budgets.

The existing evidence is 40 unique final-pass nodes across four separate runs: original GREEN20 historical 19 PASS / 1 FAIL, corrected foreign 1 PASS, new19 19 PASS, and CPU positive 1 PASS. The historical constructor-lock failure is retained. The positive test runs the original factory episode before injecting exactly six CPU outcome flags and retains zero action/model/quantity assertions; it does not establish physics or hardware success. These observations do not close the unfinished evidence audit.

## Issues

### Important — R150-B1: final commit acknowledgement failure preserves SQL success after withdrawing public artifacts

Frozen [sqlite_repository.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/sqlite_repository.py:1335) performs the actual COMMIT before the same-connection reread and private acknowledgement. The terminal dispatcher [line 1774](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/sqlite_repository.py:1774) then confirms that ack with the broker. Confirmation still checks the original prior bound ([operational_lease.py:739](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/operational_lease.py:739)); response consumption rechecks both segments ([line 708](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/operational_lease.py:708)).

The concrete trigger is an otherwise healthy SUCCEEDED publication whose final COMMIT succeeds, followed by a closed connection before the ack reread, or a confirm/consume timeout or original-bound expiry. The terminal frozen target already contains job SUCCEEDED, an ended/SUCCEEDED attempt, a released lease, success artifact paths and artifact_created event ([sqlite_repository.py:1836](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/sqlite_repository.py:1836)).

On this failure, [worker.py:522](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/worker.py:522) withdraws the promoted public files into the private unconfirmed directory, restores any previous originals and writes accepted=false. Immediate exception cleanup and poll finally then use [sqlite_repository.py:1995](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/sqlite_repository.py:1995): SUCCEEDED is outside the residual status set, the attempt is already ended and the lease already released. [Line 2013](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/sqlite_repository.py:2013) returns False without changing the successful job/attempt/event/artifact metadata or terminalizing the operational row.

The persisted API/SQL truth therefore remains SUCCEEDED with paths to withdrawn files although the final commit handshake was rejected. This is a positive terminal-publication consistency defect; it does not imply that a terminal row can revive a live lease. No new fault was executed by this reviewer: the evidence is deterministic frozen source control flow. Existing COMMIT-close tests cover acquire/bind and the CPU positive covers the healthy terminal path, not this final failure point.

ROOT was notified immediately. Track B paused. A genuine GPT-6-Astra limited new plan is required before any repair or execution.

## Closure observations

- **E1/G1: provisional source repair observed.** Negative-only safe dispatcher requires current expected owner and denies positive status changes without genuine session; positive legal-source challenges and owner mismatches are among actual new19 nodes.
- **E2/G1: provisional source repair observed.** Registered writer/dispatch owners, exact real stack/frame checks, same-job nested allowlist, direct legacy/TLS/cross-job negative tests observed.
- **E3/G2: acquire/bind residual repair observed; terminal publication unresolved B1.** Poll finally owns negative cleanup before session close; orphan scans COMMITTED/REVOKED/TERMINATED. Existing actual commit-close coverage targets acquire/bind, not terminal.
- **E4/G3: provisional source repair observed.** Frozen registry bindings retain original purpose/digest/snapshot/repository/path/conn/thread/nonce; sealed mirrors are checked, mutation/replay tests present.
- **E5/G4: provisional source repair observed.** Reply consume checks original issued proposal generation and both previous/new segment deadlines; equality and after-bound tests both actual-pass nodes.
- **E6: test mechanism repaired in source; full fixture audit pending.** Real queue barrier waits for actual wait-cap cancellation/unusable before releasing the late confirm request; no manual invalidate replaces the timeout trigger.
- **E7: test mechanism repaired in source; full fixture audit pending.** Actual running/open attempt DB backup precedes original finally; ended original session is used for orphan recovery. Durable phases each retain original acquisition and forbid operational retry/requeue.
- **R134 S: not closed.** Healthy staged publication + actual SQL/final files control exists, but terminal post-COMMIT failure leaves inconsistent positive SQL state (B1).
- **R134 C: provisional exception-safe owner/connect cleanup observed.** TLS/private writer finally cleanup and true acquire/bind fault tests are present; targeted recovery receipt/full resource fixture audit remains unfinished.
- **R134 F: corrected foreign fixture mechanism observed; independent bridge pending.** Other same-DB repo initialized before original guarded open transaction; denial occurs inside genuine original transaction and checks seven tables. Strict test-only bridge supplied but not yet fully independently read.

These are provisional read observations only. R134 S is unresolved by B1; they do not constitute final closure of the overall E1–E7/G1–G4/S/C/F review.

## Declined-to-judge

- Full raw/result/fixture semantic crosschecks and independent text delta bridge review were not completed after B1 halted Track B. Existing hashes/JUnit and source reading cannot replace those pending checks.
- R134 publication S is not closed because B1 is a terminal failure path. C/F and E1–E7/G1–G4 observations below are provisional source/evidence notes, not final acceptance.
- R150 M1 special shared backend log has exact source-supported two-worker interpretation in activated plan. Aggregate calls lack per-instance instrumentation, so exact per-worker attribution is an inference, not new raw evidence.
- Only eligible Stage A ceiling is LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO. B/C/D/P7/P8/native/physical/hardware/formal and whole-P6 acceptance remain declined.
- No new product AST/import/compile/collect/pytest/static/SQL/probe/Git was executed, and no source was edited.
- The prior reader protocol deviations remain permanent: exactly two read failures, followed by three actual unplanned replacement reads. R150 activated subsequent work only; it does not retroactively authorize those calls.
- Seven authorized R150 read batches exited 0. Batch 2's tool display truncated part of the JSON wrapper; batch 3 emitted the missing source tail and concise authority schema. Capture limits and available structured returns are preserved in read-ledger.json; separate streams were not supplied and are not invented.

## Assessment

**No acceptance.** The immutable six source hashes matched R147 authority and seven R150 batches completed without a new execution failure. B1 blocks software Stage A publication consistency. Full raw/fixture/type-only and foreign test-only bridge checks were still unfinished at the required halt. input-pins.json records full source and authority SHA256; read-ledger.json records commands, actual exits and old-deviation provenance. Work stops here pending ROOT's actual Astra disposition.
