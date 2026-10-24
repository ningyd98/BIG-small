# R337 one-commit HEAD applicability continuation plan

**Actual Astra:** `/root/astra_p6_t3_plan`, `gpt-6-astra`. **Executor:** ROOT metadata review only. Existing Sol work continues under its existing R331 authorization.

R331's fixed original HEAD is `d66e258a1ebac178cce6c510347ed22117f24cb6`. The shared branch now points to `1e9f5d5fd958147f3558f66c364dbd8cfc3caf99` after a separate proposal-PPT document commit. This is a static gate-precondition change; no runtime was launched for this finding.

## Verified finite evidence

`planner-git-readout.json` records actual read-only Git checks:

- Branch remains `research/20261004-continuation`; HEAD was identical before/after inspection.
- New HEAD's single parent is the original HEAD; exactly one intervening commit.
- Its **116 changed paths** have **zero intersection** with the original **255 R331 input paths**.
- All **254 tracked input** tree entries/blobs are identical across commits and match original manifest SHA256s. One planning input is absent from both trees; it is not represented as committed.

`plan.json.inputs` pins immediate plan/manifest/runner/ledger/RED metadata and this evidence. No currently edited product working-tree file is made an immutable R337 prerequisite. Unrelated document contents are not audited or taken into T3 delivery.

## Exact decision and ROOT procedure

This addendum permits **only `1e9f5d5fd958147f3558f66c364dbd8cfc3caf99`** to satisfy the original fixed-HEAD prerequisite for the **future R331 T3 GREEN source gate**, after ROOT accepts the finite applicability evidence. It does not edit R331's plan, release GREEN or authorize any later HEAD.

- [ ] Recheck exact HEAD/branch, direct parent and single-commit interval. Recheck the finite changed-path intersection and matching commit objects; no recursive historical audit.
- [ ] Verify unchanged R331 plan, runner, RED acceptance and both ledgers. Keep current authorized implementation edits separate from immutable commit-tree facts.
- [ ] Write `R337/root-applicability-acceptance.json`, binding this plan/readout SHA, exact old/new HEAD, non-overlap result, original RED version boundary and unchanged GREEN allowance.
- [ ] Continue already authorized product/fixture preparation. When ready for GREEN, pause writers and run the original full ROOT source/test/fixture/runner review. Create the prospective R331 `source-gate.json` with `HEAD=1e9f5d5fd958147f3558f66c364dbd8cfc3caf99`, unchanged `round=R331` and exact original command table, plus an R337 applicability reference.
- [ ] Bind actual finished source/test/runner/helper hashes and relevant fixture correction provenance, including R336. Preserve original RED's old HEAD/source/raw; new fixture/product generation belongs to prospective GREEN only. Commit-derived provenance may be newly recorded truthfully, never patched into historical evidence.
- [ ] Prospective `root-source-acceptance.json` must hash that exact gate and reference R337 acceptance. Immediately before any original R331 reservation/launch, recheck exact HEAD and frozen inputs. R337 itself reserves or runs nothing.

The existing runner already checks actual `git rev-parse HEAD == gate["HEAD"]`; preserve it unchanged. Its plan hash/command and consume-before-start checks remain intact.

## Drift and acceptance boundary

If HEAD changes again, **pause the affected runtime gate and obtain a fresh explicit applicability decision**. This plan does not approve arbitrary descendants or even another apparently unrelated docs commit. Never rewrite a frozen gate to hide drift. If drift occurs during a run, retain the original result/rejection and apply existing no-retry rules. Unaffected independent work can continue.

Keep original RED **SPENT (used 1 / remaining 0)** and GREEN **HELD (used 0 / remaining 1)**. No new/reset runtime allowance, import/collection/smoke test, source rollback, Git mutation, runner edit or unrelated-work inclusion is permitted.

Acceptance means only that this one document commit is compatible with the R331 base prerequisite. It is not GREEN release, product success, B acceptance or ownership of the other task's document delivery.
