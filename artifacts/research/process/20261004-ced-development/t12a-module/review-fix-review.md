# T12a corrected-source independent re-review

Verdict: **REQUEST CHANGES** for one remaining P2 absolute-deadline boundary. Both original P2 findings are closed: provider copies preserve the authoritative quota/deadline/observable context; unsuccessful audit publication no longer charges allowances, and a successful retry is charged once. Actual adaptive admission remains closed and ordinary software traces remain expired.

All16 corrected source copies and live files matched review-fixed-source-hashes.json when re-review began (review-fix-independent-hashes.json). Existing corrected scoped tests report **116 passed in 2.03s** (review-fix-independent-scoped.log). Re-review read the exact corrected-source delta; no production edit was made by the reviewer.

## P2 — fresh deadline is not checked after contract callback or audit acknowledgement

The judgment callback path reads `finished=self.clock()` and checks the original absolute verification deadline. However, the contract provider path at joint_policy.py:591 may return or throw late and route directly to `_fallback(..., now)` using the original decision start time. The successful audit path calls the sink at :490 and then invokes `_hard_stop(context, now)` at :492 with that same stale time. Neither path checks the current clock after the synchronous callback returns.

Exact counterexamples in review-fix-late-return-probes.log use a mutable injected clock and the unchanged original NOW+60s verification deadline. First, contract_provider changes only the clock to NOW+61s and raises TimeoutError. `decide` returns **REOBSERVE**, consumes one quota, and its trace.created_at remains NOW. Second, contract_provider is None; trace_sink changes only the clock to NOW+61s and successfully acknowledges. The policy again returns **REOBSERVE** and consumes one quota after the unchanged original deadline. Providers do not mutate the authoritative budget in either example, so the previous isolation correction does not address them.

Minimal contract reproduction:

```python
clock = [NOW]
chosen = policy(clock=lambda: clock[0])
def late_contract(context):
    clock[0] = NOW + timedelta(seconds=61)
    raise TimeoutError("late contract return")
chosen.contract_provider = late_contract
ctx = prepared_context()  # original deadline NOW+60s
assert chosen.decide(ctx) == DecisionAction.REOBSERVE
assert ctx.verification_budget.remaining_reobservations == 1
```

Required correction: read/validate a fresh timezone-aware, non-reversed clock after the contract provider returns (including exceptions), and after audit acknowledgement before reservation commit/action return. A late result cannot grant a new capture or consume recovery/capture quota. Preserve existing hard-stop behavior and audit failure idempotency; a persisted software trace remains audit-only if its action is rejected after acknowledgement. Add both late-return regressions, and check ordinary selected/provider paths as well as missing-contract fallback.

This does not require forcibly interrupting a synchronous callback: the existing report correctly states that a callback which never returns can block. The issue is the cheaper, verifiable deadline check once it has returned. The report's statement that callback latency/deadlines are checked after return must cover every callback that can precede a returned action.
