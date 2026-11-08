# Independent review — actual gpt-6-astra

Review completed at HEAD `e24407690d1f3efcfeec7a0777f3622f1e5d613c`, using static reads only.

**Important — [P2] Calibration trust extends beyond the verified default capture.**
`src/cloud_edge_robot_arm/model_control/service.py:505–515,539`

The default XML hash check proves only that the repository's default asset is unchanged. `visual_planner()` also supplies the adapter for arbitrary observations accepted by `/api/v1/plans` (`cloud/api/app.py:199`). A frame captured from a custom MuJoCo model with different gripper geometry still has `source="mujoco_camera"`; the downstream gate checks only that source and the registered profile (`vision/planner.py:554`). With this change, such a frame receives v2 calibrated grounding despite having no connection to the checked asset. Previously, the active-profile adapter rejected it as unconfigured.

Restrict automatic calibration to the trusted default-capture path, or establish and verify provenance for the actual observation/model before selecting v2. Add a CPU regression covering a custom MuJoCo observation while the repository default XML remains unchanged. This requires a new Astra scope assessment; I made no repairs.

**Minor — [P3] Reproduction classification omits two planned predicates.**
`artifacts/research/process/20261004-ced-development/astra-rounds/round486-sol-saved-session-continuation-20261108/execution/run_once.py:158–163`

`LIVE_SAFE_REJECTION_REPRODUCED` checks source and dimensions but omits `scene_id == "S01_NORMAL_STATIC"` and `sim_time_s == 0`, required by Task A5. A different-scene or advanced-time response could be mislabeled. The actual preserved result is `PAID_GATE_BLOCKED`, so this does not invalidate that execution. Preserve the historical script and receipt; document the limitation before any separately planned reuse.

Other reviewed behavior is consistent with the stated intent: normalized image mapping, real adapter/geometry assertions, asset failures before transport, real/Isaac-source rejection for the tested frame size, profile snapshot separation, unchanged no-active/legacy paths, no request retry, unknown cost accounting, and timeout lock retention without claiming server cancellation.

Behaviors considered but not judged:

- Fresh test execution: prohibited by this review assignment; supplied pass counts were not independently rerun.
- Live fixed-generation behavior and renderer closure: no runtime inspection or execution permitted; no success claim warranted.
- R469 formal acceptance, deployment, and remote delivery: outside this scoped code review.
- The existing sub-64-pixel calibration bypass: unchanged generic planner behavior, outside this diff.

Readiness: not ready for scoped product commit until the Important trust-scope finding is resolved or rebutted with a concrete caller invariant.
