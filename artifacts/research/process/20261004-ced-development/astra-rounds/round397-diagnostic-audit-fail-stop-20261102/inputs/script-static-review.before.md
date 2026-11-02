# R396 independent static driver review

Scope: pinned `diagnostic/diagnose.py` (SHA256 `411f3cd39272be1b25a62b3c0d74c817588f0df533a8e6790eca1478f23b8d36`) against actual Astra R396 plan. Read-only static review; no driver execution, product import, tests, SQLite connection, network, signals or Git mutation.

## Strengths

The driver preserves the original request and native SINGLE derivation, retains PCSC→ETEAC ordering and stops after a failed PCSC control. New metadata clearly separates the diagnostic source from the historical manifest. Profile and frame observation use passive fields and ordinary Lock.locked(), without product function replacement or lock acquisition. Time caps, child process ownership, raw retention and explicit non-PASS labels are present. Independently verified all 35 pins, driver AST, exact trace request bytes/hash/JSON, historical manifest, branch/HEAD/cached upstream, and empty tracked product diff. The only tracked dirty entries are the two protected gitlinks; reused R393/R396 preservation receipts without regenerating large nested diffs.

## Issues

Critical: none.

Important **R396-I1 — audit denial does not enforce the mandatory stop boundary** (`diagnostic/diagnose.py:129–143`, `209–220`, `269–272`, `414–424`). The audit hook records a denial and raises PermissionError, but the child never checks that record before READY or advancing to ETEAC. Product or dependency code can catch the exception and continue. The pinned native `experiments/runner.py:1456–1466` contains a broad exception catch in git_sha, demonstrating that propagation cannot be assumed; the currently approved exact git invocation is not itself a denied event. The supervisor only reads denial rows after exit/cap. This violates the plan's explicit “If denied operation occurs stop and report” rule. It does not demonstrate a network bypass: the denied operation remains denied. Route this newly identified driver issue through actual Astra, and establish a driver-owned stop independent of product exception handling while preserving supervisor cleanup and original evidence. Do not edit or run this driver under this review.

Minor: none.

## Declined to judge

- Actual replay stacks, identity match, heartbeat and close-entry absence: behavioral run has not occurred; required in final evidence review.
- Product repair and formal research/browser acceptance: outside diagnosis-only scope.
- Live remote Git identity or complete remote raw package: no delivery/network performed during static review.

## Assessment

**Ready for the single R396 attempt: No.** One Important remains. The native self-lock chain is supported statically but is not dynamically confirmed or directly proven for the historical incident. This is a static gate, not terminal evidence review, merge approval or product acceptance.
