# External RGB-D focused re-review

Date: 2026-10-03. Scope limited to F1–F5 from `final-review.md`. No implementation edits, no full-suite repetition, and no real-dataset verification claims.

## Closure results

- **F1 CLOSED:** the completed extraction inventory is persisted before any bundle-to-stage move. Recovery reads that journal and rolls remaining members forward while checking already assembled member hashes. The interrupted assembly regression now passes and retries reach COMPLETE/REUSED.
- **F2 CLOSED:** HTTP 401/403 becomes sanitized `BLOCKED_AUTH`, without network retry or credential leakage. Focused HTTP/SDK authorization regressions pass.
- **F3 CLOSED:** the executor now emits a shared cancellation event before waiting for workers. HTTP streaming, SDK progress, hash checks, and retry backoff cooperate; queued futures are cancelled and persistent partial files survive. Focused interruption regressions pass. HTTP connect/read timeouts are bounded at 15 seconds; this is cooperative cancellation, not an immediate forced socket kill.
- **F4 CLOSED for real acceptance:** discovery now validates the full raw marker source/revision/file/selection identity and inventory hashes before passing a revision to readers. Smoke additionally checks the tested index rows' dataset/revision/root, rejects synthetic provenance, and validates the raw marker before writing a real-data report. The wrong-revision and fixture smoke regressions pass. Standalone previews still consume existing index provenance rather than creating verified scope; they do not relabel samples with the requested plan revision.
- **F5 CLOSED:** discovery trajectory quarantine is included in quality output and distinct aggregate/frame/trajectory counters. `trajectory_completeness` uses canonical `group_key` identities, checks the complete expected frame-index set for each camera, and counts task coverage only from complete accepted trajectories. Status groups use the same canonical identities; the RoboMIND scope gate requires ten complete episodes and at least two complete tasks.

## Final F5 closure

The earlier partial-task fault has been corrected. The complete `task_a/same_episode` plus incomplete `task_b/same_episode` case now has one complete episode, one complete task, and one incomplete episode. The incomplete second task cannot satisfy the verified-scope task requirement. Inspected the helper, its validation/status wiring, and the final `complete_tasks >= 2` scope gate.

## Focused verification

Executed:

```text
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_deployment.py tests/test_external_rgbd_transfer.py -k 'wrong_raw_revision or interrupted_bundle_assembly or discovery_preserves_file_quarantine or smoke_rejects_synthetic or unauthorized_download or keyboard_interrupt'
```

Result: **10 passed, 35 deselected in 0.65s**. Deselection is deliberate scoped review and is not represented as PASS. A temporary Python probe separately checked F5 aggregate quarantine and canonical/task counting. Temporary synthetic data was automatically removed. No remote downloads or real-data acceptance tests were invoked by this review.

Final F5-only check:

```text
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_deployment.py::test_complete_task_coverage_excludes_partial_second_task
```

Result: **1 passed in 0.11s**. No other checks were rerun for this last correction.

Current result: **F1–F5 CLOSED.** All findings from this independent review are resolved within the reviewed software scope. Real source-backed deployment acceptance remains separate and unverified by this review.
