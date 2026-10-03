# T6a shared schema, persistence and offline replay

Implemented files: `src/cloud_edge_robot_arm/datasets/__init__.py`, `datasets/rgbd/{__init__,models,writer}.py`, `vision/offline_reader.py`, and `tests/test_rgbd_dataset_integrity.py`. No commits or staging. Source frozen at the root agent's review request.

The shared `rgbd.dataset.v1` models reject unknown fields, unsafe IDs/paths, non-finite or reversed ranges and out-of-budget counts. Scene content identity excludes seed and opaque group ID; physical grouping excludes camera, light and depth corruption variants. Runtime captured frames and dataset root bindings never enter serialized records.

Each episode is built under `.staging`, file-flushed, checked through the offline reader, and renamed atomically under `episodes`. `COMMIT.json` checksums the episode record index. The root `samples.jsonl` index is atomically replaced and reconstructible from verified committed episodes. Recovery accepts a missing or stale subset index, but rejects changed indexed rows, duplicate sample identities, incompatible configs/manifests, altered checksums, path traversal and symlinks. Same-ID publication must have identical serialized content. Actual disk errors and projected byte/free-space budget exhaustion leave no new committed episode.

Payloads are RGB/depth-visualization PNG, little-endian float32 depth NPY, uint8 valid-mask NPY, int32 semantic-instance NPY, plain camera/scene JSON and per-sample labels JSONL. Arrays are validated through their headers before allocation; object/pickle, wrong dtype, wrong dimensions and wrong byte count are rejected. Offline reconstruction preserves original acquisition timestamp, frame/episode identity, calibration and RGB-D checksum. Content hashes exclude acquisition identity/time while file checksums include metadata.

Raw evidence is required for nonzero scene depth corruption. Its five additional paths are `raw_rgb`, `raw_depth`, `raw_valid_mask`, `raw_camera`, `raw_state`. The raw physics/pass hash chain must equal the main frame's state, and reconstructed raw/main observations may differ only in depth, valid mask and resulting checksum. The `raw_captured_frame` argument to `SampleRecord.from_capture` is runtime-only.

Validation evidence:

- `storage-models-red.log`: 8 expected failures for absent schema; `storage-models-green.log`: 8 passed.
- `storage-persistence-red.log`: 15 expected storage failures, 13 passed; `storage-persistence-green.log`: 28 passed.
- `storage-boundaries-red.log`: 2 expected failures, 29 passed (unsafe header allocation and inconsistent positivity); `storage-boundaries-green.log`: 31 passed.
- `storage-budgets-red.log`: 2 expected failures, 31 passed.
- `storage-raw-linkage-red.log`: 8 expected failures, 33 passed.
- Final `storage-final-green.log`: **41 passed in 2.88 seconds** using `.venv/bin/python -m pytest -q tests/test_rgbd_dataset_integrity.py`.
- `storage-ruff.log`: all checks passed for owned Python files.
- `storage-mypy.log`: no issues in the three owned source modules (`--follow-imports=silent`); only pre-existing unused-override notes.

Verification limitation: I mistakenly included `tests/test_rgbd_observations.py` in an expanded run before inspecting its renderer requirements. That process aborted in `test_default_camera_has_visible_target_surface` during renderer construction. It also displayed one earlier failure at the position of `test_mujoco_camera_produces_registered_rgb_and_metric_depth`; the fatal abort prevented its failure traceback. `storage-observation-regression.log` preserves this unsuccessful run. Root was informed immediately and owns all rendered/full-suite regressions; this report claims only the 41 owned CPU integrity tests, not a passing broader suite or GPU acceptance.

Operational limits: one writer per dataset is the supported contract; `total_bytes` scans actual logical file sizes and has not yet been optimized. The 100/1000 group acceptance runs, generation resources and CLI end-to-end results belong to root integration, not this storage report.
