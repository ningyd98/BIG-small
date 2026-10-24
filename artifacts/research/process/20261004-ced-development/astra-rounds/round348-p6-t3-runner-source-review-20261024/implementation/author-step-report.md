# R348 source-only runner correction

Actual author: `/root/p6_t3_sol`, GPT-6.1-sol, high. ROOT activated the actual Astra R348 plan `cef32e6d886b780b99bd253ab8baaf8c15b56a6980b5391119bc3b81d9ce404d`. The only existing file modified is the new R346 `implementation/run-evidence.py`. The successor is frozen at **57,557 bytes / 1,009 lines**, SHA256 **`264ba312e849a44a93fba942015c539ce2b78568787352685530707eb1b0b9ef`**.

No candidate/helper/product/test import, runner invocation, `--help`, collection, test, parser call, timing probe, or runtime command occurred. Both nine-slot ledgers retain their original all-HELD bytes. Original R331 spent allowances were not reused. ROOT source acceptance and the future complete R346 source gate plus individual reservation are still required.

## Changes and evidence

The raw plugin-owned `prerequisite.json` remains unchanged; its derived stage receipt is now `prerequisite-observation.json`. The seven receipt names are unique. Missingness lists each prerequisite path once.

HEAD monitoring now anchors its first successful-completion deadline at child start +1.0 seconds, including child-start metadata persistence. Successful reads target +0.25 seconds; each live git operation is bounded by its inherited maximum and the remaining wall/HEAD deadline. A fresh HEAD precedes every live storage sample, its scan receives at most `min(2.0, childremaining, HEADremaining-0.1)` seconds, and another HEAD read follows immediately. Observed child-exit tails must also satisfy the bound. Actual start/completion/gap/budget/failure facts are recorded. A shorter HEAD/storage rejection sets the original wall `timed_out` flag only if the original child deadline actually elapsed. No scheduler guarantee or continuous observation is claimed.

Live directory comparisons use explicit `live_sampling=True` only at the actual live-child storage call. They preserve device/inode/type, descriptor-relative nofollow traversal and duplicate-identity protection while permitting mutable directory timestamps/size. Postrun content/DB retention and case scans keep strict full-coordinate checks. Live traversal remains a metadata sample over an interval, not an atomic snapshot.

Reserved preflight validates the actual runner `sys.executable`, realpath and `sys.prefix`, the frozen child/launcher executable, the ordered actual symlink targets and device/inode/type, and the real resolved binary/cfg pins. It uses ROOT's concrete `interpreter-evidence.json` fields. This checks launch/current-process paths and filesystem identity; it is not a loaded-memory attestation or extra version startup.

Early key/plan/reservation/mkdir failures now emit their original exception and provenance to stderr before one exclusive fixed fallback receipt attempt. The stderr attempt is bounded to 2 seconds and the whole fallback to 5 seconds from existing overhead. No unverified fallback data can mutate AUTHOR. Normal-output-created prelaunch failures emit stderr and retain the independent capture path. ROOT must preopen the fixed outer stdout/stderr files and reconcile a genuine reserved rejection as spent/no child without refund.

Finalization is separate from the generic stage wrapper. Seven nonfinal receipts finish first. Bounded finalization exclusively writes precommit missingness/status/result; result records `behavior_checks_passed` and `completion_required=true`, with no affirmative final candidate field. It validates all terminal references, then writes and verifies `completion.json` last. No success-artifact write follows that receipt. Only successful readback sets in-memory completion valid. Failure preserves partial bytes, attempts distinct `finalization-error.json` and stderr within remaining bookkeeping, and returns nonzero. A physically present receipt alone cannot pass: actual normal outer wrapper exit0 and independent ROOT review are also required. Predecessor validation now joins that wrapper provenance, completion pins, result behavior facts, child PID, exact command and source generation.

`source-proof.json` contains the complete changed/retained definition hashes, source locations, producer/consumer namespace matrix, 19 source-only branch rows, monitor/finalization/live-call/interpreter matrices, exact gate schemas and immutable observations. AST/symtable parsing succeeded with no unresolved global names. All 20 recorded source checks are true. Nineteen top-level definitions retain exact source segments; the finite diff covers only the authorized runner definitions/call sites and supporting constants.

Evidence pins:

- `source-proof.json`: `e1ade15733c853d1f259944a48b83eb91951bd3675ec43e0ceb9ce7410b972db`.
- `runner-after.diff`: `e5900bbe6b9a6654d895848732bfc1e1127f7d61484344879c8879d7cdde39d1`.
- Whole unchanged helper: `bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b`.
- Unchanged ROOT ledger: `57498e7855752e8245c32075846780fd0dcc35075e9b8206597502229452f43f`.
- Unchanged AUTHOR ledger: `ab442a8db92543baf810e5442ab7896c918e7ab3b9a3da5e69c33f5f1c69ddb3`.

