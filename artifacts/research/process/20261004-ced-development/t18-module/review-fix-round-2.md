# T18 second correction independent review

Verdict: **PASS** for the corrected SOFTWARE_ONLY archive verification and numeric rebuild scope. The remaining P2 failed-original omission from `review-fix-round-1.md` is closed. No production/test files were changed by the reviewer; no command replay, model request, GPU/rendering, dependency installation or physical reproduction occurred.

All nine frozen/live files matched manifest SHA256 `417fc9261e4d8980f5f80d12f369147f290a90bdfc7c84bcf0bccf6fe482307e` at review start. Prior releases and reviews remain in their baseline directories. To isolate later live protocol work, runtime checks used the released nine files in a temporary Python source overlay (`fix-round-2-independent-overlay.txt`).

Independent exact scoped command:

```bash
env PYTHONPATH=/tmp/t18-fix2-review-wqq0go_b/src:. .venv/bin/python -m pytest -q /tmp/t18-fix2-review-wqq0go_b/tests/test_research_reproducibility.py
```

**17 passed in7.34s**, exit0. Native-layout scoped Ruff passed reproduction source/CLI/test and native mypy passed those two production sources with the corrected API source. Their native target bytes matched the frozen manifests. Frozen reviewed-file mypy with `--follow-imports=silent` also passed. Initial temporary overlay static checks exposed import classification warnings in copied tests and an unrelated imported planning/pipeline.py type diagnostic; no claim of a full dependency typecheck pass is made.

The original independent full fixture `/tmp/ced-t18-bound-omission-jq2tq7_0` was copied without altering its original evidence. Its4199 raw/index entries versus4200 bound assignments are now rejected with `index omits bound original assigned episodes`. In an additional counterexample, the bound original assignment list was also reduced/rehashed to4199 and the file/outer manifest hashes updated. Verification still rejects with `assignment list omits exact frozen protocol assignments`, because it reconstructs all seven core methods from the actual frozen protocol and full2400-scene pool. Counts remain4199 in the invalid report, integrity_valid=false, research_accepted=false, physical/dependency reproduction=NOT_RUN. Probe output is archived in `fix-round-2-independent-omission.log`.

Verification now checks the bound original manifest's canonical content hash, unique exact IDs and protocol identity before comparing it to the reproduction index, then compares full ordered assignment objects to the actual reconstructed frozen list. Rebuild retains the same T16 analysis entry and model/protocol binding, compares saved metrics/goals, requires a fresh output directory and never executes stored structured command arguments. The complete4200-record software fixture retains failures and Tcap penalties and reproduces the saved metrics; this proves software determinism only.

Generic archives without a bound protocol prove their declared byte/index consistency, never formal completeness or source authenticity. Rewritten coherent inventories, dependency version declarations, model hash strings and archived statistics cannot prove actual source acceptance, model availability or physical success. These limits remain explicit, and no new finding was identified within this correction scope.
