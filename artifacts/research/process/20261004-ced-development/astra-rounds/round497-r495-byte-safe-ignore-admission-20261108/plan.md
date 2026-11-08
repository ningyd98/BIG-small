# R497 Byte-safe ignore-admission correction

**Planner:** actual gpt-6-astra. **Scope:** only the R495 operational runner ignore check and evidence. No product or Git-rule change; original R495/R496 plans remain binding.

Root cause confirmed read-only: ordinary `git check-ignore -- ABS_PATH` succeeds but returns a C-quoted path with octal escapes for 文档. Text `.strip()` comparison falsely rejects it. Installed Git requires `--stdin` with `-z`: the positional `-z -- PATH` form returns128. The supported command below was executed read-only and returned0 with exactly the inputbytes. Existing `.gitignore` cache/ rule already excludes the intended directory; cache remains absent.

Preserve byte-identical original runner and stdout/stderr from this draft `original/` into canonical R497 before editing. Input SHA256 pins and read-only evidence are recorded in plan.json. Failure was before cachemkdir, flock, GET, signal, launch or POST; no runtime budget was consumed.

Replace only the failing ignorecheck with:

```python
ignored_input = os.fsencode(str(CACHE)) + b'\0'
ignored = subprocess.run(
    ['git', 'check-ignore', '--stdin', '-z'],
    input=ignored_input, cwd=REPO, capture_output=True, timeout=10, check=False,
)
base.require(
    ignored.returncode == 0 and ignored.stdout == ignored_input,
    'private_cache_not_ignored',
)
```

No text decoding, `.strip()`, global `command()` change, `core.quotePath` change, or new ignore rule. Exact bytes imply exactly one expected NUL-delimited record.

Before running the operational entrypoint, verify the isolated guard: actual ignoredpath succeeds, nonignored AGENTS.md rejects, and stubbed rc128/wrongpath/missingNUL/extra record reject. No import/main execution, cachemkdir, flock, API or signal is allowed in these guard checks. Record corrected runnerSHA and narrowdiff; preserve original logs. Confirm cache and attempted/execution-start markers still absent, HEADf401 and original35 plus R496additionalpins match. Then resume the same unconsumed R495 attempt under its existing operational rechecks and maxonePOST/providerrequest4096token budget.

## Remaining runner guard review

- Validated ordering: pins/graphics precede failing ignorecheck; CACHE.mkdir/flock/metadata/signal/launch/POST all follow. Cache absent and empty stdout agree with zero runtimebudget consumed.
- command().strip remains appropriate for the currently exact HEAD hash and ASCII repo-relative diff names; do not change all subprocess handling for this fix. R496 exact progression and original35+additionalpins stay active.
- CACHE.mkdir without exist_ok and exclusive attempt/executionmarkers prevent reusing a partial operation. Do not remove a pre-existingcache or marker to bypass this guard.
- Headless EGL prerequisites are metadata-only before restart; paid=true is explicit only in newpreparedcontract. Existing profile/presencecheck and PID/starttime/listener checks remain.
- POST transport is one call, redirects not followed, absolutealarm90s and4MiB cap retained. UNKNOWN conservatively retains detachedflock owner; no replay. Classification remains separate offline stage required by R495 before claiming success.
- Existing exclusive receipt writes can stop an incomplete run; do not overwrite them or infer that restart alone permits anotherPOST. Newunexpectedguard/runtimefailure returns to Astra.
- No additional demonstrated guard blocker found in static review. This is not live-readiness proof; resource/process/runtime checks must run at R495 operationalstart.

Acceptance: the supported byte command handles the actual non-ASCII path; negative/malformed records failclosed; original failure is immutable; only one guard changed. No new runtime authorization, no source change, no secret access. Any subsequent unexpected failure follows AGENTS new-Astra rule. Planner performed only static/source reads and read-only Git ignore checks, never reran the operational runner.

Additional static review before handoff: current POSIX Popen implementation waits on the exec-error pipe until successful exec closes it; immediate identity(child.pid) is not shown to race pre-exec argv/cwd. A child that exits immediately is a genuine startup failure. Do not weaken/defer this guard based on the unproved race hypothesis. The later health/listener checks still apply. Offline classifier was read only: StrEnum comparisons, datetime timestamp equality and strict JSON model validation match pinned schema/pipeline; all positive predicates gate PLANNED_INTEGRATION. The exact semantic-label allowlist is conservative (synonyms may become an evidence mismatch requiring review); it cannot establish independent pixel/grounding truth. No additional code change is warranted by this review.
