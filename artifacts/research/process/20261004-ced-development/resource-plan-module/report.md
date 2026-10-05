# Source-bound measured-success resource compiler

Status: software implementation frozen for independent review. Actual resource acceptance, INITIAL, power and formal research remain **NOT_RUN**. No physical success was accepted.

The new `resource_plan.py` preserves legacy `budget.py` byte for byte. `estimate_resource_terms` is an explicitly SOFTWARE_ONLY calculation; `compile_resource_plan` first independently audits real selection/foundation sources and never consumes a summary acceptance flag. Tcap uses only independently recomputed successful complete B0 durations: ceil-to-10 of twice P99, clamped to 120–600 seconds. Failed durations cannot supply this reference. Rcap remains 60 seconds.

The plan includes initialization inside the complete path; all 480 selection and 120 foundation sunk episodes; 120 power groups across all seven methods; chosen formal N and a separate 2400×7 worst candidate; G4's 200 groups under both methods; the full fixed G3 opportunity set under JOINT/B3; source verification, reproduction, calibration, data-source and source-generation costs; and a separately versioned 20% future planning reserve. Every opportunity is retained, including sets larger than 2400. Conditional B0 cost references are planning inputs, not measured upper bounds for other methods.

Original settled request attempts include planner, supervisor, replanner and judge, remote/local roles, successful and failed attempts, exact application wire lengths and original provider versions. Unknown billing remains unknown. Whole source trees enumerate current logical bytes, raw/archive bytes, allocated bytes, file hashes and per-file sizes, refusing symlinks. Only the receipt's own `resource-plan.json` is excluded to avoid self-reference. Explicit wall, storage, model-request and monetary ceilings are required; missing sources or ceilings stay UNAVAILABLE/INCOMPLETE.

Auxiliary `ced.resource-phase.v1` receipts require REAL_RUNTIME scope, source inventory and archived bytes, role binding, original START/FINISH clock records and complete source-qualified coverage. Empty request ledgers cannot imply zero cost. A source-qualified closed local trace is required for a known local function; G3 additionally recomputes the exact original JOINT/B3 fixed-rule results with every frozen clock, calibration and online fact. Calibration and data groups must be separate from every frozen pool. This module reads these sources; production publishers for the auxiliary phase traces are still needed. Current pilot wire sources predate per-attempt request IDs, so the existing independently audited pilot wire-length multiset is retained there; new auxiliary sources require exact request IDs. A later formal verifier needs the full per-attempt identity join.

`verify_resource_plan_receipt` reads fixed `resource-inputs.json` and `resource-plan.json`, verifies both envelope and canonical content hashes, recompiles all raw inputs, compares the complete plan and requires WITHIN_DECLARED_CEILINGS. The T8 INITIAL reader now requires this result and binds its hash in `ProtocolSpec.resource_plan_hash`; YAML or a rehashed summary cannot substitute for the recomputation. SOFTWARE_ONLY estimates cannot pass this reader.

Verification: 29 new resource tests plus 69 relevant pilot/protocol tests passed: **98 in 6.32s** (`green-release.log`). Separate T15/T16 compatibility checks passed: **98 in 38.77s** (`downstream-compatibility.log`). Scoped Ruff, mypy for six production sources and formatting for nine files passed. RED/GREEN logs retain missing interfaces, local-zero proof, real G3 replay, provider binding and INITIAL receipt counterexamples. Tests with mocked trusted source readers explicitly exercise software composition only; their budget availability is not actual source or physical acceptance.

`actual-source-check.json` independently checked the retained unavailable foundation and returned UNAVAILABLE, actual NOT_RUN and physical acceptance false. No Max request, GPU/renderer experiment, accepted budget, INITIAL output, power outcome or formal result was produced.

The immutable manifest `source-hashes.json` SHA256 is `7a7bfee4e38bb143d609e0e2ed4e9bf595083041ba62f3e29b3eba2d347ff9f0`. `source/` contains 538 exact files: two owned files and 536 read-only dependencies, including the complete collector inventory, relevant tests and original exclusion sources. `review-package.diff` compares the two new files with the saved missing-file baseline. `ownership.json` lists every boundary. The co-frozen T8 fix1 snapshot has the same complete source manifest.

Reproduce the scoped check with:

```sh
.venv/bin/python -m pytest -q tests/test_research_resource_plan.py tests/test_ced_pilot_stages.py tests/test_ced_initial_freeze.py tests/test_research_pilot.py tests/test_research_protocol.py
.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py tests/test_research_statistics.py tests/test_research_acceptance.py
```
