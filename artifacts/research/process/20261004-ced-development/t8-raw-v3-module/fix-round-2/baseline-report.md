# Raw-v3 fix1 scoped implementation report

## Result and scope

The two independently reproduced P2 findings are corrected in exactly two owned files. The final immutable 774-file closure has only those two differences from the original reviewed release. Developer verification passed; independent re-review is pending. This remains SOURCE_CONSISTENCY_ONLY. UTC mapping is UNAVAILABLE where uncertainty is absent, continuous motion is NOT_CERTIFIED, and INITIAL/RISK/METHOD/EXECUTION admission is not granted.

No simulator state, physics step, renderer, camera capture, controller, provider, network or actual model action was run. CPU checks operate on supplied software fixtures and immutable historical sources. Current moving worker/risk files are not imported into the final verification overlay.

## Corrections

TERMINAL joins must identify the original final physics step/state and follow its known sample boundary plus every known action completion/rejection and the final complete TERMINATION interval. A frame associated with an earlier action cannot be promoted to final terminal evidence. Missing actual-return or final termination/physics boundaries remains INCOMPLETE. Partial actions with explicit final termination preserve that available relationship while their partial denominator remains INCOMPLETE. Earlier cleanup termination intervals remain ordered without falsely requiring them to follow later rejected attempts; the final termination must follow all supplied known action ends. The code neither captures nor fabricates a terminal frame.

The validator replays the full ordered command sequence and available original reset/physics states. An accepted emergency_stop latches independently of later command flags. Its own after_emergency_stop flag retains its original distinct meaning; accepted hold remains allowed and rejected ordinary commands remain present in all counts. An accepted ordinary command cannot clear or bypass the latch. Physics sampled before an in-step stop is not blindly equated with later command state. A command claiming current physical index n additionally requires that original n sample's supplied end boundary already be available by dispatch; absent boundaries are INCOMPLETE, known later boundaries are INVALID. This finite-clock relation is not a continuous-time certificate or a sim/wall 1:1 assumption.

## TDD and verification

The complete first terminal/stop RED matrix recorded 9 failures and 6 legal controls. A later two-action legal control exposed and corrected an overly broad earlier-termination requirement (1 RED, 1 control). The extra current-state availability probe first returned COMPLETE and its qualified RED recorded 1 failure with 3 legal controls; after the narrow correction it returns INVALID with command_dispatch_precedes_current_physics_state. The first 108-test fixed candidate and its snapshot/logs are retained under first-candidate/ rather than overwritten as historical proof.

Final isolated command (exact cwd/env/argv in frozen-overlay-setup.json):

`pytest -q -p no:cacheprovider --confcutdir=. tests/test_raw_episode_v3.py tests/test_visual_owner_registration.py`

Result: **109 passed in 22.58s** (61 raw-v3 cases, including 16 added cases, and 48 owner binding cases). Scoped Ruff two files, format two files, and cold mypy one source passed. Collected test names are preserved in frozen-collected-tests.log. Full command/result logs are preserved; no full suite was run.

The original root-independent-counterexamples.py was rerun unchanged against the final frozen overlay. Baseline and true-terminal controls remain COMPLETE. Stale pre-action terminal, consistently stopped accepted ordinary command, and ordered accepted stop followed by ordinary false flag are INVALID. The original estop-flag negative control remains INVALID. All original counts match byte-parsed original results; commands/actions/physics/acquisition denominators were not removed.

Post-check: 774 archive hashes, 774 isolated-overlay hashes, 750 Python AST parses, both live owned hashes, unchanged public dataclass fields, and all 819 original report/review/probe/source artifact bytes pass. Only the two owned paths changed. Original package manifest/review/report/probes and both reviewed risk files remain untouched.

## Review handoff

Read source-hashes.json and ownership.json, overlay only source/ into an isolated directory, and use frozen-overlay-setup.json exact argv with the environment venv as an environment-only link. Re-run original-root-independent-counterexamples.py or the unchanged parent script and inspect original-counterexample-expectations.json; do not use current worker dependencies. Review the full legal/negative test matrix, including partial/rejected/multi-action terminal relationships and old pre-stop physics samples. No authority, collector, backend, executor, method policy, risk reader or worker integration changed.
