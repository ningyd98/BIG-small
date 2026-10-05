# Raw-v3 independent frozen-source review

Verdict: **CHANGES_REQUESTED**, two P2 source-consistency defects. Scope remains **SOURCE_CONSISTENCY_ONLY**. Neither counterexample grants execution, authenticated clock, native/METHOD, owner, physical success or continuous-motion authority.

Reviewed only the immutable774-file archive with manifest SHA256 `cdd6684f4dcf28e09ba0e6f2e36dc95c2640d594726d297781ef77d07bad8bc0` and original report SHA256 `d736c55ace79a67dbb9703799dda7e208fdcf900e57482303231186d82bacd2d`. All774 file hashes and Python ASTs match; its772 base entries exactly match the accepted owner fix1 archive. A fresh774-file runnable overlay was copied with per-file checks. No moving worker-owner refs or live source imports were used. Setup and exact commands are recorded in `root-independent-setup.json`/`.py`; no production or previous report was edited.

## P2: TERMINAL join silently accepts an action-before frame

`source/src/cloud_edge_robot_arm/research/raw_episode_v3.py:1604` checks BEFORE_SUBMIT, AFTER_RETURN and DURING_ACTION ordering but omits the public TERMINAL relation. The qualified baseline is COMPLETE. Adding a TERMINAL join pointing to its unchanged original BEFORE_SUBMIT frame, acquired at step120 / monotonic100ms, returns COMPLETE with no reasons, despite the action ending at step121 /220ms and envelope terminal state at121. A terminal join to the true after/terminal frame remains COMPLETE as the positive control.

This labels an earlier frame as termination evidence while retaining complete source-consistency status. Check a supplied TERMINAL relation against the actual terminal physics identity and known return/termination boundary; if the source lacks the needed terminal boundary, report incomplete/unavailable rather than silently accepting the relation. No additional terminal capture or inference from timestamps should be invented.

## P2: accepted emergency-stop order is not replayed

`source/src/cloud_edge_robot_arm/research/raw_episode_v3.py:1220` rejects ordinary acceptance only when the caller-supplied `after_emergency_stop` is true; replay at1257 processes targets but never maintains the recorded stop latch. A complete software record with command order **hold_current_joints → accepted emergency_stop → accepted joint_target**, all dispatched within step120, makes the later ordinary command's flag false. Updated sequence denominator3, exact action half-open range[1,4), complete clock/parent bindings, final measured estop=True and joined hashes all remain coherent. The validator returns COMPLETE with no reasons. Switching the flag to true rejects, showing the condition trusts this redundant flag instead of reconciling accepted stop-command order. A separate consistently stopped-state probe also returns COMPLETE with an accepted ordinary command and false flag.

Replay/check the stop latch against ordered original commands and current available state, rejecting contradictory ordinary acceptance and flag provenance. An older step snapshot can legitimately precede an in-step emergency-stop transition, so do not require blind equality of every command flag with the preceding physical sample. Preserve rejected commands and hold exceptions. This is a source-record consistency failure, not proof a real controller accepted such motion.

## Independent verification and bounds

- Frozen CPU commands identical to the package setup: owned45 plus pure-owner48, **93 passed in14.94s** (`root-independent-cpu.log`).
- Scoped Ruff2 / format2 passed; separate cold mypy1 passed (`root-independent-ruff.log`, `root-independent-format.log`, `root-independent-mypy.log`).
- `root-independent-counterexamples.py`/`.log` preserve qualified baseline, terminal true-boundary control, both malformed accepted graphs, and the rejecting stop-flag control. The first probe-script setup failure (JSON serialization of MappingProxy) is retained in `root-independent-counterexamples-setup-failure.log`; the corrected probe only detaches its dictionary for hashing.
- Physics indexes preserve all121 expected rows, command half-open denominators remain closed, action full original/grounded step policy comparison and retry/deadline validation are present. Existing tests exercise overwritten/delayed commands across passive spans, rejected zero-step attempts, partial/missing returns, strict nested schema/bool/nonfinite/caller aliases and source/version drift.
- SOURCE/ONLINE derived pixels are recomputed from the frozen corruption recipe and joined by full observation/checksum; distinct acquisition intervals and all input records are reported separately. Full native camera-state binary hash is separate from canonical physical-observation hash; only registered measured arm/finger/time arrays are cross-compared, not an invented whole-world transform.
- A missing UTC uncertainty remains UNAVAILABLE; COMPLETE software structure never becomes authenticated clock or continuous certification. No physical states were constructed, no simulator step/render/capture/controller/model/network calls were made, and no callbacks returning VALID were used.

The two defects should close with qualified regression negatives against these same COMPLETE baselines before a separately frozen re-review. Other integration/authentication/clock-source prerequisites remain outside this pure module.
