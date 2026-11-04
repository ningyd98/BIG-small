# R425 T7b completion arithmetic kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` for inline implementation. Root has accepted this bounded CPU scope; no new design-permission question. This plan is authored by actual `gpt-6-astra`; this planning turn performs no implementation, tests, runtime or Git mutation.

**Goal:** Deliver the smallest useful R91 continuation: independently testable pointwise completion math, integer horizon accounting, and all-eight-action joint/component calibration diagnostics needed by the future original-data producer.

**Architecture:** Two new pure modules and two focused test files. No runtime owner, public registry, certification factory, source index or consumer dispatch is introduced. Caller-described arithmetic is always SOFTWARE_ONLY, including a finite joint quantile.

**Tech Stack:** Python 3.12+, standard-library arithmetic/dataclasses; reuse the existing independent-component graph helper only behind strict validation. Existing pytest/Ruff/mypy tools.

**Spec:** `../round91-native-full-action-support-20261007/design.md` §§2–4 and arithmetic portions of Tasks 1–3 in its `plan.md`; R424 entry assessment authorizes limited T7b development, not action acceptance.

## Evidence and diagnosis

Baseline HEAD: `0a11393aba9e851b0e38fd469aba71ea1138307a`. Original evidence is the unchanged `intake/observation.json`, whose SHA256 and all input pins are copied into `plan.json`. This is a static missing-implementation gap, not a newly executed failing test. R91 design exists; `vision/native_completion.py`, `research/native_completion_calibration.py`, and the proposed runtime horizon module are absent. `vision/action_evidence.py` still deliberately puts both old bounds at None. Old calibration cannot supply missing mutable future-reference motion or GRASP/RELEASE closure merely by wiring finite scalars.

Source review confirms: `native_geometry_calibration.py` already has full rigid geometry, component graph union, and a v1 group rank; do not duplicate its raw reader. `skill_robot.py` adds ceil(0.5/dt) steps after LIFT movement; RELEASE currently checks gripper opening, without the new independent one-second settled-object claim. R91 calls for a different explicit empirical completion metric and complete eight-action joint denominator. Implement its missing arithmetic foundation without pretending that raw reconstruction, actuation or certification exists.

## Global constraints and scope

- Preserve Qwen3.8-Max, OpenCV, visible marker, top camera, current controller and every existing source/config/test byte.
- New source only: `src/cloud_edge_robot_arm/vision/native_completion.py` and `src/cloud_edge_robot_arm/research/native_completion_calibration.py`.
- New tests only: `tests/test_native_completion_v2.py` and `tests/test_native_completion_calibration_v2.py`. Round-local plans, source manifests, verification records and step/phase reports are allowed.
- No changes to legacy e/v, UNKNOWN, three consumers, source indexes, registry, owner/lease/clock, controller, original/raw bytes or historical plans. No `native_horizon.py` runtime session in this round.
- No model, hardware, rendering, network, paid API or actual physics invocation. Git delivery is root's later existing authorized step; preserve unrelated untracked files/gitlinks.
- This advances only R91 Task 1's metric, Task 2's duration arithmetic and Task 3's joint/component reduction. Reference resolution, raw reconstruction, unique stepping/hold production, certified source, live owner and Task 4 consumers remain unimplemented.

## Review focus

1. Different points dominate U/L/M: C must use a maximum of pointwise sums, not a sum of unrelated maxima; rotated eight vertices must not collapse to a center-only comparison.
2. A missing allocated group/action/frame or failed outcome must survive in the denominator as infinity; a supplied finite scalar never supplies authority.
3. Shared ancestry/fingerprints merge transitively, even when the connecting group is unavailable; rank uses independent components, not raw groups or eight separate 0.9 gates.
4. Rounding, double-counted tails, bool-as-int, NaN/infinity and overflow must be explicit; longer/shorter terminal windows do not satisfy the exact assigned horizon.
5. Pure diagnostics must stay usable without constructing live owner/robot/backend; old mutable-reference and future-D UNKNOWN behavior remains unchanged.

