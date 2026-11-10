# R552 Observer Import Order Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this one edit. Existing authorization applies; no extra review or sub-agents.

**Goal:** Apply the exact observed Ruff import ordering, with no other runner change.
**Architecture:** Reorder only three adjacent ImportFrom statements after unchanged configure_overlay.
**Tech Stack:** Existing Python/Ruff and4 CPU unittest stubs.
**Spec:** R550 execution plan; actual planner_model `gpt-6-astra`.

## Failure and verified cause

R551 inserted a blank line, preserved whole AST and passed4 CPU checks, but its ruff-green.log still reports I001. R551 is therefore not a lint success and its plan/logs stay frozen. Actual read-only `ruff check --no-cache --diff` under current pyproject configuration (src=[src,tests]) shows scripts import first, then a blank line, then cloud_edge_robot_arm imports. Exact diff is preserved as planner-ruff.diff; exit1 means a proposed fix, not source mutation. The previous plan assumed the wrong grouping order. No further investigation or production change is needed.

## Single task

- [ ] Recheck frozen inputs and preserve both R550 original I001 and R551 unsuccessful lint output. Save current runner source/AST as R552 evidence.
- [ ] Replace only the three-import block with exactly:

```python
        from scripts.probe_molmo_grounded_planner import main as cli_main

        from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
        from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
```

  All three remain immediately after the same configure_overlay/preflight call and before original_process/original_post bindings. Do not change imports/aliases, bootstrap, wrappers, counters or Ruff configuration; no broad --fix.
- [ ] Compare pre/post AST after normalizing **only this block's ordering**: locate main's existing try.body, assert exactly these three consecutive ImportFrom nodes with the same modules/names/aliases, and sort only those three nodes by module in deep-copied ASTs. Require `ast.dump(..., include_attributes=False)` equality for the entire normalized trees. Also require textual diff exactly matches planner-ruff.diff. Do not globally sort imports or drop other nodes; actual whole AST differs only in these imports' order.
- [ ] From R550 implementation directory run the existing absolute app Python with `-m unittest test_observer -v`; require4 PASS. Run existing Ruff `--no-cache` on run_live.py/test_observer.py and `git diff --check`; both exit0. Save new R552 logs, leaving earlier logs unchanged. No runner main, native, cloud or GPU operation is needed.
- [ ] Record hashes, normalized-AST comparison, exact diff,4-test/lint exits in R552 report. Resume unchanged R550 execution after PASS, with its input/runtime/resource gates and allocation intact.

## Preconditions and acceptance

Existing app Python/Ruff and managed-worktree write permission only. Scope is R550 implementation/run_live.py's named three imports, plus R552 evidence. Acceptance requires exact requested import order and no other AST difference,4 CPU tests and clean Ruff/diff. A different failure requires the next actual Astra plan rather than another guessed adjustment. R552 uses zero native/cloud/GPU/hardware calls. R550 remains unused: additional at most1load/2generation starts/1paid attempt, cumulative native caps3loads/6generations, no retries. No model/endpoint/profile/TTL changes or new real/physical acceptance.

## Frozen inputs

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/implementation/run_live.py` — 6714 bytes — SHA256 `c171cfe216f21176e25fcf15db823919c1d9f5c926cb618e84fe3efae2234b01`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round550-molmo-sol-live-interface-20261110/observer-ruff.log` — 825 bytes — SHA256 `d3d57136f118e56b44d1e8778a18ae785bbdcb009b1d331aefbbc1fdb10381ca`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round551-r550-observer-imports-20261110/ruff-green.log` — 833 bytes — SHA256 `ff93d1eeeb1b6854d2092e95d1968cd0af69cd2c469561e4af8d7cf71297749f`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round551-r550-observer-imports-20261110/plan.md` — 3981 bytes — SHA256 `43c076dd1151e55452b8431ea2e04f7c9cf8e61575ca1cb597a5f39ba0772ec6`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round551-r550-observer-imports-20261110/plan.json` — 2847 bytes — SHA256 `20abf5514ff8683543feec9df791548478b26a26541c459772dce719076f8bef`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round551-r550-observer-imports-20261110/observer-tests-green.log` — 817 bytes — SHA256 `de5c479efd912c7be2ef68e7bfae4163e98a93745d50de174e7d2bdad64c0a5a`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/pyproject.toml` — 2486 bytes — SHA256 `42fdefae6dff25d26e3ded9ab39c7910ee8116f4aed2e9d8f60eee23809e0933`

Read-only diff SHA256 `649a8592f918d67a70d8cbcdc6cf10e37ac64e0a7debec0578180344fd18575e` (867 bytes).
