# R348 runner source-review correction plan

> Same actual `/root/p6_t3_sol` implements only after ROOT activation. This actual **gpt-6-astra** plan authorizes source preparation, not execution.

The frozen first R346 runner has four linked capture/control defects. Repair only the new runner and its versioned proof metadata. Keep all nine runtime slots HELD, the whole helper byte-identical, and all product/test/plugin files and original plans/evidence unchanged.

## Evidence and diagnosis

`runner-before.py` is the actual 41,012-byte draft, SHA `a5b37e1f22acacf429e19456701a92ffd0be26e4fb86c46474e14b6a9f2c77ce`. ROOT finding SHA is `adf37e46fb3f5d6faddec9bc8f46cc5c6e0a765d610d52171f4b7a7b35c59272`. Exact input pins and full-line source slices are in `plan.json` and `source-readout.json`. No candidate import, runtime exception or measured timing failure occurred.

1. The plugin owns `out/prerequisite.json`; generic `stage("prerequisite")` then exclusively writes the same path. Missingness repeats it.
2. A loop scheduling HEAD at `now+1` while synchronous git and storage can each block two seconds does not establish one-second successful observation gaps. Relatedly, storage `DeadlineExpired` reaches the catch labelled child wall deadline and sets `timed_out=true` before the actual 600-second wall need have elapsed.
3. `result.json` may already claim candidate pass when final-summary persistence fails. The stored stage status never advances beyond `WRITING_FINAL_RESULT`.
4. Plan validation precedes output-directory creation. A rejection there is retained only in memory and returns failure without the original error receipt or stderr.

## Task 1 — separate raw and derived prerequisite paths

Keep the plugin path and child environment unchanged. Rename only the capture stage to `prerequisite-observation`; its receipt is `prerequisite-observation.json`, while the helper continues reading raw `prerequisite.json`. Update stage/result/missingness consumers consistently and list each once. Produce a source-derived writer/reader matrix for every raw and stage path; no capture writer may alias a raw producer path.

## Task 2 — explicit HEAD freshness and timeout attribution

The accepted maximum successful HEAD completion gap remains **1.0 second**. Scheduling targets **0.25 seconds** after each successful completion. This is a measured acceptance condition, not a promise that the OS always schedules this process in time. Any late completion rejects behavior and enters existing cleanup/capture.

- Anchor the first deadline to child start +1.0 seconds, including initial child-start metadata persistence.
- Record HEAD read start/completion and actual gap. Limit each live git operation to the minimum of its inherited 2-second maximum, remaining child wall time and remaining HEAD-completion deadline. Reject nonpositive budget or completion beyond the deadline. Only a successful exact-HEAD observation advances the deadline.
- Before each five-second storage scan, obtain a fresh HEAD observation. Give the single scan at most `min(2.0, childremaining, headdeadline-now-0.1)` seconds; reject if no positive time remains. Immediately check HEAD again after storage. The 0.1-second reserve is scheduling headroom, not a guaranteed git duration.
- Bound sleeps by 0.1 seconds, next target and both deadlines. At observed child exit check the final interval too. Record overruns; do not infer uninterrupted observation between samples.
- Distinguish HEAD/storage subdeadline errors from exhaustion of the original 600-second child deadline. Set the wall `timed_out` flag only when that deadline actually elapsed; preserve simultaneous reasons if applicable.

This explicitly resolves the R346 timing wording without editing its historical plan. Dynamically shorter storage windows remain within its two-second maximum. No timing probe, new thread, extra interpreter or product clock authority is introduced. An insufficient future monitoring budget fails the attempt; it does not silently relax the guard.

## Task 3 — terminal completion receipt and ROOT gate

Remove final-summary from the generic stage wrapper. Keep the existing 15-second finalization window and shared bookkeeping reserve; add no time.

1. Finish and persist the seven independent nonfinal capture receipts.
2. Exclusively write missingness and stage-status. Status records completed/failed nonfinal stages and names `completion.json` as the required terminal record; it does not claim that final persistence already succeeded. Missingness explicitly describes a precommit observation.
3. Exclusively write `result.json` with `behavior_checks_passed`, `completion_required=true`, the real facts/errors, and `ROOT_accepted=false`. It must not contain an affirmative final `behavior_candidate_pass`.
4. Validate the referenced pins, then write `completion.json` last. It binds command/PID/source gate/runner, result/missingness/status and all seven receipt pins; records finalization complete and the qualified candidate check; and states that actual wrapper exit0 and ROOT review are still required. Verify its readback before setting in-memory completion valid. No later success-artifact writes.
5. Return0 only after valid completion and all candidate checks, with no errors/signals. On any failure preserve partial bytes, attempt a distinct `finalization-error.json` within remaining bookkeeping time, emit the original exception to stderr, and return nonzero. Never overwrite a prior result or receipt to hide failure.

