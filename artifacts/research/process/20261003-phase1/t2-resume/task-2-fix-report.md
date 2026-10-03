# T2 acceptance fixes — 2026-10-03

Status: the assigned fixes pass their focused regressions and the four-file T2 acceptance run. The parent agent owns full-suite verification and the final persisted capture. Renderer ownership was returned after these checks. No commits or staging were performed; preexisting changes were preserved.

## Scope and investigation

Read the T2 brief, design §4.1, roadmap Global Constraints, and systematic-debugging / test-driven-development / verification-before-completion skills. Changed only these code/test files, plus this report and adjacent verification logs:

- `src/cloud_edge_robot_arm/vision/observations.py`
- `src/cloud_edge_robot_arm/simulation/mujoco/camera.py`
- `tests/test_rgbd_observations.py`
- `tests/test_rgbd_capture_session.py`

Root causes and fixes:

1. `observation_from_sensor_frame` used conversion time when acquisition time was absent. It now rejects `captured_at=None` explicitly. Old timezone-aware acquisition timestamps remain valid for conversion, JSON round trips and crops; they are never rewritten. `SensorFrame.captured_at` remains optional for non-RGBD consumers. Both current MuJoCo and Isaac RGBD producers supply timestamps. The online planner's separate 5000 ms age / 1000 ms future-time checks were untouched.
2. Pillow silently accepted excess RGB bytes. Width and height are now validated as integers in the existing 1–1280 / 1–720 bounds, RGB must contain exactly width × height × 3 bytes, and depth must contain exactly width × height values, all before image encoding or depth packing. Regression tests cover short/excess RGB and depth and malformed dimensions; the encoder sentinel verifies malformed input is rejected before allocation/encoding.
3. MuJoCo sampled wall time after rendering. Capture now records its timestamp at the start. A real-render regression advances a controlled wall clock by two seconds per pass and proves the output retains the initial timestamp, with six seconds of observation age after three passes. The controlled clock is a unit-test device, not a measured six-second hardware latency claim.
4. Additional audit concern reproduced: `cam_xpos`, `cam_xmat` and `cam_fovy` could change after RGB rendering without changing the existing physics hash. All three cases previously emitted an observation instead of rejecting it. Severity: high for geometry integrity, because a valid-looking calibration can back-project pixels from a different camera configuration. The tests mutate translation by 0.1 m, apply a valid 180-degree rotation, or change vertical field of view by one degree while leaving qpos/qvel/act/ctrl/time unchanged. Capture now copies calibration at its start, checks it after scene preparation and each render pass and before finalization, and derives final intrinsics/extrinsics from the copies. Calibration mutation raises `RuntimeError` and context cleanup closes the camera.

## Commands and evidence

All commands ran from `/home/ningyd/文档/ChatGPT/BIGsmall` with the repository `.venv`. Each logged command used `set -o pipefail` and `2>&1 | tee artifacts/research/process/20261003-phase1/t2-resume/<log>`; exit statuses below are pytest/Ruff statuses, not masked pipeline statuses. Real-render tests used EGL and did not overlap another agent's rendering.

| Stage | Exact test/check command before log redirection | Outcome | Log |
|---|---|---|---|
| RED, converter | `MUJOCO_GL=egl .venv/bin/python -m pytest -q --tb=short tests/test_rgbd_observations.py -k sensor_frame` | Exit 1; 12 failed, 2 passed, 11 deselected | `red-observation-boundaries.log` |
| RED, camera | `MUJOCO_GL=egl .venv/bin/python -m pytest -q --tb=short tests/test_rgbd_capture_session.py -k 'timestamp or calibration_change'` | Exit 1; 4 failed, 5 deselected | `red-camera-capture.log` |
| GREEN, acquisition time | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py -k acquisition_timestamp` | Exit 0; 2 passed, 23 deselected | `green-acquisition-timestamp.log` |
| GREEN, converter | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py -k sensor_frame` | Exit 0; 14 passed, 11 deselected | `green-observation-boundaries.log` |
| GREEN, camera time | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_capture_session.py -k timestamp` | Exit 0; 1 passed, 8 deselected | `green-camera-timestamp.log` |
| GREEN, calibration | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_capture_session.py -k calibration_change` | Exit 0; 3 passed, 6 deselected | `green-camera-calibration.log` |
| T2 acceptance | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py` | Exit 0; 37 passed in 1.32 s | `green-t2-acceptance.log` |
| Online stale gate | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_planning.py -k stale` | Exit 0; 1 passed, 3 deselected; one dependency deprecation warning | `green-online-freshness.log` |
| Scoped Ruff | `.venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/observations.py src/cloud_edge_robot_arm/simulation/mujoco/camera.py tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py` | Exit 0; All checks passed | `green-t2-fix-lint.log` |

The preliminary converter run used the same selection without `--tb=short` and produced 13 failures / 1 pass / 11 deselections. Its short-RGB case unnecessarily asserted a new error string; that assertion was simplified to rejection, since short RGB already failed in Pillow. The stable RED rerun above is the saved log and proves the actual missing behavior. The historical-timestamp and short-RGB cases passed before changes; they protect compatibility. Each production fix was applied after its RED evidence and checked separately. The final edit after acceptance only wrapped three long test lines for Ruff; the parent is rerunning the full suite on that final file state.

## Limits and remaining parent work

- The online-gate run emitted the existing Starlette warning about `anyio.abc.BlockingPortal`; no test failed. No dependency or unrelated source was changed.
- Calibration checks provide the same defensive consistency model as existing physics checks. They do not turn a camera session into a thread-safe shared object: an arbitrary mutate-and-restore entirely between checks is outside this narrow fix. The intended capture session remains single-owner; no backend concurrency redesign was introduced.
- The new timestamps conservatively include preparation/render latency. Offline observations remain parseable regardless of age; online freshness rejection remains a separate responsibility.
- This report establishes software/real-render acceptance evidence, not model availability, physical task success, formal research success, or hardware validation. The parent will run the broader suite, its selected type checks, and the final capture script, and record those outcomes separately.
