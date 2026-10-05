# Registered raw risk-source reader: first bounded implementation

Only two new production/test files are owned: `src/cloud_edge_robot_arm/research/risk_sources.py` and `tests/test_research_risk_sources.py`. The approved design is frozen separately in `t9-actual-risk-source-design`. No existing fit/calibration/CLI/admission/runtime/source/asset/config file or historical artifact was edited. There was no simulation, rendering, model request, account/key access, source collection or actual risk fitting.

The reader now independently reconstructs saved **RAW_EXECUTION** source consistency. **RISK_SUPERVISION remains UNKNOWN** because genuine INITIAL source audit, risk-label source, wall/simulation clock mapping, calibration and risk-selection replay are unavailable. Formal source eligibility is always false; no method/execution admission field is emitted. This first module does not complete actual T9 calibration or METHOD. The next risk replay/runtime integration tasks remain outstanding as described in the design.

## Exact API and scope

`RiskSourceAuditor(registrations).audit(evidence_id, *, scope='RISK_SUPERVISION') -> RiskSourceAudit` accepts only a server-registered evidence ID and one of RAW_EXECUTION/RISK_SUPERVISION. It has no arbitrary VALID callback, caller-root API or persisted receipt authority. The application-owned registration fixes all assigned original attempts, full per-attempt byte inventories, expected counts, complete scene/context, evaluator criteria, current validating-helper sources, asset and optional actual RoleRuntimeBinding. Nested data/source/policy/provider maps are copied and frozen.

Every audit rereads all original files and current helper sources before/after reconstruction. Paths, root ancestors and payload ancestors reject symlinks/traversal. Exact registered file coverage cannot shrink or grow silently. Unknown or malformed JSON/table/physics shapes fail validation; missing assigned attempts remain UNKNOWN rather than disappearing. Expected registration digests for missing/invalid originals remain in `original_file_hashes`; actual successful rereads are separately listed in `verified_original_file_hashes`. A digest table alone never implies acceptance.

Counts retain the complete `allocated` denominator and separately show reconstructed, independently physically failed, physical-success and unknown attempts. A reconstructed task failure is a valid raw source reconstruction, not an accepted task success. Unsupported/missing sources retain their attempt and reasons. This is reset/command/controller/frame/evaluator consistency, not cryptographic collection authenticity, complete physical safety certification or a MuJoCo dynamics replay.

## Implemented raw adapters and actual result

The explicit adapters are CED_PILOT_RAW_V2 and MARKER_MOTION_DEVELOPMENT_RAW_V1. They reconstruct every raw PhysicsStepObservation, check reset0 through terminal step/time, strict row/schema/episode/step identities, full reference collision scope and the immutable evaluation start120. The complete source scene/reset and initial controller basis are checked. Commands start at sequence1; every pre-step actuator joins the previous physical q/time, accepted dispatch targets, clamp±2.8, controller error clamp±0.10, gravity bias/gain and control range. Command/action prefix, terminal tail and frame counts remain bound to original registration.

Typed action ranges are source joins, not independently inferred action-success labels. Known teacher `hold_current_joints` dispatch at an action's end_step is allowed only as that boundary operation; its subsequent actuator application remains in the complete trace. Marker action declarations/unframed scope must reproduce original range rows. Original RGB/depth/mask bytes, full embedded RGBD, acquisition identity/time and marker decoder result are checked; every initial/post-action marker boundary must be present.

The **existing CED collector does not currently persist typed raw-actions.json ranges**. A CED source with commands and missing action ranges therefore remains UNKNOWN (`CED_raw_action_ranges_unavailable`); the reader does not infer action count/success from dispatch count. A genuine CED request additionally requires the complete paired/base assignment join, current role binding/source hashes and current asset. Missing actual role/source remains UNKNOWN. Pure SOFTWARE_ONLY fixtures test CED table/hash/parser reconstruction and its negative boundaries; no synthetic actual CED positive is claimed.

The one real saved marker-motion attempt is explicitly excluded development. Its existing raw files were only read, not recaptured or modified. The reader independently derives **4807 PhysicalSamples**, checks **4806 actuator steps**, **743 commands**, **9 action ranges**, **10 original RGBD observations** and marker replays. Its scoped simulator physical outcome matches the original successful transfer, while **nine post-action marker frames remain UNKNOWN**. Both facts are retained. RAW_EXECUTION is VALID within RECORDED_SIMULATION_RAW_ONLY, RISK_SUPERVISION remains UNKNOWN, formal eligibility remains false. No geometric/motion bound, INITIAL, METHOD, G3/G4 or actual formal task acceptance follows.

## TDD and validation evidence

Initial collection RED was the expected missing new module/API. The first implementation exposed seven failures; later passes exposed actual-layout differences and three strict-shape/role-snapshot failures. All original logs are retained. Corrections included separating initial physical finger position0.04 from control target0.039, explicit scene group identity, end-boundary hold semantics, the existing valid-mask accessor, full paired/base assignment hashing, strict null/list summary rejection and immutable provider snapshot copying. No blanket AttributeError catch was added.

Additional failed-original-hash RED exposed loss of registered hashes when an original attempt was unavailable; the output now preserves expected hashes for every attempt and distinguishes verified bytes. A final test regex spelling error is retained in `final-owned-cpu.log`; its corrected run is separate. Diff generation for new files exits1 by normal `git diff --no-index` semantics and was not a test failure.

Verified final commands/results:

* New scope: `.venv/bin/python -m pytest -q tests/test_research_risk_sources.py` — **35 passed,9.77s**, `final-cpu-with-original-hashes.log`.
* Related unchanged math/marker regressions: risk calibration, marker evidence and marker assets tests — **59 passed,1.47s**, `related-cpu.log`. These counts are separate software sets, not research episode counts.
* Owned Ruff and format — PASS, `final-ruff.log` and `final-format.log`.
* Cold `mypy --no-incremental` on the new production source — PASS one source, `final-cold-mypy.log`; existing unused-section note retained.
* Immutable dependency overlay: PYTHONDONTWRITEBYTECODE=1, PYTHONPATH pointing to frozen source/src, pytest with cacheprovider disabled/confcutdir at the frozen source — **35 passed,9.68s**, `frozen-overlay-cpu.log`. This verifies the archived source/fixture closure rather than silently importing live owned files.

No full repository suite or extra physical/model runs were conducted. All saved task evidence remains at its original hashes. `source-hashes.json` freezes **545 files**, including exactly two owned files, the current local Python namespace, validating helpers, scoped tests/configs and complete original excluded-motion fixtures/source references. The broader namespace copies are historical dependency context, not new role or risk acceptance. Manifest SHA256 is `b8eedda6ef991631a175d8a9c0ee71c4f61e514a0b2a45f9ea92c50475b4cbe8`.

## Remaining implementation boundary

This release can audit raw execution originals. It cannot yet independently reconstruct the frozen risk-label horizon, registered geometric estimator error, independently measured calibration feature source, whole-action clock/motion residuals, connected risk allocation/split/exclusion closure or train/calibration/candidate-selection artifact replay. Consequently its risk scope is intentionally closed and cannot be wired into estimate_risk as a positive permit. Current risk-file source_accepted flag semantics, CLI authority gap, actual risk estimate/selection and native admission are unchanged. A later reader/replay/owner integration must supply these sources and pass the design regressions before actual risk or METHOD can become admitted.

Sources and the review package are now frozen for independent review; implementer software validation is PASS, independent review is pending. Actual risk calibration and formal execution remain NOT_RUN.
