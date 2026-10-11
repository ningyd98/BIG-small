# Stage A independent final review

**INDEPENDENT_FINAL_REVIEW_COMPLETE — no blocking Critical/Important findings identified for LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO.** The frozen change is eligible for ROOT's bounded Stage A software decision. This report does not declare Ready-to-merge, whole P6 completion, full public publication closure, native/physics/hardware or formal acceptance.

The reviewer is independent from the author. Head is the six canonical flat snapshots in the final R147 new19 index; Base is R113's frozen four before files, with the new lease module/test initially absent. This was a source/diff and existing evidence review, not a Git HEAD diff. No product imports, AST, compilation, static checks, SQL, tests, probes, source edits or Git operations were executed by this reviewer. Cumulative R150/R151/R152 read allowance is 24 used / 0 remaining, never reset.

## Strengths

Private authority is tied to concrete writer/function/frame ownership and the actual guarded transaction. Holding a publication lock or a TLS connection cannot issue a lease capability. Same-job subordinate writers remain possible under the registered owner's connection; foreign-job nesting and positive status CAS with mismatched ownership reject. The issued view has independently sealed bindings for repository/database/connection/nonce/process/thread/session/job/lease/attempt/generation/revision/purpose/operation/full row and an issuer-controlled lifecycle.

The source separates SQL durability from broker authority. A proposal is PENDING, real INSERT/CAS must affect exactly one row and commit once, the concrete transaction owner rereads using the same connection to issue a private ack, and the broker freshly checks its original domain before activating the exact generation. SQL COMMITTED alone is nonauthorizing. Acquisition starts after guard+BEGIN; early heartbeat preserves ACQUIRED/attempt-null until real start_attempt binds the unique open attempt. Renewal preserves original acquisition/task budgets and original domains. Response confirmation/consumption retains the original prior hard-open bound and rejects equality as expiry; timeout/cancel/reassignment/rollback/late reply cannot renew authority retroactively.

Worker poll-wide finally covers acquire/initial heartbeat/bind failures, invalidates authority before stopping the heartbeat and closing the broker in its owning thread, and closes residual current job/attempt/lease through restricted negative cleanup. Historical terminal truth is preserved. Recovery terminates genuine unfinished old epochs before legacy expiry/requeue; operational same-job retry and raw QUEUED CAS do not create a new origin.

The actual positive control reaches the normal terminal publication path with genuine CAS/COMMIT/readback/private ack/fresh broker confirmation. It calls the original software episode once, then changes only six outcome flags. It retains zero measured quantities, actions, model calls and verification evidence. The same job/attempt/lease ends SUCCEEDED/ended/released, natural job/result/attempt/lease/transition/events files agree, and all22 declared generated hashes match independent frozen byte recomputation and the natural consistency file. This supports a software publication path only.

## Issues

Critical: none confirmed. Important: none confirmed. Minor: none confirmed. No different new product defect was established in this final review.

The former B1 facts are retained without converting an unsupported inference into a defect: a terminal SQL COMMIT may survive a later readback/ack/confirm failure while public names are withdrawn to unconfirmed output. R113 design75–82 explicitly defines lost-ack committed rows as nonauthorizing evidence; R127's cleanup contract prevents unauthorized overwrite of already complete terminal success. The broker still requires exact private active generation/digest and rejects TERMINAL at operational_lease.py747–754. Retaining a truthful SUCCEEDED SQL history does not itself revive authority. Final confirmation is a fresh original-bound authority check, not merely a transport ACK. The original B1 report/addendum are preserved unchanged.

A real limitation remains: protected service.py202–242/394–427/493–509 presents SQL attempt/status/artifact paths and batch success counts without distinguishing confirmed publication from rejected/unconfirmed output. This is the explicit **Open B9 public confirmation distinction** in R151 next-b9-inputs.md/json. No consumer was identified that grants broker permission from those fields alone. The stronger public publication/consumer closure claim is therefore declined. The precise terminal COMMIT-success followed by close/confirm-timeout/prior-bound-crossing fault was not actually executed among the four final runs; no reproduction or raw fixture is invented.

## Prior findings and obligations

