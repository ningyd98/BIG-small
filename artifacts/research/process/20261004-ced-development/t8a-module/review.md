# T8a independent module review

Review date: 2026-10-04. Scope: supplied `review-package.diff`, `report.json`, module docstring, existing pool/capture/backend/independent-evaluator contracts, and ced.research.v2 sections 4, 5, 8 plus roadmap T8a. All four new-file package snapshots match the inspected working files. Read-only source review; no tests, model calls, network calls, GPU, renderer, or physical experiments were run. Only this review was written.

**Specification verdict: REQUEST CHANGES; useful offline prototype, insufficient as the independent formal-evidence acceptance gate.**

**Code-quality verdict: REQUEST CHANGES.** Positive contracts include measured fault displacement, fixed alternating disturbance parameters, independent lift/hold/place and safety evaluation, rejection of no-fault success, finite physics-array validation, physical-group isolation, retained bounded attempts, raw byte hashing, and explicit offline access roles. The report/docstring correctly state that actual generation/freezer integration and all 200 physical proofs are pending. The existing 18-pass log was inspected, not reproduced. No fixture was counted as research evidence in this review.

## Findings

### P1 — COMPLETE does not require the fixed formal pool topology

Location: `research/protocol_evidence.py:128-145`, `:601-602`, `:686-692`.

The pool check verifies uniqueness and scene/group hashes, but not required pool names, formal size, registered strata, ordinal assignment identities, or assignment perturbations. The completion condition requires only a nonempty formal dictionary and 200 proven recovery groups. Thus one arbitrary formal opportunity plus 200 recovery proofs can be called COMPLETE despite the specification's 2400 predeclared formal candidates and fixed isolated development/formal topology. Changing `stratum_id` or `perturbation` also does not affect the independently checked scene hash.

Validate against an externally fixed expected pool identity/schema (or enforce the complete prescribed topology), bind the full assignment rows and candidate schedule, and return INCOMPLETE for a deliberately partial input. Generator/freezer integration may be pending, but the independent verifier must not label a reduced formal pool complete.

### P1 — arbitrary images/instance IDs and unsupported context can yield a formal VALID label

Location: `research/protocol_evidence.py:199-244`; input bundle schema in the module docstring at `:9-14`.

The label routine checks only matching image dimensions, an arbitrary positive instance integer, valid-depth fraction, and truthy episode/frame strings. It accepts the test's 8×8 image and float64 depth as VALID, requires no calibration, optical-z convention, intrinsics/extrinsics, capture-pass synchronization, physics state hash, or instance-ID-to-object mapping. A distractor's ID can be declared the target ID. The capture episode/frame/TCP/action are not independently tied to an assigned raw physical context or a predeclared candidate set. The geometry uses static scene distractor boxes and a straight TCP sphere while ignoring the row's dynamic/sensor perturbations and full manipulator trajectory. The docstring discloses this narrow scope, but that applicability limit is not encoded in the accepted label or COMPLETE decision.

Use the existing calibrated 320×240 capture evidence, bind semantic instance mapping and actual capture/context/candidate identities, and explicitly encode/check geometric applicability. Unsupported arm/dynamic context or missing identity/calibration must remain UNKNOWN/INCOMPLETE rather than becoming an unqualified formal VALID label. Do not substitute the scoped TCP test for actual controller-path safety.

### P1 — a trace trimmed after reset can still prove recovery and safety

Location: `research/protocol_evidence.py:325-345`, `:357-378`, `:399-407`.

The first observation is checked for approximate initial XY/size, but its physics step/time need not be reset step 0. The reused evaluator requires consecutive steps only from the first supplied row (`episode_evaluator.py:349-368`). Removing an unsafe early prefix while retaining a stationary pre-fault row, injection interval, and successful recovery suffix therefore retains PROVEN and scoped-safe outcome. This contradicts the input contract's reset plus every-step raw trajectory and loses safety evidence before the retained prefix.

Require an independently bound reset record and complete step sequence from that reset through the terminal collector step. Treat missing prefixes/tails as INCOMPLETE; retain and evaluate every collected safety observation.

### P1 — teacher action markers and actuator commands are not joined into an execution proof

Location: `research/protocol_evidence.py:379-398`.

