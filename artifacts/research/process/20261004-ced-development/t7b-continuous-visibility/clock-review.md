# Every-step camera acquisition: independent clock and observer review

Date: 2026-10-05. Scope: read-only source inspection for the proposed actual teacher acquisition. No renderer, physics step, provider, product edit, or test suite was run. This report does not establish native authority, calibration acceptance, or a continuous motion certificate.

**Finding:** the existing paused per-physics-step observer is usable for indexed, losslessly saved RGB-D observations. Keep the original `max_sample_gap_s=0.005`, camera, controller, full executed action ranges, and unavailable rows. Approximately 4,807 frames is a planning estimate; the required count must come from the actual reset/terminal step coverage. Every-step sampled visibility and motion can be observed; between-step and unseen future bounds remain `NOT_CERTIFIED`.

## Exact hook and association

- `MuJoCoPhysicsBackend.observe_physics_steps` (`backend.py:669`) supplies a detached `PhysicsStepObservation`. With `VisualRawRecorderV3` active, `step` (`:554`) applies control, records the original PHYSICS operation, then calls this observer before the next step. The raw PHYSICS END has already closed when the callback begins. Capture in this callback must have its own acquisition interval; it must not be presented as occurring inside the closed PHYSICS interval.
- This observer coexists with the recorder's separate, single operation-boundary observer (`backend.py:245`; `raw_recorder_v3.py:187`). The physics observer also has one slot, and reset clears it (`backend.py:520`). Attach after reset and compose with the existing teacher collection/poll callback rather than replacing it. Step zero needs an explicit paused baseline acquisition; the callback covers actual steps, not reset.
- Existing online collection (`vision/execution.py:2240`) appends the independent physical sample and calls `monitor_physics_state` (`:1662`), which checks cancellation/deadlines and polls supervision with `atomic_action_active=True`. Preserve that path if present. A physics-observer exception disables that observer and propagates out of the step, unlike an operation-observer error, which is retained without interrupting the operation. Keep the final executed step and failed acquisition in the denominator.
- Public backend capture enters the observed CAPTURE decorator and rejects observer re-entry (`backend.py:164`, `:740`). The proposed direct call is the existing `camera._capture(data, rng=..., noise_std_m=..., scene_id=..., episode_id=..., include_instances=False)` (`camera.py:75`), with the existing camera object. It does not run the backend CAPTURE boundary decorator, allocate a recorder acquisition, populate `RawFrameV3`, or add action joins. Publish these saved frames as a separately identified source stream linked to exact episode/physics/command/action rows; do not relabel them automatically as complete raw-v3 frame records or ONLINE input.
- `execute_attempt` (`raw_recorder_v3.py:704`) allocates before execution, retains original start/end steps and the half-open command range, and keeps partial/aborted attempts. Match saved frame step, simulation time, camera state hashes, and the latest actual raw PHYSICS row; retain action/purpose identity and resolve the complete action span after it closes. Do not shorten the horizon to the visible or successfully saved subset.

## Clocks and saved payload

`raw_recorder_v3.py:396` samples `monotonic_ns`, then UTC, then `monotonic_ns`; these are bounded clock-read pairs, not simultaneous clocks. Its descriptor (`:239`) records resolution but explicitly leaves `utc_uncertainty_ns=None`. The validator (`raw_episode_v3.py:1040`) checks source domain, non-overlapping clock order, and UTC offset consistency, while retaining `utc_mapping=UNAVAILABLE` without independently supported uncertainty. Copying clock reads into a new stream cannot manufacture that uncertainty or authentication.

Allocate and atomically publish BEGIN before acquisition, with exact source identities and monotonic/UTC pairs; close END only for the actual completed operation. Camera `captured_at` is sampled near the start of `_capture`, while `latency_ms` uses `perf_counter` (`camera.py:85`); neither alone is a complete acquisition bracket. Distinguish the capture interval from compression/persistence time. If END encloses both, label it capture-plus-persistence and retain a separate capture bracket. A crash, cancellation, write failure, unmatched BEGIN, or missing physical step stays unavailable, never zero motion or zero gap. Preserve both successful and failed row counts.

