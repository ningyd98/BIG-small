# Phase 9.1.1 Runtime Acceptance Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Completed on 2026-06-16 after final Phase 9.1 verification.

**Goal:** Harden Phase 9.1 ROS 2 / MoveIt runtime acceptance so environment blocks cannot hide missing runtime evidence, and so artifacts contain auditable MoveIt collision, timeout, shutdown, and log-integrity evidence.

**Architecture:** Keep the existing verifier and runner entrypoints, but make their contracts stricter. Add explicit aggregation helpers in `scripts/verify_phase9_1.py`, stricter artifact-shape checks in `src/cloud_edge_robot_arm/simulation/phase9_1/verification.py`, and richer runtime evidence in the ROS 2 / MoveIt evidence runners.

**Tech Stack:** Python, pytest, ruff, mypy, ROS 2 Jazzy / rclpy, MoveIt 2 service APIs, JSON artifacts.

---

### Task 1: Acceptance Aggregation Gate

**Files:**
- Modify: `scripts/verify_phase9_1.py`
- Test: `tests/test_phase9_1_verifier_hardening.py`

- [x] Add table-driven tests for `ros2=INCOMPLETE`, `ros2=ROS2_READY`, `moveit=INCOMPLETE`, and `moveit=MOVEIT_READY` with Isaac blocked; each must return `PHASE9_1_REJECTED`.
- [x] Add positive tests for ROS 2 + MoveIt validated with Isaac/cross-backend blocked returning `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`, and all components/cross-backend validated returning `PHASE9_1_ACCEPTED`.
- [x] Extract status aggregation into a helper so tests can exercise the full decision without running ROS.
- [x] Implement strict component gates: ROS 2 accepts only `ROS2_INTEGRATION_VALIDATED` or true `BLOCKED_BY_ENV`; MoveIt accepts only `MOVEIT_SAFETY_VALIDATED` or true `BLOCKED_BY_ENV`; READY/INCOMPLETE/FAILED/unknown reject.

### Task 2: Runtime Artifact Integrity

**Files:**
- Modify: `src/cloud_edge_robot_arm/simulation/phase9_1/verification.py`
- Modify: `scripts/phase9/run_ros2_runtime_evidence.py`
- Modify: `scripts/phase9/run_moveit_safety_evidence.py`
- Test: `tests/test_phase9_1_runtime_evidence_contract.py`

- [x] Add tests showing logs with `Traceback`, `Segmentation fault`, `RCLError`, or `process exited unexpectedly` make runtime evidence incomplete.
- [x] Add tests that MoveIt collision evidence must include `baseline_plan`, `collision_object`, `planning_scene_confirmed`, `replanned_or_rejected`, `collision_free`, `trajectory_delta`, `moveit_error_code`, and process provenance.
- [x] Add tests that planning-timeout evidence must include normal-budget success, timeout budget result, wall-clock timings, configured timeout, and must not accept arbitrary non-success planning failures.
- [x] Implement shared log issue detection and runtime observed-result validators used by ROS 2 and MoveIt verification.

### Task 3: MoveIt Collision And Timeout Evidence

**Files:**
- Modify: `scripts/phase9/run_moveit_safety_evidence.py`

- [x] Generate a baseline plan for the same target before adding obstacles.
- [x] Insert a collision object near the baseline path and confirm it through the planning scene service/topic.
- [x] Replan the same target and classify the result as collision rejection or valid replanning.
- [x] For success, check trajectory collision-free status and compare trajectory point count, joint-space path length, and sample deltas against baseline.
- [x] For timeout, first prove the normal budget succeeds, then rerun the same target with an extremely short budget and record timing and MoveIt error semantics.

### Task 4: ROS 2 Shutdown Hygiene

**Files:**
- Modify: `ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/sim_bridge_node.py`
- Modify: `scripts/phase9/run_ros2_runtime_evidence.py`
- Modify: `scripts/phase9/run_moveit_safety_evidence.py`
- Test: `tests/test_phase9_1_runtime_evidence_contract.py`

- [x] Add a bridge shutdown API that stops accepting new goals before executor shutdown.
- [x] Destroy action servers explicitly before `rclpy.shutdown()`.
- [x] Stop child processes before destroying the parent evidence node, and tolerate expected shutdown exceptions without writing tracebacks.
- [x] Fail evidence completeness if non-whitelisted shutdown errors remain in logs.

### Task 5: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/phase9_1_acceptance.md`
- Modify: `docs/phase9_1_report.md`

- [x] Document that ROS 2 runtime and MoveIt 2 safety are validated, Isaac and cross-backend remain environment-blocked, and real robot validation is not started.
- [x] Add the exact Phase 9.1 runtime and aggregate verifier commands.
- [x] Run the final command suite: ruff format check, ruff check, mypy, pytest, Phase 9 verifier, ROS 2 verifier, MoveIt verifier, aggregate verifier.
- [x] Commit and push `fix: harden phase9.1 runtime acceptance evidence`.
