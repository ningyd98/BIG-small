# RGB-D direct-input design

The user requires the current project to consume vision and depth directly, rather than simulate model perception from text descriptions. The default development API and workbench must use paired camera observations. Existing deterministic experiments remain explicit software/legacy evidence only.

## Input and geometry

An RGB-D observation contains an actual PNG color image, aligned optical-axis depth in little-endian float32 metres, acquisition time, simulation time, dimensions, pinhole intrinsics, and an optical-camera-to-world rigid transform. Invalid dimensions, encoding, calibration, missing imagery and stale observations are rejected. Model requests contain both RGB and a full-frame depth visualization with its metric legend; raw metric depth remains available for exact geometry. A VLM selects target/destination pixels and an ordered list of registered high-level skills. The server back-projects selected pixels using measured depth and calibration. Object positions and detections derived from simulator ground truth are not given to the VLM.

## Runtime

MuJoCo renders registered RGB and depth from a fixed camera. Isaac's process protocol transports actual image/depth arrays and calibration, rather than dropping them after capture. Unsupported or missing camera data block RGB-D runs. An observation capture API exposes simulated camera frames. A multimodal planner sends image messages to a local Ollama vision model (default `qwen3-vl:4b-instruct`) or an explicitly configured compatible service. Text-only/missing model capabilities do not fall back to Mock.

The server assembles the selected skills using existing high-level skill templates and validates the resulting TaskContract. This assembly is schema completion, not model perception. Existing safety, contract validation and simulation-only hardware boundaries remain in force. The default workbench produces RGB-D planning evidence; it must not call an unrelated canned joint trajectory or claim pick-and-place execution after planning alone. Legacy trajectories require explicit `LEGACY_PIPELINE` input mode.

## Evidence and acceptance

Persist color PNG, metric depth, depth visualization, calibration, hashes, model identity, image count, decision and validation outcome. Model absence produces `BLOCKED_BY_ENV`; rejected grounding produces failure, not success. Planning-only completion is labelled `PLANNING_ONLY`, with task execution not accepted. Historical fake baselines cannot establish visual performance. Verify real MuJoCo rendering, depth back-projection, image-bearing HTTP payloads, missing/stale/invalid frames, API defaults and workbench rejection paths. A live VLM result is accepted only after an actual local model call; unavailable model runtime is reported explicitly.
