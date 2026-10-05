# Independent review: whole-step RGB-D recorder

2026-10-05. Initial verdict: **REQUEST_FIX**. Scope: `research/step_rgbd.py` and `tests/test_step_rgbd.py`, read-only product review. No renderer, physical step, provider, remote operation, or broad suite was run. Evidence is software only.

Reviewed quiet source SHA-256 `fc2d1c8b44450a62352023e9e3246152ca97bb40305a441407f621c1c67b8fd3`; tests SHA-256 `65bece053a97590eadb9e2e64046c020795657527b596e28d58689dd4264a278`. Both fingerprints were verified unchanged after review. The new targeted suite passed **13 cases in 0.17 seconds** (`independent-module-tests.log`).

## Qualified findings

1. **P2 — BEGIN journal failure permits retry and COMPLETE.** `record_step` increments its attempted denominator and writes BEGIN before entering its exception handler. A first-write `OSError` therefore leaves `_failed` unset. The exact probe invokes no camera on that failed attempt, retries the same step successfully, and obtains `status=COMPLETE`, `attempted_captures=2`, `completed_captures=1`, `failed_captures=1`, `reason=null`. The journal contains only the later successful BEGIN/END. This contradicts the fail-closed/no-retry contract and can erase an acquisition allocation failure from the durable event stream. Include BEGIN publication in the failure boundary and retain the first failure even if publishing FAILED also fails.
2. **P2 — original episode and sample-gap controls remain mutable.** After construction at `0.005`, ordinary assignment `max_sample_gap_s=0.1` permits a 0.1-second simulation gap and reports COMPLETE, also changing the summary's `original_max_sample_gap_s` to 0.1. Ordinary assignment `episode_id='other'` after step zero permits BEGIN rows from `['episode', 'other']` and reports COMPLETE under the second identity. Preserve immutable constructor snapshots for all validation and summary fields, or reject configuration changes. The collection must retain the original episode and criterion throughout its lifecycle.

Reproducers and exact outputs are saved in `independent-module-probe.py` and `independent-module-counterexamples.json`. They use a tiny synthetic RGB-D observation and an injected journal-write failure; no real camera or simulator is created. All assertions qualified against the quiet source above. The owner received these findings before actual acquisition started.

## Remaining reviewed behavior

- Successful frames retain the validated original `RGBDObservation` PNG/float32 depth/mask and calibration metadata through JSON plus gzip. The targeted test independently decompresses/revalidates each saved observation and compares it with the captured value and checksum. The preservation claim is for this observation representation, not arbitrary higher-precision caller depth.
- Failed camera/pass/episode/time cases become FAILED, remain in attempted/completed denominators, and prohibit retry after the captured failure. Missing steps and excessive original gaps reject before another camera call. Finalization compares the declared final step/time with the complete zero-based collection; it retains `allocated_steps=final_step+1` for a valid declaration even when collection is incomplete.
- The generic library does not independently inspect raw-v3 command/action/terminal rows or establish camera-source authenticity. The actual adapter must supply and validate the full original raw terminal horizon and exact per-step source association, rather than a shortened caller horizon. Its acquisition stream must remain distinct from raw-v3 CAPTURE rows, which private camera capture does not automatically create.
- Stable dimensions, intrinsics, transform, calibration, scene, source, and identical two-pass state hashes are checked. The actual adapter remains responsible for using the original camera, preserving backend RNG/cache/controller state, and indexing the camera hashes to the actual raw physical row.
- Clocks are explicitly labelled `SAME_PROCESS_NOMINAL_BRACKETS_ONLY`; external UTC uncertainty stays UNAVAILABLE. END clocks enclose camera capture plus observation validation, before gzip/file persistence. These are nominal acquisition brackets, not an audited UTC mapping or a guarantee about write durability. Original simulation-time gap and measured wall-time acquisition duration remain different quantities.
- `continuous_motion=NOT_CERTIFIED` and `formal_accepted=False` remain closed in all qualified outputs. COMPLETE denotes declared collection coverage only. This review grants no native calibration, bounds, online truth, INITIAL, or METHOD acceptance.

Root owns the narrow product fixes. This initial REQUEST_FIX, the passing 13-case log, source fingerprints, and counterexamples are retained for a subsequent bounded post-fix review.

## Post-fix independent review

2026-10-05. Final bounded verdict: **PASS — both P2 findings CLOSED**. Owner confirmed formatted source quiet before this review. Source SHA-256 `35e778904c0eadd9a49438b811e396fab76e7fd5e8458579d0b5c8cd09c62df0`; tests SHA-256 `b2aace52da5386aac7310fbf59550d72a328eb40937797b649fa2b752d3c920e`. Both fingerprints were independently checked before and after verification. Only the 17-case targeted module suite was rerun, passing in **0.18 seconds** (`independent-module-fix1-tests.log`). Its four new regressions cover first/persistent journal failure and ordinary mutation of both original controls.

The exact retained original counterexample fixture definitions were loaded in memory and replayed by `independent-module-fix1-probe.py`; results are in `independent-module-fix1-counterexamples.json`:

- Original first BEGIN-write `OSError` is now retained. Retry raises `RuntimeError`, no camera is called, the journal retains FAILED when writable, and finalization is INCOMPLETE with attempted allocation 1, camera calls started 0, completed 0, failed 1, and the original failure reason. Persistent FAILED-journal errors also retain the first failure and block retry, as independently covered by the targeted regression.
- Ordinary assignment to `max_sample_gap_s` now raises `AttributeError`. Replaying the original 0.1-second step then raises `ValueError` before another capture; finalization retains the original `0.005` control and is INCOMPLETE, with the full two-state declared denominator.
- Ordinary assignment to `episode_id` now raises `AttributeError`. Replaying the original second-episode input raises `ValueError` before another capture; only the original episode has a BEGIN event, and finalization retains that identity and is INCOMPLETE.

The genuine no-mutation path still passes the original lossless payload, gap, full declared horizon, and failure tests. All replay outputs retain `continuous_motion=NOT_CERTIFIED`, external UTC uncertainty UNAVAILABLE, and `formal_accepted=False`. The generic library remains diagnostic collection infrastructure; actual adapter provenance, full raw terminal/action association, RNG/cache preservation, and any native calibration acceptance remain separate work.

Initial evidence was not overwritten: original probe SHA-256 `d198471db095ccf5ae2d802e320cdfcb79eb1ce3332a44e8ea260ed1d160f9c2`, initial counterexample JSON SHA-256 `29958a77871a92978f8a8532f807bd472755b6c733c30b9e2a708881e4595b25`. No product source, rendering, physics, provider, remote operation, or broad test suite was touched by this reviewer.
