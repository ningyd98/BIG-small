# R223 Public Writer Binding Race — Implementation Plan

> Actual planner: gpt-6-astra, /root/astra_status_plan. Sole source author: /root/p6_stage_b_sol (gpt-6.1-sol). Use the existing gated execution workflow; no delegation or implementation by this planner.

**Goal:** close the confirmed check/unlock/relock window without changing private authority or frozen T2 tests.
**Architecture:** recheck binding inside each actual legacy writer critical section. SQLite recheck and mutation share a real BEGIN IMMEDIATE transaction; keep nonreentrant locks and the existing private/negative dispatch branches.
**Spec:** frozen R158 T2 contract and the exact R223 original source finding; plan.json contains full pins and executable contracts.

## Evidence and scope

The original source reads show the wrapper releases its lock before original save_state reacquires it, while real bootstrap stores binding. This is a confirmed static gap, not a measured runtime bypass. The observed inventory has 36 writer methods per backend. Only protocol.py, memory.py and sqlite.py are product targets; add tests/test_local_public_writer_binding_race.py. Keep the frozen original seven T2 scenarios, runner, 211 protected files and all historical evidence unchanged.

## Tasks

- [ ] Freeze complete actual parent T2 baseline after its real private bootstrap chain is source-ready. R222 may progress independently; use its archived runtime only as historical context, never require an authorized newer runtime to equal that archive.
- [ ] Sole Sol prepares the new test and two author scripts. ROOT reviews their full source, arguments, bounded output and actual resource capture before any execution.
- [ ] Prepare RED metadata once, then run exactly three new deterministic race cases. Both original wrapper precheck and genuine bootstrap commit must actually occur. Only the stated late-binding assertion failures are legal RED; setup failures and timeouts stop the round.
- [ ] After ROOT accepts RED, add the explicit inner fence across all 72 backend/method entries. Preserve SQL business predicates/data/CAS and transaction ownership. Never hold the outer lock across an original that reacquires it, replace locks with RLock, or mint a scope.
- [ ] Prepare GREEN proof once, narrow Ruff once, GREEN9 once and ROOT settlement once. No retries; every slot is independent of historical parent slots.

## Validation and review focus

The RED set is Memory same object, SQLite same object and SQLite second connection. GREEN includes these three plus two backend variants each for legitimate writer-before-binding, bound negative cancellation and unbound legacy roundtrip. Barriers only observe/pause real entry; they never replace guards, locks, database results or binding writes. The actual private bootstrap produces binding and COMPLETE publication. Resource evidence counts every real constructed/partial object and distinguishes never-polled workers from active lifecycles; no assumed per-node denominator.

SQLite checks must happen after BEGIN IMMEDIATE, including formerly implicit-transaction writers; preserve early-return cleanup and existing helper commit ownership. The same-instance mutex alone does not close a second-connection window. Late losing public operations fail closed; the original bound positional CANCELLED exception remains supported.

## Budget and boundaries

Six new once-only slots: prepare_red 120s; RED3 600s; prepare_green 120s; narrow Ruff 120s; GREEN9 600s; ROOT settlement 120s. Exact argv, finite environments, fresh evidence paths and gates are in plan.json. Parent T2 RED remains spent1/0; parent GREEN remains held0/1. No old command is rerun and no new final-review seat is created.

All source implementation, validation and acceptance remain unperformed at plan freeze. This round can establish bounded software race closure only; original T2 GREEN7 and independently authorized review remain pending. T2/T12/native/physics/formal completion is not granted. Any new root cause or scope expansion stops for a new genuine Astra plan.
