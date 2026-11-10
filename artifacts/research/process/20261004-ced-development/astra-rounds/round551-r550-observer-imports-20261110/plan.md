# R551 Observer Import Grouping Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this single bounded edit. Existing authorization applies; no extra review/sub-agents.

**Goal:** Clear one I001 while preserving the exact observer program AST.
**Architecture:** Add only the import-group separator before the scripts import; retain import order and all code.
**Tech Stack:** Existing Python/Ruff and four CPU unittest stubs.
**Spec:** R550 execution plan; actual planner_model `gpt-6-astra`.

## Evidence, root cause and scope

Original observer-ruff.log reports exactly one I001 at run_live.py:160–162: cloud_edge_robot_arm imports and scripts import need grouping. Original observer-tests.log reports4 tests PASS; its FileExistsError capture-gap line is the intentional exception-preservation test output, not a failed test. Hashes of current runner, both original logs and R550 plan are recorded below.

Only modify R550 implementation/run_live.py by inserting a blank line immediately before `from scripts.probe_molmo_grounded_planner import main as cli_main`. No import reordering is needed; whole-file AST must remain identical. No production, test, runtime, counter, observer, model or cloud logic changes. Preserve original logs byte-for-byte.

## One task

- [ ] Recheck all input hashes and save pre-edit `ast.dump(ast.parse(source), include_attributes=False)`.
- [ ] Insert only the described blank line. Do not run broad automatic/unsafe fixes or move imports before the R545 package-identity configuration.
- [ ] Assert exact pre/post AST equality, then rerun the existing4 CPU observer checks using the existing app interpreter from the implementation directory: `python -m unittest test_observer -v` (use its absolute interpreter path). All4 must PASS; no project/model/GPU/cloud run is involved.
- [ ] Rerun existing Ruff `--no-cache` on run_live.py and test_observer.py plus `git diff --check`; require exit0. Save new logs under R551 without overwriting R550 originals.
- [ ] Record old/new hashes, AST equality,4-test and lint/diff results in a short R551 report. Resume unchanged R550 execution only after these checks pass; no additional review gate.

## Preconditions and acceptance

Existing app Python/Ruff and approved managed-worktree writes suffice. Acceptance is grouping-only diff, identical AST,4 CPU checks and Ruff/diff PASS. Any other finding or AST drift requires a new actual Astra plan before broader repair. This planning/style round uses0 native/cloud/GPU/hardware calls. R550 allocation remains unused: additional at most1load/2generations/1paid attempt, cumulative native caps3loads/6generations from prior2/4, no retries. No execution is authorized beyond the already established R550 gates; real/physical/formal acceptance is unchanged.

## Input identity

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/implementation/run_live.py` — 6713 bytes — SHA256 `d59dff4fab4b9967f3ba039f9e0981f3c10c62886a6a4a16ec74a87496b78af5`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/observer-ruff.log` — 825 bytes — SHA256 `d3d57136f118e56b44d1e8778a18ae785bbdcb009b1d331aefbbc1fdb10381ca`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/observer-tests.log` — 817 bytes — SHA256 `de5c479efd912c7be2ef68e7bfae4163e98a93745d50de174e7d2bdad64c0a5a`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/plan.md` — 19221 bytes — SHA256 `d40e7c7c2731b9c9972dd66a661c96bec8cbc1dcdda1b4d11295cadac9815b46`
