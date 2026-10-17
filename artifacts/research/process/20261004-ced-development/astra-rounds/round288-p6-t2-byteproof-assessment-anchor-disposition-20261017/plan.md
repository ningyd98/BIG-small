# R288 — exact byte-proof initialization anchor

Actual gpt-6-astra; plan only.

The original metadata proof **966fc6 exited 1** at line 22. Its new final-region marker, `outcome["final_assessment"] = `, occurs twice in the frozen candidate: byte 80634 / line 1365 (initialization), and byte 84538 / line 1417 (exception handling). The other boundary strings each have the expected single occurrence. The overly short marker caused the uniqueness assertion to fail.

Use the exact consecutive initialization lines recorded in plan.json. This complete byte literal occurs once at byte 80634. Do not edit the candidate, select an ambiguous first match, strip whitespace, or mix character and byte coordinates.

## Limited recovery

Preserve the complete failed source/invocation/actual and candidate/native originals. Sole Sol may prepare **one new durable metadata proof** under R288, derived from the saved failed proof. Its changes are limited to this anchor and new R288 output paths. Keep both authorized R287 regions, all unique/ordered/full-line checks, unchanged prefix/middle/suffix comparisons, and full candidate reconstruction.

ROOT must read the complete new proof and its limited diff, verify source/input SHA and exact argv before a single ordinary metadata execution (120 seconds; stdout ≤6000 UTF-8 bytes). No execution is authorized during planning. Failure means preserve and STOP, with no retry.

On success, resume only the already authorized R287 native source preparation and ROOT full source/native/input review. Marker counts do not prove candidate semantics; this plan does not approve the candidate's runtime behavior.

## Evidence and boundaries

The failure, frozen candidate and full old runner have exact pins in input-observation.json. R288 before/manifest.json preserves full failure/candidate bytes, base64 and mode; the complete failed heredoc is saved without execution. At observation time, limited.diff, scope-proof output and implementation target did not exist.

No product, fixture, test, plugin, old runner, role or context changes; no new runtime/static/review/Git slots. R287's independent ROOT failure-settlement attempt remains separate. If it changes the current ROOT ledger before this proof, use only its explicit actual fullbefore/archive/after mapping under the existing R287 contract, reviewed in the fresh source/input gate. Never skip a path or require a historical pin to match a new live generation.

Freeze and STOP for ROOT review.