## Fixed interfaces

All new result dataclasses are frozen with tuple data. Static `schema_version`, `evidence_scope="SOFTWARE_ONLY"`, `native_authority="UNAVAILABLE"` fields use `init=False` (or read-only properties), never caller-selectable acceptance flags. No result has a VALID/PASS/admit method or native bound. Module docs state that source authenticity and exchangeability are external proof obligations. Strict invalid input raises ValueError; unavailable evidence has an explicit reason and an unavailable diagnostic score. Outputs use None for a mathematical positive-infinity score, allowing strict JSON without NaN/Infinity.

### 1. `vision/native_completion.py`

`COMPLETION_SKILLS_V2` is the immutable ordered tuple `("MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT")`. Recipe ID is `FULL_HORIZON_JOINT_CONTACT_COMPLETION_V2`; metric schema is `native.completion.metric.v2`.

`completion_metric_v2(*, geometric_error_m: float, command_points_m: Sequence[Sequence[float]], capture_reference_points_m: Sequence[Sequence[float]], terminal_reference_points_m: Sequence[Sequence[float]], actual_points_m: Sequence[Sequence[float]]) -> CompletionMetricV2`

All four point arrays are nonempty, equally sized, ordered and exactly 3D; entries are built-in int/float (not bool), finite, and detached into tuples. Geometry is finite and nonnegative. The reader later provides registered corresponding contact/control points, including all eight object vertices for RELEASE; this kernel neither certifies completeness nor invents correspondence. No target_pose is needed, allowing the future GRASP/RELEASE reconstruction to use their correct points.

For each point i calculate `u_i=dist(p_i,r_c_i)`, `l_i=dist(x_i,p_i)`, `m_i=dist(r_t_i,r_c_i)` and `e_i=dist(x_i,r_t_i)`. Reject nonfinite derived arithmetic. Return `geometric_error_m`, `point_u_m`, `point_l_m`, `point_m_m`, `point_endpoint_error_m` tuples, maxima `u_m/l_m/m_m`, `completion_error_m=max(G,max_i(u_i+l_i+m_i))`, and `endpoint_error_m=max_i(e_i)`. Do not infer M=0 from a skill label; it is zero only when the provided corresponding references coincide. These numbers are neither continuous v nor future D evidence.

`completion_horizon_v2(skill: str, *, physics_dt_ns: int, original_timeout_ns: int, original_expected_ns: int, compiled_timeout_ns: int, compiled_expected_ns: int, effective_owner_required_ns: int, builtin_tail_included: bool = False, registered_wait_steps: int = 0) -> CompletionHorizonV2`

Exact built-in positive ints for dt and each of the five durations; nonnegative exact int wait steps; exact bool inclusion flag; skill in the eight-element tuple. Ns are a caller-described exact discrete time unit, not a wall-clock certificate. Unsupported sub-nanosecond/rational dt requires later design; do not silently round float dt. Compute base with integer ceil `(max_duration_ns+dt_ns-1)//dt_ns`. Required tail is `ceil(500_000_000/dt_ns)` for LIFT, `ceil(1_000_000_000/dt_ns)` for RELEASE, zero otherwise. Added tail is zero iff `builtin_tail_included`, otherwise the required tail. Inclusion flag means that the max base duration already contains the entire registered tail; reject true for no-tail skills or if base_steps < tail_steps. This is an explicit input accounting claim whose producer must independently justify, not a discovered fact. Registered wait steps always represent only additional, not already-counted, waits.

Return `physics_dt_ns`, `base_steps`, `builtin_tail_steps`, `added_tail_steps`, `registered_wait_steps`, `total_steps`, `total_sim_ns=total_steps*dt_ns`. All are exact integers; no conversion through float seconds. Do not step, hold, read time or certify an endpoint.

