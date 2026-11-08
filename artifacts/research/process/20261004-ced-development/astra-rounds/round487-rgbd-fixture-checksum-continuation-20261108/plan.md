# R487 RGB-D fixture checksum recovery plan

Actual gpt-6-astra recovery plan under AGENTS.md. Continue the authorized R486 work without another confirmation loop. This round corrects only two parametrized synthetic-source cases, then returns to R486; it adds no product scope.

## Original failure and root cause

R486 `execution/red.stdout`, `red.stderr` and `red-result.json` are immutable evidence: 7 failed, 5 passed. Five failures are expected pre-fix assertions. Both `test_saved_profile_does_not_calibrate_other_camera_sources` cases (rgbd_camera, isaac_camera) unexpectedly fail while constructing InitialPlanningRequest with `RGB-D checksum mismatch`, before reaching the planner.

The fixture uses `observation.model_copy(update={"source": source})`, retaining the old checksum. `vision/observations.py` includes source in checksum_fields and rejects mismatches at validation. Its own crop() reconstructs via model_validate with checksum_sha256="". The production check is correct; only fixture reconstruction is wrong. Original service SHA256 remains `7eeaacd932542feaaf77ad48b71cab5421edb13e827fd27a49879defad94da39`.

## Scoped executable steps

1. Recheck companion plan.json pins before editing. Preserve all original R486 RED files and plans. Only `tests/test_model_control_rgbd_snapshot.py` may change in this recovery; no product changes until corrected RED is accepted.
2. In `test_saved_profile_does_not_calibrate_other_camera_sources`, replace the single shared source-construction statement for its two parameter values with a validated synthetic observation. Add a local RGBDObservation import if needed:

```python
observation = RGBDObservation.model_validate({
    **frame.observation.model_dump(),
    "source": source,
    "checksum_sha256": "",
})
frame = replace(frame, observation=observation)
```

Keep timestamps, pixels, depth, mask, source parameters, fake transport and all assertions unchanged. Clear the checksum only for this freshly constructed synthetic observation; never alter a captured/live frame or disable production validation. `_request(frame)` must now validate and reach the actual planner's non-MuJoCo calibration rejection.
3. Execute once, recording a new unique stage under R487 `execution/corrected-red.stdout`, `corrected-red.stderr`, `corrected-red-result.json` (exclusive create, refuse overwrite):

```bash
.venv/bin/python -m pytest -q tests/test_model_control_rgbd_snapshot.py
```

Save command, elapsed time, rc and current service/test SHA256. Expected rc=1 with exactly **5 failed, 7 passed**: main grounding case; missing/changed/unregistered default asset cases; normalized non-square center case. Both external-source cases must pass their existing rejection assertions. Review failure identities/messages, not only totals. Network/render/API counts remain zero under existing test guards. Any different unexplained failure stops dependent repair for a new Astra assessment; do not mask failures or alter expected product assertions.
4. Once corrected RED matches, return directly to R486 Task B3's minimal service fix, focused GREEN, and B4 adjacent command **as replaced by cpu-verification-supplement**. Do not rerun the old flawed RED stage or rewrite its report. Record R487 correction and the two separate RED generations in the R486 step report. Existing R486 live paid-gate block and no-restart/no-secret-export boundary remain unchanged.

## Acceptance and self-review

Recovery acceptance is exactly the validated synthetic constructor and explained 5-failure corrected RED with the original service unchanged. It is not a product fix or runtime qualification. R486 later GREEN/adjacent and generation-boundary requirements still apply; R469 remains NOT_RUN. All 12 input files and SHA256 values are pinned in plan.json. This planner statically inspected the original failure, schema and crop pattern; ran no tests, APIs or renderers; changed no product/test files; delegated nothing. Scope and assertions were self-reviewed against the two unexpected fixture failures.
