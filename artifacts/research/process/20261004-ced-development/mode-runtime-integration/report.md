# Mode repository integration — software only

The existing experiment harness rewrote status after the new repository transaction,
doubling switch_count and replacing the frozen policy. A new regression first failed
with switch_count=2; the facade now retains the committed state, including on retries.
The API created a temporary service for each prepare request: a repeated identical
request returned 409 instead of the original record. The new API regression first
failed (201 versus 409); preparation now uses the configured repository, preserving
the transition ID and returning 409 only for conflicting payloads.

Final relevant regression: 34 passed, exit 0; scoped Ruff and mypy (two production
files) exit 0. Exact commands/output are in green.log, ruff.log and mypy.log. Original
RED results above are from this turn's tool transcript; no RED log file is claimed.
source-hashes.json, source/ and review-package.diff retain the tested source against
this turn's initial snapshot. Independent review is pending.

This fixes existing software facades. It does not provide an accepted research mode
selection, actual Max request, physical outcome, INITIAL or FINAL protocol. Strict
research services still need a verified boundary guard, durable checkpoint and actual
source-bound mode policy selection. No commit or external publication was performed.