### 2. `research/native_completion_calibration.py`

Four frozen input/output records, with structural/numeric validation at the function boundary:

```python
CompletionActionAssignmentV2(skill: str, full_horizon_steps: int, sample_ids: tuple[str, ...])
CompletionGroupAssignmentV2(group_id: str, ancestor_ids: tuple[str, ...],
                           fingerprints: tuple[str, ...],
                           actions: tuple[CompletionActionAssignmentV2, ...])
CompletionActionDiagnosticsV2(skill: str, outcome: str, capture_step: int,
                              dispatch_step: int, terminal_step: int,
                              samples: tuple[tuple[str, float | None], ...])
joint_completion_calibration_v2(
    assignments: Sequence[CompletionGroupAssignmentV2],
    observations: Mapping[str, Sequence[CompletionActionDiagnosticsV2]],
) -> CompletionCalibrationDiagnosticsV2
```

Assignments must be nonempty with unique nonblank group IDs; every group has all eight actions exactly once, positive exact-int horizons, and nonempty unique sample IDs per action. Ancestor and fingerprint tuples must each be nonempty, unique, nonblank strings. They are declarations for graph arithmetic; actual ancestry/fingerprints must later come from original-data validation. Reject duplicate/foreign group/action/sample observations, wrong record types, malformed IDs or numeric fields. The allowed outcomes are exactly `COMPLETE`, `FAILED`, `UNKNOWN`, `INCOMPLETE`. Every supplied numeric field is validated even when outcome is failed; reject bool, strings, negative values, NaN, -infinity and arithmetic overflow. A score of None or +infinity explicitly represents unavailable evidence. Step integers must be exact nonnegative ints; malformed type/value raises ValueError, while coherent-but-unsupported timing produces unavailable group diagnostics.

For every assigned action, missing observation or any missing/None/+infinity assigned sample, outcome other than COMPLETE, `capture_step != dispatch_step`, or `terminal_step != dispatch_step + assigned.full_horizon_steps` makes the group score infinity. This includes early success, longer endpoints and reversed time order; the source reader must eventually provide real event identities and prove the exact steps. Do not silently drop rows or accept an observation-selected shorter horizon. Finite action score is max of its assigned sample C values. Finite group score is max over all eight actions. Preserve sorted reason codes with action/sample context, e.g. `missing_action:RELEASE`, `missing_sample:LIFT:hold-1`, `outcome:GRASP:FAILED`, `capture_dispatch_mismatch:GRASP`, `terminal_horizon_mismatch:LIFT`, `unavailable_sample:PLACE:terminal` and `missing_group`.

Build transitive independent components from ALL assignments using shared ancestor OR shared fingerprint, including missing/failed groups. Reuse `native_geometry_calibration.independent_components` behind this strict wrapper; do not change it. Component score is max of its group scores, infinity propagating. Let n be component count, `rank=(9*(n+1)+9)//10` (exact ceil((n+1)*9/10)); `joint_bound_m` is None when n<9, rank>n, or the selected ordered component score is infinite, otherwise that score. Infinite components remain in the sorted list; for n=19 a single infinity need not occupy rank18, and this is the fixed rank rule, not permission to discard a failed group. Coverage is fixed 9/10, with no caller override.

Output: `assigned_group_count`, `component_count`, `rank`, `joint_bound_m`, sorted `group_scores: tuple[(group_id, score_or_none), ...]`, sorted `components: tuple[tuple[group_id,...],...]`, parallel `component_scores: tuple[float|None,...]`, sorted `unavailable_group_ids`, `group_reasons: tuple[(group_id, tuple[str,...]),...]`, and the static scope/version/authority fields. No geometric_error_bound_m or motion_bound_m_s. Use stable group-ID tuples instead of delimiter-joined component keys to prevent collisions. Scores are explicitly public arithmetic inputs, not certificates.

## One cohesive implementation task

