# R343 Second Document HEAD Applicability Plan

> **For agentic workers:** ROOT metadata review only; no implementation or runtime action under this plan.

**Goal:** Adapt only the future R331 GREEN exact-HEAD prerequisite to `18e1844b6ad870c10a07cd7a490e1a40dfd6fb2a`.

**Architecture:** Preserve the original RED and R337 generations, attach this finite Git applicability decision, and let the unchanged runner check the exact future gate HEAD.

**Tech Stack:** Read-only Git object/path/blob inspection and standard-library JSON/SHA256.

**Spec:** `root-finding.json`, `git-tree-readout.json`, original R331 input pins and accepted R337. Actual Astra: `gpt-6-astra`, `/root/astra_p6_t3_plan`.

## Verified evidence

Current branch is `research/20261004-continuation`. Candidate `18e1844b6ad870c10a07cd7a490e1a40dfd6fb2a` is the direct child of R337's `1e9f5d5fd958147f3558f66c364dbd8cfc3caf99` and the only intervening commit. Its 34 paths have zero intersection with R331's 255 input paths. All 254 tracked input tree entries and blob bytes are unchanged and match the original pinned SHA256. The single original untracked `root-intake.json` remains absent from both commit trees; it is not a committed input. HEAD stayed unchanged through this readout.

`planner-git-readout.json` contains independent finite ancestry, paths, both trees and blob hashes. Full input hashes are in `plan.json`. Original plan/runner hashes and both ledgers were checked: RED used1/remaining0; GREEN used0/remaining1 HELD. No current mutable product source was executed or pinned as an immutable prerequisite.

## Exact successor decision

After ROOT accepts this evidence, only `18e1844b6ad870c10a07cd7a490e1a40dfd6fb2a` may replace the fixed HEAD prerequisite for the future R331 GREEN source gate. This is an external addendum. Original R331/RED HEAD `d66e258a1ebac178cce6c510347ed22117f24cb6` and R337's prior exact successor remain unchanged historical evidence. No later HEAD, descendant or apparently unrelated document commit is automatically authorized.

## ROOT sequence

- [ ] Recheck exact branch/HEAD, direct parent and pinned evidence. Reuse immutable tree/blob proof when the object IDs match. Verify original plan/runner/RED evidence and ledger states; do not compare authorized in-progress source edits to obsolete baseline hashes as a stop condition.
- [ ] Write R343 applicability acceptance and step report referencing this plan/readout and R337 acceptance. State that only the prospective GREEN HEAD prerequisite changes.
- [ ] Let separately authorized corrections continue. At original GREEN readiness, stop source writers and freeze the actual completed source/test/fixture/runner generation with all applicable correction evidence. Set the future gate HEAD to the candidate above and reference R343 acceptance; keep the R331 command identities and runner unchanged.
- [ ] Immediately before original reservation/launch, re-read exact HEAD and final gate/source/runner pins. R343 itself reserves and runs nothing. Original consume-before-spawn and no-retry rules remain.
- [ ] On further HEAD drift, hold the affected execution gate and request fresh actual Astra applicability. Preserve existing gates, runner rejections and results; do not silently update frozen bytes to match.

## Boundaries

No product/test/runner/document edits, Git mutation, rollback, resets, imports, collection, probes or runtime. Do not stage/commit/push or claim ownership of the independent presentation delivery. Keep R331 plans/RED raw/gates, R337 evidence and all original failures intact. No added/reset allowance; GREEN remains HELD until its separate original release gates pass.

Acceptance establishes compatibility of this one exact commit with R331 inputs and future HEAD binding only. It does not approve GREEN execution, product/test/B/C acceptance or document delivery.
