# Local replanning

Phase 6.1 local replanning connects persisted edge failures to deterministic or configured cloud replanning adapters.

## Request lifecycle

The edge creates a `LocalReplanningRequest` after local recovery cannot proceed. The request is persisted and placed in the event outbox before execution waits for cloud update.

`LocalReplanningService.process` then performs:

1. idempotency lookup through repository result storage;
2. event lookup;
3. failure summary lookup;
4. current contract lookup when a provider is configured;
5. task, robot, plan, command, and scene identity checks;
6. adapter call;
7. schema and semantic validation;
8. completed-step immutability validation;
9. trusted version and command sequence injection;
10. CAS plan-version update;
11. result persistence;
12. optional dispatch through an outbox-style callback.

## CAS behavior

The repository method `advance_plan_version_if_current` rejects stale or concurrent plan-version updates. Tests cover both successful version upgrade and old-result rejection.

Verified by:

- `scripts/verify_phase6.py` checks 17, 19, and 20.
- `tests/test_phase6_e2e_executor.py::test_replan_cas_rejects_old_result`.

## Adapters

- `MockReplannerAdapter`: deterministic test/CI adapter with injected clock support.
- `RuleBasedReplannerAdapter`: derives the failed skill from the failed step and contract; it does not hardcode GRASP.
- `OpenAICompatibleReplannerAdapter`: requires explicit endpoint/API key configuration and fails fast when configuration is absent.

Production must explicitly configure an external adapter if the OpenAI-compatible path is selected.

## Fail-closed behavior

Adapter failures and validation failures do not update the active plan. API responses avoid exposing full internal tracebacks; service results use bounded outcome and reason fields.