- [ ] Recheck every plan.json pin, baseline HEAD, absent new targets and existing dirty/untracked baseline. Record activation/source manifest; do not overwrite another actor's newly created source. Pin tests and later new sources separately as each stage is frozen. Any source drift affecting scope goes back to Astra.
- [ ] Write the 20 named tests below. Import new APIs inside test functions through an `api()` helper asserting module existence, so the approved RED consists of test assertions that the specific new kernel is absent, not a collection crash or unrelated missing dependency. Test utilities may create only local CPU descriptions.
- [ ] Run one grouped RED on exactly the two new test files; preserve command, complete stdout/stderr, events, JUnit, exit and source pins. Approved RED is the named absent-module/API assertions only; no unrelated import/environment failures count.
- [ ] Implement the two new pure modules, following the fixed APIs and semantics. No other product edits. Format owned files once before GREEN; run owned static checks once. An unanticipated runtime/test defect or scope expansion requires a new actual Astra plan; ordinary formatting normalization is part of implementation.
- [ ] Run one grouped GREEN of the same two files plus the four named unchanged legacy nodes below. All selected tests must pass without skip/xfail. Save denominator and raw outputs; no per-node rerun or full suite.
- [ ] Root obtains one fresh final review, records the implementation result, limitations and next producer entry in round-local step/phase reports. Address new review defects only under the applicable Astra round. On accepted delivery root commits exact new paths and round artifacts, pushes the existing research branch normally, and verifies local/upstream/live-remote SHA equality. Do not stage raw, secrets or unrelated paths.

## Frozen tests and independent expected values

`tests/test_native_completion_v2.py` (10 functions; bounded loops within a test are allowed, no parameterized node multiplication):

1. `test_joint_triangle_example`: p=(.002,0,0), rc=(0,0,0), x=(.005,0,0), rt=(-.004,0,0), G=.001 => U=.002,L=.003,M=.004,C=.009,endpoint=.009 (approx tolerance); distinct version and unavailable authority.
2. `test_noncollinear_three_dimensional_metric`: p=(1,2,2), rc=(0,0,0), x=(1,2,6), rt=(0,0,-12) => U=3,L=4,M=12,C=19,endpoint=sqrt(329); G=20 makes C=20.
3. `test_pointwise_sum_and_rotated_vertices`: two points with (U,L,M)=(3,0,0),(0,4,0) => C=4, not 7. Separately rotate eight (+/-1,+/-1,+/-1) vertices 90 degrees about z with coincident centers, p=rc=rt=unrotated, x=rotated => L=C=sqrt(8), vertex count8.
4. `test_metric_requires_complete_finite_points`: reject empty/mismatched arrays, non-3D, bool/string/None/NaN/+inf/-inf coordinates, negative/nonfinite G, and finite input subtraction overflow (opposite 1e308 coordinates); do not drop or impute points.
5. `test_metric_reference_drift_and_detachment`: reference moves => M>0 regardless of other values; coincident points => M=0; mutate input lists after return and assert result unchanged; attempted result mutation fails.
6. `test_horizon_rounds_exact_integer_ns`: dt=3_000_000, max duration999_000_000 =>333 base steps; +1ns =>334; each of five inputs independently can determine max; total_sim_ns equals product exactly.
7. `test_lift_release_tails_and_waits`: max duration1_000_000_000, dt3_000_000 => base334, LIFT tail167,total501; RELEASE tail334,total668; extra2 wait steps =>503/670. Assert these are duration descriptions, not physical stability proof.
8. `test_horizon_included_tail_is_not_added_twice`: same inputs, included true =>334 for both LIFT and RELEASE; reject true for MOVE_ABOVE and base shorter than required tail; include every other supported skill with zero tail.
9. `test_horizon_strict_numeric_inputs`: for each integer field reject bool, float even integral, string, None, NaN/inf and negative; zero rejected for dt/durations, accepted for wait; inclusion flag rejects 0/1/None; unknown skill rejects.
10. `test_metric_and_horizon_are_public_diagnostics_only`: direct positive outputs retain SOFTWARE_ONLY/UNAVAILABLE and expose no admission or legacy e/v fields; no construction of backend, owner or source. Mutability/finite-value checks are real API assertions, not source-text matches.

