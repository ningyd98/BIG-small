# RGB-D Direct Input Implementation Plan

> 原型历史计划。后续开发由 [代理开发执行计划](2026-10-03-rgbd-evidence-research-roadmap.md) 统筹，输入与数据细节参见 [MuJoCo 数据计划](2026-10-03-rgbd-mujoco-dataset.md)。本文不代表原型已通过完整验收。

> **For agentic workers:** Use superpowers:executing-plans to implement this plan in the current session. Steps use checkbox syntax for tracking.

**Goal:** Make camera RGB and registered metric depth the project's default model input.

**Architecture:** Validate and preserve RGB-D observations, render physical simulator cameras, request multimodal decisions and ground them with depth. Route default API/workbench jobs through this pipeline and preserve explicit legacy software tests.

**Tech Stack:** Python 3.12, Pydantic, MuJoCo, Pillow, NumPy, FastAPI, Ollama-compatible HTTP, React/TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-03-rgbd-direct-input-design.md`

## Global Constraints

- Simulation-only; no real hardware writes or paid inference without existing authorization.
- Default vision model: `qwen3-vl:4b-instruct`; loopback Ollama endpoint.
- Aligned depth is little-endian float32 optical-axis depth in metres.
- Preserve unrelated user changes in `docs/README.md`, Chinese documents and `output/`.
- No silent text/Mock fallback for RGB-D requests.

## Review Focus

- Malformed/oversized image and depth payloads must fail validation before allocation or model calls.
- Camera pose conventions and pixel coordinates must yield calibrated world points.
- Missing/stale/invalid depth at model-selected pixels must not invent geometry.
- Missing model/camera services must block, without claiming task success or completing canned motion.
- Evidence and manifests must identify RGB-D planning separately from legacy and real task execution.

### Task 1: Observation contract and simulator camera

**Files:** Create `src/cloud_edge_robot_arm/vision/observations.py`, `src/cloud_edge_robot_arm/simulation/mujoco/camera.py`; modify simulation models/config/backend and scene XML; test `tests/test_rgbd_observations.py`.

**Interfaces:** Produce `RGBDObservation`, `observation_from_sensor_frame(frame)`, `world_point(pixel)`, and registered camera fields in `SensorFrame`.

- [ ] Write tests for actual RGB/depth rendering, calibrated back-projection and malformed payload rejection.
- [ ] Run tests and observe missing feature failures.
- [ ] Implement bounded RGB-D validation/encoding and MuJoCo rendering; remove synthetic detections from rendered frames.
- [ ] Run observation tests and existing MuJoCo physics tests.

### Task 2: Multimodal decision and planning API

**Files:** Create `vision/planner.py`, `vision/capture.py`, `cloud/api/vision.py`; modify planning models/pipeline/API schemas and app entry points; test `tests/test_rgbd_planning.py`.

**Interfaces:** Consume Task 1 observations; produce a grounded `PlannerDraft` and default vision pipeline. Model output selects target/destination pixels and high-level skills.

- [ ] Write HTTP boundary tests proving that both images are sent and depth changes world geometry; test missing/stale frames and invalid model decisions.
- [ ] Observe failures, implement image-bearing requests, grounding and API capture/planning.
- [ ] Run new planning tests and historical planning regression tests.

### Task 3: Default workbench, model control and experiment evidence

**Files:** Modify runtime worker, experiment draft, model-control dry-run, LLM-only real-provider runner/providers, dashboard defaults/generated schema; add `scripts/run_rgbd_smoke.py`; test `tests/test_rgbd_runtime.py`.

**Interfaces:** Consume RGB-D planning pipeline; default `input_mode=RGBD`, explicit `LEGACY_PIPELINE` for historical software trials. Persist paired observation and model/contract evidence.

- [ ] Write rejection/no-fallback tests and default-workbench behavior tests, observe failures.
- [ ] Implement default RGB-D routing and planning-only evidence; retain explicit historical tests.
- [ ] Run runtime/provider regressions, frontend tests/typecheck/build and actual-rendering smoke.

### Task 4: Isaac transport, documentation and verification

**Files:** Modify Isaac backend and standalone sensor protocol; add transport tests; update README, RGB-D setup docs and config examples.

**Interfaces:** Isaac transports paired raw image/depth and calibrated camera metadata into Task 1 observations.

- [ ] Write transport tests for actual paired payloads and missing imagery rejection, observe failures.
- [ ] Implement data transport and update run instructions/acceptance boundaries.
- [ ] Run Ruff, mypy, project pytest suite, frontend checks and a local VLM smoke if the runtime is available.
- [ ] Obtain an independent final code review and address material findings.
