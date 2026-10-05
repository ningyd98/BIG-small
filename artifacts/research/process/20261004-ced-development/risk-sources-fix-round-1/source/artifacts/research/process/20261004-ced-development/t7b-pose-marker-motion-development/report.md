# Single marked-v2 motion development episode

The one authorized NORMAL offline teacher episode completed the simulated transfer under the existing independent evaluator. Marker observability failed during the action sequence: the initial settled frame decoded ID7, while all nine post-action frames remained UNKNOWN. This negative visual result is preserved alongside the successful scoped simulator outcome; it does not admit native evidence or supply a continuous visual certificate.

## Exact scope and execution

No existing production/test/asset file was edited. The process-only script reused `run_teacher_episode`, `MuJoCoSkillRobot`, `MuJoCoMotionController`, physical/actuator observer APIs and `evaluate_episode`; it introduced no online executor. All frozen colored-v2 source17 and v1 sources remain unchanged. There was exactly one actual episode, no retry, fallback, controller tuning, target adjustment or additional capture.

`header.json` records the explicit SceneSpec, simulator configuration, asset, source hashes and excluded development identity. Group `dev-marker-motion-4ebb9f9b7c662d4b3c87ad8c`, scene hash `4ebb9f9b7c662d4b3c87ad8c81194fabcec4990519dfb9656837020b32d47921`, colored-v2 asset hash `2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4`, seed0, 70 mm red cube. Native 640×480, physical top camera position `(0.35,0,1.4)`/identity quaternion/fovy50 and controller remain the same. Existing offline scene application adds its standard inactive distractor slots and applies clean raw depth: sensor noise and invalid fraction are zero. This is explicitly distinct from the earlier standalone 1 mm-noise capture; no noise calibration equivalence is claimed.

`development-exclusion.json` binds this new group/asset/scene to development-only exclusion. It does not alter the existing frozen formal exclusion proof or automatically modify a future formal pool; a future source collector must honor this explicit exclusion.

## Script-only cadence ruling