`tests/test_native_completion_calibration_v2.py` (10 functions):

1. `test_nine_complete_eight_action_groups_have_joint_rank_nine`: nine independent groups, all eight actions, each terminal plus one assigned hold sample; valid capture=dispatch10, H5,terminal15. Derived scores from metric API set per-group maxima i/1000, i1..9; n9,rank9,q=.009,all72 actions and exactly16 assigned samples per group included, no unavailable groups and all diagnostics complete. Use actual metric outputs, not a mock q.
2. `test_any_of_eight_actions_controls_joint_score`: vary each skill once to .02 in otherwise .001 complete controls => group/component maximum .02 for all eight, including GRASP and RELEASE. No per-action quantile shortcut.
3. `test_missing_group_action_sample_retains_infinite_denominator`: independently remove one group, one of each eight action observations, or required hold/terminal sample => assigned count9, component count9, rank9,qNone and exact missing context; do not delete its assignment.
4. `test_failed_unknown_incomplete_and_infinite_samples`: each non-COMPLETE outcome even with finite samples, and each None/+inf sample, => affected group/componentNone, correct reason, n9 unchanged. Include malformed score on FAILED input and require ValueError (no validation bypass).
5. `test_exact_assigned_horizon_and_zero_age`: H5,capture=dispatch10,terminal15 positive; terminal14/16, capture9/11, reversed terminal, zero-duration effective observation all produce unavailable diagnostics, not shorter/longer-window acceptance.
6. `test_ancestry_and_fingerprint_merge_transitively`: a-b share ancestor, b-c share fingerprint => (a,b,c); plus six other assignments =>9 assigned,7 independent,rank8,qNone. Missing b still merges and makes its component unavailable; input ordering does not alter output.
7. `test_exact_rank_and_infinity_ordering`: n8 =>rank9,qNone; n9=>rank9; n19=>rank18 exactly. Scores1..18 plus infinity =>q18, unavailable group retained; replacing score18 with infinity =>qNone. n0 is malformed assignment and rejects.
8. `test_assignment_and_observation_schema_is_strict`: reject missing/duplicate assigned action, duplicate group/sample/ancestor/fingerprint IDs, empty lineage/fingerprint/sample tuple, blank/nonstring identity, foreign group/action/sample, duplicate observations, wrong record types, invalid outcome and malformed steps (bool,float,string,negative); no weaker required-action subset.
9. `test_scores_are_strict_and_diagnostics_detached`: bool,string,negative,NaN,-inf scores reject; finite0 accepted; +inf/None unavailable. Mutating outer input lists/maps leaves previously returned tuples unchanged; result mutation fails. Collision-prone IDs `a|b` and `a`,`b` must remain distinct groups/components.
10. `test_finite_joint_diagnostics_cannot_upgrade_legacy_evidence`: calculate finite new q, then call existing native_action_contract using the existing CPU sample helper with that q and VALID claims injected as visual facts; old e/v remain None and validator UNKNOWN. New result's static scope/authority cannot be supplied as constructor overrides.

Also select these existing nodes unchanged, only in grouped GREEN:

```
tests/test_native_action_submit.py::test_unsupported_native_bounds_stay_unknown_despite_claimed_valid
tests/test_native_references.py::test_mutable_grasp_reference_without_future_support_remains_unknown
tests/test_native_references.py::test_fixed_goal_zero_reference_velocity_is_not_zero_body_velocity
tests/test_native_calibration_source.py::test_full_future_wall_bound_missing_is_unknown_when_required
```

