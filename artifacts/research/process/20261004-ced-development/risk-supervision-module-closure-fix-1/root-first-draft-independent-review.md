# Independent review — registered risk supervision closure 515

**Decision: CHANGES_REQUESTED.** One P2 caller-alias defect remains in the owned registration boundary. The frozen 515-source closure and the existing 178 CPU checks reproduce, but they do not prove complete criteria isolation.

## Finding

**P2 — caller-owned criterion workspace lists remain aliased after registration.** `RiskSupervisionRegistration.__post_init__` copies the criterion using `replace(raw.criteria)` (frozen source line178). The concrete `CompletionCriteria` constructor accepts `workspace_min_m` and `workspace_max_m` lists, and dataclass `replace` retains those same nested lists. The internally constructed concrete RAW registration and auditor perform further shallow criterion copies. Consequently an ordinary mutation of a caller list after `RiskSupervisionAuditor` construction changes its frozen task-label criterion, even though every registered original file and SHA remains unchanged.

The preserved independent software counterexample first writes a source-bound summary that agrees with the concrete RAW replay and registers the resulting exact inventory. Before mutation, the supervision diagnostic is VALID with two rows and actual source is UNKNOWN. It then changes only the original caller's `workspace_max_m[2]` to0.001. All original hashes remain equal, yet the next audit becomes INVALID with zero rows because the physical summary no longer reproduces under the silently changed internal criterion. This is a registry isolation defect; the counterexample makes no actual-source, physical-task or METHOD claim.

Required correction: at the new supervision boundary, independently copy the workspace sequences into immutable validated tuples, or reject mutable/noncanonical criterion sequences. Add regression coverage for both workspace bounds and verify that changing either caller container after registration cannot change reconstruction. Preserve the reviewed RAW fix2 and historical release packages; correction can remain within the two new owned files.

Evidence: [counterexample source](root-criteria-alias-probe.py), [failing assertion and unchanged-original diagnostic](root-criteria-alias-probe.log). The tuple/scalar reassignment control passes in [additional probes](root-additional-probes.log).

## Independent verification

The reviewer created a new isolated `/tmp` overlay from this release's source manifest, verified all515 archive hashes and all515 initial overlay/live hashes, and parsed all387 Python sources. No live production source fallback was used. A cold import resolves all67 imported production files into that overlay and matches all seven dataclass public contracts plus the required-source inventory.

Fresh commands in that overlay produced178 CPU tests passed / one compiled-dynamics test explicitly deselected in30.94s; Ruff2 / format2 / cold mypy1 passed. The eight additional independent probes passed: subclass rejection for allocations, histories and measurement carriers; missing clock and missing calibration retain two scheduled observations/two terminal task labels and create zero feature rows; finite calibration values whose residual norm overflows reject; UTC/monotonic interval drift rejects; immutable tuple criterion/scalar reassignment is isolated. These are separate controls and are not added to the178 test total.

Post-run all515 archive/overlay/live hashes and all532 existing release artifact hashes match. New review files are additive; no production source, existing tests, report, manifest or release artifact was edited. Commands/results are recorded in `root-review-command-results.json`; setup in `root-review-setup.json`; logs in `root-cpu.log`, `root-ruff.log`, `root-format.log`, `root-cold-mypy.log`, `root-cold-import-contract.log`, and `root-post-source-artifact-check.json`.

## Scope and remaining research work

The code internally uses concrete RAW fix2 and INITIAL auditors, preserves complete original frame allocations and terminal task labels, separates online features from offline truth labels, rejects known history and connected-source split leakage, and returns missing clock/calibration/INITIAL/commit/replay prerequisites by name. No actual source becomes VALID. The reread saved excluded marker-motion trace retains all ten observations, one marker-center point diagnostic and nine unavailable point diagnostics, with no invented feature rows in the absence of clock/calibration. Marker-center translation is not object extent, grasp geometry, rotation or continuous stability.

Actual RISK remains UNKNOWN; INITIAL/METHOD/execution/selection acceptance and actual model training remain unproven. This review launched no dynamics step, renderer, camera capture, provider request or new physical action. Existing numerical software fixtures and static model compilation for RAW controller constants are within the tested diagnostic scope. The pending caller-alias correction must receive a separate frozen fix release and independent re-review.
