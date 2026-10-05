# Raw-v3 immutable recorded-source schema

Status: SOFTWARE_ONLY checks complete; independent review pending. Scope: SOURCE_CONSISTENCY_ONLY. Actual INITIAL, METHOD and EXECUTION admission remain unavailable; this module neither samples nor grants authority.

The two new files define strict immutable physics, control, command, action, acquisition, frame-join and clock records, and a pure whole-episode consistency validator. Complete recorded input can produce COMPLETE instead of a permanent UNKNOWN stub. COMPLETE means the supplied graph is internally complete and consistent; it does not certify authentic files, a real owner lease, a genuine clock source, calibration, continuous motion, physical success or permission to execute.

## Frozen ownership and reference basis

Owned NEW files:

- `src/cloud_edge_robot_arm/research/raw_episode_v3.py`
- `tests/test_raw_episode_v3.py`

The frozen closure has 774 files: the exact independently reviewed owner-repository fix1 772-file source plus these two new files, with no reference overwrite. Reference manifest SHA256 is `0271d4785ef84c7a4f5fdcf4efd0ded0e9baccec02f7351f04d7b9bde4a917d6`; its root independent review SHA256 is `c48270fa86423028cfe1033a71e8210c9082f63a17fc79eba4bfd8864034eb53`. New raw-v3 manifest SHA256 is `cdd6684f4dcf28e09ba0e6f2e36dc95c2640d594726d297781ef77d07bad8bc0`.

The moving `worker_owner.py` work is excluded. Existing backend, camera, execution, worker, writer, risk reader, assets and configurations were not edited. Source files are in `source/`; `ownership.json`, `source-hashes.json`, `review-package.diff` and `public-contract.md` identify the exact release. The approved read-only design remains at `../t8-raw-v3-collector-design/`, reference manifest `a20b507772d006f02352c70318f3b5b1db224c45acce2d2a20b1526a1127ed92` and report `b926fabe4926aa4354855a07f7c8d07a6b46398194bb1a5cea211c862b5f0803`.

## Concrete behavior

Constructors and strict JSON decoding reject booleans used as numbers, numeric strings, oversized integers, nonfinite values, naive/reversed timestamps, duplicate/unknown JSON keys, malformed hashes and placeholder identities. Public subclass records and nested owner requirements are rebuilt into concrete types from declared fields; overridden serialization/digest methods and mutable nested aliases cannot define the frozen source. Serialization returns detached JSON-compatible data.

The validator retains allocated attempts and input records when observations or effects are absent. Missing original rows and partial/aborted intervals produce INCOMPLETE with precise reasons; contradictions produce INVALID. Malformed schema construction raises ValueError. Declared huge missing physics/command tails retain the full denominator without allocating or iterating the missing population.

Physics uses `(n0,n1]` while commands use `[c0,c1)`. Every original step has a pre-control, post-physics and explicit purpose interval; evaluation begins after the full 120 SETTLE steps. Commands retain their original order, accepted/rejected state and effective-step provenance. Initial controller targets, arm clipping, holding, gripper targets and delayed target application are replayed from all commands, including commands overwritten in the same step and effects appearing in a later passive interval. The control equation is checked against the supplied raw targets, bias, gain and limits. This checks recorded source consistency, not independent dynamic truth or asset authenticity.

Each typed action binds its original compiled plan and complete canonical policy separately from optional derived grounding. Full actually submitted TaskStep arguments must equal the original or grounded step; their absence is INCOMPLETE. Timeout, retry, targets, conditions, sensors, tolerance, error, TTL and expected duration survive the original requirements type. Plan-version reuse cannot change the original payload; task, verification and contract deadlines are individually forbidden from extending. ONLINE_CED started attempts require grounding, exact current frame/calibration/source identity and any longer-horizon duration-check binding. Those source bindings are not actual owner or duration authority. The action return's recorded physics-step count is checked against its raw interval; zero-step rejection retains its denominator and cannot contain effects. Simulated ActionResult duration is never substituted for actual monotonic return time.

