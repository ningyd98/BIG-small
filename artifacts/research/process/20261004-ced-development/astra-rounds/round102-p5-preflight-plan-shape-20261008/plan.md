# R102 — P5 preflight plan-shape recovery

Actual planner: gpt-6-astra. Status: PLAN_ONLY / READY_FOR_ROOT_REVIEW; implementer remains gpt-6.1-sol. One metadata-reader error, no new product root cause. This plan performs no implementation, product import, tests/static, actual, network or Git.

## Failure and independent check

R101 original `implementation/failed-preflight.py` SHA256 `964f85151647e7bf11865de34a5cf8b51d64c374c18a3dd59fa4d708e89c8062` is the exact body in its saved tool receipt. Tool `c5f000`, exit1, original merged output:

```text
Traceback (most recent call last):
  File "<stdin>", line 7, in <module>
KeyError: 'owned_paths'
```

The script reads all `input_pins` into memory at lines5–6, then evaluates `p['owned_paths'][0]` inside the dictionary argument of `print` at line7. Python evaluates that argument before printing. Thus it emitted no40-match report, reached neither line8 guard nor line9 mkdir/source-before, and wrote no product/tests. The actual R101 JSON has `scope.owned_paths`, not top-level `owned_paths`; both accesses in the old script must be corrected in a NEW recovery helper. Preserve the old failed script unchanged.

Astra independently read the actual schema and stop report, compared saved script with the receipt body (equal), recomputed40/40 R101 pins and ten source states (nine files equal, operational module still absent). This new read-only observation does not retrospectively create missing original stdout. Source hashes/absence, input hashes and original failure pins are embedded in `plan.json`. The original tool supplies only merged output and no start/end UTC; do not invent split streams or timestamps.

## Current directory facts

R101 `implementation` now exists because the author saved stop evidence. Its current exact nine entries are `budget.json`, `failed-preflight.py`, `finite-evidence-pins.json`, `preflight-tool-output.txt`, `preflight-tool-receipt.json`, `progress.md`, `source-freeze.json`, `step-report.json`, `step-report.md`. None may be overwritten. `source-before`, `input-check.json`, `green` and `/tmp/bigsmall-p5-r101-green` were absent at this observation. In particular `progress.md` DOES exist; it is stopped-history evidence, not proof the failed script reached its write.

Use NEW R102 `implementation` for the corrected helper, input-check, current source-before, progress and subsequent implementation/proof reports. Do not require the entire R101 implementation directory to be absent. The unchanged R101 GREEN command still writes to R101 `implementation/green/junit.xml`; recheck that exact leaf directory and original basetemp are absent before the single authorized GREEN. Do not delete or recycle either if present. No historical evidence cleanup/copying is necessary.

## Limited recovery steps

1. ROOT reviews this plan and current input/source pins, confirms the same Sol writer remains active. Read R101 JSON as a mapping; explicitly check `schema_version==1`, round identity, `scope` is mapping, `scope.owned_paths` is a list of ten unique nonempty strings, `input_pins` is a40-item list of mappings with path/bytes/sha256, and budget/commands have the expected bounded types/keys. Validate against the ten literal approved paths and frozen source manifest, not merely length. Unknown shape produces a clear metadata stop; do not guess/fallback silently or build a generic schema framework.
2. Save the NEW helper/argv before running it. It reads only the exact plan, stop evidence,40 input pins, ten source states and specified output-path existence. Recompute all hashes/sizes/absence and report them as a NEW current input receipt. Validate module absence by its explicit path, not list index. The existing RED test is present and pinned, although originally introduced as NEW; do not demand every `new_paths` item be absent.
3. After all checks pass, exclusively create R102 `implementation/source-before`; save the nine existing owned files byte-for-byte and record the tenth module's absence. Record source-before SHA/bytes against the same preflight reads. If a planned output already exists, stop for inspection, do not overwrite. Preserve R100 and R101 originals, including their source-before/freeze, original27 RED, budgets and stop reports. Report this recovery exit and actual output; no fabricated40-match receipt from the failed attempt.
4. Continue the already approved R100+R101 implementation only after recovery success. R101 explicitly supersedes R100's inclusive-age/strict-deadline conflict: AGE_CLOSED and HARD_OPEN stay distinct. This round changes no product design, ten-source scope,32-case denominator, original input boundaries or test commands. Keep the existing proof and static/GREEN budgets; append new progress under R102 rather than rewriting R101 stopped history. ROOT's usual independent review/delivery gates remain.

## Budgets and acceptance

Original RED used1/total1, remaining0; do NOT run RED again. Proof has0 executions and continues only as already approved, no new proof budget here. Ruff0/1, format-check0/1, GREEN0/1 remain; GREEN is32 new P5 cases plus actual OC1 JUnit denominator. Formatter/mypy/collect-only/model/network/renderer/actual/Git remain0. This failed metadata attempt consumed no test budget and does not reset any counter.

Allow one corrected finite metadata-preflight execution after ROOT activation; source inspection and plan review are not product validation. Recovery acceptance is correct schema resolution, fresh40/40 pins and ten source-state checks, exact source-before/absence receipt, unchanged original evidence and inherited budget. This is METADATA_RECOVERED only, never software PASS or actual qualification. Unknown schema, changed source/input or unexpected execution failure stops the affected work for Astra; do not iterate by guessing.
