# R346 finite T3 successor execution and capture plan

> **For agentic workers:** use the existing same-Sol execution workflow, task by task after ROOT activation. No new agent is needed for preparation. No runtime is released by this saved plan.

**Goal:** obtain reviewable evidence for exactly the original nine T3 software nodes after the accepted R344 adapter repair, using explicit new attempts and resilient capture.

**Architecture:** nine successive single-node pytest children share one frozen source generation. The new R346 runner records each capture stage independently so rejection of behavior cannot suppress unrelated evidence retention. The reviewed helper is copied whole and byte-identical into R346.

**Tech stack:** existing Python/pytest/R235 startup plugin; stdlib source inspection and capture. **Spec:** `root-intake.json`, pinned R331 contracts and R345 `next-plan-inputs.json`; all exact pins and commands are in `plan.json`.

Actual planner: `/root/astra_p6_t3_plan`, **gpt-6-astra**. Implementer: existing `/root/p6_t3_sol`, gpt-6.1-sol high. Reviewer/releaser: ROOT. Status: **ready for preparation review; runtime not released**.

## Evidence and boundaries

R331 GREEN is SPENT on both ledgers. Its child reached 600.0875676120049 seconds, exited −15, and produced `FFFF`; four completed sidecars record the same grounding exception, entered behavior, and incomplete assertions. Cleanup recorded a reaped leader, no remaining group, and no cleanup errors. The fifth directory proves no completion. JUnit and source-after are missing. A concurrent document HEAD change interrupted the old shared capture block. Individual node durations remain unknown.

R344 independently accepted exactly two live-adapter dispatch changes; operational_windows.py now has SHA `3bed52bb9ec8689a943ef3808223ba23e92749cd6af414edff1309e81517b0a7`. No new behavioral pass is claimed. R345 independently retained 220 regular files / 59,542,786 bytes plus link metadata. Its final manifest, missingness, resource observation, exact-HEAD acceptance, and ROOT byte acceptance are pinned. These later copies do not turn the original run into complete capture or a coherent database backup. R347 corrected only the existing narrative report read path.