Native camera binary state hashing is replayed from full recorded time/qpos/qvel/act/ctrl arrays and kept distinct from the canonical PhysicsStepObservation digest. Explicit state joins compare measured arm/finger arrays and the recorded physical index/time. RGB/depth/mask byte checksums and original file inventory must match. SOURCE and derived ONLINE inputs share the same physical acquisition interval; source metadata, exact corruption recipe/source inventory and transformed saved pixels are recomputed. No new acquisition or renderer is called.

Every physics, control, command, passive-purpose, action and acquisition interval uses the same frozen clock descriptor, owner epoch and paired monotonic/UTC domain. Original pair order and monotonic bounds are checked, while UTC offset brackets must intersect. `utc_uncertainty_ns=None` remains UNAVAILABLE. Finite ordered time samples are not a continuous-motion certificate; there is no endpoint interpolation or simulated-to-wall 1:1 mapping.

## Denominators and limitations

`recorded_acquisitions` is retained as the allocated input-record compatibility count, not the number of camera calls. The view explicitly includes `recorded_acquisition_records`, `distinct_acquisition_intervals` and `derived_online_inputs`; a SOURCE/ONLINE derivative pair contributes two input records and one physical acquisition interval. Failed input records stay in allocated/missing counts. Every disposition and original row remains available in the caller-supplied immutable records.

This module performs no source-file IO, disk identity audit or real monotonic/UTC measurement. Callers supply the source inventory and original bytes. A later concrete registered collector and independent source auditor must establish their authenticity, clock uncertainty, genuine owner registry and actual preconditions. Legacy raw-v1/raw-v2 were neither migrated nor overwritten. An incomplete ONLINE_CED grounding record cannot acquire authority by supplying a boolean, VALID callback or receipt; no such API exists. Software fixture source hashes and clock values have no actual scope.

Current Safety-limited execution arguments are not silently treated as a matching original/grounded payload. A later separately sourced deterministic derivation is required if that executor boundary changes them. This block is not wired to the real worker, durable repository, provider, mode selector, SafetyShield or SkillExecutor. It cannot dispatch, resume or activate recovery. Actual method/calibration/selection prerequisites remain absent.

## TDD and verification

Qualified missing-module RED is saved in `red-missing-module.log` and `red-schema-and-coverage.log`. Subsequent precise RED logs cover the separate camera hash domain, initial-target/effective-step replay, unbounded missing population allocation, substituted execution arguments, retry policy, extended original deadlines, boolean return step counts, malformed transform policy and unchanged ONLINE bytes under a nonzero recorded corruption policy. The logs are retained without replacing failed observations with GREEN summaries.

All fixtures are SOFTWARE_ONLY and use hand-built saved 2x2 pixels, original pure-owner fixtures and recorded numeric rows. Tests construct no MjModel/MjData and perform no simulator step, capture, renderer, controller action, provider/model/network call or research episode.

From the isolated frozen 774-file copy:

- 45 owned plus 48 reviewed pure-owner dependency tests: **93 passed in 14.99s**, `frozen-tests.log`.
- Owned Ruff: PASS; format check: both files already formatted.
- Cold mypy for the new source: PASS, one source checked.
- All 774 archived and isolated source hashes match after checks; all Python sources parse; the two live owned files still match. See `post-check-hashes.json`.

The exact argv/environment/cwd are saved in `frozen-overlay-setup.json`, the expanded 93-test list in `collected-tests.log`, and return codes in `frozen-check-results.json`. Checks used the reviewed immutable closure rather than current moving imports. No full suite, simulator workload, commit or publication was run.

## Next integration boundary

Root-owned subsequent work can register the clock/source descriptor and emit immutable intervals at actual pre-control/post-step, dispatch, acquisition and sole executor entry/actual-return boundaries. It must retain failed attempts, original sequence/effect timing, camera source derivatives and unknown uncertainty. A concrete disk/source auditor and current owner/grounding/deadline verification remain distinct prerequisites. No existing submit gate or all-pending duration/evidence requirement was weakened by this schema block.
