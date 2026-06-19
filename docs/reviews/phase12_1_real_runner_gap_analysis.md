# Phase 12.1 Real Runner Gap Analysis

Baseline `7b4c9af2b0d10d44969f5f29ca6f700b55e1b96f` provides a complete Phase 12 smoke pipeline, but the smoke artifacts are deterministic pipeline samples. They validate registry expansion, aggregation, plots, tables, reports, and safety claims. They do not prove that Phase 8, MuJoCo, Isaac, MoveIt dry-run, Simulation Runtime, or Planner dry-run runners were invoked.

## Evidence Classes

- `SYNTHETIC_PIPELINE_SAMPLE`: deterministic formulas from the Phase 12 runner. These rows have `actual_runner_invoked=false` and `authoritative_for_thesis=false`.
- `PHASE8_ACTUAL_RUN`: software experiment rows collected from the Phase 8 `ExperimentRunner`.
- `PHASE9_MUJOCO_ACTUAL_RUN`: MuJoCo physical trial rows collected from the Phase 9 MuJoCo runner.
- `PHASE9_2_ISAAC_ACTUAL_RUN`: Isaac rows. When Isaac is unavailable they must be `BLOCKED_BY_ENV` and must not be replaced by Mock rows.
- `PHASE10_SYNTHETIC_DRY_RUN_ACTUAL`: actual synthetic safety dry-run verification evidence.
- `PHASE10_MOVEIT_RUNTIME_ACTUAL`: MoveIt runtime dry-run evidence. Phase 12.1 validation records this as `BLOCKED_BY_ENV` unless the dry-run environment is explicitly enabled.
- `PHASE11_RUNTIME_ACTUAL`: actual software runtime path used for queue/recovery/stress validation.
- `PHASE11_2_PLANNER_ACTUAL`: planner dry-run rows with `dispatch=false` and `hardware_execution=false`.

## Current Gaps

- The Phase 12 smoke summary previously allowed `PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`, although its 90 rows are synthetic pipeline samples.
- Raw run rows did not carry source metadata proving whether a row came from synthetic formulas or an actual software runner.
- Aggregation and thesis exports did not explicitly exclude synthetic rows from authoritative statistics.
- Validation profile did not enforce actual-runner invocation or source artifact hash checks.
- Full profile sample policy was represented by broad seed counts rather than per-experiment requirements such as F15 pairing and F20 stress task count.
- `BLOCKED_BY_ENV` rows needed a first-class breakdown so environment blocks cannot be counted as success or algorithmic failure.

## Phase 12.1 Repair Plan

- Add execution source fields to manifests and results.
- Add fixed allowlisted runner adapters for Phase 8, MuJoCo, Isaac, synthetic dry-run, MoveIt dry-run, Simulation Runtime, and planner dry-run.
- Keep smoke as synthetic pipeline data and emit a corrected smoke status artifact instead of overwriting the historical smoke artifact.
- Run validation through actual software runners for every F01-F20 row, with Isaac and MoveIt dry-run allowed to block by environment.
- Treat `authoritative_for_thesis=true` as a row-level runtime-complete marker only; statistics,
  effect size inputs, thesis tables, and thesis plots require verifier-gated accepted evidence.
- Require source artifact paths and hashes for actual-runner rows.
- Keep hardware claims fixed: `real_controller_contacted=false`, `hardware_motion_observed=false`, and `hardware_write_operations=[]`.

## Non-Claims

Phase 12.1 validation is not the full final evaluation. It can accept `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` and `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED`, but it must not output `PHASE12_FINAL_EVALUATION_ACCEPTED`, `PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`, or `BIGSMALL_SOFTWARE_AND_SIMULATION_PROJECT_ACCEPTED`.