| Item | Final disposition and independently read basis |
|---|---|
| G1 / E1 public positive status bypass | Closed for bounded A: concrete private owner dispatch and exact negative cleanup classification; three actual mismatched/revoked cases leave all7 SQL tables unchanged. Anchor: sqlite_repository.py248 and operational dispatcher. |
| G1 / E2 legacy/TLS helper bypass | Closed: exact function/code/frame registration, guard+BEGIN and same-job subordinate allowlist; direct legacy, forged TLS and genuine nested foreign-job negatives reject. |
| G2 / E3 residual durable orphan | Closed: worker.py146 poll-wide finally; sqlite_repository.py1977/2040 cleanup. Actual acquire-close, initial-HB and bind-close capture real durable state before cleanup, then exact interruption/release/owner removal. Unfinished COMMITTED/REVOKED/TERMINATED orphans close; completed terminal truth remains. |
| G3 / E4 mutable issued binding | Closed: independent sealed issuer bindings and private lifecycle; four actual retarget/replay cases plus clone/dict/foreign-thread and corrected concrete foreign repository denial. |
| G4 / E5 lost prior response bound | Closed: original prior segment remains in issued request/ack relation after pending-map changes; actual deadline equality and after-deadline cases reject and leave session unusable. |
| E6 fake lost-RPC scenario | Evidence corrected: actual wait cap expires before barrier release; cancellation/unusable are captured before late reply and a genuine late relation error follows. |
| E7 completed-attempt restart scenario | Evidence corrected: before snapshots have RUNNING attempt with ended_at null; both recovery_service/manual_retry close that same attempt INTERRUPTED and cannot requeue the original job. |
| main/maintenance heartbeat producers | Actual worker.py719–728 delay loop and worker.py183 maintenance thread; actual producer JSON shows distinct real caller threads/broker ingress while original D_app/export/acquisition remain exact. |
| R134 S/C/F | Correct labels: S dataclass serialization, C exception-safe connection/owner/TLS cleanup, F genuine after-COMMIT-close fixture preservation. R147 is the separate foreign fixture repair. Historical3 raw/JUnit and197 hashes independently read, with targeted3PASS; no extra final-node count. |
| normal SUCCEEDED chain | Positive control at test1577, worker.py433 and sqlite_repository.py1786; genuine authority/transaction/publication chain with22 natural hashes, explicitly CPU controlled outcome. |

The G1–G4 category names were supplied from the existing pinned R127 plan by ROOT after the read allowance was exhausted; the closure conclusions above rely on independently read frozen source and actual evidence, not those supplied names or author static proof.

## Actual evidence and limits

| Run | Actual result | Use in final40 |
|---|---:|---|
| Original GREEN20 | exit1,19PASS1FAIL,0error/skip | Retain the19 actual passes only; foreign constructor lock failure remains permanent history. |
| R147 corrected foreign1 | exit0,1PASS | Exact foreign-only fixture delta plus genuine concrete-repository denial/unchangedSQL/transaction-active evidence. |
| R127 new19 | exit0,19PASS | Genuine additional authority/binding/lifecycle/producer negatives and real fixtures. |
| R141 positive1 | exit0,1PASS | Genuine normal publication chain under controlled CPU outcome; prior production bridged only by R145 type-only text delta. |

Batch24 independently parsed all four frozen JUnits and found **40 distinct final PASS nodes across four runs, not a single40run**. Original foreign failure occurred during initialization INSERT while another genuine transaction held the database; relocation outside the locked transaction removes that fixture setup failure and retains the precise denial. R147 changes only that fixture branch/assertions/sidecar; production remains exact and other39 source nodes are unchanged. R145 changes only two production type-expression/annotation/cast/alpha-renaming forms; independent text diffs support the source-only bridge, while existing actual proof remains a static witness rather than behavioral permission.

Final static original invocation/result/stdout/stderr were independently read: R145 formatter/type-delta/Ruff/mypy each actualexit0; R147 test formatter/foreign-delta/testRuff each actualexit0. Mypy covers five production sources. Prior failed static snapshots/receipts remain historical; their failures are not rewritten into these successful commands. No new static or test command was run by the reviewer.

Main final index1208 and additional old/foreign/positive1249 frozen records have matching actual byte hashes; R134's197 historical records, including the generated snapshot-only step report, were independently checked against their own historical pins. Databases were hashed as bytes and never opened. Symlink records remain metadata only; targets were not followed and missing schema fields were not invented. Exact per-file pins are retained under the full-SHA authority indexes and independent receipts.