A receipt that physically exists before failed readback is insufficient. ROOT must independently verify receipt/pins **and actual outer wrapper exit0 without timeout or signal**. Update predecessor validation and future aggregate/disposition schemas to require that pair, then join the result's behavior-check facts. Remove the old shortcut that trusts `prior["behavior_candidate_pass"]`. Missing receipt, nonzero wrapper or pin mismatch rejects and leaves later slots HELD. Precommit missingness is not rewritten after commit; chronology remains explicit.

## Task 4 — preserve prelaunch rejection evidence

ROOT must preopen exclusive `R346/root-launch/<key>.stdout.txt` and `.stderr.txt` for each future reserved launcher, bind them in launch/reservation metadata and retain actual exit/timeout. This changes output retention only; exact launcher/child argv and environment remain unchanged.

Cover key parsing and early validation with an outer error-retention boundary. For a failure before normal output creation, emit the original exception type/message/traceback, argv/key, actual wrapper PID, no-child flag and reconciliation requirement to stderr first (bounded two-second attempt). Then attempt once to create fixed `implementation/prelaunch-rejections/<key>-<pid>.json`, using an invalid-key label for invalid argv. Entire fallback is bounded to five seconds from existing overhead, with no new child/capture/outer allowance. Exclusive collisions or failures do not trigger retries or overwrites.

Use the already verified reservation if available. Otherwise any optional fixed-ledger read is only observed metadata and status remains unknown until verified. Never mutate AUTHOR using untrusted fallback data. ROOT reconciles an already reserved invocation to spent/no child on both records, with no refund. An unauthorized invocation must not invent a reservation. Normal-output-created prelaunch failures still retain capture evidence and also emit the primary rejection to stderr. If all persistence channels fail, no complete-retention claim is possible; nonzero/missing evidence rejects and requires separate recovery.

## Verification, activation and limits

Same Sol supplies a narrow diff, complete successor hash, AST/symtable proof, output namespace matrix and finite branch table under R348. The branch table covers rejection before mkdir, failed reservation/mkdir/spend/Popen, HEAD/storage deadlines, actual child deadline, and every final write/readback failure; each row identifies cleanup, error retention, spending and held successors. These are source inspections only, never executed scenarios.

ROOT checks the real successor source and immutable pins, including unchanged helper and both still-HELD nine-slot ledgers. Future R346 source-gate/acceptance must bind original R346 plan **plus R348 plan/acceptance**, the corrected runner hash, refined monitor policy, completion receipt contract and fallback capture paths. Only later complete source-gate acceptance and an individual reservation can release runtime.

No product/test/helper/plugin repair, import, dry run, new test, timing probe, attempt or timeout extension is authorized. Original R331 failures/spends, R346 plan and R348 before snapshot stay intact. Any unrelated cause or wider scope returns to actual Astra.

## Related supplemental observations adjudicated

ROOT supplemental source evidence is pinned at SHA `db4a0fd416c07da4b3513cd4e6219c28bca0d417091774ee2a38233b3245fc3e`. These are conditional source defects, not observed runtime failures.

**Live directory sampling:** add an explicit `live_sampling=False` parameter to the new runner traversal and enable it only at the actual live-child storage call. For directories in that mode, compare device/inode/file type at descriptor and path boundaries; do not require size/mtime/ctime to remain unchanged while the child legitimately creates entries. Keep descriptor-relative nofollow traversal, duplicate identity protection and rejection of errors, disappearing paths or identity substitution. Postrun content/DB retention and case scans retain strict default checks. A completed live traversal is a sample over its recorded interval, not an atomic filesystem snapshot. No regular-file contents are read live.

**Actual interpreter binding:** replace the nonempty-dictionary check with verification of a concrete ROOT record: frozen requested executable, ordered actual symlink chain, resolved regular-binary SHA/bytes, venv root and pyvenv.cfg pin. During the reserved runner's existing preflight, compare its own `sys.executable`, `realpath`, `sys.prefix`, declared child executable, actual link targets and endpoint/cfg bytes. ROOT rechecks the same real metadata before each reservation. No new startup, `--version`, import or probe is allowed; no interpreter files are changed. The proof describes launch/current-process path and filesystem identity, not loaded-memory attestation. Mismatch follows the same prelaunch failure/spend boundary.
