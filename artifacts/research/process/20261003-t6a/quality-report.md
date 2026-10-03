# T6a source grouping, quality validation, and grounding export

Implemented by the quality/split/export worker on 2026-10-03. Production files are frozen for the root-owned 100/1000-group acceptance runs. No GPU, model, external service, commit, or staging operation was performed by this worker.

## Delivered

- `splitter.py`: source group, episode, canonical physical/asset identity, full scene content, persisted content hash, and local RGB-D near-duplicate connected components. Source identity excludes random seed and observation variants (camera, lighting, depth noise, missing-depth fraction), independently of caller-provided group IDs. Connected components cannot cross roles. Seeded canonical hash ordering is insensitive to input iteration order. Largest-remainder quotas give exactly 80/5/5/10 independent groups for 100 groups. Duplicate-pair evidence records the reason and both sample IDs. Each role index is atomically replaced; the split audit is published last, so an interrupted mixed set fails validation.
- `quality.py`: restores registered observations through the strict reader; validates committed checksums, schema, original acquisition metadata, lossless numeric payloads, source/config/content hashes, complete indexes, semantic mask label counts/bboxes/depth fractions, valid instance pixels, metric surface backprojection, target/destination positive thresholds, object-center consistency, explicit research negative reasons/actions, and complete disjoint source-connected split coverage. Validity requires requested independent groups and all declared counts. Fully populated RUNNING may pass the generator's final gate with a warning; other unfinished/failure states remain invalid.
- `exporters.py`: runtime denial of test export; requires complete dataset validation; includes every retained selected-role example, with negatives represented by REQUEST_MORE_OBSERVATION. User content contains exactly an instruction and two opaque RGB/depth-visualization file paths. Grounding labels live in assistant content, while raw depth/calibration references live in top-level metadata. Export writes atomically and cannot overwrite original dataset files.

## Perceptual API and limits

Public generator APIs are `quality.perceptual_signature(observation) -> str` and `quality.find_duplicate(candidate, existing) -> str | None`. Set `candidate.perceptual_hash` before screening and persistence; the returned matching ID names an existing sample. The signature is canonical JSON with version `local-rgbd-v1`, source dimensions, an RGB 64x48 box thumbnail and a metric depth 32x24 nearest thumbnail. It contains no truth labels.

Comparison uses channel-centered local colors, chromatic foreground overlap, per-location foreground changes, then valid-depth support and metric differences. A uniform +4 RGB brightness offset matches, while a 12-pixel target translation on the same fixed background does not. A coarse local-color rejection accelerates clearly different layouts. Achromatic images use local luminance differences. This is conservative, deterministic near-duplicate screening, not a general visual semantic equivalence model. Canonical source grouping supplies protection for camera/corruption derivatives. Pairwise comparisons are quadratic in sample count; the present scope is the bounded 100/1000-group T6a batches.

The root's already-generated real five-group pilot was independently revalidated read-only after the final quality changes: valid=true, 5 samples/5 groups, 2 positive/3 negative, 0 duplicate pairs, no errors or warnings, split 4/0/0/1. Full acceptance rendering is owned and reported by the root agent.

## Verification evidence

- Initial RED: 9 explicit missing-module test failures and 9 fixture setup failures before implementation (`splitter`, `quality`, `exporters` did not exist).
- Initial GREEN: 18 tests passed in 17.88s.
- Additional RED: 5 failures caught missing positive surface grounding, inconsistent object center, invalid reasons/English instruction structure, and attempting to export over a dataset directory. Two further failures caught an undersized destination and a selected destination pixel with invalid depth. All were fixed and the resulting 25-test run passed.
- Source audit RED: 4 failures demonstrated missing/tampered source evidence, invalid canonical source hash, and empty dataset content hash could pass validation. These are now rejected.
- Final dedicated command: `.venv/bin/python -m pytest -q tests/test_rgbd_dataset_splits.py tests/test_rgbd_dataset_export.py` -> **29 passed in 57.06s**. Output: `quality-tests.log`.
- Ruff on the three production files and two test files: **all checks passed**.
- `.venv/bin/python -m mypy --follow-imports=silent` on the three production files: **success, no issues in 3 files**. The only note identifies unrelated unused project configuration overrides for `ament_index_python.*` and `rclpy.*`.

A combined run also exposed nine generation-test failures because that worker's CPU source fixture was only `{"source_hash":"fixture-code"}` and no longer met the required source evidence contract. The generator owner was notified to replace the fixture with complete canonical source/asset file hash maps. These failures were fixture incompatibility, not hidden or treated as passing. The latest integration result is owned by the generator/root agent.

The full repository suite includes GPU/render tests and was not launched by this CPU-only delegated worker. Root owns the final combined regression and GPU scheduling.

## Additional delegated final-review repairs

After the quality module freeze, the root delegated `generator.py` and its generation tests to this worker for final-review findings. The resulting production code is now frozen as well.

- Finalization now accounts for all retained split indexes, split audit, quality report and final manifest bytes before writing. Sequential atomic replacement planning includes the simultaneous old/new file peak for the filesystem free-space reserve. Actual report/manifest sizes are checked again immediately before publication. An exhausted budget produces INCOMPLETE while preserving committed episodes. The resource record defines `max_bytes` as the total retained dataset files and treats temporary write copies separately against `min_free_bytes`.
- Initial metadata gets an admission check. A budget too small for the source/config/index/manifest headers returns INCOMPLETE with `manifest_persisted=false` without writing those files. Existing committed datasets are never deleted to satisfy a cap.
- Started/outcome attempt-journal writes also reserve their actual size, outcome room and terminal manifest metadata. This fixes the independently reproduced 190,091 retained bytes under a 190,000-byte cap during repeated duplicate rejection.
- The final byte report includes the final manifest itself. A separate CPU smoke measured reported_bytes=actual_bytes=249,544.
- Source binding additionally fingerprints contracts/models.py, contracts/__init__.py, errors.py, simulation/backend.py, simulation/mujoco/spec_randomization.py, and the root/datasets/vision/simulation/simulation.mujoco package initializers. Tests change bytes through a read-only mock at the filesystem boundary and prove source_hash changes without editing those repository files.

RED evidence: the 20-group finalization cap and atomic-free-space cases both incorrectly returned COMPLETE; ten runtime-dependency hash tests failed; two tiny-cap tests failed; the rejection-journal test exceeded its cap by 91 bytes. Logs are `finalization-budget-red.log`, `source-binding-red.log`, `initial-budget-red.log`, and `journal-budget-red.log`.

Verification: 12 finalization/source tests passed; the initial 33-test complete generation suite passed in 17.88s; the added journal-budget regression passed in 26.62s (`journal-budget-green.log`). The final complete generation suite passed **34 tests in 47.79s**, recorded in `finalization-budget-suite.log` after the production freeze. Ruff and mypy for the changed generator are clean, with only the preexisting unused mypy override note.
