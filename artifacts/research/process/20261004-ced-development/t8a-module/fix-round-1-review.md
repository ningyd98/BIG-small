# T8a independent fix-round-1 review

Review date: 2026-10-04. Scope: original `review.md`, frozen `fix-round-1.diff`, `fix-round-1-source-hashes.json`, appended `report.json`, and the exact current protocol verifier, rules, CLI and tests. All four manifest hashes match current files. No production code was edited. No network, GPU, rendering, physical simulation or full suite was run.

**Scoped specification verdict: REQUEST CHANGES.** The original eight findings have substantial effective fixes; one execution-accounting boundary remains open below. Actual formal acceptance remains pending independently of this software verdict.

**Code-quality verdict: REQUEST CHANGES.** Only one remaining P2 finding; no separate P1 or Minor finding. This round materially improves fail-closed behavior, raw-source coverage and auditability.

## Original findings

1. Fixed topology: v2 now requires the six isolated pools totaling 3260 assignments (selection/foundation/power 120 each, formal 2400, recovery 200, OOD 300), canonical ordinal IDs and strata, balanced registered perturbation cycles, full assignment digests and fixed candidate specs. Partial pools and legacy v1 remain INCOMPLETE.
2. Label applicability: calibrated 320×240 optical-z float32 RGB-D bytes, assigned camera, episode/frame, semantic target map, raw capture state/pass hashes, oriented physical geometry and fixed MOVE_TCP execution are checked. Full reference-arm collision scope and actual command/control provenance replace the old straight-TCP-only shortcut. Unsupported or missing context yields UNKNOWN/INCOMPLETE; observable sensor defects can remain UNKNOWN with verified geometric applicability. No caller-supplied success boolean substitutes for these checks.
3. Complete reset/terminal trace: typed v2 collector headers bind reset step/time 0 and both endpoint hashes; every physical step and actuator step must be present. The reused independent evaluator checks safety across the entire trace, including the pre-recovery prefix.
4. Execution proof: exact nine-action T5 sequence, strict actual ActionResult, contiguous dispatch intervals, typed command ranges, episode/time/step/target joins and per-step reference controller reconstruction now exist. Terminal hold dispatches are supported. The remaining command-prefix issue below limits closure of this finding.
5. Attempt accounting: foreign assignments, duplicate/nonconsecutive ordinals, missing raw/hash status fields and changed eligibility/fault schedules are rejected; the selected proof must be the first independently PROVEN ordinal, while failed/incomplete/excluded attempts remain archived.
6. Fault events: nonstandard JSON numbers and nonfinite numeric event values are rejected; early finger-contact termination requires physical contact evidence.
7. Output safety: exclusively fresh output directories, safe ordinal IDs, no-symlink writes/copies and contained source reads are enforced before writes.
8. Manifest coverage: exact archived inventory, required control manifests, strict flags/denominator, valid digests and full pool/candidate lock reconstruction are mandatory.

## Remaining finding

### P2 — the complete command audit permits an omitted reset command prefix

Location: `src/cloud_edge_robot_arm/research/protocol_evidence.py:631` and `:768`.

`_execution` derives `first_sequence` from the first supplied backend record, then checks only `range(first_sequence, sequence_cursor)`. The backend resets its command list for each episode and emits 1-based sequence IDs; the adapter promises the complete reset-terminal command history. A source beginning at sequence 2 therefore necessarily omits a dispatch, but the verifier accepts it when action ranges use the same offset. Initial controller targets are taken from the provenance header rather than closing that missing-dispatch identity.

Independent synthetic CPU reproduction reused the software recovery fixture, incremented every `backend_record.command_seq` and both action range endpoints by one, and left physical samples, exact actuator controls, targets and other IDs unchanged. `prepare_protocol_evidence` returned `integrity_valid=true`, `errors=[]`, `recovery_proven=1`; first backend sequence was 2. Overall status stayed INCOMPLETE because the fixture pool is deliberately partial. This fixture is not actual recovery evidence. Reproduction artifacts: `/tmp/ced-t8a-rereview-uhn4yncm`.

Require the episode command sequence to begin at 1 for the supported complete collector contract and cover all dispatches through the final action. If a future scope supports pre-teacher dispatches, archive and validate their prefix separately instead of accepting an arbitrary starting sequence. Add an adversarial fixture that drops/offsets the command prefix and expects no PROVEN recovery.

## Verification and evidence limits

- Independently ran only `.venv-data/bin/python -m pytest -q tests/test_protocol_evidence_generation.py`: **49 passed in 17.89s**. These are offline synthetic contracts; no actual simulation was initialized.
- Verified all four frozen source hashes; inspected the reported related-test/static-check evidence without rerunning those suites.
- The passive `write_recovery_source` adapter serializes detached existing observer records and actual action results; it performs no stepping, rendering, model inference or new actuator behavior.
- Previously inspected development evidence contains 5368 physical states, 5367 actual controls and nine successful teacher actions; its separate audit has zero integrity errors and one proven recovery, while formal topology is incomplete and `g4_measured=false`. This review does not convert historical source hashes or that single development case into a formal accepted version.
- Complete historical-root enumeration, trusted collector and frozen role/root bindings, actual fixed formal captures, 200 preregistered actual injected safe teacher recoveries, INITIAL freeze and online G4 remain external pending work. Self-reported hashes authenticate bytes, not measurement origin. Filesystem label isolation also requires orchestration controls.
