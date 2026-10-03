# T2 scoped re-review — 2026-10-03

Verdict: **approved for T2 scope**. Both P2 findings from `task-2-review.md` are resolved. No new issue was found in the fixes or their immediate interactions. This closes the earlier changes-requested verdict; it does not claim the broader regression run has completed.

## Findings closed

1. **Supported resolution versus framebuffer:** `src/cloud_edge_robot_arm/simulation/mujoco/camera.py:25–27` now expands each offscreen framebuffer dimension to `max(existing, requested)` before allocating the renderer. This permits the accepted 1280×720 configuration while preserving a larger preconfigured buffer. It adds no renderer allocation and leaves the existing reuse/release lifecycle intact. The new real-render test checks observation size, full depth/mask/instance payload lengths, and three equal pass hashes at 1280×720; another test protects larger-buffer preservation. The existing reuse/cleanup test remains in the passing acceptance suite.

2. **Depth-conversion calibration consistency:** `src/cloud_edge_robot_arm/simulation/mujoco/camera.py:91–104` now snapshots and checks `znear`, `zfar`, and `stat.extent` alongside camera pose and FOV. The existing guard executes after scene preparation, every render pass, and before finalization. A persistent mutation therefore rejects the capture before a mismatched observation is returned. The expanded real-render regression independently changes each field after RGB rendering, requires the calibration error, and checks context cleanup.

## Evidence inspected

Reviewed `wave2-diff.patch`, the current camera implementation and affected tests, `task-2-fix-report-wave2.md`, the RED/GREEN logs, final Ruff/mypy logs, and `final-capture/measurement.json`. The reviewer did not run duplicate tests or GPU work.

- RED evidence: 4 failures and 1 pass, covering the maximum-resolution failure and the three formerly missing calibration rejections; the preservation case already passed.
- Focused GREEN: framebuffer cases 2 passed; depth-calibration cases 3 passed.
- Complete T2 acceptance: 42 passed in 2.09 seconds.
- Final scoped Ruff: all checks passed. Final mypy: no issues in 7 source files; only the existing unused-section note.
- Fresh final capture: 100 plane samples, maximum absolute height error 0.0027281284332274502 m ≤ 0.005 m, three identical state hashes, and renderer-release evidence.

## Limits

At the last inspection, `final-regression.log` was still progressing without a summary. Broader regression completion belongs to the root's final verification report. The root also reported that the earlier full-suite attempt was interrupted after partial progress and that its Chinese-docstring failure was repaired separately; this re-review does not convert that attempt into a full-suite pass.

The single-owner concurrency limit and the original review's exclusions remain unchanged: arbitrary mutation-and-restoration entirely between checks, arbitrary-camera localization accuracy, model availability, physical task success, Isaac runtime validation, formal research results, and unrelated changes are outside this narrow re-review. No further issue was declined within the two requested fixes. Only this report was written; product files, git state, and concurrent P1 closeout documents were left untouched.
