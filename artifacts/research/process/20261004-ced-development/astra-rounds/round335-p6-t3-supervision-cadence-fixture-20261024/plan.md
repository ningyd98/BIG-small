# R335 original supervision cadence fixture plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Implementer:** existing `/root/p6_t3_sol` only.

The prerequisite hypothesis is confirmed by source: protected factory `_draft` retains `supervision_period_ms=300`; the observer's original `_Counter.now` starts at zero and is not advanced; `_b_t3_supervision` immediately reserves cursor 1. Original cadence requires start + cursor × period to have elapsed. Local migration must preserve that rule. This is a fixture prerequisite defect, not an executed product failure.

`root-finding.json`, `original-supervision-helper.py` and `planner-cadence-readout.json` retain evidence. `plan.json.inputs` pins immediate sources, original clock structures and both unused ledgers. Current whole-test SHA is `083bd235d54cb3961ec40a52d6eb997275a4cda3c9075297b4ffea95114dcb45`.

## Scoped change

Change only `_b_t3_supervision`, its sole existing call in the UTC provenance test, and one evidence field in that caller's returned mapping. No product/protected helper changes.

- [ ] Extend signature to `_b_t3_supervision(runtime, data, key, observed)`; pass the existing `observed` namespace at the one call.
- [ ] Read original period through `_runtime_option_sources()` and the real persisted configuration through `_job_configuration()`. Check the original 300 ms policy, period 0.3 s and exact 300000000 ns conversion; do not derive time from UTC. Register supervision normally and preserve its schema assertion.
- [ ] Select exactly the `(clock, raw, domain)` tuple whose clock **is** `runtime._operational_owner._clock` and whose domain kind is `D_app`. Verify current thread/native id against actual owner clock domain and startup owner. Never select a counter by list position or touch another thread's clock.
- [ ] Record actual original task bracket/token/domain, hard bounds, original policy/configuration and counter before mutation. Obtain current bracket through the genuine clock after the original token.
- [ ] Compute `due_ns = original_task_origin.upper_ns + 1 * period_ns`; use the immutable upper endpoint conservatively. Set `target_ns = max(before_counter_ns, due_ns)`, requiring it strictly below every original app hard deadline. Advance only this existing `raw.now` on its owning thread. No new event/origin, renewal, sleep, rollback or D_lease mutation.
- [ ] Read actual current bracket again; require its lower bound reaches due, while original domain/token/bracket/original_time/hard bounds remain unchanged. Call normal `runtime.check_active` before the existing reserve capture. Preserve the complete reserve/capture/context/plan/completion chain and all existing assertions.
- [ ] Add detached `cadence` evidence to helper return and persist it as `supervision_cadence` in the same UTC-provenance observation: actual period/configuration source, cursor/due, raw and bracket before/after, original identity/bounds, owning-thread identifiers. Existing returned fields remain. Do not fabricate runtime values during preparation.

The present fixture is expected to advance from 0 to 300000000 ns; the helper must derive and record actual values. Existing hard-open and frame-age checks still apply. A product migration gap is recorded under original R331, not solved by relaxing cadence.

## Source-only verification

- [ ] Parse complete after source with stdlib AST and symbol table; do not import/run/collect anything.
- [ ] Prove diff is limited to the helper, its sole argument addition and the evidence field. Original **260206-byte prefix**, SHA256 `dfe6ce74fd0fe2c8f1694b73e74766f0933cb5ad1f67e7a033838c89d9adaf29`, and all other source bytes remain unchanged.
- [ ] Inspect identity/thread checks and original-origin monotonic advance preceding reserve. No new clock factory/origin/deadline/renewal/sleep/worker, broker mutation or forced VALID path.
- [ ] Existing time/source/cost assertions remain; the same four T3 functions, nine nodes and fifteen-poll cap apply. Evidence flows into the existing case JSON.
- [ ] Product/protected files, runner, R331 plan and ledgers remain unchanged. Both RED/GREEN are **used 0 / remaining 1 / HELD**.

Save actual before/after pins, minimal diff and `implementation/source-proof.json` under R335. ROOT independently checks and accepts the static correction before ordinary R331 source-gate continuation. Eventual R331 tests establish actual elapsed counter evidence and legal behavior; this plan adds no runtime allowance or acceptance claim.

If the actual policy/identity mapping does not support these steps or another defect requires scope expansion, stop affected changes for actual Astra. Do not modify product cadence, protected helpers, historical snapshots or R331's plan.
