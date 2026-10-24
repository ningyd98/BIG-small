# R361 SIGSEGV Evidence and Administrative Schema Disposition Plan

Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**. Same `/root/p6_t3_sol` is the only author/operator; ROOT reviews metadata. This plan authorizes only bounded analysis of existing evidence after ROOT activation. It grants no candidate run, database operation or source repair.

## R361-A — unexpected child SIGSEGV

The actual R354 child exited **-11**, wrapper **1**, with no outer timeout and an empty `deadline_events`. The reported **270.1065520400007 seconds** is child elapsed through cleanup, not a timestamp of the faulting instruction. ROOT rejected the diagnostic and verified retained evidence: 539 source inputs consistent, 79 regular output files/20,243,954 bytes, cleanup reaped/empty and no errors. Retention integrity does not establish observer neutrality or product success. Resources, JUnit and cases stages failed; observer status and genuine completed resource counts are missing/UNKNOWN.

There are 18 stack-request JSONL rows representing nine intent/outcome pairs. The ninth syscall-return receipt is at `252675.775778051`; first observed nonzero child exit is at `252675.876453007`. Their difference, **0.10067495598923415 seconds**, is temporal association only. Submission explicitly says `SIGNAL_SYSCALL_RETURNED_NOT_STACK_ACK`; it does not acknowledge a complete dump. The final raw growth interval `[76832,77146)` is **314 bytes**, contains `operational_lease.py`, `line ???`, `_rpc`, and ends at an incomplete `File `. It has no `Current thread` header. Do not infer a fault instruction, main stack or lock owner from it.

The profile contains 148 rows and saturates at approximately **61.527409 seconds** after child start, after **30.000000374 seconds** measured observer CPU. Later profile coverage is UNKNOWN. There are 55 OS observations and seven signal-ownership rows. Earlier raw main-thread excerpts repeatedly show local copy/decode/validation; this is useful context, not proof of the crash or the original 600-second noncompletion cause. Nested inclusive profile times overlap, and observations include substantial instrumentation cost.

**Decision: crash cause UNKNOWN; no proven source repair.** Signal/unwinding interaction, native/interpreter state and unrelated product/extension faults cannot be distinguished by present evidence. Loaded extension names do not identify a culprit. An `_rpc` source read shows two waits, but the raw `???` cannot select either. R350’s earlier deadline failure and R311’s historical SIGSEGV remain separate cases.

## R361-B — administrative summary schema error

Same Sol’s tool `2268ac` exited 1 with `KeyError: actual_monotonic`. ROOT preserved the full command/output/finding without replay. The OS schema uses **observed_monotonic**; stack requests use **actual_monotonic/submitted_monotonic**. The printed `maximum_guard_elapsed=0` came from `.get(..., 0)` on an absent field and is explicitly invalid as timing evidence. Keep that original output unchanged.

A new bounded metadata reader may:

- Check actual container/key/type presence before arithmetic. Missing/null/invalid values remain UNKNOWN with denominators, never zero; booleans are not accepted as numeric timestamps.
- Use OS `observed_monotonic` and source-specific stack timestamps. Never rewrite raw keys or blanket-rename fields across schemas.
- Derive an OS result `completed_monotonic - observed_monotonic` span only when both are present. Label it as that derived span, excluding setup before `observed_monotonic`; do not call it total guard elapsed. Compare actual completion with actual guard deadline separately where both exist.
- Keep JSONL `completed_monotonic_before_receipt` separate: it excludes receipt append and later bookkeeping. Frozen `proc_sample` writes that row before adding completion/guard fields to the in-memory result. Stack-request result fields likewise may postdate their outcome JSONL. Do not copy derived fields back into originals.
- Join by actual opportunity/PID/epoch and row kind, retaining source line/offset and missing denominators. No UTC timestamp ordering as causal ordering.

## Exact bounded scope

`plan.json` lists the complete pinned inputs; `source-evidence-readout.json` records actual schemas, nine byte intervals, timing operands, raw tail and finite source slices. Only those pinned artifacts may be read. Five gate-pinned product/test source files may be read as text/AST to map existing frame names/lines: the operational runtime closure test, `local_temporal.py`, `worker_runtime.py`, `operational_windows.py` and `operational_lease.py`. No candidate import, package-tree audit or recursive historical review. Reuse ROOT database-byte integrity findings; do not open database files or engines.

Same Sol may create only new R361 `implementation/` artifacts: `metadata-command.txt`, `schema-summary.json`, `stack-offset-map.json`, `diagnosis-report.md`, `step-report.md`, and metadata stdout/stderr/result. No new diagnostic tool/framework is needed. If convenient, use one short fixed stdlib-only inline metadata command, retain its exact text, and inspect its AST/import/path/write limits before the corrected metadata operation. Manual report writing from the verified reads is also permitted. No original failed-command replay, candidate subprocess/import, eval/exec/runpy, live `/proc`, network, DB, test, help, collection or probe. New artifacts use exclusive creation; no existing source/raw/plan/gate/ledger/report bytes change.

Bound the analysis to the fixed 148 profile, 55 OS, 18 request and seven ownership rows, 77,146 raw stack bytes and nine byte intervals, at most 23 existing profile target summaries. The exact input byte total is in `plan.json`. One inert metadata-generation operation may take at most **60 seconds** and produce at most **2 MiB** total new output, including logs. This is not a live diagnostic allowance. No automatic retry; retain partial output and report a new issue on failure.

## Steps and proof

1. ROOT reviews plan/pins and confirms exact HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b`, branch `research/20261004-continuation`, both R354 ledgers SPENT1/0, and new output paths absent. Activate same Sol for metadata only.
2. Preserve raw evidence and the exact bounded metadata command if used, then produce schema-correct summaries and offset mapping with actual line numbers and arithmetic operands.
3. Treat pre-request file-size intervals as uncertain byte-growth associations, not acknowledged or exclusive signal dumps. Preserve truncated bytes and unknown line numbers. Do not map hexadecimal Python/native thread addresses to OS TIDs without evidence; no such mapping is available here.
4. For OS CPU differences require same PID/starttime and clock tick rate; for thread deltas require actual TID/starttime. The first16 TIDs are not the full18-thread population. `wchan` is snapshot context, not lock-owner evidence. Do not sum overlapping profile inclusive times, fill missing resource records or extrapolate beyond saturation.
5. Write a diagnosis report separating facts, hypotheses and unknowns, explicitly withdrawing the fake zero and retaining instrumentation limitations. Any newly established source concern is reported for another plan, not repaired here.
6. Verify input hashes unchanged, output schemas/offsets/denominators and arithmetic. ROOT reads the complete report and independently checks the limited derived evidence before recording a static-evidence disposition.

## Acceptance boundary

R354’s diagnostic remains SPENT1/0 on both ledgers; R350 three SPENT/six HELD remain unreleased. **Zero new runtime/DB allowances.** No source repair, retries, refunds, fixture/poll/UTC changes, behavior credit or final-review-seat claim. The acceptance is only for faithful static analysis and an administrative reader correction; neither completed capture nor corrected metadata is a passing product test.

If further live/native/DB diagnosis or a repair is required, first obtain a new actual Astra plan with the exact hypothesis, changed-source scope, fresh command identity, explicit time/resource/output/cleanup bounds and one-time ROOT/AUTHOR reservation. R361 does not implicitly approve disabling signal sampling, increasing timeout, toggling profiling or rerunning the node. Root cause remains UNKNOWN unless later evidence establishes it.
