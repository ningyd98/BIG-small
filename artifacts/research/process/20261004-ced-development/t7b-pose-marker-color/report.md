# Colored-rim marker v2 review handoff

This bounded developmental refinement preserves the base v2 asset, immutable marker v1, physical camera and controller. The new portable asset has a 45 mm ID7 tag, 60 mm white quiet area and a 5 mm rim of the original red 70 mm cube. The fresh excluded S01 640×480 frame decoded ID7 at native resolution and retained observed red pixels. It does not establish native whole-object association, calibrated error coverage, continuous motion bounds or physical task success.

## Ownership and freeze

Only three new files are owned: `src/cloud_edge_robot_arm/vision/pose_marker_assets.py`, `tests/test_pose_marker_assets.py`, and `assets/robots/franka_panda/scene_pose_marker_color_v2.xml`. The builder exports `build_colored_pose_marker_xml(base_xml: bytes) -> bytes` and constants `COLOR_MARKER_SIZE_M=.045`, `COLOR_QUIET_EXTENT_M=.060`, `COLOR_RIM_WIDTH_M=.005`. It reuses the immutable v1 generation dependency, which requires the exact frozen base SHA; no external textures or existing production edits are involved.

The research runner captured the pre-v2 final T8/resource fix2 dependency snapshot before new source writes: 768 files, manifest `8b5b3f58dd5b21fdb5052341d88504fa09037e1d59f86df76362c0bac43883b0`. The v1 14-file manifest remains unchanged. This package freezes three owned files plus 14 read-only references in `source/`; `source-hashes.json` SHA256 is `19cb8aa56a2ac8b3ea1fad8fe178ec6ad2d7e5072d13520eb46c5b27513d5f77`. `ownership.json` names the exact scope and `review-package.diff` contains only the three new files. No more writes to these source/test/asset files are planned during review.

Owned hashes:

- Builder: `b1e1be9ea6bae24c43f0eeb5aadbc200444b6126a2993329080ea7c42d142a62`.
- Test: `5b080341b80f8819013064d3945182cf11577dbf9368d5f5601c5fc909c74efc`.
- Colored asset: `2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4`.
- Unchanged base asset: `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`.

## Scoped software verification

`red-initial.log` preserves three qualified absent-module failures before implementation. `green-initial.log` records three passing tests after implementation. A fourth test replays the genuine saved 640×480 observation; it verifies native ID7 decode and actual red pixels, with bounds unavailable and stability UNKNOWN.

The tests verify deterministic geometry and quiet/rim extents, original XML attributes unchanged, wrong-base rejection, zero-mass/no-contact additions, exact compiled physical arrays for the original body/joints/DOFs/actuators/camera/sites/contact geometries, and identical qpos/qvel after 20 passive steps. These are SOFTWARE_ONLY checks of asset equivalence and replay behavior, not physical success evidence. No controller/task action is executed by them.

Final command:

```text
.venv/bin/python -m pytest -q tests/test_pose_marker_assets.py tests/test_pose_marker_evidence.py tests/test_rgbd_top_grasp.py tests/test_rgbd_observations.py -k 'not mujoco_camera_produces_registered_rgb_and_metric_depth and not default_camera_has_visible_target_surface'
```

`green-final-after-style.log`: 77 passed, 2 existing renderer tests deselected, 0.91 s. `ruff-final.log`: both owned Python files pass. `mypy-final.log`: new builder module passes. No broad suite or additional rendering regression was run. Earlier style-check output is preserved; its test-only long-path line was corrected before the final checks.

## Actual excluded developmental capture

Root authorized and was notified before and after the single serial EGL capture. `capture_actual_640.py` and `actual-capture-640.log` preserve the procedure. S01 seed0 used reset and 120 passive settling steps with the same physical top camera position `(0.35,0,1.4)`, orientation, 50° field of view and controller. Counts are model requests 0, controller command records 0, task/robot actions 0. Actual native decoding succeeded, so the conditional 960×720 fallback was not used.

The fresh 640×480 frame has fx=fy `514.6816609222941`, cx=319.5, cy=239.5, calibration version `3a224602f7d34743`, and explicit profile `color-rim-v2-S01-native-640x480-development-only`. Its observation checksum is `98404f7842992664586ca2e620972ad61b8466fc0ffa57dfe3417e1a21e4e156`; the marker registration hash is `a4972858b0d708c169229ca4bc4a514a229579eef6d106a560937541d3871e67`. Raw RGB, float depth, depth preview, validity mask, instance audit and full observation bytes/hashes are saved under `actual-capture-640/`. Detector inputs are registered expected ID/geometry plus actual RGBD only; instance IDs and simulator pose are not online inputs.

`assessment.json` reports OBSERVED with reason `uncalibrated_single_frame_pose_estimate`, ID7 and native minimum side 16 pixels. Geometric and angular velocity bounds are null, stability UNKNOWN, native evidence NOT_PROMOTED, physical success NOT_RUN. This is an actual renderer observation, not an executed grasp/recovery episode or physical acceptance result. Original v1 failed 320×240 raw evidence and logs remain untouched in the v1 process package.

`offline-truth-comparison.json` was written separately after detection. For this single static frame, marker-center error is 0.0002711844567712784 m and full rotation error is 0.0068663638618887725 rad; sensor noise standard deviation is 0.001 m. These offline errors do not provide calibrated coverage or interval guarantees.

## Observed red and remaining association gap

`actual-color-association.json` reports 150 observed red pixels, all in one largest component; 124 lie in the nominal rim ROI and 130 in the marker neighborhood. ROI coordinates use decoded corners and a registered centered-marker/70 mm cube-face assumption. HSV classification reads only actual RGB; ROI rasterization does not alter/fill the color mask. `measure_observed_color.py` replays the saved raw observation without simulator/instance/truth inputs; `observed-color-replay.log` and `actual-color-association-replay.json` reproduce the same diagnostic.

This is conditional observed color near a decoded marker. It does not prove the entire requested object, rule out a decoy/partial/occluded ring, certify its full extent or target-region relation, or supply the current native condition mapper. No tracker, capture, configuration, grasp profile, planner, future-action map or native admission gate was changed. Existing fail-closed behavior and LOCAL_RECOVER admission remain unchanged. Next integration requires a reviewed whole-object association source, current marker/asset/frame/calibration binding, calibrated pose/depth error coverage and continuous angular-motion evidence; endpoints alone cannot establish stability. No arbitrary color-hole filling is authorized or implemented.

The package is ready for scoped independent review. Actual action/execution/geometry acceptance remains unavailable; no new capability is enabled by this asset or saved observation.
