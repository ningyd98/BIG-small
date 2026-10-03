# T6a storage cross-review and repair

Date: 2026-10-03. Scope: `datasets/rgbd/models.py`, `writer.py`, `vision/offline_reader.py`, and their CPU integrity tests. Root subsequently authorized this reviewer to repair `writer.py`, `offline_reader.py`, and `test_rgbd_dataset_integrity.py` exclusively. No renderer/GPU work, model services, commits or staging were performed.

## Findings and disposition

### P2: incomplete synchronized-pass evidence accepted — CLOSED

Before repair, `DatasetWriter._prepare` checked mismatching pass hashes with `any(...)`, so an empty main pass list passed. Raw evidence rejected empty lists but accepted one, two or four matching hashes. The main pass list was also lost after publication, preventing replay from inspecting it independently.

CPU reproduction: replacing the existing storage fixture frame's `pass_state_hashes` with `()` allowed episode publication and `load_offline_observation` to succeed (`EMPTY_MAIN_PASS_HASHES_ACCEPTED 1`).

Repair: the writer now requires exactly three matching main/raw hashes and a nonblank indexed state hash. Every main sample includes a checksummed `state.json`; the reader independently validates its hash and pass list. The raw state file uses the same replay validation. New tests cover empty/short/long pass lists, blank state hashes, persisted main proof and a modified state file whose declared file checksum has been refreshed.

### P2: unrelated depth visualization accepted — CLOSED

Before repair, the reader only checked PNG dimensions. Replacing a fixture's depth visualization with a solid-magenta RGB PNG and updating its declared file checksum was accepted (`UNRELATED_DEPTH_VISUALIZATION_ACCEPTED`). SFT export consumes that persisted visualization, so this could produce a second image inconsistent with metric depth in an otherwise coherent package.

Repair: the reader requires the grayscale pixel values to match those derived from the metric depth. PNG compression differences are irrelevant because decoded pixels are compared. All-invalid depth remains a retained negative example with an all-black visualization. Tests reject both unrelated grayscale and RGB images, including when declared file hashes match.

## Other checks

- Episode payloads are fsynced under staging, validated, then atomically renamed; COMMIT hashes bind episode record indexes. Root indexes may be absent or a stale subset after interruption and are rebuilt from verified commits. Changed indexed rows or committed payloads fail closed.
- The generator's separate CPU tests already cover cancellation and failure immediately after episode publication; recovery keeps the committed sample and consumed attempt.
- Raw and perturbed observations must share acquisition identity, RGB, calibration and state. Only depth/mask/checksum differences are accepted. Nonzero configured depth corruption requires raw evidence.
- Numeric headers, dimensions, byte counts and dtypes are checked before NumPy loading; pickle/object arrays are rejected.
- Relative paths are checked for ownership by episode/sample, traversal and symlink escape. All required files have checksums, and offline reconstruction preserves the original observation checksum and timestamp.
- The review did not find another blocking defect within these storage boundaries after the two repairs. The independent finalization-budget finding belongs to generator coordination and remains outside this storage conclusion.

## Verification

Baseline review command: `.venv/bin/python -m pytest -q tests/test_rgbd_dataset_integrity.py` — **41 passed in 3.06s**.

New regressions before repairs: [storage-review-red.log](storage-review-red.log) — **12 failed, 43 passed in 5.05s**. Failures covered missing pass cardinality/nonblank checks, absence of the main state file, and acceptance of unrelated depth visualization.

After repairs: [storage-review-green.log](storage-review-green.log) — **55 passed in 3.67s**, exit 0.

```text
.venv/bin/python -m ruff check src/cloud_edge_robot_arm/datasets/rgbd/writer.py src/cloud_edge_robot_arm/vision/offline_reader.py tests/test_rgbd_dataset_integrity.py
All checks passed!, exit 0

.venv/bin/python -m mypy --follow-imports=silent src/cloud_edge_robot_arm/datasets/rgbd/writer.py src/cloud_edge_robot_arm/vision/offline_reader.py
Success: no issues found in 2 source files, exit 0
Existing unused-override notes for ament_index_python/rclpy only.
```

These three files were declared frozen to root and the final reviewer after the checks. Earlier developmental pilot datasets lack the newly required main `state.json` and must not be reused as final accepted datasets. Root owns fresh real-render acceptance and the combined final regression.