Before execution, root inspected and authorized suppressing `backend._update_sensor_frame` only after `apply_scene`, for this one excluded process. The unchanged controller/grasp/release/state/dwell path uses physical state, and T5 uses `_dwell` rather than `robot.observe`. The script aborts on `robot.observe` or `backend.get_sensor_frame`, checks frozen controller source for cached sensor reads, and restores original update/get-sensor/camera methods in the episode finally block. No production source was changed. The initial prepared script/header/source snapshot is retained under `pre-cadence-baseline/`; both old and revised manifests contain 25 files (the earlier coordination note's count24 was a counting error).

Actual render call counts are one setup RGBD capture, ten explicit existing T5 boundary RGBD+instance capture calls, and 765 suppressed cached-update calls. Setup is counted separately from episode observations. This is intentionally different from original unsolicited controller-chunk render cadence; no renderer cadence or random-number-stream equivalence is claimed. There is no per-physics-step rendering.

Root received serial EGL START and END notices. `actual-run.log` is the complete one-run log; the 180 s wall wrapper was not reached. The run took about 5.90 s wall time and 20.0250001602 s simulation time, including 120 passive settling steps. Renderer ownership was released after completion.

## Actual actions and independent scoring

Episode ID `6ff8c12944d3466889f1b2129abca1b4`. Zero cloud/model calls; **743 actual controller command records**, **9 framed actions**, zero unframed actions, **4806 physics steps**, 4807 detached physical samples including initial step0, and 4806 applied-actuator samples. These are actual simulated controller/task actions, unlike the preceding zero-action static captures. Both OBSERVE action results are existing passive teacher dwell intervals, not calls to `robot.observe`.

The unchanged independent evaluator scored SUCCESS with lift 0.1038992081273 m, stable bilateral hold 0.7625000061 s, placed stable 2.1541666839 s, no listed safety events, safety assessment `SCOPED_NO_VIOLATION`. Its configured self-collision checked pairs are persisted in `summary.json`; this is scoped simulator scoring, not a comprehensive physical safety certificate. The script recomputed `evaluate_episode` before shutdown and the offline verifier separately reconstructed and rescored saved physical samples via `evaluate_evidence`, obtaining the same outcome. Action-return success was not used to override the score.

## Boundary visibility

The immutable detector received only each genuine RGBDObservation and ID7/45 mm/actual-asset registration. Simulator truth, instance labels and scorer outcome were never detector inputs. Bounds remained null and stability UNKNOWN for observed evidence; no UNKNOWN was filled or converted into an observed pose.

| Existing T5 boundary | Simulation time (s) | Decoder |
|---|---:|---|
| Initial settled | 0.5000 | OBSERVED, minimum side16 px |
| MOVE_ABOVE | 3.1042 | UNKNOWN |
| APPROACH | 5.3958 | UNKNOWN |
| GRASP | 6.3917 | UNKNOWN |
| LIFT | 9.2875 | UNKNOWN |
| Post-lift dwell | 9.7875 | UNKNOWN |
| MOVE_TO_REGION | 14.8083 | UNKNOWN |
| PLACE | 17.8292 | UNKNOWN |
| RELEASE | 18.8250 | UNKNOWN |
| Post-release dwell | 20.0250 | UNKNOWN |

All missing results report `known_marker_not_observed`; decode failure alone does not identify its cause. Inspection of saved RGB shows the hand/arm overlapping the top tag. A separate **offline-only** diagnostic projects the known simulator marker plane at the exact matching physical sample into the saved image and compares actual raw depth to expected plane depth. With a diagnostic 5 mm foreground threshold, foreground occupies 95–100% of nominal marker ROI pixels at the nine post-action boundaries, versus zero initially. This supports foreground occlusion in these saved frames, without calibrated occlusion error coverage or online association authority. Projection uses simulator truth only after decoder replay and writes only `offline-occlusion-diagnostic.json`; it is never fed back into the detector or an action gate.

This camera/tag placement therefore does not provide current marker observations through grasp/lift/hold/transfer/place/release. The transfer succeeds physically in this scoped simulator while visual verification remains unavailable. No continuous angular velocity/stability certificate, calibrated pose/depth error bound, G1/G4 acceptance, native admission, whole-object association or LOCAL_RECOVER capability is promoted.

## Raw layout and verification

`source/` and `source-hashes.json` freeze the 25 exact source/asset/test/script references used at run time; manifest SHA256 `ad45b2fa05e8eb92a782d0b6cd1f5ae5ec28f7e7d9c5a82c4be2add7af8ac1e2`. `attempt-1/` contains:

- `raw-physics.jsonl`: actual detached physical snapshot at step0 and every physics step.
- `raw-actuators.jsonl`: actual pre-step control targets, gravity bias, actuator gains/ranges and finger controls.
- `raw-actions.jsonl`: real teacher action results and step/command ranges; `commands.json`: actual backend command records.
- `physical-samples.json`, `actions.json`, `unframed-actions.json`, `summary.json`, `observability.json`.
- `frames/INITIAL_SETTLED` and nine `AFTER_*` directories: raw RGB PNG, float depth, validity mask, depth preview, payload-free metadata, full RGBD JSON and frozen decoder estimate. T5 captures instance passes for registration consistency but discards their instance payload; no instance evidence is fabricated here.
- `raw-hashes.json`: exact persisted-byte SHA256 manifest for the original run evidence.

`verify_offline.py` runs without MuJoCo simulation/rendering/network. `offline-verification.log` passes raw byte/source archive+live hashes, contiguous episode/physics/actuator/command/action identities, independent saved-sample scoring, and all ten strict decoder replays. The first diagnostic attempt used a nonexistent depth accessor and failed after reading saved data; exact script/log are retained as `verify_offline-first-failure.py` and `offline-verification-first-failure.log`. Only that offline accessor was corrected; no actual episode/capture was repeated. The final verifier decodes the existing depth_float32 bytes directly.

`final-check.log` verifies source/AST/raw identities, immutable prior package hashes and development exclusion binding; `artifact-hashes.json` binds the final report, scripts, sidecars and raw evidence. This handoff is ready for independent read-only review. Further observability changes or motion runs require a new assignment; the current single episode is complete and excluded from formal source pools.
