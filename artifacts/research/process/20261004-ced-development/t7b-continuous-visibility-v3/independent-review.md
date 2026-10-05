# Custom V3 collector independent software review

**REQUEST_FIX — two qualified P2 software replay defects.** The frozen runner/reader/test/header/manifest pins match the handoff. Independent 61 CPU tests pass, but six additional counterexamples make malformed or incomplete original traces return VERIFIED. No actual collector, MuJoCo model/reset/physics/renderer, decoder, provider or hardware operation was run.

## P2: operation and actuator original identities are only partly joined

`verify_offline.py:570–607` retrieves CONTROL/PHYSICS BEGIN and END by operation ID and requires their nominal clocks to be ordered. It checks PHYSICS END kind/step and its frame/physics-result identity, plus CONTROL END kind/step. It does not validate the full expected kind/episode/step/time identities of the BEGIN rows, CONTROL END episode or ACTUATOR episode.

The SOFTWARE_ONLY probe uses the existing saved-byte CPU fixture and calls the real `verify_attempt()` and source/header/guard/index readers without replacing a validator. Starting from its accepted baseline, each of these separate variants still returns VERIFIED, failures=[], allocated=verified=3:

- PHYSICS BEGIN `physics_step=999`.
- CONTROL BEGIN `kind=COMMAND`.
- CONTROL END `episode_id=wrong-episode`.
- ACTUATOR source `episode_id=wrong-episode`.

The valid upcoming ACTUATOR identity is n while preceding CONTROL and PHYSICS BEGIN identities are n−1, and PHYSICS END/frame identities are n. Bind every joined original to the same episode, exact expected kind/phase and step/time domain, and preserve complete unique operation and actuator identities. Correctly ordered clocks and a matching operation ID alone cannot repair a contradictory source record. Reject these variants before decoder eligibility.

## P2: unmatched original acquisition BEGIN/FAILED rows are omitted from replay denominators

`verify_offline.py:414–454` records acquisition BEGIN/END rows but ignores ACQUISITION_FAILED. The subsequent loop at `:511` visits only the declared series horizon. The checks at `:624–635` compare summary counters with declared/END counts; they do not require the complete original BEGIN set to equal the allocated set, nor join failed original records to refusal/counts.

Appending either a well-sequenced, clock-ordered extra ACQUISITION_BEGIN at step 3 or ACQUISITION_FAILED at step 3 to the accepted three-frame fixture still returns VERIFIED, failures=[], allocated=verified=3. The original journal now contains an additional attempted/unavailable acquisition, but the replay accepts the old zero-failure summary and shortened horizon denominator. This contradicts the required allocation-before-BEGIN and retained BEGIN/END/FAILED denominators.

Derive and reconcile the full attempted, successful and failed source-event sets with summary/index/terminal counters. Reject unmatched or out-of-horizon BEGIN, END or FAILED rows, contradictory terminal summaries and retained failure events. Preserve every allocation and orphan/partial record in the refusal diagnostics; do not trim the journal or delete the failed allocation. Apply the same complete-set discipline to action lifecycle records when reconciling their existing separate counters.

## Qualified evidence and independent checks

`independent-reader-probe.py/.log` retain the exact fixture-based variants, accepted baseline and real production reader calls. All input-tree hashes remain unchanged during replay; outputs are outside inputs in isolated /tmp trees. The final assertion expects the six malformed/incomplete variants to be refused and deliberately produces **exit 1**. The fixture's fake source archive/runtime/ndarray records are software controls and establish no acquisition authenticity, native admission or physical coverage. Decoder is false in every probe call.

Independent fresh verification, each exit 0:

- 61 owned V3 CPU tests passed in **3.49 s**; `independent-cpu.log`.
- Ruff passed on runner, reader and CPU tests; `independent-ruff.log`.
- In-memory AST/compile passed for those three files without executing their CLI; `independent-compile.log`.

The author's 61 tests overlap this independent suite and are not additive. Green tests do not cover the six qualified source/journal variants above.

Static review confirms the runner composes all eleven original protection components with the reviewed support-aware dynamic-array contract, revalidates real data views, compares full guarded snapshots and the supplementary two-pass physical hash, and restores wrappers in finally. Acquisition/action allocation increments occur before BEGIN publication; camera calls increment immediately before delegation; successful acquisition/action END counts increment after publication. FAILED publication errors retain notes on the original exception and no retry is allowed. The corrected dtype/shape/byte contract source and its independent root review pins remain intact. These software observations do not substitute for a real capture guard replay.

## Separate pre-execution and coverage limits

`run_once.py:515–556` checks environment file bytes and constructs the guard contract using the header's declared MuJoCo version. The actual backend runtime `__version__` and exact MjData/MjModel class checks occur at `capture_state():213–218`, called after entering/applying the session at `:715–725`. The pinned backend initializes MjModel/MjData and performs reset/forward/initial sensor rendering before that call. Before any future sole execution, obtain and validate the actual imported runtime version, classes and loaded binding/source origin **before the first model/reset/camera operation**. Record that provenance explicitly. This is a preflight/ordering limitation and recommendation; no native bypass or wrong-runtime actual execution is claimed or reproduced here.

The runner statically retains 120 passive settling steps, the pinned original teacher and its two dwell wrappers. Full actual nine-action/two-dwell collection has not run. An additional bounded fixture observation shows that adding `settle_steps=120` and `planned_teacher_actions=9` to a consistent saved header still permits the compressed three-frame/one-action fixture to be VERIFIED: the reader does not certify that recipe coverage. This remains a scope limitation, not an instruction to force remaining actions after an original teacher failure. Actual partial prefixes must remain preserved and unavailable; a normal complete recipe requires explicit original coverage evidence before it can be described as full 120/9/2 collection.

Decoder receives saved RGBD plus the registered marker only, after the top-level replay has no failures. Its control-flow gate is present, but the two qualified omissions above currently let malformed/incomplete traces reach that eligibility branch. No actual decoding was run or authorized by this review.

`independent-preservation.json` records all current input pins, 32 live/source archive pairs, 20 environment byte pins, original32/diagnostic33 source manifests and bytes, original21/diagnostic142 raw files (9908577 bytes total), and the reviewed guard source/review. The existing raw missing frame and prior failed/diagnostic outcomes are unchanged. Only new `independent-*` review/JSON/probe/log artifacts and /tmp synthetic fixtures were written; no core/source/test/header/manifest/old report/raw/archive/Stage/Git was modified. The future attempt directory remains absent.

Source authenticity remains UNKNOWN, custom protocol is not native RawV3, independent calibration-group status is false, native/formal admission is not promoted, continuous motion is not certified and future stability/error bounds remain unavailable. REQUEST_FIX is for software integrity replay; it grants no actual execution or native authority.
