# Independent T2 continuation — R323

Reviewer: `/root/fresh_t2_review`, the original fresh review seat.

## Verdicts

- **R317 scope — Spec: Approved; Quality: Approved.**
- **Cumulative bounded T2 — Spec: Approved; Quality: Incomplete.**
- **Overall T2 acceptance: not granted.** The remaining item is **T2-FR-02 / R319**, the observer classifier repair and its evidence/interpretation review.

## Read coverage and quota

R323 used its single authorized read: **1/1 SPENT**, actual `8c17ec`, exit0. The reader displayed144 source lines and precomputed16711 UTF-8 body bytes under its24000-byte guard (hard limit28000). Exact arguments and the complete raw return are preserved in `batch-01-receipt.json`.

Current source ranges: `protocol.py:153–239`, `memory.py:1784–1805`, `sqlite.py:2362–2396`. The complete frozen-to-live diff reconstructed to3300 bytes, SHA256 `1aead231aef0bc2ae0d85f10245adc9a1de46dbb0af399c68da9092397ce02bd`, exactly equal to the full diff previously read. All four run result pins, raw/index/registered-file/DB/archive hashes and expected sidecar absence checks matched. Wrapper cleanup was complete; unobserved native/GPU/OS-handle fields remain null.

Original12/12, R31716/16 and R3222/2 remain SPENT. Their failed output guards retain zero coverage. R319's separate four-read budget remains unreleased and unused. R323 retains the old `R322_BASE` output label and R322 plan/release metadata because the release required exactly seven literal substitutions; this does not reset or consume R322 quota.

## Product reasoning

The public outbox claim is deferred to candidate selection. Within the original Memory Lock or SQLite transaction, the backend checks the selected task's local binding before mutation. Memory checks at line1792; SQLite at lines2376–2377 after BEGIN and selection. A binding introduced during an actual wait is therefore seen before a claim can change state.

The no-candidate branch preserves the no-argument local-only denial (Memory1797; SQLite2374). Private dispatch remains first, and the exact legacy negative-cancellation guard remains present. Existing eligibility, ordering and mutation statements are preserved. The repair closes the original unrelated-local-row starvation path.

The full382-line regression test and63-line diff were read in R317. Its two expected RED failures and two actual GREEN passes were independently reviewed in the preceding receipts. Each GREEN performed five checks and18 operations plus the real waited-binding path. R323 closes the remaining generation and retained-artifact checks.

## Closed read gaps

**G1/G2:** Complete diff equality and independent four-run raw/index/file/DB/archive/sidecar validation are now closed, with no mismatch.

**G3/G4:** R322 batch2 already read the four original COMMIT seam scalar histories, same-owner duplicate, restart no-authority checks, memo copied-context/exception records and zero-registry arrays. Each seam spent exactly one reobservation and one revision; retries, original time and limits stayed fixed. Restart/detached/reconciliation checks did not grant authority or repeat the debit.

**G5:** All76 planned frozen fixture lines and144 planned current product context lines have now been read. The previous32-file catalog comparison found29 unchanged files and only the three R317 product changes; R323 reconstructs those changes exactly.

## Remaining finding

**T2-FR-02 remains open.** The historical observer at `tests/test_operational_runtime_closure.py:3817–3822` used `_sealed` to classify a mutable lease session whose constructor does not set that field. Preserve the original **5708 attempts /5693 recorded initialized /5708 cleanup** and15 misclassified session records.

Separate session-to-worker, heartbeat, completed-poll and cleanup linkage supports an interpretive constructed count of5708. The worker installs a session only after its opener returns. This is evidence of normal construction, not a retroactively recorded constructor-return trace. Allocation and cleanup denominators are independent of the faulty flag. The30 DB pairs are original-database/retained-archive pairs.

The separately planned R319 repair, new evidence and historical overlay require their own released review. No other G1–G5 read gap remains.

## Evidence limits

These are bounded software/CPU fixtures. No whole-P6B/P6C, physical, native or formal acceptance follows. The old R311 writer SIGSEGV remains unexplained; newer passing runs do not establish its cause. No further runtime is required solely for the completed R317 scope.

All prior reports, raw evidence and exact read receipts remain unchanged. This reviewer performed no product/test edits, imports, AST, SQL, Git, tests or probes.
