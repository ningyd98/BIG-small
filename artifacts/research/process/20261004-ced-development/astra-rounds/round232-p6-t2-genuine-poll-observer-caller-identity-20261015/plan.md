# R232 — genuine poll caller identity recovery

Actual planner: `gpt-6-astra`, `/root/astra_status_plan`. Plan only; implementation and every execution remain HELD pending ROOT review.

## Actual failure and diagnosis

R223’s first RED attempt is permanently spent and **not legal RED**: child/wrapper 1, three startup failures, zero errors/skips. All fail at `_open_worker_lease_session` before bootstrap or the race assertion. The original 15 raw files, 27 source/archive pairs and role history remain immutable. The failed run observed 54 resource records, three entered polls and three never-polled workers; it proves no race outcome.

The frozen observer stores the genuine poll function, replaces the class attribute with a counting wrapper, and calls the original body. The actual traceback reaches that original body. Its immediate frame is compared against the *current* class attribute’s code, which is now the wrapper. This exact mismatch is confirmed. Relevant repository/owner/runtime code comparisons were checked; no other same-cause edit is authorized.

## Exact repair

Only `simulation_runtime/worker.py` and `simulation_runtime/operational_lease.py` may change. At module definition time, after the worker class, capture the original poll code object and its module globals as private anchors. Preserve the entire existing worker class/function bodies. In the lease opener’s first guard, compare the immediate caller to those fixed anchors and require caller self identity plus the existing exact worker class. Preserve all existing configuration, binding, active-session, registry, token and lifecycle checks and their rejection message.

No generic unwrap, wrapper allowlist, stack search, dynamic first-poll registration, caller-provided authority or guard removal. The observation wrapper itself acquires no authority. Frozen tests, observer, parent runner, protected 211 and the other 25 sources remain unchanged. Event3 must remain vulnerable until recovery RED is accepted.

## Finite execution and generations

Two **new R232 slots**, each once and initially HELD: 120-second stdlib baseline preparation and 600-second recovery RED using the identical frozen three nodeids. The JSON contains exact argv, cwd, environment, fresh paths, cleanup and capture limits. No new static/review/Git allocation. Full source/script text and SHA gate precedes either reservation.

Baseline preparation proves the two-file delta against the complete original archives and captures all 27 new sources. Recovery RED must reach real bootstrap COMPLETE and the raced legacy write, then fail only with the original three `R223 late local binding was not rejected` assertions. Startup rejection, missing evidence, another error or an unexpected pass is a new STOP. Actual resource denominators and cleanup are measured anew; historical 54 is not an expected count.

After this legal RED only, resume original event3 repair. Original R223 `prepare_green`, narrow Ruff and GREEN9 retain their existing once-only slots, argv and paths. The unchanged prepare script already accepts an explicit `red_source_index_pin`; use the actual R232 baseline. From that baseline to GREEN only event3 may change, including strict continuity of the repaired caller pair. The unchanged narrow Ruff does not purport to lint the caller pair separately.

Original three R223 scripts remain unchanged. A new ROOT-only continuation settler replaces only the **effective source/argv/output of the original unused ROOT settlement slot**, not its budget. It records historical R223 baseline/startup failure separately from effective R232 baseline/legal RED, then original R223 prepare-green/Ruff/GREEN9. It verifies the two distinct scope intervals and all original raw, resource, source and role checks. It must never require the failed RED to pass or overwrite its result.

## Gates and evidence

Observed 285 identity comparisons passed: 27 original/current archive pairs, 15 raw records, the baseline index, four role archives and protected 211. Full 58 input pins and archive map are in JSON; current role generations are distinguished from immutable history. Before authorized role/gate amendments, save complete bytes and perform CAS. Old plan and spent records stay unchanged. Source identity comparison uses exact path/bytes/SHA while preserving additional metadata.

Same actual Sol is the sole source/test-author-script author; ROOT owns its stdlib settler and metadata. New scripts are `implementation/prepare-evidence.py`, `run-command.py`, and ROOT `root-settlement-continuation.py` under this round. Their source must be fully reviewed before one-shot execution. Full results/raw remain durable; stdout is at most 6000 UTF-8 bytes of scalar/path/hash summaries. Tool returns are stored before display; unavailable independent tool streams stay null. No hidden probe or collector.

Any unexpected result or scope expansion stops for a new genuine Astra plan. Parent T2 GREEN7, final checks, reviews and Git remain separately held/exhausted as applicable. This document grants no T2/T12/native/physical/formal acceptance.

Authoritative exact contract and all full pins: `plan.json`. Planning observations: `input-observation.json`.

## Independent ROOT metadata observation

ROOT reported tool `50b82d`, exit 127, `/bin/bash: line 1: python: command not found`, during a bare-python plan-presence read. Its Python body did not execute; this is unrelated to the poll cause. The complete object is in ROOT’s store, not this planner’s store; no full-call bytes or hash are invented. ROOT must preserve that object natively before activation. Abandon the bare-python command; necessary ordinary metadata work uses the confirmed repository `.venv/bin/python`. No extra execution or product budget is created.
