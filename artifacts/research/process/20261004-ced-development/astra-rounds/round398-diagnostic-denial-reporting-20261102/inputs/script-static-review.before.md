# R396 successor static review — R397 delta

Reviewed new driver SHA256 `8a35abf5bfcf78bfde8aa1dd40d345fefcb5f7e955e5bbe1f4307809c8f267bb` (27301 bytes) against actual Astra R397 plan SHA256 `dce949eb10a11a50315b1ee659fb4f9ec2bc473722b1dc7c011e6bd91dcbbcd9`. Original review remains byte-exact at `round397-diagnostic-audit-fail-stop-20261102/inputs/script-static-review.before.md` and `.json`; original driver is preserved there as `diagnose.before.py`.

## Strengths and resolution

**R396-I1 is resolved statically:** every denied audit event enters a driver-owned helper whose finally unconditionally exits the child with code78, even when marker/log persistence raises. Product exception handlers cannot resume. Exclusive first-marker creation, READY/mode/poll/success guards and parent marker watch are present. The delta leaves product inputs, native functions/locks, allowlist, sampling and budgets unchanged. Independently verified exact before snapshots, new driver/plan hashes, the recorded full delta, all 35 original pins and AST. No run root or execution-start exists.

## Issues

Critical: none.

Important **R397-I1 — diagnostic decoding can preempt denial-result precedence** (`diagnostic/diagnose.py:446`, `459–461`; auxiliary reads at `463`, `476`). Before deriving marker/exit78 denial, line446 performs unprotected read and JSON decoding of the audit log. The plan explicitly supports log-write/persistence errors, which can leave partial records. Such a record raises before the denial classification and result.json are built. Unprotected boundary parsing can similarly prevent the result after denial is known. Child-outcome/READY auxiliary decoding also must not mask an established denial. The child stops and existing cleanup executes first; this defect concerns the required INFRA_BLOCKED_AUDIT_DENIAL/BLOCKED_BY_DIAGNOSTIC_POLICY receipt, not a network escape or continued product execution. Obtain actual Astra planning for the reporting repair: derive known denial independently, tolerate incomplete diagnostic reads/records with explicit error receipts, retain raw bytes and preserve valid evidence. No code was changed or run in this review.

Minor: none.

## Declined to judge

- Runtime termination/sampling and ETEAC cause: no behavioral attempt is allowed by this static review.
- Unchanged driver sections: covered by the preserved full R396 static review, with exact delta verified here.
- Product fixes, formal/browser acceptance and remote delivery: outside this static delta scope.

## Assessment

**Ready for the single R396 attempt: No. C=0 / I=1 / M=0.** Original child-stop issue resolved; one newly exposed reporting issue remains. All runtime/import/test/SQLite/network/signal/Git-write counters remain zero. The driver and product bytes were not modified by the reviewer.
