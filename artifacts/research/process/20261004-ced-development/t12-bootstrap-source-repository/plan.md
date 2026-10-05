# Persistent bootstrap repository increment

This is the store/promotion increment, not the previous ordinary-route release. Keep that774-file archive and its five-file reviewed scope immutable. Owned existing: event_autonomy protocol/memory/sqlite incremental methods/storage only; NEW tests/test_visual_bootstrap_repository.py. Root owns pure visual_bootstrap.py/test and worker/factory/runtime sources. Do not edit/archive moving root pure sources as final release. All SOURCE/BOOTSTRAP records remain non-authoritative; no actual model/capture/control/physics calls.

## Stable storage proposal

```python
initialize_visual_bootstrap_if_absent(definition: VisualBootstrapDefinition) -> VisualBootstrapRecord
get_visual_bootstrap(bootstrap_id: str) -> VisualBootstrapRecord | None
transition_visual_bootstrap_if_current(*, request: VisualBootstrapTransitionInput) -> VisualBootstrapTransitionResult | None
```

Use the existing event DB/lock, one bootstrap_id derived from job/run plus independently enforced job/run and episode uniqueness. Initial rows are their own bootstrap group; never create active/original/ordinary verification/retry rows prematurely. Strict current row codec replays bounded original history and verifies hash/revision/definition and indexed identities before returning/transitioning. Exact initial definition is idempotent: repeat/restart/new observed timestamps cannot overwrite it. New lease/attempt/episode/limits/deadline under existing job/run conflict; an explicit future handoff is out of scope.

Transitions use transaction UTC and actual typed pure producer; no callback returning VALID. Initialize/start uses frozen task-start deadlines, not transaction-now plus a new horizon. Historical duplicate result has no side effects; randomized keys do not replay pending claim. Duplicate/get/init of pending claims cannot authorize capture/request. Completion binds current claim and concrete result/frame source; late/failed/foreign source does not refill. No automatic replay/refund after lost reply or uncertain action.

## Budget and promotion challenge

Promotion must inherit the entire current VerificationBudgetState: remaining observation/retry counts, consecutive no-progress, verification_rounds, best condition history, exhausted_reason, original limits and absolute deadline. No VerificationBudgetState.start during adoption. Ordinary retry pool definition and all spent counts must consistently agree with the bootstrap source; retry consumption remains its sole reviewed producer. Preserve task-start/task deadline and source camera/frame/proposal identities, not only remaining counters. A source already exhausted/terminal, pending claim, unusable or stale planning receipt cannot promote.

The existing owner initializer gets optional typed bootstrap_promotion only after root's stable helper. Under SAME lock/BEGIN IMMEDIATE: read current bootstrap by job/run AND episode; absent promotion cannot bypass an existing bootstrap through a relabeled original job/run or episode. Validate the root helper against exact original/checkpoint/inherited pool/retry/source; prepare ADOPTED and every ordinary owner row before writes; commit all or none. Do not call public initialize while holding the repository lock, and do not allow public transition to ADOPT_ORIGINAL. Old no-bootstrap initialization must remain byte/AST-compatible outside the required guard/promotion increment. Exact promotion retry is historical; subsequent legal ordinary debits cannot be repaid by reinitializing from the older bootstrap snapshot.

## TDD and sequence

1. Baseline copies/hash of current route3 before mutation; NEW tests/design may proceed while root does one-time old-release live checks.
2. Missing init/get/transition qualified RED on real memory/SQLite. Tests cover one-time rows, no partial ordinary pools, strict source row corruption, lost pending claim/restart, exact duplicate vs changed key/current CAS, hardstop/late frames, unchanged deadlines and quotas, real SQLite rollback trigger/two connections.
3. After root quiet-release notice, add private stores/readers and three public methods with TYPE_CHECKING/lazy imports. Preserve all old ordinary-route methods and report their scoped hashes separately.
4. Wait for root frozen helper interface before promotion implementation/RED. Root producer remains single semantic source; storage does not create proposals/originals, positive source certificates or authority flags.
5. Final transitive freeze combines accepted route774 + frozen worker-fix2 additions and root's stable bootstrap module/test plus NEW store test; do not claim a fixed count before verifying overlap. Explicitly retain original route archive/report/manifests and separately detail this increment's three-file changes. Scoped CPU/static/race/restart/cold imports, source isolation and independent review before runtime integration.
