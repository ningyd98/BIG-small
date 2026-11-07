# R443 — collection protocol JSON roundtrip

Planner: actual `gpt-6-astra`. Status: PLAN_ONLY. Planning performed filesystem reads, evidence preservation and this plan only; no tests, product imports, physics, renders, network or Git writes.

## Original failure and root cause

R439 `validation/t2-green` finished with **6 failed, 71 passed, 1 deselected**, pytest 10.98 s, supervisor 12.012078 s, returncode 1, reaped true; no remaining processes, source drift or leaked ports reported. Parent reports 0 physics steps / 0 render passes. Original stdout, stderr, JUnit, result and spec are copied byte-for-byte into `intake/`; original locations remain untouched. `intake/evidence.json` extracts all six failed names and messages. The valid and deliberately assignment-mutated protocol fixtures from the original `/tmp/bigsmall-r439-t2-green` are preserved byte-for-byte. Twenty-six input SHA256 pins are recorded in `plan.json` and `intake/source-index.json`.

`RationalCompletionHorizonV1.registered_dt_ratio` is a tuple. `action_horizons()` uses `asdict`, which retains that tuple. `save_exclusive()` writes JSON arrays, and `load_json()` reconstructs lists. Consequently `read_protocol()` line 190 rejects an untouched protocol before intended checks; after repairing this comparison, the whole-protocol direct comparison at line 195 would reject the same representation difference. Settings direct Python equality also treats booleans and some numbers as equal, inappropriate for fixed registration. Existing strict `canonical()` supplies the required uniform representation. Original source excerpts are retained in `intake/original-source-excerpts.json`.

The 71 passing cases **do not establish factory construction, one-shot origin/claim, unreleased-assignment rejection, or the software worker/lease path passed**. Four failed authority tests stop in `from_startup` before those target assertions. No live full-H entry was validated by this result.

## Exact repair scope

Only edit `src/cloud_edge_robot_arm/research/native_calibration_collection.py` and focused assertions in `tests/test_native_calibration_collection.py`. In `read_protocol`, compare `canonical(protocol["settings"])` against `canonical(load_json(ROOT / CONFIG))`, and `canonical(protocol["actions"])` against `canonical(action_horizons())`. In the existing `if current_sources` branch, compare `canonical(protocol)` against `canonical(_protocol(ROOT / CONFIG))`. Keep existing error categories/messages and source-generation digest check.

Use existing canonical JSON encoding unchanged: key order and whitespace are immaterial after parsing; tuple/list both represent JSON arrays; array order and every field/value remain material. Boolean versus integer and integer versus floating representation remain distinct under this encoder. Do not use decoded-object equality, approximate arithmetic, field projections, permissive coercion, dropped metadata, ignored extra keys, or expected values derived from the submitted protocol. Preserve duplicate-key/nonfinite and regular-file/symlink rejection. Do not change `current_sources=False` semantics or imply it grants execution authority; offline provenance remains the R439 T3 obligation.

No edits to horizon arithmetic, config, assignment release, geometry, marked assets, raw schema, worker/controller/Shield, private authority, recorder, or previous plans/results. An old fixture correctly becomes a stale source generation after repair; do not rewrite its hashes for reuse. Newly created test fixtures register the repaired source generation before their read.

## Tests and one bounded repair GREEN

The preserved six failures are this repair's RED evidence; no extra RED invocation. Keep all existing 77 selected CPU cases and the exact original real-two-step deselection. Add exactly three collected tests in the allowed test file; use internal case loops rather than parametrization:

1. `test_protocol_canonical_json_roundtrip`: freshly prepare/read a valid protocol; assert original in-memory tuple and disk list for both horizon and tail_basis ratios, canonical equality, preserved action ordering and receipt digest consistency. Re-encode equivalent input with indentation/reordered dictionary keys and verify it still reads. Monkeypatch physics initialization to raise, following the existing prepare test.
2. `test_protocol_recipe_and_settings_tampering_rejected`: independent copies of a fresh fixture reject ratio-element mutation, integer-to-float/boolean substitution, altered timeout/tail flag, action-order change, added action field and altered settings. Require the recipe error, not an unrelated downstream exception. Exercise both current_sources values for recipe checks. Restore each case from an immutable canonical byte snapshot, never the preserved evidence originals.
3. `test_protocol_registration_typed_metadata_and_source_tampering_rejected`: independent copies reject assignment seed/status changes, added top-level field, admission `execution_admitted=False` replaced with `0`, and integer metadata replaced by an equal float. Default current-source validation must reject with the registration error. A changed source_hashes entry without digest update must fail source-generation digest; the same change with recomputed digest must still fail whole current-source registration. Retain the existing assignment rejection test and specific expected error.

ROOT creates a **new** `R443/implementation/run_stage.py` and frozen `commands.json`; never modify R439 `commands-r440.json`, runner or results for this repair. Reuse unchanged R413 `bounded_stage.py` and pinned original T2 environment. The full exact transformed spec is `plan.json.verification.spec_template`; redirect every stage-relative environment/output location into `R443/validation/t2-repair-green`, use fresh `/tmp/bigsmall-r443-t2-repair-green`, stage id `r443-t2-repair-green`, attempt 1. Preserve plugins `r413_events` and `r235_startup_prerequisite`, exact seven test-file arguments and this exact deselection:

```text
--deselect=tests/test_visual_raw_recorder_v3.py::test_real_render_disabled_passive_two_steps_have_ordered_actual_begin_end_and_old_observers
```

Runner refuses any existing stage/basetemp, pins current sources before launch and rejects stage-time drift; records full setup/call/teardown and subprocess cleanup. Execute once:

```text
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round443-collection-protocol-roundtrip-20261107/implementation/run_stage.py t2-repair-green
```

Inner bound 600 s; outer bound 720 s. Expected **80 passed, 1 deselected**, no skip substitution; actual physics/render/model counts remain zero. No collect-only, probes, repeated fullsuite or new standalone static runs. Original R439 final static stages cover this repair later. Any unexpected failure stops dependents and requires a new actual Astra plan; no rename/retry. Capture original and new outcomes separately in step-report and phase summary.

## Acceptance and remaining work

Before edits, verify input pins still applicable. ROOT may continue independent T3 test preparation, but that work cannot change this repair's collected test scope or pinned inputs unnoticed. Allowed product/test hashes change through implementation; freeze the new runtime source generation before validation and preserve initial pins. Fresh software fixtures use that generation; no source drift is allowed during the stage.

Acceptance requires the exact bounded GREEN result and evidence that all six former failed nodes now reach intended assertions, including the real SQLite/worker lease test whose execution body remains software-only. This does not prove or authorize physics, rendering, full-H native closure, online PASS or calibration validity. Native remains UNKNOWN. T3's original quota is unconsumed; after repair passes, continue R439 remaining stages under R440/R441/R442 and implicit-frame addendum. No actual quota increase, nine-group expansion or new design approval loop.

Self-review: both tuple/list-sensitive comparison sites are covered; strict settings and whole-protocol comparison retain field/type rejection; original failure is preserved; repair uses one fresh supervised CPU stage; scope and downstream proof limits are explicit.
