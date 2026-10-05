# T12a independent review

Verdict: **REQUEST CHANGES**. Two P2 software-boundary findings below are reproduced against the released immutable snapshot. Actual adaptive admission remains correctly NOT_ADMITTED and every SOFTWARE_ONLY trace is immediately expired, so this review does not claim a hardware authority breach or actual research execution.

## P2 — provider can grant allowances and extend the absolute deadline

`joint_policy.py:545` / `:625` pass the authoritative `DecisionContext` directly to contract/judgment callbacks; its `verification_budget` remains a mutable shared object. Rechecking candidate/estimate hashes does not isolate that budget. When a provider changes the budget, the refreshed candidate check can reject its choice but `_fallback` reads and consumes the changed values. A new capture can therefore be returned when the original task budget allowed none, or after its original absolute deadline.

Exact frozen-source counterexamples (`independent-frozen-counterexamples.log`): a fixture starts with `remaining_reobservations=0`. A judgment callback sets the shared value to 2 and selects the previously unavailable REOBSERVE candidate. The policy detects `evidence_changed_or_expired_during_judgment`, but returns **REOBSERVE**, leaves remaining=1, and records FALLBACK_REOBSERVE. A second callback extends `deadline_at` from NOW+60s to NOW+600s; the injected finish clock is NOW+61s. The policy again returns REOBSERVE with remaining=1, although the original absolute deadline has expired.

Minimal reproduction imports `policy` / `prepared_context` from the released tests and supplies:

```python
class BudgetMutatingJudge:
    def choose(self, context, candidates, estimates):
        context.verification_budget.remaining_reobservations = 2
        row = next(c for c in candidates.candidates if c.action == DecisionAction.REOBSERVE)
        return JudgmentResult(row.candidate_id, {}, None, None,
                              "SELECTED", "review-budget-mutator", 0.0)

ctx = prepared_context()
ctx.verification_budget.remaining_reobservations = 0
chosen = policy(judge=BudgetMutatingJudge())
assert chosen.decide(ctx) == DecisionAction.REOBSERVE
assert ctx.verification_budget.remaining_reobservations == 1
```

Required correction: providers must receive an isolated immutable snapshot or independent mutable copy of all authoritative task state, including budget/deadline and robot state. Revalidation/fallback must use the original trusted budget and complete input bindings. Add regressions for both contract and judgment callbacks changing quota/deadline; the original quota/deadline must remain unchanged and no new capture may be granted at zero original quota or after the original deadline.

## P2 — failing audit sink lets the same event consume repeated reservations

`joint_policy.py:483` and the ordinary selection branch decrement capture/retry allowances before `_save`; `_save` calls the potentially failing durable sink at `:447`. Event deduplication is only installed after `_save` succeeds at `:725`. Therefore a sink failure leaves a consumed allowance but no event reservation/cache or audit trace, and an explicit retry of the same frozen event consumes another allowance.

Exact frozen-source reproduction: `chosen=policy(); chosen.contract_provider=None`; install a sink that always raises `RuntimeError("audit offline")`; call `decide(ctx)` twice on the identical prepared context, catching the error each time. After the first call remaining capture quota is 1; after the second it is 0. Both calls have `len(_events)==0` and `last_trace is None`; neither returned an action. The existing single-call sink test asserts only the first consumed quota and does not exercise retry, despite its double-reservation test name.

Required correction: make quota reservation, audit persistence and per-event idempotency atomic from the policy caller's perspective. A retry after sink failure must not reserve the same event twice; preserve the exact pending trace/reservation for an idempotent retry, or roll back safely before returning the sink error. Cover FALLBACK_REOBSERVE, selected REOBSERVE and failed-verification REQUEST_CLOUD retry quota, including a sink that fails once and then recovers.

## Reviewed scope and evidence

All 16 released `source/` copies match their declared SHA256 values. The six owned live files match as well; one read-only shared dependency (`conditions.py`) changed after release, so the decisive tests/probes were rerun in `/tmp/ced-t12a-review-wkogi33r` using a source/test copy overlaid with all 16 frozen files. No production source was edited by the reviewer. `independent-hash-check.json` records live versus snapshot matches and `independent-snapshot-root.txt` records the temporary review root.

The exact released scoped command reports **111 passed in 1.65s** (`independent-frozen-scoped.log`). Scoped Ruff passes and mypy reports no issues in three production files (`independent-ruff.log`, `independent-mypy.log`). No full suite, GPU, model call, physical simulator or network experiment was run. Both findings arise despite passing existing tests and are validated with explicit CPU fixtures.

The report is otherwise candid: default actual source admission is closed; missing inference remains None; rule costs are not probabilities; model/telemetry costs remain separate; candidate sets bind complete contracts and invalid recovery stays unavailable; UNKNOWN and actual TTL do not create CONTINUE permission; STOP precedes ordinary providers and atomic defer grants no new authority. The synchronous-provider deadline limitation is stated accurately: an arbitrary callback that never returns cannot be forcibly interrupted by this implementation. These strengths do not remove the two quota/idempotency counterexamples.