Only exact HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b` is applicable. Keep original RED/GREEN, gates, sources, attempts and raw bytes immutable. No product/test/fixture/plugin edits, old helper execution, hidden collection/smoke/probe, T2 rerun, SQLite semantic read, B9/final-static/full-B/C/native/model/physical gate is included.

## Fresh finite command contract

Each command is a fresh R346 allowance of one attempt, initially HELD. Original spent slots are never reused. ROOT reserves one command only after accepting its predecessor; first unexpected outcome stops the sequence with remaining slots HELD. The exact absolute argv, environment, output directory, expected case filename and launcher are in `plan.json.commands`.

| ID | Selected node suffix | Max worker polls |
|---|---|---:|
| R346:t3_01 | `test_private_startup_to_transaction_grounding[memory]` | 2 |
| R346:t3_02 | `test_private_startup_to_transaction_grounding[sqlite]` | 2 |
| R346:t3_03 | `test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]` | 3 |
| R346:t3_04 | `test_local_new_schema_ignores_utc_jump_but_external_does_not[sqlite]` | 3 |
| R346:t3_05 | `test_b_terminal_publication_confirmation_fault[commit_close]` | 1 |
| R346:t3_06 | `test_b_terminal_publication_confirmation_fault[confirm_timeout]` | 1 |
| R346:t3_07 | `test_b_terminal_publication_confirmation_fault[prior_bound]` | 1 |
| R346:t3_08 | `test_b_public_confirmed_publication_control[memory]` | 1 |
| R346:t3_09 | `test_b_public_confirmed_publication_control[sqlite]` | 1 |

Each child has a new **600-second ceiling**, total **5,400 seconds** across nine attempts; this is an explicit fresh ceiling, not an estimate inferred from the failed run. One-node grouping prevents earlier work from consuming every later node’s allowance. Each invocation performs its genuine startup prerequisite once; there is no preliminary import or warm-up.

Each cleanup is bounded to 15 seconds (TERM grace 5), each capture to 240 seconds, and each outer launcher to 900 seconds plus emergency kill-after 20. Aggregate outer ceiling is 8,100 seconds plus at most 180 seconds emergency kill grace. The child starts its own process group; one command runs at a time. Preserve all actual worker/session/thread accounting and the **15 total poll** ceiling.

Raw streams keep the inherited 32 MiB each sampled threshold; stop the child upon crossing and retain measured overshoot. Persistent output has a 1 GiB/10,000-entry sampled threshold, checked by nofollow metadata traversal every five seconds with a two-second scan deadline; scan failure rejects and cleans up. Require 3 GiB free before each launch and preserve it during monitoring. Round output threshold is 20 GiB. These are sampled stop thresholds, not strict OS quotas; overshoot is retained and reported. Never delete evidence to meet a limit.

## Task 1 — prepare new runner, helper and actor binding

- [ ] ROOT verifies plan/input applicability and activates the same Sol for preparation only.
- [ ] Sol creates `implementation/run-evidence.py`, whole-file `resource-evidence-helpers.py`, helper provenance, fresh author binding, source-only proof, and preparation report. ROOT and AUTHOR ledgers each contain exactly nine HELD slots. No runner invocation, import, test or dry run is permitted at this step.
- [ ] Copy the entire 27,181-byte helper with SHA `bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b`. Retain its complete dependency closure. Import only this new frozen copy during a reserved command; do not execute the historical path.
- [ ] Adapt only new-runner command/cardinality: selected `nodes` has length one; `diagnostic_resources` derives its expected nodes from the exact single-node argv, `junit_observation` receives `[node]`, and case selection requires the one frozen family filename. Keep the helper’s four CASE_NAMES and original schemas. Check new command identity, actual child PID and selected node in every record; unexpected/duplicate records reject but remain retained.
- [ ] Keep every inherited resource check, add the selected-node poll ceiling, and enforce aggregate actual polls <=15. No weaker constructor/thread/cleanup proof or invented completion records.

## Task 2 — independent bounded capture

Reuse the working process/CAS/cleanup mechanisms under new paths and identities. Cleanup must happen even when ledger or source validation fails. TERM/INT enters cleanup/finalization. Poll exact HEAD at most one second apart with a two-second git-command deadline, plus mandatory before/after source pins. Any observed change stops the child and rejects behavior; it never prevents later capture. Shared writers must coordinate to keep the frozen generation and HEAD stable; no repository lock or rollback of document work.

| Stage | Seconds | Required independent outcome |
|---|---:|---|
| Raw/process/ledger receipts | 15 | Preserve actual streams, exits, cleanup and errors |
| HEAD/source observations | 30 | Per-pin actual/missing/error; drift recorded as rejection data |
| Persistent inventory and database bytes | 90 | Tolerant per-file inventory and stable byte copies; no database engine |
| Resource sidecars | 30 | Original bytes, exact-node helper diagnostics and completion facts |
| JUnit, case JSON, prerequisite | 30 | Three separately guarded 10-second substeps |
| Final summary | 15 | Stage statuses, missingness, result and all errors |
| Bookkeeping reserve | 30 | Total capture ceiling remains 240 seconds |

Use bounded stdlib main-thread stage timers/deadlines after cleanup, restoring signal state. Catch ordinary errors and stage timeouts independently, persist partial observations, then attempt remaining stages. Do not reuse the old throwing snapshot/JUnit/strict-index sequence as one shared capture block. A source mismatch produces `source-after-observed.json`; accepted source-after is possible only when all pins and HEAD match.

The tolerant nofollow inventory preserves actual path types, link metadata, stable regular-file hashes and per-file errors. Copy real DB and WAL/SHM/journal bytes separately (including orphan sidecars), checking before/read/after stability and destination equality. Continue to other files on per-file failure. Keep originals and label partial traversal/copies explicitly. No SQLite connect, backup API, checkpoint, vacuum, query or coherent-backup claim.

Call only the named frozen helper functions within the reserved runner: resource diagnostics once, behavior-completion facts once, JUnit once, prerequisite once, plus byte/pin utilities and cleanup. Case JSON/XML analysis reads only genuine newly produced artifacts. Resource or JUnit failure cannot suppress case/prerequisite readout. No capture retry, hidden parser probe, test replay or post-failure helper rerun.

Record artifact retention, required-evidence completeness, behavior candidate pass and independent ROOT acceptance separately. Missing JUnit/sidecar/source-after remains missing. A clean child exit alone is insufficient. If final output is interrupted or unwritable, preserve existing bytes and return to Astra for later recovery rather than inventing successful capture.

## Task 3 — freeze, review and release one command at a time

- [ ] Sol supplies AST/symtable/hash proofs and full new runner source. ROOT reviews all branches and stage bounds without running it.
- [ ] New source gate rechecks old 300 pins, replacing only operational_windows.py with accepted R344 bytes, preserving the other 299; append new plan/helper/runner/provenance/actor and finalized prerequisite pins. Mutable ledgers/results are outside source pins and use explicit CAS receipts. Historical product packages remain historical; do not relabel them as current source.
- [ ] Bind exact interpreter identity from available environment evidence, frozen R235 plugin and prerequisite module, test SHA `54b988c6257f51efcc796fd5a3f376c45fee84c31c6b3fa3f7593853da0d11ca`, absolute paths, exact HEAD and actual new runner/helper hashes in ROOT acceptance. Runtime remains unavailable until this acceptance and individual reservation exist.
- [ ] ROOT reserves only the current slot, used1/remaining0; actual runner consumes AUTHOR before Popen. Prelaunch failure after reservation spends the attempt with explicit no-child evidence. Cleanup and capture remain reachable even if spending reconciliation errors. No refund/retry.
- [ ] ROOT reviews each new raw/result/JUnit/case/resource/prerequisite/byte-retention/source record and binds its disposition before reserving the next slot. Source/HEAD drift, timeout, failure, missingness or resource discrepancy stops remaining runs for a new actual Astra plan.

## Task 4 — aggregate software evidence only

- [ ] After nine independently accepted commands, require exact original order/unique nine-node coverage, nine real JUnit passes with zero failures/errors/skips, exact genuine case/sidecar provenance and <=15 actual polls under one source generation.
- [ ] Produce aggregate result and step report distinguishing new allowance, actual spend, software behavior, capture and formal research boundaries. Preserve accepted T1/T2 version-specific passes, R311 unknown SIGSEGV and historical DB gaps.
- [ ] ROOT requests a separate fresh actual Astra independent review only after successful nine-node behavior. This plan does not allocate B9/final-static/full-B/C work or authorize committing a changed HEAD during the frozen sequence.

## Verification and acceptance limits

Preparation proof is source-only: JSON/AST/symtable/hash checks, exact command coverage and sums, helper byte equality/name closure, finite Git metadata and independent review of cleanup/capture control flow. It imports no product/helper/test and consumes no runtime slot. No new tests or probes are authorized. Input pins and planning-readout are attached in `plan.json`.

A per-command pass requires actual exit0, no timeout/output/storage/ledger/source/capture error, stable HEAD/pins, one exact non-skipped passing JUnit record, genuine behavior/assertion completion, strict inherited resource relations and complete process cleanup/evidence retention. Acceptance is software-only and version-specific. Any new cause or needed scope change returns to actual Astra; all unused slots stay HELD.
