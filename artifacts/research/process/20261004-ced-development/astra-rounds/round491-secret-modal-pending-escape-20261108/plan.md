# R491 pending-key-modal Escape reproduction audit

Actual gpt-6-astra plan under AGENTS.md, scoped to the review finding. Draft only in writable Codex work directory; root installs canonical R491 plan/receipts through required escalation. Existing R489 authorization and no-live-operation constraints remain.

## Evidence and corrected hypothesis

Reviewer hypothesized that Escape bypasses disabled mask/cancel/close controls: DialogWrap defaults keyboard=true and calls onClose for Escape. However the installed Ant Design Modal wrapper's handleCancel explicitly returns when confirmLoading is true (`node_modules/antd/es/modal/Modal.js:110–116`), and this page passes confirmLoading=updateSecret.isPending. The portal dispatches window keydown to the dialog. The full chain therefore may already prevent the alleged cancellation. This is **not an established product defect**; do not force a RED or add defensive changes merely to satisfy the original hypothesis.

Latest R489 frontend attempt3 is rc0,11 tests; parent reports backend49 plus adjacent39/1 deselected and earlier typecheck pass. Pin original results/source/installed wrappers; retain bytes. R490 selected existing Node24.22.1. No new dependency or runtime recovery is needed.

## Steps and exact scope

1. Recheck plan.json pins. Add only a focused real-component regression in `dashboard/src/modelControl/pages/ModelControlCenterPage.test.tsx`, reusing deferred mocked fetch and motion-disabled provider. Do not mock Modal/Dialog, call onCancel directly, override their pending props or mock their event listeners. Name it `keeps pending key modal open on Escape and settles safely`; parametrize successful and failed PATCH outcomes.
2. Establish keyboard test validity first: open the modal while idle, dispatch `fireEvent.keyDown(window, {key: "Escape", code: "Escape"})`, and confirm it closes; reopen and confirm password is blank. Enter fictional key, submit, wait for exactly one deferred PATCH and rendered pending/disabled controls, then dispatch the same real Escape event. Require the same visible dialog/profile and password remain, no second write/no replacement modal, and no success/error notice before settlement. Do not assert a detached DOM input is blank; inspect the current/reopened dialog.
3. Settle the captured request. Success must close programmatically and show its correct persistence notice; reopening is blank. Failure must retain the same profile/password with only generic error, then after pending settles Escape closes and reopening is blank. Preserve existing query invalidation and settled mutation-cache-secret clearing assertions. If using two profile rows, only open the second after the first request settles; verify it starts blank and has no previous form error. Do not fabricate user access to an obscured underlying button to manufacture the alleged Escape defect.
4. Run the new focused test once with the R490 verified Node child PATH via existing work/run_r489_check.py, unique label `r491-escape-audit`:

```bash
python3 /home/ningyd/Documents/Codex/2026-11-08/new-chat/work/run_r489_check.py r491-escape-audit --dashboard -- /usr/bin/npm run test -- src/modelControl/pages/ModelControlCenterPage.test.tsx -t 'keeps pending key modal open on Escape and settles safely'
```

The runner currently saves to R489 execution; retain that original output there and write an R491 audit receipt referencing its path/hash, rather than overwrite/move evidence. Record rc, exact assertion/event path and effective Node version. A GREEN result is valid audit evidence: mark REVIEW_HYPOTHESIS_NOT_REPRODUCED_WRAPPER_GUARD_CONFIRMED, retain the regression, and make **no page implementation change**. Test fixture/selector errors may be corrected within this test scope but must not be relabeled as product failures.
5. Only if the authentic deferred-pending Escape sequence demonstrably dismisses the modal, preserve that actual RED and perform the already-planned minimal repair in `ModelControlCenterPage.tsx`: set keyboard={!updateSecret.isPending}; guard user-cancel and row-open handlers while a save is pending (a synchronous pending ref if a render timing gap is the demonstrated cause); separate guarded user cancellation from internal successful clear/close so success can close while mutation state is settling. Capture submitted profile identity and prevent old completion from clearing/closing/showing an error in a different modal if the reproduced route still permits replacement. Do not introduce a general request manager, abort semantics, hook/API/backend changes or weakened failure retention. Add a targeted stale-response test only for that actually reproduced replacement route. A different cause/scope requires another Astra assessment.
6. Run both original targeted frontend files once and typecheck under the same Node runner, unique labels `r491-frontend-verified` and `r491-typecheck`. These remain the R489 commands:

```text
/usr/bin/npm run test -- src/modelControl/pages/ModelControlCenterPage.test.tsx src/modelControl/api/modelControlApi.test.ts
/usr/bin/npm run typecheck
```

No backend rerun is needed for a test-only audit or narrowly scoped page fix. Record actual results and whether source changed; integrate the finding disposition into R489 final report. Retain originals and commit only named test (and page only if justified), R491 artifacts and associated derived report through root's scoped delivery process.

## Acceptance and self-review

Accept either a reproducible defect with verified minimal repair or a genuine GREEN no-repair audit demonstrating installed wrapper behavior. Do not promise stale-response safety beyond tested paths. Password clearing on successful programmatic close, failed-open preservation, idle Escape clearing and cache semantics must remain intact. No live API/model call, real key/vault access, restart, dependency edit or extra delegation. Planning inspected the full installed event chain and saved only these drafts; tests and source were not executed/modified.
