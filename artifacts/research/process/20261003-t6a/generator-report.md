# T6a generator and CLI implementation report

Date: 2026-10-03. Evidence level: SOFTWARE. No rendering, model service, large dataset generation, Git staging, or commits were performed by this worker.

## Delivered

- `src/cloud_edge_robot_arm/datasets/rgbd/generator.py`: one-process output lock; configuration/source/asset/dependency binding; bounded deterministic sampling; durable attempt journal; duplicate screening; original raw-frame preservation; cancellation and disk-failure handling; committed-episode recovery; split publication; validation before COMPLETE.
- Four CLI entry points: generate, validate, permitted-split grounding export, and timestamp-preserving offline replay. Generate returns 0 COMPLETE, 3 BLOCKED, 4 incomplete/failed, 130 cancelled; malformed configuration returns 2. Export denies the test split and export/replay cannot write inside the source dataset.
- Smoke/validation/full YAML configurations specify 100/1000/10000 groups with different seeds. The full configuration is explicitly T6b and was not run.
- `tests/test_rgbd_dataset_generation.py`: CPU fixtures replace only scene capture boundaries; storage, payload verification, splitting, validation, export and replay use production implementations.

## Verification

Initial red run: four CLI help tests failed because entry files did not exist; nine generator fixtures failed at setup because the generator module did not exist. After implementation, production quality checks rejected incomplete synthetic fixture labels; the fixtures were corrected to supply actual corrupted depth and corresponding geometry, without weakening quality validation.

A separate duration regression first failed with measured 0 rather than 7 seconds when final validation advanced the controlled clock. Final resource measurement now includes final validation.

Final commands and results:

```text
.venv/bin/python -m pytest -q tests/test_rgbd_dataset_generation.py
19 passed in 8.67s, exit 0

.venv/bin/python -m ruff check src/cloud_edge_robot_arm/datasets/rgbd/generator.py scripts/generate_rgbd_dataset.py scripts/validate_rgbd_dataset.py scripts/export_rgbd_training.py scripts/replay_rgbd_sample.py tests/test_rgbd_dataset_generation.py
All checks passed!, exit 0

.venv/bin/python -m mypy src/cloud_edge_robot_arm/datasets/rgbd/generator.py
Success: no issues found in 1 source file, exit 0
Existing note: unused mypy sections for ament_index_python/rclpy.
```

The 19 tests cover model/network-independent production, retained negatives, the five-times sampling cap across repeated resumes, cancellation, disk failure before and after atomic publication, disk reserve, unavailable renderer, source/config mismatch, journal ahead of manifest, missing/partial journal, complete-dataset revalidation and corruption rejection, rejected validation, inclusive wall time, all four CLI help paths, real persisted-data validate/export/replay and denial of test export.

## Measurement and remaining acceptance

Generation wall time includes validation and accumulates across invocations. Dataset bytes are measured before final manifest replacement, which is recorded explicitly. Process lifetime peak RSS is measured through `getrusage`; per-process GPU peak remains `NOT_MEASURED` with a reason. Root owns independent GPU sampling and the actual 100/1000 production runs.

The source was declared stable to root after the final checks. No subsequent implementation changes are planned during real acceptance. Full project/GPU tests were not run by this worker because root retains the shared renderer/GPU and final integration responsibility. No SOFTWARE fixture is evidence of physical execution success.
