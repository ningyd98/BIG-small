# Independent colored-rim v2 review — PASS for bounded software scope

Reviewed 2026-10-04. No Important correctness finding was reproduced within the released builder/asset scope. This verdict concerns the deterministic portable visual asset, CPU equivalence and archived static RGBD replay. It does not admit an object association, motion bound, native action or physical task.

## Immutable setup

The released `source-hashes.json` SHA256 is `19cb8aa56a2ac8b3ea1fad8fe178ec6ad2d7e5072d13520eb46c5b27513d5f77`, containing **17 files: 3 owned and 14 read-only references**. All hashes and Python AST parses passed. The review overlay `/tmp/pose-marker-color-independent-waza3u7b` begins with the complete root-reviewed 768-file final T8/resource software closure (`db5ab161b94d4ee1c49b3f527cd4203b99475781d6cd2023148600f60bee2b22`) and overwrites the exact 17 review files. Saved v1/v2 replay observations and diagnostics were separately copied and hashed; their 33-file inventory is recorded in `independent-review-setup.json`. The declared v2 `raw-hashes.json` entries all match.

The first scoped run had 76 passing tests and one missing archived-v1 observation fixture in the disposable overlay. That setup-only failure is preserved in `independent-tests-missing-fixture.log`; the missing raw inputs were copied and hashed without source changes. The corrected run imports frozen source dependencies and uses only copied saved observations. No new capture, renderer regression, GPU, model or controller action was run.

## Verified behavior

The builder calls the immutable v1 generator, which rejects any base bytes outside the exact registered original SHA. It rescales only the 36 newly added ID7 cells to45mm and quiet area to60mm, preserving a5mm red rim on the70mm original object. All new geometry retains zero mass/density and no contact flags. Existing body, camera, geometry and controller attributes are preserved. CPU tests compare compiled physical arrays and20 passive step states; these checks are asset equivalence evidence, not task success.

Independent probes additionally confirm that the checked-in colored XML equals the deterministic builder bytes, all47 original named element attribute maps are unchanged, and three nonexact bases (including whitespace-only byte drift) reject. A saved native640×480 observation decodes ID7 while an ID8 registration remains UNKNOWN. Geometric and angular velocity bounds remain null and stability UNKNOWN. The RGB-only replay reproduces total observed red150, nominal rim red124 and marker-neighborhood red130. Polygon rasterization selects an ROI; it never fills or modifies the color mask. Instance and simulator pose are absent from those online detector/color inputs.

## Exact checks

```sh
PYTHONPATH=src:. /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -q tests/test_pose_marker_assets.py tests/test_pose_marker_evidence.py tests/test_rgbd_top_grasp.py tests/test_rgbd_observations.py -k 'not mujoco_camera_produces_registered_rgb_and_metric_depth and not default_camera_has_visible_target_surface'
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/pose_marker_assets.py tests/test_pose_marker_assets.py
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m mypy --follow-imports=silent --no-incremental src/cloud_edge_robot_arm/vision/pose_marker_assets.py
```

**77 passed, 2 existing renderer tests deselected in0.89s**; scoped Ruff2 passed; native mypy1 passed (only existing unused optional module notes). `independent-probes.py/.log` preserves the additional exact-asset/base/bounds checks. `independent-color-replay.log` preserves the archived color replay. `independent-post-test-hashes.json` confirms all17 source/overlay hashes and all33 copied raw/archive hashes still match after checks. No production files were edited by this reviewer.

## Acceptance limits

The saved single-frame offline truth errors are diagnostic and provide no calibrated interval coverage. A centered marker/70mm face ROI assumption and red pixels near it do not prove the whole requested object, exclude a decoy/occluded ring, or establish target-region semantics. Static endpoints cannot certify continuous angular motion. Existing native and LOCAL_RECOVER gates remain unchanged. The asset/marker/frame/calibration binding, reviewed whole-object association, calibrated sensor error and continuous-motion source are still future prerequisites. Consequently no physical success or new runtime capability is claimed.
