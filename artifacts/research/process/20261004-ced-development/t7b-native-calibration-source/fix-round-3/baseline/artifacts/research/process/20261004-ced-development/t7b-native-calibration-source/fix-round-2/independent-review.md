# Task2 fix round 2 independent review

**REQUEST_FIX — P2: malformed or incomplete independent UTC samples abort reconstruction instead of retaining the assigned group as unavailable.** This finding is a software reader and diagnostic denominator issue. It is not a finite-bound or native-source bypass.

`research/native_geometry_calibration.py:226` reads `sample["pair_hash"]` while building the inventory before validating each sample's schema. A missing `pair_hash` raises KeyError. At `:233`, a present `utc_lower_at` with JSON null raises TypeError in `datetime.fromisoformat()`. `_group()` at `:497` catches only ValueError, so both escape the real registered reconstruction. No assigned-group, component or infinity quantile diagnostics are returned. This violates this round's requirement that missing trusted UTC originals remain unavailable while all assigned groups are retained.

`independent-clock-reader-probe.py/.log` independently reproduces both cases with the actual `NativeCalibrationRegistration.revalidate()`, RawV3 validator, per-group reader and aggregation, without replacing a production validator or reconstruction function. The fixture's in-memory source inventories contain the current actual producer hashes. In all four cases RawV3 is COMPLETE and original-source reasons are empty. The clock source join uses an existing source file/hash only as a SOFTWARE_ONLY arithmetic control; it does not claim an independent acquisition implementation or external time authority.

- Complete clock control: group INCOMPLETE because v1 lacks reset chronology; assigned=independent=geometry quantile count=1, geometry/action bounds=None.
- Missing one entire sample: group INVALID, the same counts=1 and both bounds=None.
- Missing `pair_hash`: KeyError, no diagnostics returned.
- `utc_lower_at=null`: TypeError, no diagnostics returned.

The final assertion requires every case to retain assigned count 1 and deliberately fails with **exit 1** for the two counterexamples. Validate the complete sample container, exact row keys and value types before dereferencing fields or parsing timestamps; normalize malformed sample input to ValueError so the existing group refusal path retains the allocation and infinity score. Preserve the complete-clock and missing-whole-sample controls, strict chronology, reset unavailability and the source/horizon/policy checks. Do not remove the group or reduce its denominator.

## Verified repairs and scope

The exact pre-round three-file diff was read. RECORDER_SOURCE_PATHS contains eight actual required paths and is a subset of the expanded current native source inventory. Known original producer/asset mismatches are rejected. The source reader compares all original producer paths/hashes and asset identity with current registered bytes; the registration revalidates current executing source and original file bytes. No public registration or result flag can create the application-owned source through its normal constructor. The fixed app index, exact role type/current root, registry/catalog pins and content-equality gate remain intact.

`independent-original-replay.py/.log` verifies the original source-link probe hash and replays its unchanged fixture/real reader, replacing only the historical bug assertions. Known wrong producer SHA and asset SHA now return INVALID; a post-2099 preregistration with no independent UTC returns INCOMPLETE. Every case retains assigned=independent=geometry/action quantile count=1 and unavailable bounds. Missing independent UTC is not misrepresented as evidence of a proven chronology violation.

The same replay executes the preserved exact component-collision fixture and fixed assertions. Eleven assigned groups still produce ten components; legal IDs `a`, `b`, `a|b` do not collide. Both geometry/action quantiles retain n=10, rank=10, bound=None and unavailable component `["a","b"]`. The historical qualified collision remains closed.

Preregistration compares the original ACQUISITION and EXECUTOR_ATTEMPT starts with their matched independent lower UTC brackets, uses strict `<`, and v1 always keeps RESET UTC unavailable. It does not infer reset from SETTLE or simulation zero. Offline owner duration and online original/resolved/owner reference full duration must exactly equal the registered terminal horizon. Truth endpoint arithmetic uses the reconstructed owner's DeterministicGroundingPolicy and matches the actual existing owner compiler for all six motion skills, including non-default clearance/minimum height. A per-skill digest must be uniquely derivable from every assigned group's action owner originals and receipt hash; the current rebuilt receipt must match it. Missing or mixed policies cannot support a source.

Independent fresh scoped verification:

- 53 Task2 CPU tests passed in 22.40 s; `independent-cpu.log`.
- Ruff passed on three owned Task2 files; `independent-ruff.log`.
- Mypy passed on two owned Task2 sources; `independent-mypy.log`. Existing unused-configuration note remains.
- Preserved source-link/component replay passed, exit 0; `independent-original-replay.log`.
- Qualified UTC reader retention probe failed as expected, exit 1; `independent-clock-reader-probe.log`.

The author's 175 affected tests were not repeated, and the independent 53 are not additive to that author total. Their success does not cover the newly qualified missing/null UTC row cases.

## Evidence preservation and activation limits

`independent-preservation.json` records 76 exact byte/hash checks of both minimal frozen baselines, their unchanged historical source/report/log bytes, old live reports/probes and Task1 pins, current owned source/test pins and all round-2 author evidence. The original independent reviews and probes remain unchanged. Audited current pins:

| File | SHA256 |
| --- | --- |
| vision/native_calibration.py | 0888c38f4caf4dd65c27c29315d8253a1aa8fa1a6fece0bf2b18bcc9bcedb2a6 |
| research/native_geometry_calibration.py | 99220498b5e768fc1a58d81a80aa8c262e8521c01d2a426f1826036e2950f0ad |
| tests/test_native_calibration_source.py | b6f16fb6646515da175d3e68505164a1b6c2dbffb95af73b4b03076ccfaf2c51 |
| fix-round-2/implementation-report.json | 5957516cd07d55ed56ad6276eb0e002b5b79dc649afe8d708036f3c839eed542 |
| fix-round-2/baseline-manifest.json | 9c1b5836891994409fdade7bc7c44fa1d63f7dc50b685955e2b185ab49616940 |

There is still no genuine app-owned index/catalog, independent authenticated UTC acquisition/reset originals, nine genuinely independent supported groups, or actual native finite publication. v1's unconditional reset refusal makes the offline finite action/horizon path unreachable with the real current protocol. Numeric estimate controls explicitly replace the app/marker/reference proof boundaries and are software evidence only. Static inspection and these controls do not establish the genuine positive branch or empirical coverage. Future versioned reset capture/publisher authentication, complete assignment/history originals, exact horizon/owner policy/geometry/contact/TCP source joins, true app-owned positive-branch exercise and consumer activation require their own reviewed evidence. Continuous/future-motion, whole-loop safety/effect/holding, Max/model validation and deferred edge hardware remain outside this review.

Only new `fix-round-2/independent-*.{md,json,py,log}` artifacts and isolated /tmp fixtures were written. No production/test/Task1, old report/probe/baseline, raw archive/header or Stage file was changed; no Git mutation, actual renderer/physics/controller/model/provider/hardware call, broad suite or download was performed.