Any nonempty action type with in-range start/end steps passes the teacher check, and one accepted `move_joints` or `set_gripper` anywhere in the entire recovery time interval passes the actuator check. The command need not fall in any declared teacher action, identify the same episode/source, have finite/validated target parameters, or account for the trajectory that produces the measured success. For example, replacing the teacher interval with a short later `NOOP` marker while leaving an earlier unrelated accepted command and the success trace satisfies these predicates. A marker plus one command is not actuator/step provenance for the teacher recovery.

Collect typed teacher action IDs, actual command targets/episode/step IDs, and controller dispatch-to-step provenance; validate supported actions, their ordered intervals, and their matching accepted command/physics progression. Reject unrelated or absent links. The existing backend command list lacks these fields, so this needs an explicit collector integration contract rather than inferring execution from the current markers.

### P2 — attempt audit accepts duplicate/foreign ordinals and does not enforce first successful attempt

Location: `research/protocol_evidence.py:634-656`, `:676-682`.

Audit entries are filtered per known assignment, with only their count bounded. There is no validation of unique consecutive `attempt` numbers, unknown assignment entries, mandatory raw/hash fields by status, or the producer's first-PROVEN selection rule. Duplicate ordinals and unrelated attempt entries can remain integrity-valid; a later PROVEN bundle can be selected despite an earlier PROVEN bundle. This weakens the preregistered full attempt denominator and allows selection of a convenient recovery proof.

Validate the complete attempt identity set and per-assignment ordinal sequence, independently reconstruct every available attempt including failures, and enforce the first successful attempt as the fixed proof.

### P2 — nonfinite fault-event timestamps bypass alignment validation

Location: `research/protocol_evidence.py:58-59`, `:357-364`.

The JSON reader accepts NaN, while event-to-observation time checks use `abs(observation_time - event_time) > tolerance` without a finiteness check. With a valid step key and a NaN event `sim_time_s`, that comparison is false and the injection is accepted; duration/proof are subsequently derived from the finite observation times. Finite raw physics arrays do not close this separate event-timestamp hole.

Reject nonstandard JSON numbers or explicitly require finite numeric event timestamps and strict step types before alignment. Also independently validate the raw contact basis for an early `finger_contact` termination rather than trusting its reason string alone.

### P2 — fresh-output and destination containment are checked too late

Location: `research/protocol_evidence.py:62-64`, `:142-143`, `:417-423`, `:444-449`.

Preparation accepts an existing nonempty output when three sentinel files are absent. Writes/copies then follow existing destination symlinks without checking canonical containment; an existing `output/raw` symlink can write raw files outside the chosen output before `_inside` rejects them during verification. Assignment ID `..` also passes the basename test and escapes the intended `raw/<assignment>` namespace. This is a concrete destination/source-isolation issue, even though archived reads use `_inside`.

Require an empty exclusively created destination, safe assignment IDs excluding dot segments, and canonical containment/no-symlink checks before every destination write/copy. Do not overwrite partial output or existing files.

### P2 — manifest validation does not require complete payload coverage

Location: `research/protocol_evidence.py:578-589`.

The verifier hashes only entries supplied by `payload_hashes`; it never requires the referenced control manifests and all archived files to appear in that mapping. Omitting the `evidence-pools.json` hash leaves assignment-only fields unprotected because `_pool_check` validates scene identity but not the full assignment. Missing checksums should be an integrity failure, not a valid incomplete hash manifest.

Require exact required/archived payload coverage, validate manifest flags and digest syntax, and bind the manifest's external frozen root hash at integration. The missing external freezer binding itself remains a pending root task, not an assertion that self-reported hashes authenticate measurement origin.

## Cannot verify / integration dependencies

- No actual fixed formal captures, 200 actual injected safe teacher recoveries, selection scan, or INITIAL freeze exists in this package. Keep physical evidence INCOMPLETE and all G4 performance unmeasured.
- Trusted collector/source snapshots, complete historical-root enumeration, integration of typed action/command provenance, source-role hashes, fixed candidate topology, and the strict freezer gate are pending root work. This verifier cannot establish sensor authenticity from caller-authored files.
- The offline role check is an API/CLI boundary; arbitrary filesystem readers require orchestration isolation. This accurately disclosed limitation is not an additional finding.
- The scene swept-path evaluator is useful only within its explicit static straight-TCP geometry scope. Formal gate applicability to real arm skills, dynamic distractors, and sensor-defect strata is not established.

No separate Minor finding.
