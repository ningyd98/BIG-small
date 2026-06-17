# Project Status

当前权威状态：`PHASE10_MOVEIT_DRY_RUN_ACCEPTED`。该状态只表示 MoveIt Runtime Dry-Run 规划证据已通过，且没有发送真实硬件执行命令。

## 状态总表

| Domain | Status | Verifier | Evidence | Environment | Hardware Claim |
| --- | --- | --- | --- | --- | --- |
| Core runtime | Accepted | `scripts/verify_phase6_2.py` | Phase 6.2 reports | CI-safe | No hardware |
| PCSC / ETEAC / AUTO | Accepted | `scripts/verify_phase8_2.py` | Phase 8.2 artifacts | CI-safe | No hardware |
| MuJoCo | Accepted | `scripts/verify_phase9.py` | `artifacts/phase9` | local sim | No hardware |
| ROS 2 / MoveIt safety | Accepted | `scripts/verify_phase9_1.py` | `artifacts/phase9_1` | ROS 2 / MoveIt host | No hardware |
| Isaac Sim | Accepted | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | Isaac host | No hardware |
| Cross-backend | Accepted | `scripts/run_phase9_2_cross_backend.py` | `artifacts/phase9_2/cross_backend` | MuJoCo + Isaac | No hardware |
| Synthetic Dry-Run | Accepted | `scripts/verify_phase10_1.py` | `artifacts/phase10/phase10_1` | CI-safe | No hardware |
| MoveIt Runtime Dry-Run | Accepted | `scripts/verify_phase10_moveit_dry_run.py` | `artifacts/phase10/moveit_dry_run` | ROS 2 / MoveIt host | No hardware |
| Repository documentation | Accepted after Phase 10.2A-R | `scripts/check_docs.py` | docs and CI checks | CI-safe | No hardware |
| Real Robot Read-Only | Not started | `scripts/run_phase10_acceptance_level.py` | none | physical site | Hardware read-only not claimed |
| Real Robot Motion | Not started | none | none | physical site | Motion not claimed |

## Historical Status Notes

Phase 9.1 ended with `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK` because Isaac and cross-backend were then environment-blocked. Phase 9.2 later completed Isaac smoke, benchmark, and cross-backend validation, producing `PHASE9_2_ACCEPTED`.

Current Phase 10.2A does not change Phase 9.2. It adds stronger dry-run evidence and repository governance while keeping real robot validation at `NOT_STARTED`.

## Current Blockers

- No authorized real robot controller configuration is committed.
- No physical emergency stop or controller status has been read.
- No Level 0 real hardware acceptance evidence exists.
- No physical motion test has been run.

## Next Stage

Phase 10.2B is planned as an experiment and safety acceptance console. It is not a browser remote-control surface; it may display state, gates, evidence, and operator workflow only through backend APIs.
