# Marker association source-path fix1

Ready for scoped independent re-review. This fixes the two root-reviewed source-path gaps in the DEVELOPMENT_ONLY diagnostic module. It does not integrate a tracker, action proof, planner or native gate.

The original 39-file release remains unchanged. Its manifest is `a3e6b97a1a06651bde41cf64260d4009e9e9bd7e03e812aeb9668ff24e259614`; source, report, ownership, diff and root counterexamples were additionally preserved under `fix-round-1-baseline/` before editing. The new 39-file manifest is `5eee3ff4d4f1edb682045b54abed8e6612a853e7cb53019ee6b15dc6cd81043c` at `fix-round-1-source-hashes.json`, with exact source in `fix-round-1-source/` and the three-owned-file diff in `fix-round-1-review-package.diff`.

## Changes and evidence

Root's first counterexample was confirmed: resolving the source root before inspecting its path removed a symlink root or ancestor from consideration. The second counterexample was also confirmed: identical registry bytes through a symlink parent loaded successfully. Before production edits, qualified real-filesystem regressions produced **4 failures and 1 existing rejection control** (`fix-round-1-red.log`): source-root symlink, source-root ancestor symlink, registry parent symlink and identical registry outside the source root. The direct registry symlink control already rejected.

The fix checks the supplied root and all lexical ancestors for symlinks before resolving it. Each source file and the registry must likewise have no symlink in any lexical ancestor, be a regular file, and resolve beneath the validated source root. Existing source byte hashes and the marked asset digest still apply. The registry's owned association-module hash was updated to the exact fixed implementation. No other registry/layout/asset/identity fields changed.

The original root counterexample script was replayed unchanged from the separate immutable fixed overlay. It now reports `sources_valid=false`, status INVALID, and registry parent accepted=false. Admission remains NOT_ADMITTED and whole identity UNKNOWN (`fix-round-1-original-counterexample-replay.log`). The two original saved static replay positives still produce OBSERVED_CANDIDATE solely as diagnostics; bounds remain null, extent false and stability UNKNOWN.

## Verification

Targeted marker association suite: **42 passed in 9.00s**. Frozen scoped regression: **96 passed in 9.62s**, including pose detector, asset equivalence and top-grasp software tests. Scoped Ruff and format passed on the two Python owned files. Fresh-cache `mypy --no-incremental` passed on the module; the existing pyproject unused-section note is preserved in its log.

The fixed overlay `/tmp/ced-marker-association-fix1-7937_bda` is the complete frozen 768-file T8b fix3 base plus the scoped 39-file release (790 unique closure files). `fix-round-1-verification-setup.json` and `fix-round-1-closure-hashes.json` record the immutable inputs. All original39 hashes remained unchanged. All fixed39 archive/overlay/live hashes and Python ASTs matched after verification; all closure790 hashes remained unchanged. Only the three explicitly owned paths differ from the reviewed baseline.

Commands ran with the project virtualenv, the frozen overlay as cwd, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=src`:

```text
python -m pytest tests/test_marker_association.py tests/test_pose_marker_evidence.py tests/test_pose_marker_assets.py tests/test_rgbd_top_grasp.py -q
ruff check src/cloud_edge_robot_arm/vision/marker_association.py tests/test_marker_association.py
ruff format --check src/cloud_edge_robot_arm/vision/marker_association.py tests/test_marker_association.py
mypy --no-incremental --cache-dir /tmp/ced-marker-association-fix1-7937_bda/.cold_mypy src/cloud_edge_robot_arm/vision/marker_association.py
```

No new capture, cloud/model call, renderer operation, controller command, task action, GPU invocation or full project suite was run. Source identity is a bounded software path/hash check; it does not create accepted physical object registration, calibrated geometry, continuous motion bounds or execution admission. Historical motion decode failures and raw source packages remain preserved. Owned production files are frozen pending independent review; no further writes are planned.