All immutable R348 inputs still match; the designated live runner is the sole permitted replacement. The old 300-pin generation has 299 exact unchanged pins and only the independently accepted R344 windows replacement. Exact observed HEAD remains `729bce11bbd55a4a869e25e52174da3d0db1825b`, branch `research/20261004-continuation`. The original R346 draft/proofs/report, R348 before snapshot, helper, actor binding, product, test and plugin bytes are preserved.

## Exact ROOT artifact contract

Every pin below is a regular-file `{path, bytes, sha256}` object. These are required reader fields; ROOT may add explanatory metadata.

R348 `root-source-acceptance.json` must contain `reviewed=true`, `plan` equal to the exact R348 plan pin, and `runner` equal to the successor pin above.

R346 `source-gate.json` requires `round="R346"`, exact HEAD/branch, `commands` equal to the entire original unchanged R346 command table, immutable `pins`, `sources={runner, helper}`, fresh unchanged `executor_binding`, and `interpreter_evidence` embedding ROOT's actual record. It also requires:

```json
{
  "corrections": {
    "R348_plan": "exact R348 plan pin",
    "R348_source_acceptance": "ROOT R348 acceptance pin"
  },
  "monitor_policy": {
    "maximum_successful_HEAD_completion_gap_seconds": 1.0,
    "HEAD_target_seconds_after_completion": 0.25,
    "storage_HEAD_headroom_seconds": 0.1,
    "git_seconds_max": 2,
    "storage_seconds_max": 2
  },
  "completion_contract": {
    "terminal_record": "completion.json",
    "wrapper_exit0_required": true,
    "result_is_precommit": true,
    "ROOT_independent_review_required": true
  }
}
```

The exact interpreter fields are `requested_path`, `resolved_path`, `resolved_binary` pin, ordered `symlink_chain` records `{path,target,device,inode,file_type:"symlink"}`, `venv_root`, and `pyvenv_cfg` pin. Immutable binary/cfg and the original R346 plan, R348 plan/acceptance, fixed new source/proof/actor/helper/prerequisite records belong in the gate generation. Mutable ledgers, per-command results and growing root-launch streams must not be source pins. Frozen first-draft preparation records retain their historical status.

R346 `root-source-acceptance.json` requires `reviewed=true`, `source_gate` equal to the exact new gate pin, matching `executor_binding`, and `runtime_implementation` exactly equal to `gate.sources`.

Only the selected ROOT ledger slot may be `RESERVED`, used1/remaining0, with `successor_identity="R346:t3_XX"`, a unique nonempty `reservation_id`, matching `source_gate`, `acceptance`, `executor_binding`, and:

```json
{
  "launch_capture": {
    "stdout_path": "<R346>/root-launch/<key>.stdout.txt",
    "stderr_path": "<R346>/root-launch/<key>.stderr.txt",
    "preopened_exclusive": true,
    "launcher_argv": "exact selected plan launcher array"
  }
}
```

ROOT preopens those files exclusively before the single existing launcher invocation and redirects its stdout/stderr to them. The runner checks its actual descriptors against the fixed regular-file identities. Later slots stay HELD; earlier slots must be SPENT and independently accepted.

An earlier ROOT slot's `disposition` pin must resolve to `ROOT_accepted=true`, exact `command_id`, genuine `completion` pin, `result` equal to `completion.result`, and `wrapper_status={exit_code:0,timed_out:false,signal:null,provenance:<pin>}`. The provenance JSON must itself retain the actual outer launcher result with matching `command_id`, `exit_code`, `timed_out` and `signal`. It must come from ROOT's observed launcher outcome, never be inferred from a receipt.

`completion.json` binds exact command/node/actual child PID/source gate/runner, `result`, `missingness`, `stage_status`, and the seven ordered `stage_receipts` pins. It requires `finalization_complete=true`, `final_summary_state="COMPLETE"`, `wrapper_exit0_required=true`, `ROOT_accepted=false`, and a candidate flag matching the result's strict boolean behavior checks. The result/PID/source generation and every referenced pin must match. Candidate true plus this receipt still requires actual wrapper exit0 and ROOT review. Future aggregation consumes these qualified dispositions, preserves exact nine-node order and <=15 actual polls, and never trusts result alone.

The original nine commands/environments/nodes, 600-second child ceilings, 5,400-second total child budget, 900-second outer ceilings, 240-second capture windows, 15 total poll ceiling, <=2 concurrent polls and inherited <=64 actual worker constructions per invocation are unchanged. No runtime is released by this report. All author writes now stop pending ROOT review.
