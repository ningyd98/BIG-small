# Task2 UTC reader fix independent review

**PASS_SCOPED — the qualified missing/null UTC sample reader and assigned-group diagnostic retention defect is closed.** The round-2 REQUEST_FIX and original RED evidence remain unchanged. This approval covers software structure/refusal/denominator behavior only; native source activation remains unapproved.

The exact producer diff adds outer dictionary, independent-source dictionary, samples list, exact sample-row keys, pair-hash SHA and UTC string validation before field dereferences and timestamp parsing. Existing aware/ordered brackets, complete original-pair inventory and independent-source checks remain. Malformed fields now raise ValueError and enter the existing per-group refusal path. `_group` did not gain a broad exception handler, and no assigned group or UNKNOWN score is removed.

The only other production difference imports Pose and constructs `RobotState.tcp_pose` explicitly from the existing RawV3-validated three finite xyz values. The original static typing failure and final source snapshot are preserved. This does not change the completion quantity or source authority. `vision/native_calibration.py` is byte-identical to round 2; source/current producer joins, strict preregistration, exact full horizon, owner policy/endpoint/compiler checks and app index/catalog gates remain intact.

The **exact original** `fix-round-2/independent-clock-reader-probe.py` SHA remains `0225ea99a501d27e0281ac7badde5fe4f5c129cd22114caac9a92e51a1fc1c6c`. Its fresh replay passes without source edits, boundary replacements or changed assertions. All four SOFTWARE_ONLY real-reader cases have RawV3 COMPLETE, empty source reasons, assigned=independent=geometry quantile count=1, retained unavailable group identity and geometry/action bounds=None. The complete clock stays INCOMPLETE with `reset_utc_originals_unavailable`; missing-whole-sample, missing-pair-hash and null-lower-UTC cases now return INVALID with `independent_clock_originals_invalid`. No case throws KeyError/TypeError or returns a finite bound. See `independent-clock-reader-green.log`.

The original producer/asset consistency and component-collision replay also passes on this revision. Wrong known producer/asset hashes remain INVALID, missing trusted UTC stays unavailable, and the `a`, `b`, `a|b` case retains eleven assigned groups, ten components, n=10/rank=10 and UNKNOWN in both geometry/action quantiles. See `independent-original-replay-green.log`.

Fresh independent checks, each exit 0:

- **61 Task2 CPU tests passed in 23.81 s**, including eight additional malformed-structure negatives; `independent-cpu.log`.
- Ruff passed on the three owned Task2 files; `independent-ruff.log`.
- Format check reported three files already formatted; `independent-format.log`.
- Mypy with `--follow-imports=silent` passed on two owned sources; `independent-mypy.log`. The existing unused-section note remains.
- Both unchanged independent real-reader/old-counterexample replays passed, as described above.

No broad suite was repeated. Earlier 53/175 results remain historical for their original revisions; counts are not additive. The root's eight-case qualified unit RED (8 failed, 53 deselected) and initial mypy RED are preserved.

`independent-preservation.json` records the exact eight-file/116563-byte round-3 baseline, old REQUEST_FIX/RED/probe/report pins, previous round-1/round-2 baseline and Task1 preservation checks, current three source/test pins, final source snapshots and author evidence pins. All were rechecked after verification. Current inputs:

| File | SHA256 |
| --- | --- |
| vision/native_calibration.py | 0888c38f4caf4dd65c27c29315d8253a1aa8fa1a6fece0bf2b18bcc9bcedb2a6 |
| research/native_geometry_calibration.py | 7d555c23c5d2ffcdc1a9ba5aacd4601c71e1f6691b69da56893fad6b45dc822d |
| tests/test_native_calibration_source.py | 0363bfd373810b1377e07c09aa7284bbc779bd86c19219031c3644b503a0f473 |
| fix-round-3/implementation-report.json | 9bcf3c281ede9907fb1c0c6dbfc752be1008c5f866ea38035f27e083d8a68cef |

No genuine app-owned index/catalog, independently authenticated UTC acquisition/reset originals, nine genuinely independent supported calibration groups or actual native finite publication has been obtained or covered. v1 still cannot provide reset chronology, so its real calibration candidates remain unavailable. The SOFTWARE_ONLY source/UTC arithmetic controls and mocked numeric estimate controls do not establish the true app-owned positive branch, empirical coverage or native activation. The deferred versioned reset capture/publisher, authenticated assignment/history, complete exact horizon/policy/geometry/contact/TCP joins, consumer activation and scoped real validation require separate evidence. Continuous/future-motion, safety/effect/holding, model/Max/formal validation and edge hardware remain outside this approval.

Only new round-3 `independent-*` review/JSON/log artifacts were written. No production/test, Task1, old evidence/baseline/raw/archive/header/Stage file or Git state was modified by the independent reviewer; no actual acquisition, renderer, physics, controller, model, provider, hardware operation or download was run.
