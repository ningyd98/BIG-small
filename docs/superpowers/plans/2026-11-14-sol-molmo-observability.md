# Sol+Molmo observability implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this approved scope in this session.

**Goal:** Restore endpoint observation for the selected diagnostic asset, clarify simulation-only cloud requests, and apply genuinely different physical starting conditions.
**Architecture:** Extend the existing component worker, shared grounded planner and scenario reset; keep formal/native execution paths unchanged.
**Tech Stack:** Python 3.12, pytest, MuJoCo, OpenCV, existing Molmo BF16 and Sol profile.
**Spec:** docs/superpowers/specs/2026-11-14-sol-molmo-observability-design.md

## Global Constraints
- Preserve existing raw evidence, selected marker/camera/controller and resource/budget checks.
- Do not infer pose from physics truth online or promote unknown calibration/qualification.
- Preserve refusal, freshness, source binding, lease and safety checks.
- Real requests retain the already authorized api.openai.com destination and synthetic task/geometry payload scope.

## Review Focus
- A formal/default planner must never acquire simulation diagnostic authority.
- Empty cloud decisions, hidden/foreign markers and invalid geometry still stop.
- A seed label must change the actual physical starting state, not only metadata.
- Tampered or mismatched scene specifications must reject before execution.
- Diagnostic success cannot overwrite missing visibility or native qualification.

### Task 1: Endpoint observation
Files: research/sol_molmo_components.py; tests/test_sol_molmo_worker_integration.py.
- [x] Add an integration assertion that a successful baseline has a strictly decoded endpoint ID7.
- [x] Observe the current real-render test fail with known_marker_not_observed.
- [x] Apply a bounded -0.100 m y offset only to RETREAT for the selected component marker family; bind and audit the actual safety-checked step.
- [x] Run the integration checks including physical outcome and injected capture failure.

### Task 2: Explicit simulation context
Files: vision/grounded_planner.py; research/sol_molmo_single_episode.py; tests/test_molmo_grounded_planner.py.
Interface: optional component_diagnostic: bool = False on adapter/builder, explicit only with worker-owned refresh.
- [x] Test encoded simulation scope, unchanged development geometry qualification, default scope isolation and empty-decision refusal.
- [x] Observe failures before implementation.
- [x] Add the explicit component context to outbound requests and preserve fail-closed decisions.
- [x] Run existing and new planner/entry tests.

### Task 3: Physical scene variation
Files: new research/sol_molmo_scenarios.py; simulation/models.py; simulation/mujoco/backend.py; vision/molmo_worker.py; research/sol_molmo_single_episode.py; research/sol_molmo_components.py; scripts/run_sol_molmo_single_episode.py; tests/test_sol_molmo_scene_variation.py.
Interfaces: sample_component_scene(seed, split); physical_component_scenario(seed, scene); scene_split=None on the entry; object_yaw_rad=0.0 appended to PhysicalScenarioConfig.
- [x] Test deterministic distinct pose samples, split separation, bounds/tampering, real yaw reset, diagnostic-only admission and actual-state evidence.
- [x] Observe failures before implementation.
- [x] Apply exact seeded poses to physics, bind the scene to the role policy, archive actual initial state and expose --scene-split.
- [x] Run focused checks, lint/type checks and inspect final diff.
- [ ] Complete the whole-project regression: blocked by the documented legacy test timeouts/diagnostic crash; partial results are retained.
- [x] Run fresh-process neural/cloud follow-up with separate fixed/development/held-out accounting; verify evidence; commit and push only the requested source/tests/docs.

Global-regression limitation: the full 6,680-test collection did not complete. Six partitions completed 4,963 cases (4,900 passed, 57 failed, 6 skipped); two UTC-jump cases were terminated after extended replay and one resumed diagnostic process exited -11. Remaining cases are not counted as passing. Scoped implementation, real-model matrix and evidence verification are complete; whole-project green status is not claimed.