Save all original returned RGB bytes, depth values, validity mask, intrinsics, transform/calibration, frame/scene/episode IDs, capture timestamp, and render pass hashes without resizing, lossy image encoding, quantization, or depth rounding. Gzip is compatible with this requirement only when the serialized payload preserves those original values and its digest/length is verified on replay. Camera pass-state hashes and raw PHYSICS payload hashes have different representations; retain both and validate the association rather than equating the digests.

## Mutation and cadence limits

The camera checks `time`, `qpos`, `qvel`, `act`, and `ctrl` before/after RGB/depth passes, plus camera pose and calibration (`camera.py:67–162`). `include_instances=False` avoids a segmentation pass. These checks do not cover RNG state, controller targets, pending commands, model arrays, cached sensor frame, or all renderer state. The public observer guard (`backend.py:887`) blocks public mutating methods; private access is not a comprehensive immutability guarantee. Do not create a new camera in the callback, change model/controller fields, replace the cached frame, run decoding/control, or advance physics.

**Concrete mutation risk:** nonzero depth noise calls `rng.normal` (`camera.py:141`), consuming the shared backend RNG. The backend normally uses depth noise `0.001`, is seeded at reset, and later camera captures use the same RNG (`backend.py:512`, `:527`, `:758`, `:1136`). Extra teacher frames must not silently change later ONLINE sensor observations. If acquisition uses a detached RNG copy to preserve the original stream, pin and report that side-source noise sampling explicitly; do not claim an identical original noise sequence or alter the original noise setting to bypass the issue.

The evaluator's `_continuous` (`episode_evaluator.py:349`) requires consecutive physics steps and positive **simulation-time** gaps no larger than the immutable criterion's `0.005` seconds. Rendering, gzip, and disk writes pause progression but consume wall time. Thus every-step coverage can satisfy the existing simulation sampling control when the original timestep permits it; it does not imply a 5 ms wall-clock camera cadence. Preserve both gaps and do not divide simulation displacement by wall duration while labelling the result simulation speed, or translate simulation velocity fields into online wall-clock bounds.

Dense saved images permit offline measured marker/point observations and interval secants, with raw physical truth restricted to the original independent offline evaluation. A maximum over saved future samples must remain labelled **sampled future maximum**. Continuous target motion between samples, unseen future motion, clock uncertainty, estimator residual calibration, immutable calibration criteria, and native admission require separate evidence. This stream is source-backed acquisition/calibration input only.

## Inspected source fingerprints

SHA-256 at this review (no source copies made):

| Source | SHA-256 |
| --- | --- |
| `simulation/mujoco/backend.py` | `b7b6026b1173448de826e53253ae74f92b6b70ea46a404e10054c5cd451a62a6` |
| `simulation/mujoco/camera.py` | `d85aa6eda7c9f658f2e3bb550c44b3462ebd65e290d5c7d9b79fa30639136e2f` |
| `vision/raw_recorder_v3.py` | `4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303` |
| `research/raw_episode_v3.py` | `6aaeb0b482cab54d97468f28be281cb8f13788199d3140d9e0d0ddc0c8802096` |
| `simulation/mujoco/episode_evaluator.py` | `a0b5891a70752400dcf0dea0cbe837476114148000b9eb345c27fe468860af50` |
| `vision/execution.py` | `2770da01bfe1869622b104d763c6852b621158d7aaac4004a04fadfdf2a164de` |
| `research/pilot_worker.py` | `81dd1d02e4b264adba731eec07d6921042f933b795af4e68726e29f03b7ee3e2` |

Paths in this table are relative to `src/cloud_edge_robot_arm/`. The recorder pins its existing eight-source inventory (`raw_recorder_v3.py:54`); any new acquisition publisher and replay decoder need their own pinned source and payload identities. Existing pins alone do not cover newly written acquisition code.