New19 has18 natural lifecycle records:17 have shutdown1; the exact shared-backend two-worker case has shutdown2 with its precise sequence and two distinct terminal jobs. Factory source actually returns the shared backend for both constructors. Attribution of each shutdown to its worker is source-backed inference; the aggregate log has no instance IDs. Broker/heartbeat/app/event owner closure and selected real transaction cleanup are supported by source assertions plus actual PASS/fixture records, not by claimed exhaustive file-descriptor or temporary-directory accounting.

Batch16 output was truncated; batch17 completed the bounded positive semantics and22 hashes. Batch21 output was truncated by large lifecycle rows; full JSON receipt was saved, and batch24 completed the necessary bounded recovery/resource fields. Other capture limits are in the read ledger. Combined tool outputs are preserved where available; separate reviewer stdout/stderr were not supplied and are not fabricated.

## Declined-to-judge

- B/C/D, P7/P8 and full local temporal/public codec migration: not activated; Open B9 remains explicit.
- Native clock authority/accuracy, suspend/host pause and real process restart qualification: CPU clocks/domains are SOFTWARE_ONLY/UNVERIFIED.
- MuJoCo physics, real controller/hardware motion, model/action success and formal research acceptance: controlled software backend and injected flags cannot establish these.
- Exact final terminal ackloss combination and complete public consumer confirmation veto: not actually covered; SQL history presentation lacks the B9 distinction.
- Full legacy regression suite and all dataset/nonvisual/batch behavior: legacy code/UTC veto were reviewed, but no repository-wide suite was run. The genuine in-memory repository is a temporary SQLite wrapper, not a separate mocked permission engine.
- Exhaustive scheduling/state-space and unrestricted in-process reflection/module mutation/direct external SQL attacks: finite CPU scenarios and API/owner guards are not a general Python sandbox or formal proof.
- Exhaustive TemporaryDirectory/file-descriptor lifetime closure: the available owner-resource fixtures do not prove every such lifetime.
- Git integration/push/remote raw reproducibility package: outside this reviewer task and not performed.

## Inputs and assessment

The final head inputs are:

- [repository.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/repository.py) — 4851 B, SHA256 `228e5480630fe14ad6752ec75f9ea42f4c1cf89c8ce278b6378b2ab9a5624447`
- [worker.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/worker.py) — 91533 B, SHA256 `d0833f98112ccac9b5e9b04163dfcbf2f7d1d053f72c9ab7a7a18398a5e6cdab`
- [recovery.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/recovery.py) — 4062 B, SHA256 `70edefdc953cea27c65d9fe6228aaf7be4a062320c306966c5c7f04862857d79`
- [operational_lease.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/operational_lease.py) — 40472 B, SHA256 `524bce7ee480fc7f9757e23a8360257900d3600c3b6842c46b80d0771201ec90`
- [sqlite_repository.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/sqlite_repository.py) — 104321 B, SHA256 `e4a60c5c8dd6edd468f3033637fce3003ec83dcd0599c59d31dff99dd0291e32`
- [test_operational_runtime_closure.py](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/sources/test_operational_runtime_closure.py) — 80556 B, SHA256 `c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861`

The main authority is /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/new19-freeze/source-index.json, SHA256 `3db973746084304abe73cc2149c9f7b38f85dd98bb46a8cf863d5d3c2fd51063`. Full raw/proof/contract/receipt pins are in input-pins.json; actual command returns, paths and capture limits are in read-ledger.json and read-captures.

Original two reader failures and three unauthorized replacement reads before R150 remain preserved and are not retroactively authorized. R151 batch18's integer/list TypeError remains preserved with exact command/full combined/exit1; no postfailure replacement occurred. Genuine Astra R152 authorized the single typed schema helper, which actualexit0 restored only metadata reading. The final24 budget was inherited without reset. These are reviewer protocol history, not product test failures. Original STOP/B1 reports remain unchanged.

ROOT's authorized facts sync changes mutable STATE/PHASE and two ROOT consumption ledgers; that parent-reported sync is not independently reread here and does not imply acceptance or a product byte delta. Frozen snapshots remain the basis of this review.

**Assessment:** No blocking Critical/Important issue identified within the frozen Stage A lease foundation and legacy UTC veto contract. The evidence is sufficient to pass this independent bounded review to ROOT for its Stage A software decision. Full public publication/consumer closure, all P6, native/physical and formal acceptance remain unclaimed. Review complete; no further source read or verification budget is consumed.

