# T8b staged cloud-edge-device pilot software

Status: implementation frozen for independent review. Actual selection, foundation, power, INITIAL and FINAL acceptance remain **NOT_RUN**. This package contains no accepted cloud or physical research result.

## Step 1 — complete stage assignment and selection accounting

`build_pilot_assignments` validates six isolated pools: selection 120, foundation 120, power 120, formal 2400, recovery 200 and OOD 300. Selection pairs all 120 full scenes, physics seeds, perturbations and network schedules across B0 periods 0.5/1/2/5 seconds, with a deterministic randomized persisted order and 10 groups in each of the 12 strata per period. All 480 original assignments and outcomes remain in the denominator. The fixed quality gates are static success ≥90%, overall success ≥80% and safety violation ≤1%. Eligible candidates rank by total cloud requests, mean measured wall duration, then the fixed candidate order. The pure selector produces a SOFTWARE_ONLY diagnostic period and leaves the actual selected period empty.

`run_pilot_stage` retains every original case, including absent prerequisites and executor failures. Explicit injected fixtures remain SOFTWARE_ONLY and cannot accept or freeze a protocol. Foundation with no verified selection keeps 120 `B0_PERIOD_NOT_SELECTED` originals. Power keeps its 120 groups, declares the full-method runtime unavailable, and has no invented episode denominator.

## Step 2 — strict public persisted role-probe reader

`verify_role_probe_evidence(Path)` reads the original report/hash, roles snapshot, each first/warm request and response wire, parsed convenience artifacts and synchronized 320×240 RGB/depth/instance payloads. It rebuilds the exact two-image request from the actual frame and effective settings, reparses and grounds the original response, recomputes offline pixel checks, verifies settled wire costs, reconstructs the exact legacy model snapshot/digest and reruns `can_accept_role_probe` with current source/config bindings. Missing, suppressed, drifted or symlinked evidence is unavailable. A successful reader result is NOMINAL_PROBE_ONLY, with physical and edge acceptance false.

## Step 3 — explicit real runtime collector and independent raw audit

The existing CLI can resolve the explicitly selected service/profile and bind `RoleRuntimeBinding`, OpenCV, existing B0 supervision and the existing skill executor only when execution/payment flags, credentials and fresh nominal role evidence are supplied. No legacy fallback or guessed foundation period is used. Private real execution saves reset-to-terminal detached physical states, every pre-step actuator state, backend commands, faults, complete original wire and settled costs. Credentials are excluded from persisted bodies.

`audit_ced_pilot_stage` independently rebuilds the full assignment set, requires the exact complete collector source inventory and matching archived/current hashes, rejoins calibrated frames and actual wire to the role/model/policy, and recomputes physical samples/outcomes from continuous reset-complete raw physics. It checks assigned reset geometry, reference controller initial state, every command/controller step, exact actual wire lengths, costs and all original outcomes. Summary acceptance flags alone cannot pass. Controller/reset/wire numeric fixtures verify these boundaries only and supply no physical verdict.

The real collector and a valid full real stage audit have not been exercised. Current native action bounds contain UNKNOWN, which keeps physical actions closed. No new role probe or Max credential was provided. The nominal reader does not authenticate remote weights. The separate measured-success resource compiler requested by root follows this frozen package; legacy failed-mean budget estimates are not treated as successful-path resource acceptance.

## Step 4 — v2 protocol bindings and preserved v1 shape

`ProtocolSpec` adds explicit `ced.research.v2` role-bundle, selection-evidence, selected-B0-period and budget-rule hashes. The v1 serializer omits these four new fields and rejects their use under v1. Existing entry points remain callable and historical protocol artifacts are untouched. INITIAL derives its values only after full independently audited real selection/foundation evidence with identical pools/roles/period, fixed quality gates and verified opportunity/recovery evidence. Its N remains empty. FINAL remains blocked. YAML cannot override role, selection, period or budget evidence.

## Step 5 — verification and retained stage reports

- RED/GREEN logs retain initial missing interfaces, strict raw-audit and CLI boundaries, exact model digest, narrowed source inventory, changed reset geometry/controller and changed original wire lengths.
- `green-release.log`: **62 passed in 5.88s** across new stage/freeze tests and existing pilot/protocol tests; 42 are new scoped cases.
- `ruff-release.log`: PASS. `mypy-release.log`: PASS for five production source files. `format-final.log`: seven files formatted.
- `compatibility-cpu-final.log`: **241 passed, 1 deselected in 70.69s**, covering T15/T16, protocol generation/raw observers, runtime role bindings and role models. Exact deselection: `tests/test_protocol_raw_observers.py::test_teacher_passive_hooks_cover_real_steps_and_exact_command_ranges`.
- The first compatibility attempt, retained in `compatibility-final.log`, passed 241 tests but mistakenly included that renderer test; it failed creating an OpenGL context because DISPLAY was missing. No actual trial completed. This failure is not relabeled as passing or as an experiment result.
- Three default CLI invocations retained selection 480, foundation 120 and power 120 NOT_EXECUTED originals, each exiting 3 with actual NOT_RUN. `dry-stage-verification.json` verifies exact assignment/original identity sets, full denominators, zero accepted successes and no selected period or freeze readiness.
- `freeze-initial-rejection.log` and `freeze-final-rejection.log`: both exit 3. Neither `initial-attempt` nor `final-attempt` protocol directory exists.

The nine owned files and 23 read-only dependencies are copied in `source/`; `source-hashes.json` SHA256 is `c777ea24b269bf206cf263d10dd387b28105ef52ae942ed0a6e1e806e7c4927f`. `baseline-manifest.json` and the five original source copies remain unchanged. `review-package.diff` compares only owned source against that baseline. No commit, GPU/cloud trial, full suite or historical artifact rewrite was performed.

## Reproduction commands

```sh
.venv/bin/python -m pytest -q tests/test_ced_pilot_stages.py tests/test_ced_initial_freeze.py tests/test_research_pilot.py tests/test_research_protocol.py
.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py tests/test_research_statistics.py tests/test_research_acceptance.py tests/test_protocol_evidence_generation.py tests/test_protocol_raw_observers.py tests/test_ced_runtime_binding.py tests/test_rgbd_role_models.py --deselect tests/test_protocol_raw_observers.py::test_teacher_passive_hooks_cover_real_steps_and_exact_command_ranges
.venv/bin/python scripts/run_rgbd_pilot.py --stage selection --config configs/research/ced_selection.yaml --output NEW_SELECTION_OUTPUT
.venv/bin/python scripts/run_rgbd_pilot.py --stage foundation --config configs/research/ced_foundation.yaml --output NEW_FOUNDATION_OUTPUT
.venv/bin/python scripts/run_rgbd_pilot.py --stage power --config configs/research/ced_foundation.yaml --output NEW_POWER_OUTPUT
.venv/bin/python scripts/freeze_rgbd_protocol.py --stage initial --expected-protocol-version ced.research.v2 --pilot NEW_FOUNDATION_OUTPUT --output NEW_INITIAL_OUTPUT
```

The last four commands are deliberately dry or rejection checks. They cannot establish actual selection, foundation, power or INITIAL acceptance.