## Executable verification and run conditions

Core argv (place exact args, not shell strings, in frozen stage specs):

```
.venv/bin/python -m pytest -q tests/test_native_completion_v2.py tests/test_native_completion_calibration_v2.py --junitxml=<round>/validation/red/junit.xml
.venv/bin/python -m pytest -q tests/test_native_completion_v2.py tests/test_native_completion_calibration_v2.py <four exact legacy node IDs above> --junitxml=<round>/validation/green/junit.xml
.venv/bin/python -m ruff check <the four new source/test paths>
.venv/bin/python -m ruff format --check <the four new source/test paths>
.venv/bin/python -m mypy --follow-imports=silent <the two new source paths>
```

Use the existing R413 bounded_stage.py supervisor with one RED stage and one GREEN stage (each timeout600s, cleanup30s); keep the existing event plugin and R235 import prerequisite where inherited by the selected test bootstrap. Read its spec/env requirements before constructing specs; run through its documented entrypoint, never edit old supervisor/pins. Root may load it and redirect only its ROUND evidence-root global to a fresh R425 supervisor context so `preflight/runtime-source-pins.json` belongs to this round; source code remains byte-identical. Put wrappers/specs/manifests within this round. Retain all stage-owned descendant termination evidence. Do not reuse the R424 runner or its exhaustion loop. A stage env may be derived from existing R424 lease-02 spec only after removing trace/profile fields and changing all output paths; never treat old test argv/source list as this stage's manifest. Do not copy an unrestricted environment containing secrets into evidence.

Preflight is filesystem/source/interpreter/plugin/import availability only, no collection or runtime smoke that duplicates tests. Confirm R235 expected test_operational_time_v1.py SHA exactly matches before enabling it; no fake clock warmup. Require empty profile/trace channels. Test import failure, timeout, unexpected FAIL/ERROR, skip/xfail, dirty source drift or leaked child is not the planned RED; retain evidence and seek the next Astra plan. If the supervisor integration itself is not applicable, pause that integration rather than expanding this kernel into process/timing maintenance.

At most 20 expected new RED assertions, then 24 GREEN tests; one owned static set on the frozen implementation, one final fresh review. No full-suite, per-node supervisor, profiling, benchmark or repeated run until green. Final review may inspect sources/results without rerunning; only an actual new change/failure justifies a targeted new verification plan.

## Acceptance, report, next real producer entry

SOFTWARE acceptance requires exact pinned applicable inputs, 20 expected REDs attributable to absent APIs, all24 GREEN passes, owned static checks, fresh review and preserved evidence. Record actual selected node count from events rather than manufacturing a denominator. A missing source or environment abort is BLOCKED/INCOMPLETE, not RED or PASS. Actual collection=NOT_STARTED, native action acceptance=HOLD, formal research acceptance=NOT_STARTED.

Next mainline step is the bounded original-data reconstruction/producer adapter: preregister complete sample/point inventory and ancestry; obtain p from exact online grounded payload (GRASP from real proprioceptive hold, RELEASE from exact PLACE receipt and registered rigid grasp transform); independently reconstruct offline rc/rt/x/G; prove every registered hold sample and terminal, every horizon inclusion claim, same episode/source/recipe and unique owner/step path. Then call these kernels. That adapter must reject/cache-proof original mismatches before reduction; a tuple of caller residuals is insufficient. Future real producer must establish original D guards, live P4/P5/P6 authority, original-byte inventories, newly assigned independent components and correct same-domain/exchangeability assumptions. Continuous v, future D guarantees, all-path collision freedom, actual settled release and actual object lift are not supplied by this kernel. Only a separately reviewed producer/source/consumer implementation and fresh real evidence can advance those boundaries.

Self-review: fixed scope covers the three named arithmetic slices; all five review concerns have tests. Deliberately deferred interfaces and real evidence obligations are explicit. No legacy semantics or original experimental bytes are modified.
