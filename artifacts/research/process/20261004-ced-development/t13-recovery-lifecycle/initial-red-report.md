# T13 verified recovery lifecycle work in progress

Status: approved design and initial RED only. No lifecycle production module or repository changes have been made. Repository implementation waits for root acceptance of activation fix-round-2.

Plan: plan.md. Root approved same-repository-transaction reuse of the existing retry pool, frozen typed canonical proof and actual injected canonical ReplanExecutionReceipt source. Provider callbacks must be pure with no locked-repository reads/writes. Root owns retry_budget.py, actual execution/evaluation/completion wiring and test_verified_recovery_lifecycle.py. Proposed producer signature was explicitly approved; the new task-pool envelope exposes its CAS revision separately from its VerificationBudgetState.

Initial failing test file tests/test_recovery_lifecycle_module.py uses the real memory and SQLite repositories. Ten RED failures in 1.37s reproduce the absent initialize_verification_budget_if_absent/get_verification_budget producer, covering spent quotas/deadline, detached mutable state, exact SQLite row bytes after restart, two-connection concurrent initialization and missing task identity. No skipped test or mocked-success evidence is used. Test-only Ruff passes. Root's new whole-project software suite may encounter these intentionally failing development tests until the implementation is released; this file is not a completed GREEN module.

One additional source distinction is explicit in the design: canonical ReplanExecutionReceipt proves actual start, not completed recovery motion. RETRY_EXECUTED/post-execution resolution requires the injected execution provider to also supply an actual completed-action/checkpoint time; missing completion source remains unavailable rather than invented from ACK/start/current time. No actual execution provider is enabled here.

No network/model/GPU/render/full-suite/commit/dependency changes were performed. Actual capability/physical acceptance is NOT_RUN and LOCAL_RECOVER remains disabled.
