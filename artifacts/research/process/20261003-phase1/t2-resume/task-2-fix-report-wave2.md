# T2 fix report addendum — review wave 2

Status: both P2 findings in `task-2-review.md` are fixed and pass focused RED/GREEN verification. The complete four-file T2 acceptance run now passes 42 tests. This separate addendum preserves reports currently maintained by the concurrent P1 documentation writer. No commits or staging were performed.

## Changes and root causes

Only `src/cloud_edge_robot_arm/simulation/mujoco/camera.py` and `tests/test_rgbd_capture_session.py` changed in this wave, alongside these new evidence files. The receiving-code-review skill was read and applied with the existing systematic-debugging / TDD workflow.

1. **Framebuffer provisioning.** Installed `mujoco/renderer.py` checks requested dimensions against `model.vis.global_.offwidth/offheight` before creating a GL context. The default scene's 640×480 buffer rejected an accepted 1280×720 camera. The camera constructor now increases each offscreen dimension to `max(existing, requested)` before its single renderer allocation. A real 1280×720 RGB/depth/instance capture verifies full payload dimensions and equal state hashes across all three passes. A second regression explicitly provides a 960×600 buffer for a 320×240 camera and verifies it remains unchanged. The existing renderer-reuse/cleanup test continues to pass.
2. **Depth-conversion calibration.** Installed renderer depth conversion reads `model.vis.map.znear`, `model.vis.map.zfar` and `model.stat.extent` after rendering the prepared scene. Mutating each by 10% after the RGB pass previously returned an observation without rejecting the mismatch. Capture now snapshots all three at its start and checks them with camera pose/FOV after scene preparation, after each render pass and before finalization. The three real-render mutation regressions now reject with the existing calibration error and confirm camera cleanup.

## Commands and evidence

Commands ran from `/home/ningyd/文档/ChatGPT/BIGsmall` after the parent explicitly transferred rendering ownership. Every command below was executed with `set -o pipefail` and `2>&1 | tee artifacts/research/process/20261003-phase1/t2-resume/<log>`. GPU ownership returned immediately after the final acceptance and Ruff checks; no full suite was started by this agent.

| Stage | Exact command before redirection | Result | Log |
|---|---|---|---|
| RED, both review findings | `MUJOCO_GL=egl .venv/bin/python -m pytest -q --tb=short tests/test_rgbd_capture_session.py -k 'maximum_resolution or larger_offscreen_framebuffer or znear or zfar or extent'` | Exit 1; 4 failed, 1 passed, 9 deselected, 1 warning | `red-camera-review-wave2.log` |
| GREEN, framebuffer | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_capture_session.py -k 'maximum_resolution or larger_offscreen_framebuffer'` | Exit 0; 2 passed, 12 deselected | `green-camera-framebuffer-wave2.log` |
| GREEN, depth calibration | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_capture_session.py -k 'znear or zfar or extent'` | Exit 0; 3 passed, 11 deselected | `green-camera-depth-calibration-wave2.log` |
| Combined T2 acceptance | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py` | Exit 0; 42 passed in 2.09 s | `green-t2-acceptance-wave2.log` |
| Scoped Ruff | `.venv/bin/python -m ruff check src/cloud_edge_robot_arm/simulation/mujoco/camera.py tests/test_rgbd_capture_session.py` | Exit 0; All checks passed | `green-camera-lint-wave2.log` |

The RED failures were the expected 1280-vs-640 framebuffer exception and three missing calibration rejections. The larger-buffer preservation case passed before implementation and protects against shrinking configuration while repairing the maximum-size case. The RED run also exposed an upstream `Renderer.__del__` warning because the rejected constructor had not assigned `_gl_context`. This warning disappeared after provisioning prevented that constructor failure; every GREEN run above is warning-free.

## Limits and handoff

These fixes extend the existing single-owner capture contract. They do not add thread synchronization or claim to detect a mutation restored entirely between checks. The parent owns broader regression results and full-suite status; this addendum claims only the checks above. Real rendering is verified at the maximum supported resolution, but no model execution, physical task success, real robot experiment or formal research result is implied.
