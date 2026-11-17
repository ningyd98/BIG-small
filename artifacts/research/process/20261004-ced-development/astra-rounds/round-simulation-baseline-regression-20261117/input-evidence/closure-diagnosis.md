# Operational runtime closure: current regression gap diagnosis

Scope: nine nodes listed as uncompleted in 20261117 regression-summary.json. Code examined at 4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa. Two actual runs selected only the memory startup node, with the real software-only fixture and no EGL/GPU, physical hardware, or model services. Inputs are pinned in input-sha256. No current assertions were changed, product files were edited, frozen bytes changed, or current PASS inferred.

Current run A: /tmp/bigsmall-closure-diagnosis.7LppGKYz. Pytest faulthandler_timeout=20 emitted the two ordinary waiting broker/heartbeat threads, reached the main thread interpreter trampoline, and ended SIGSEGV (wrapper 139, 21.61 s). This reproduces the symptom of 11/17 full-final-03 (returncode -11: same partial traceback). The causal attribution is to the watchdog path for this reproduction; the native crash internals were not inspected. Current run B: same node with faulthandler_timeout=0 and Python main-thread signal sample every 20 s. Timeout 124 at 120.00 s, 119.56 process CPU s (99%); no JUnit or PASS. Samples show 20 s adopt_plan; 40 s bootstrap after adoption; 60 s bind_grounding; 80 s publish_grounding entry; 100 s confirmable publish_grounding mutation still decoding bootstrap. The worker's local reads rebuild nested immutable histories, including strict copies, canonicalization, semantic projection, and validation. The successful decode memo is scoped to one root; no cross-read reuse occurs. Profile frames appear repeatedly, but their separate overhead was not measured.

Historical completed nodes (seconds and provenance):

| Current node family | Historical PASS wall evidence |
|---|---|
| startup memory / sqlite | 242.040 / 245.041 outer, R374 t3-results.json |
| UTC memory / sqlite | 2355.490 / 2353.836 pytest; 4711.366 combined outer, R374 utc-memory-result.json / utc-sqlite-result.json |
| terminal commit_close | 240.74 pytest / 241.577 outer, R381 acceptance.json |
| terminal confirm_timeout | 238.221 outer, R376; 246.19 pytest after R380 scope restoration |
| terminal prior_bound | 253.500 outer, R376 terminal-handoff.json |
| public memory / sqlite | 246.574 / 246.463 outer, R376 terminal-handoff.json |

The historical schema-missing UTC issue from R368 is already repaired in current source; the current SceneSummary fixture passes updated_at=external.captured_at, and R374 completed both variants. R374 historical UTC was a diagnostic pass only; the original combined 600 s acceptance failed. R374 R376 and R381 executions refer to their exact historical workspaces and are not evidence of pass on the current revision. No fresh assertion failure has been demonstrated for these nine nodes.

Narrow runner change: allocate the seven startup/terminal/public nodes to their existing class of isolated long tests with per-node outer watchdog and historical 600 s development budget. Disable pytest native faulthandler timer for this group or use safe Python-only diagnostics. Reserve time before launch rather than mark tests as passed. Keep all SQL/UTC/lease assertions and inner waits. Run independent temp, JUnit and log destinations and pin the sources. For UTC, keep the formal combined 600 s judgment distinct; the historical 3600 s/node diagnostic envelope, if authorized for a fresh run, can provide software completion evidence only. A product performance fix would require fresh scoped attribution and a measured baseline, strict malformed/tampered codec and mutation isolation controls, then all nine real tests; neither cross-read authority caching nor lifting the formal limit is supported by this diagnosis.

RED/GREEN boundary: new runner reproductions provide an actual watchdog SIGSEGV and a 120 s noncompletion, but no product assertion RED or current GREEN. Historical PASS is prior evidence only.
