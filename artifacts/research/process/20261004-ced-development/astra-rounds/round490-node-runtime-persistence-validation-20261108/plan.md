# R490 supported Node runtime for R489 validation

Actual gpt-6-astra recovery plan under AGENTS.md. Draft only in the writable Codex work directory; root installs canonical R490 plan/evidence through required filesystem escalation. No feature-scope expansion or user question.

## Original failure

R489 `execution/frontend-behavior-red.json/stdout/stderr` records rc1 after0.656s, before tests start: rolldown imports `styleText` from node:util, but the selected Node lacks that export. package.json requires Node>=22.12. Parent runtime inventory reports system `/usr/bin/node`18.19.1/npm9.2.0. This is an environment prerequisite failure, not feature RED. Preserve all original bytes. Backend behavioral RED independently reached its intended two assertions and is not repeated by this recovery.

Read-only load_workspace_dependencies identifies installed candidate `/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`. Its presence/hash is pinned, but this planner has not executed it or asserted its version. Use the existing compatible runtime if its actual version passes; no installation, package edits or lockfile changes.

## Exact scope and steps

1. Recheck original evidence, package.json, tests and runner SHA pins. Record the load_workspace_dependencies candidate source and parent-reported system version distinctly. Run the absolute bundled executable with `--version` and `--input-type=module -e 'import {styleText} from "node:util"; console.log(typeof styleText)'`, saving unique canonical R490 version-probe stdout/stderr/rc. Require supported Node>=22.12 and output function. Version comparison must parse numeric major/minor, not lexicographic strings. Failure stops this runtime path; no fallback to old system Node, download, global node switch or unrelated dependency repair.
2. Modify only `/home/ningyd/Documents/Codex/2026-11-08/new-chat/work/run_r489_check.py`: for --dashboard invocations prepend the verified bundle `node/bin` directory to the child PATH, keep all other environment cleaning/paid=false behavior, and record only selected absolute node path, verified node version and runtime binary SHA in the receipt. Do not dump full environment. Non-dashboard Python checks retain their current runtime. Use absolute `/usr/bin/npm` for dashboard commands; its env-node shebang must resolve through that child PATH. Inspect its launcher shebang before relying on that behavior, or invoke its resolved npm CLI using the absolute bundled node. Do not edit npm, node_modules, package.json, shell startup files or system alternatives.
3. Verify the runner-selected child `node --version` matches the absolute probe and required version before any test retry. Then rerun the same two R489 target frontend files exactly once as a **new** unique attempt, e.g. `frontend-behavior-red-node-supported`; refuse overwrite:

```bash
python3 /home/ningyd/Documents/Codex/2026-11-08/new-chat/work/run_r489_check.py frontend-behavior-red-node-supported --dashboard -- /usr/bin/npm run test -- src/modelControl/pages/ModelControlCenterPage.test.tsx src/modelControl/api/modelControlApi.test.ts
```

Preserve raw stdout/stderr/rc/duration, runner before/after SHA and effective runtime identity. Expected: Vitest starts and reaches R489 feature assertions about missing persistence/key-update UX. Nonzero assertion failures are the intended RED; a startup error is not. Do not invent an exact count without running the already-written tests. If unexpectedly GREEN, inspect whether tests demonstrate required behavior before implementation. Any new unexpected root cause pauses its dependent repair under AGENTS.
4. After actual feature RED is obtained, resume original R489 implementation. Use the same verified runner PATH for its later frontend GREEN and typecheck commands; backend execution remains as planned. Add a small R490 receipt linking environment failure to corrected runtime and feature RED. Canonical delivery is only R490 plans/receipts and the declared local runner change; no original failed evidence overwrite.

## Acceptance and limits

Recovery succeeds only when a recorded supported Node executes Vitest and reaches the intended tests. It does not prove persistence or live deployment. All original R489 constraints remain: no user vault/key reads, current-service restart, live API/model/GPU/render work, or paid-flag enabling. No subagents or dependency reinstall. Planning only read files/runtime inventory and wrote draft plans; no version probe, tests or repository mutation was performed.

Self-review: actual package engine requirement and original startup error pinned; candidate provenance and version-unverified status explicit; minimal child-only PATH change; original evidence immutable; unique retry and return to R489 specified.
