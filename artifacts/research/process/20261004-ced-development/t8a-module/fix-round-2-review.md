# T8a independent fix-round-2 review

Review date: 2026-10-04. Scope: `fix-round-1-review.md`, `fix-round-2.diff`, the correctly named `fix-round-2-source-hashes.json`, `report.json.fix_round_2`, and exact current source/tests. All four manifest hashes match current files. No production code was edited. No physical simulation, rendering, GPU, network or full suite was run.

**Scoped specification verdict: PASS (software only).**

**Code-quality verdict: PASS.** The remaining P2 command-prefix finding is resolved. No new P1, P2 or Minor finding identified in this narrow repair.

## Resolved P2

`_execution` now rejects an empty dispatch history and requires the first original backend command sequence to be 1 (`protocol_evidence.py:637`). Its action cursor starts at 1 (`:641`); strict contiguous half-open action ranges must begin at that cursor (`:669`). The entire dispatch sequence must equal `range(1, sequence_cursor)` (`:777`), and existing strict integer, uniqueness, action/source/time/target and actual actuator-step joins remain enforced. A caller cannot establish the reset boundary from the first supplied record or offset all action ranges to hide a missing prefix.

The added omitted-first case is meaningful: a complete source with two identical same-step dispatches is accepted before the first dispatch is removed; removal preserves the measured controls and full physical trace, so control matching alone cannot catch it. The repaired command audit rejects this omission. The documentation explicitly leaves pre-action dispatches unsupported until an independently validated prefix contract exists. Physical/controller semantics and the passive collector are unchanged.

## Verification and limits

- Independently ran only the three synthetic CPU command-prefix cases: **3 passed, 49 deselected in 2.73s**. They cover shifted sequences/action ranges, omitted first same-step dispatch, and empty history. No real physics backend was initialized.
- Verified all four hashes in `fix-round-2-source-hashes.json`. Inspected the two pre-fix failing cases, supplied module-only result (**52 passed in 20.42s**), clean Ruff log and mypy result for two source files; did not rerun the full module or physical suites.
- `report.json.fix_round_2` correctly preserves the old physical development source/audit until root performs a separately tagged software re-audit. The existing `t8-real-raw-development` report and audit remain DEVELOPMENT_ONLY, topology INCOMPLETE, `valid=false`, one proven recovery and `g4_measured=false`. They contain 5368 physical states, 5367 controls and nine successful teacher actions under historical source hashes; this review neither reruns nor relabels that experiment as acceptance for the repaired source.
- Actual fixed formal captures, all 200 preregistered injected safe teacher recoveries, complete history exclusions, external frozen source/role/root bindings, INITIAL freeze, filesystem consumer isolation and online G4 remain pending integration/research requirements. Software fixtures provide no actual research acceptance evidence.
