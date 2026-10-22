# Independent T2 continuation: R317

Reviewer: **/root/fresh_t2_review**, the same original independent seat. No delegation, product/test edits, tests, probes, imports, AST, SQL or Git commands were performed.

## Verdict

| Scope | Verdict |
|---|---|
| Fully reviewed R317 patch — Spec | **Approved** |
| R317 quality and evidence closure | **Incomplete** |
| Overall bounded software T2 acceptance | **Withheld** |

No new product defect was found in the complete R317 delta. The final read attempt failed its display guard, leaving specific evidence gaps. The separate observer finding T2-FR-02 also remains open for R319. These are not a product runtime failure or an invented test failure.

## R317 repair

The complete new test (382 lines) and three-file diff (63 lines) were read. The repair moves public legacy claim classification to the selected candidate under the original Memory Lock or SQLite transaction. The candidate's current task binding is checked before mutation. If no eligible legacy candidate exists, the original noargument local-only rejection remains.

The private dispatch branch, eligible statuses, retry ordering, time placement and selection/update behavior are preserved in the reviewed delta. Waiting while another thread/connection adds the candidate's binding results in the expected scope error, without claimant mutation.

**T2-FR-01 is resolved in the reviewed delta.** Final complete-text derivation proof remains an evidence coverage gap, G1.

## Actual targeted validation

| Run | Child exit | JUnit | Case evidence |
|---|---:|---|---|
| Memory RED | 1 | 1 expected failure | Only mixed-delivery assertion at test:120; 5 recorded operations |
| SQLite RED | 1 | 1 expected failure | Same assertion and original scope ValueError |
| Memory GREEN | 0 | 1 pass | 5 checks; 18 operations; real held Lock wait |
| SQLite GREEN | 0 | 1 pass | 5 checks; 18 operations; real blocked BEGIN |

Each GREEN preserved all local rows and publication receipt bytes throughout the recorded operations. Successful legacy claims changed only the selected legacy key. Denials preserved all state. All four case cleanup records are complete and registry snapshots are unchanged.

Memory uses no SQLite connection; GREEN has one started and joined claimant. SQLite RED closes its one connection; GREEN closes both connections and joins its one claimant. The recorded DB/archive pins were inspected; independent byte verification remains G2.

All four runs are **unit-only**, with no worker poll or new live authority. Their behavior_candidate_pass=false is expected and is not represented as an additional original behavioral node.

## Source generations

An independent hash comparison of all 32 catalog files found exactly **29 unchanged files** and the three authorized changes: protocol.py, memory.py and sqlite.py. The old observer was still unchanged at that read. The new test source pin matches every RED/GREEN case.

The historical five behavior runs use the earlier pure codec; wait2 and dual also precede the two read-only visual-owner accessors. Current writer2 runs and the current memo micro cover the newer bounded full-canonical/class memo. The unchanged validators, fresh returned objects and absence of authority creation support reuse of those earlier software cases. No blanket original-seven rerun is justified solely by this repair or pure memo change.

The historical R311 writer SIGSEGV remains unexplained. Later passes do not establish its cause.

## Original T2 paths reviewed

Continuation coverage includes the full specified fixture/lifecycle ranges, full observer lifecycle test, all 1002 lines of operational_lease.py, all 1165 lines of operational_windows.py, all 536 lines of operational_time_v1.py, and the listed SQLite writer/transaction/finalization/cleanup and worker scope/commit/resume paths.

The original review already read all 19 diffs (2884 lines), including the 36 fenced APIs per backend. Exact private issuer, current worker/thread/process/boot identity, immutable source/policy, and actual registered view/proposal/ack are required; decoded JSON creates no authority.

The initial job guard/transaction precedes the event lock/BEGIN. The authority decision follows both acquisitions. Later COMPLETE writes derive from the same frozen updates and only complete receipts; they do not repeat the semantic debit or create a new live handle. Subsequent positive operations still require a new private scope.

Four actual COMMIT-close seams were independently observed: event PENDING, job EVENT_COMMITTED, event COMPLETE and job COMPLETE. Each had a real completed commit, in_transaction=false, and the same connection's actual ProgrammingError after close. Every seam returned no NEW_COMMIT; the last had durable COMPLETE in both databases. Deep raw counter comparisons remain G3.

## Observer finding T2-FR-02

The old observer tests session._sealed at test_operational_runtime_closure.py:3817–3822. The actual mutable session constructor at operational_lease.py:416–460 never sets that field.

All 15 raw session records are classified incomplete by this predicate. Separate exact worker links, observed owned session/heartbeat and normal polls exist. Worker.py:166–168 installs the session only after its factory returns. This supports an explicit interpretation of successful construction; it is not an original normal-constructor-return trace.

| Count | Value |
|---|---:|
| Completed original polls | 15 |
| Allocation attempts | 5708 |
| Recorded initialized=true | 5693 |
| Misclassified sessions | 15 |
| Interpreted constructed total | 5708 |
| Observed cleanup=true | 5708 |
| DB-to-archive pairs | 30 |
| Two-database scenarios | 15 |

The allocation/cleanup denominator includes all records, independently of initialized. Original raw bytes and recorded5693 must remain. R319 remediation and its separate quota have not been reviewed or consumed.

## Read budget and precise remaining work

The original **12/12** budget remains spent and its report/receipts remain frozen. The R317 continuation is now **16/16 spent**. Successful batches displayed 6091 source/diff lines in total, including overlaps. Every attempt has an exact invocation and raw actual return.

Batch16 computed a 49323-byte formatted payload and rejected it before display against the 39000-byte cap. Its actual exit is1. It adds **zero coverage** and was not retried.

Exact paths and selectors are in [remaining-after-16.json](remaining-after-16.json):

1. **G1:** Independent complete frozen→live three-file diff reconstruction result.
2. **G2:** Four wrapper cleanup/unobserved/raw fields, actual raw/DB/archive hashes and sidecar absence.
3. **G3:** Finite old seam/restart/same-owner raw no-repeat counter and nonauthority comparisons.
4. **G4:** Finite current memo copied-context, exception and validation-counter details.
5. **G5:** Narrow surrounding source/helper ranges listed in the failed invocation, if needed to bind those comparisons.
6. **G6:** Separately authorized R319 observer repair, test evidence and historical interpretation overlay.

G1–G5 need bounded read-only closure, not new runtime. R319's four-read authorization remains reserved and unreleased. No whole P6B/P6C, native, physical or formal acceptance is claimed.

## Files

- [Full report](report.json)
- [Precise remaining selectors](remaining-after-16.json)
- [Failed attempt16 exact receipt](batch-16-receipt.json)
- [Observer finding](finding-T2-FR-02.json)
- batch-01-receipt.json through batch-16-receipt.json preserve all actual reads.

