# Phase 11 Simulation Workbench Gap Analysis

Baseline: `85d354f429e3431cc4a362815a56dfbcb2c0e73b`

Phase 11 moves the main development line from real hardware readiness to the BIG-small Simulation Workbench. The real robot modules remain frozen for regression only. The required invariant for this phase is:

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`

## Current Authoritative Sources

- `src/cloud_edge_robot_arm/experiments/scenario.py` exposes `scenario_registry()` with S01-S15 and is the authoritative source for scenario definitions.
- `src/cloud_edge_robot_arm/experiments/models.py` exposes `ExperimentConfig`, `ExperimentMode`, `NetworkProfileName`, `CachePolicy`, `FaultProfile`, and metric/result models.
- `src/cloud_edge_robot_arm/experiments/runner.py` provides a deterministic simulation `ExperimentRunner` for Mock/software experiments.
- `src/cloud_edge_robot_arm/experiments/batch_runner.py` can run smoke/validation/full suites over scenarios, modes, seeds, and network profiles.
- `scripts/run_phase9_benchmarks.py` and `scripts/run_phase9_2_cross_backend.py` already separate MuJoCo, Isaac, and paired cross-backend semantics. Isaac unavailability is represented as `BLOCKED_BY_ENV`, not a Mock fallback.

## Frontend Gaps

- `dashboard/src/pages/SimulationLabPage.tsx` still hardcodes experiment kinds in `experimentKinds`.
- `dashboard/src/pages/SimulationLabPage.tsx` still hardcodes `PCSC`, `ETEAC`, and `AUTO` in `controlModes`.
- `dashboard/src/pages/SimulationLabPage.tsx` only exposes `S01_NORMAL_STATIC` and `S14_EMERGENCY_STOP`; S01-S15 are not dynamically loaded from `scenario_registry()`.
- The current simulation form only exposes backend, scenario, mode, seed, and repetitions. It does not expose latency, jitter, packet loss, bandwidth, cache policy, retry budget, supervision period, timeout, domain randomization, output profile, or fault profile editing.
- The current frontend has no unified simulation tool namespace under `dashboard/src/simulation/`.
- There is no `SimulationCapabilityService`, `ScenarioCatalogService`, `ExperimentSubmissionService`, `RunMonitorService`, `MetricsService`, `ComparisonService`, `ReproductionService`, or `ExportService`.
- There is no immutable `ExperimentConfigBuilder`, `SweepPlanBuilder`, `BatchPlanBuilder`, `ComparisonQueryBuilder`, or `ReportDefinitionBuilder`.
- There is no preset repository for saving, cloning, importing, exporting, or creating experiment presets from historical runs.
- Large JSONL and metric aggregation are not isolated from the browser main thread.

## Experiment Design Gaps

- Batch execution is not exposed in the dashboard.
- Sweep execution is not exposed in the dashboard.
- Multi-seed design is not exposed in the dashboard.
- Mode comparison across `PCSC`, `ETEAC`, and `AUTO` is not available as a first-class workflow.
- Backend paired runs are not available as a first-class workflow.
- Backends are not presented with readiness, supported modes, supported run types, export formats, blockers, and limits from a simulation capability API.
- Scenario cards do not show category, fault type, trigger time, allowed/forbidden result statuses, expected invariants, maximum virtual duration, or backend support.

## Runtime Monitoring Gaps

- The existing dashboard event stream supports replay and heartbeat, but there is no simulation-specific `RunMonitorService`.
- There is no multi-run status manager for `QUEUED`, `VALIDATING`, `STARTING`, `RUNNING`, `FINALIZING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, and `BLOCKED_BY_ENV`.
- There is no sequence-gap detection, event deduplication, reconnect handling, polling fallback integration, or stale run detection in the simulation workbench layer.
- There is no unified event timeline assembler for experiment start, step transitions, fault injection, fault detection, network degradation, cloud calls, supervision ticks, local retry, recovery, replan, SafetyShield decisions, emergency stop, task completion, and artifact creation.

## Metrics And Analysis Gaps

- `dashboard/src/pages/ComparisonPage.tsx` displays a small table from existing dashboard comparison artifacts and does not use a Phase 11 comparison query model.
- There is no typed `SimulationMetric` frontend model with `name`, `value`, `unit`, `source`, `aggregation`, `sample_count`, `backend`, `scenario`, `seed`, and `control_mode`.
- There is no chart layer for completion time, success rate, cloud calls, communication count, retry/replan counts, virtual-time timeline, latency sensitivity, recovery distribution, seed box plots, backend paired deltas, SafetyShield timelines, or mode transitions.
- There is no paired comparison validation requiring matching scenario, seed, mode, network profile, and paired key.
- There is no explicit handling that Mock, MuJoCo, Isaac, and MoveIt dry-run results are distinct evidence classes.

## Reproducibility And Export Gaps

- Historical artifacts are not converted into a normalized reproduction request in the dashboard.
- There is no frontend `ReproductionService` validating source commit, source tree hash, config hash, environment hash, backend, scenario, seed, and control mode.
- There is no export service for manifest JSON, metrics CSV, events JSONL, comparison CSV, chart PNG/SVG, Markdown reports, paper-table CSV, or reproducibility bundle manifests.
- Export redaction is not centralized for local absolute paths, usernames, tokens, credentials, and controller configuration.

## Backend API Gaps

- There is no `/api/v1/simulation` FastAPI router.
- There are no Phase 11 API endpoints for capabilities, scenarios, parameter schema, validation, runs, events, metrics, artifacts, cancellation, clone, reproduction, batches, comparisons, exports, or simulation stream.
- The OpenAPI schema currently covers dashboard routes but does not expose the Phase 11 simulation workbench contract.
- Existing dashboard jobs are Phase 10 console jobs. They are not a Phase 11 run manager with manifests, per-run evidence, batch progress, paired comparison, export, and reproduction semantics.

## Safety Boundary Gaps

- The existing pages do not yet communicate that Phase 11 is simulation-only and that real robot development is frozen.
- No Phase 11 verifier exists to prove `real_controller_contacted=false`, `hardware_motion_observed=false`, and no hardware route additions.
- No Phase 11 frontend checks currently prove that browser code cannot directly connect to MuJoCo, Isaac, ROS, MoveIt, or a robot controller.

## Required Phase 11 Closure Work

- Add a simulation workbench backend router backed by `scenario_registry()` and `ExperimentConfig`.
- Add safe allowlist runner support for Mock, MuJoCo, Phase 8 batch/sweep, Phase 9 MuJoCo benchmark, Isaac benchmark, and cross-backend paired comparisons without arbitrary shell, executable, script, path, environment, or controller access.
- Add the `dashboard/src/simulation/` toolkit and migrate the simulation and comparison pages to use it.
- Add backend tests, frontend unit tests, and at least 15 Playwright tests against real FastAPI.
- Add Phase 11 docs, verifier, and verification artifacts under `artifacts/phase11/verification/`.
